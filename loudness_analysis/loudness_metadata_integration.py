#!/usr/bin/env python3
"""
Integration module for BS.1770-5 loudness analysis with existing FTP Media Sync database
Follows the pattern of existing ai_analyzer.py for consistency
"""

import os
import logging
from datetime import datetime
from typing import Dict, Optional, List
import asyncio
import asyncpg

from loudness_analyzer import LoudnessAnalyzer

logger = logging.getLogger(__name__)


class LoudnessMetadataProcessor:
    """
    Processes media files for loudness analysis and stores results in metadata table
    Following the existing pattern from ai_analyzer.py
    """
    
    def __init__(self, db_config: dict):
        self.db_config = db_config
        self.loudness_analyzer = LoudnessAnalyzer()
        self.metadata_type_id = None
        
    async def ensure_metadata_type(self, conn):
        """Ensure 'loudness' metadata type exists in metadata_types table"""
        # Check if loudness metadata type exists
        row = await conn.fetchrow(
            "SELECT id FROM metadata_types WHERE type_name = 'loudness'"
        )
        
        if row:
            self.metadata_type_id = row['id']
        else:
            # Create loudness metadata type
            self.metadata_type_id = await conn.fetchval(
                """INSERT INTO metadata_types (type_name, description, data_type)
                   VALUES ('loudness', 'BS.1770-5 loudness measurements', 'json')
                   RETURNING id"""
            )
            logger.info(f"Created loudness metadata type with ID: {self.metadata_type_id}")
    
    async def process_asset_loudness(self, asset_id: int, file_path: str) -> Dict:
        """
        Process loudness analysis for a single asset
        Similar to the transcription processing in ai_analyzer.py
        """
        try:
            logger.info(f"Processing loudness for asset {asset_id}: {file_path}")
            
            # Perform loudness analysis
            results = self.loudness_analyzer.analyze(file_path)
            
            # Store in database
            await self.store_loudness_metadata(asset_id, results)
            
            return {
                'success': True,
                'asset_id': asset_id,
                'loudness_data': results['loudness']
            }
            
        except Exception as e:
            logger.error(f"Error processing loudness for asset {asset_id}: {str(e)}")
            return {
                'success': False,
                'asset_id': asset_id,
                'error': str(e)
            }
    
    async def store_loudness_metadata(self, asset_id: int, analysis_results: Dict):
        """Store loudness analysis results in metadata table"""
        conn = await asyncpg.connect(**self.db_config)
        
        try:
            await self.ensure_metadata_type(conn)
            
            loudness_data = analysis_results['loudness']
            
            # Define metadata keys to store
            metadata_mappings = {
                'loudness_integrated_lufs': loudness_data.get('integrated_lufs'),
                'loudness_integrated_threshold': loudness_data.get('integrated_thresh'),
                'loudness_range_lu': loudness_data.get('loudness_range'),
                'loudness_lra_low': loudness_data.get('lra_low'),
                'loudness_lra_high': loudness_data.get('lra_high'),
                'loudness_true_peak_dbtp': loudness_data.get('true_peak'),
                'loudness_short_term_max': loudness_data.get('max_short_term'),
                'loudness_momentary_max': loudness_data.get('max_momentary'),
                'loudness_target_offset': loudness_data.get('target_offset'),
                'loudness_atsc_a85_compliant': loudness_data.get('atsc_compliant'),
                'loudness_ebu_r128_compliant': loudness_data.get('ebu_compliant'),
                'loudness_analysis_date': datetime.now().isoformat(),
                'loudness_target_lkfs': analysis_results.get('target_lufs', -24.0)
            }
            
            # Store each metadata item
            for meta_key, meta_value in metadata_mappings.items():
                if meta_value is not None:
                    await conn.execute(
                        """INSERT INTO metadata (asset_id, metadata_type_id, meta_key, meta_value)
                           VALUES ($1, $2, $3, $4)
                           ON CONFLICT (asset_id, metadata_type_id, meta_key)
                           DO UPDATE SET meta_value = $4, updated_at = CURRENT_TIMESTAMP""",
                        asset_id, self.metadata_type_id, meta_key, str(meta_value)
                    )
            
            # Also store the complete analysis as JSON for reference
            await conn.execute(
                """INSERT INTO metadata (asset_id, metadata_type_id, meta_key, meta_value)
                   VALUES ($1, $2, 'loudness_full_analysis', $3::text)
                   ON CONFLICT (asset_id, metadata_type_id, meta_key)
                   DO UPDATE SET meta_value = $3::text, updated_at = CURRENT_TIMESTAMP""",
                asset_id, self.metadata_type_id, 
                json.dumps(analysis_results)
            )
            
            # Update asset to mark loudness analysis as complete
            # (Following pattern from ai_analyzer.py which sets analysis_completed)
            await conn.execute(
                """UPDATE assets 
                   SET updated_at = CURRENT_TIMESTAMP
                   WHERE id = $1""",
                asset_id
            )
            
            logger.info(f"Stored loudness metadata for asset {asset_id}")
            
        finally:
            await conn.close()
    
    async def get_assets_needing_loudness_analysis(self, limit: int = 50) -> List[Dict]:
        """
        Get assets that haven't been analyzed for loudness yet
        Similar to how ai_analyzer gets assets needing transcription
        """
        conn = await asyncpg.connect(**self.db_config)
        
        try:
            await self.ensure_metadata_type(conn)
            
            # Find assets without loudness analysis
            rows = await conn.fetch(
                """SELECT DISTINCT a.id, a.content_title, i.file_path, i.storage_location
                   FROM assets a
                   JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
                   LEFT JOIN metadata m ON a.id = m.asset_id 
                       AND m.metadata_type_id = $1 
                       AND m.meta_key = 'loudness_integrated_lufs'
                   WHERE m.id IS NULL
                   AND a.duration_seconds > 0
                   AND a.content_type IN ('ID', 'SPOTS', 'SHORT_FORM', 'LONG_FORM')
                   LIMIT $2""",
                self.metadata_type_id, limit
            )
            
            return [dict(row) for row in rows]
            
        finally:
            await conn.close()
    
    async def batch_process_loudness(self, max_assets: int = 10):
        """
        Batch process multiple assets for loudness analysis
        Similar to the batch processing in ai_analyzer
        """
        assets = await self.get_assets_needing_loudness_analysis(max_assets)
        
        if not assets:
            logger.info("No assets found needing loudness analysis")
            return []
        
        logger.info(f"Found {len(assets)} assets needing loudness analysis")
        
        results = []
        for asset in assets:
            # Construct full file path based on storage location
            if asset['storage_location'] == 'source':
                # Adjust path based on your actual storage configuration
                file_path = asset['file_path']
            else:
                file_path = asset['file_path']
            
            result = await self.process_asset_loudness(asset['id'], file_path)
            results.append(result)
            
            # Add a small delay to avoid overwhelming the system
            await asyncio.sleep(0.5)
        
        return results


# API endpoint handler for the backend
async def analyze_loudness_for_asset(asset_id: int, db_config: dict) -> Dict:
    """
    API endpoint function to analyze loudness for a specific asset
    Can be called from the File Scanning and Analysis interface
    """
    processor = LoudnessMetadataProcessor(db_config)
    
    # Get asset info
    conn = await asyncpg.connect(**db_config)
    try:
        asset_info = await conn.fetchrow(
            """SELECT a.id, a.content_title, i.file_path, i.storage_location
               FROM assets a
               JOIN instances i ON a.id = i.asset_id AND i.is_primary = true
               WHERE a.id = $1""",
            asset_id
        )
        
        if not asset_info:
            return {'success': False, 'error': 'Asset not found'}
        
        # Process loudness
        result = await processor.process_asset_loudness(
            asset_info['id'], 
            asset_info['file_path']
        )
        
        return result
        
    finally:
        await conn.close()


# Function to retrieve loudness metadata for display
async def get_loudness_metadata(asset_id: int, db_config: dict) -> Dict:
    """Retrieve loudness metadata for an asset"""
    conn = await asyncpg.connect(**db_config)
    
    try:
        # Get loudness metadata
        rows = await conn.fetch(
            """SELECT m.meta_key, m.meta_value
               FROM metadata m
               JOIN metadata_types mt ON m.metadata_type_id = mt.id
               WHERE m.asset_id = $1 AND mt.type_name = 'loudness'
               AND m.meta_key LIKE 'loudness_%'""",
            asset_id
        )
        
        # Convert to dictionary
        metadata = {}
        for row in rows:
            key = row['meta_key'].replace('loudness_', '')
            value = row['meta_value']
            
            # Convert numeric values
            if key in ['integrated_lufs', 'range_lu', 'true_peak_dbtp', 
                      'short_term_max', 'momentary_max', 'target_offset', 'target_lkfs']:
                try:
                    value = float(value)
                except:
                    pass
            elif key in ['atsc_a85_compliant', 'ebu_r128_compliant']:
                value = value.lower() == 'true'
            
            metadata[key] = value
        
        return metadata
        
    finally:
        await conn.close()


if __name__ == "__main__":
    # Example usage for testing
    import json
    
    # Example database configuration
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'ftp_media_sync',
        'user': 'your_user',
        'password': 'your_password'
    }
    
    # Test batch processing
    async def test():
        processor = LoudnessMetadataProcessor(db_config)
        results = await processor.batch_process_loudness(max_assets=5)
        print(f"Processed {len(results)} assets")
        print(json.dumps(results, indent=2))
    
    # Run test
    # asyncio.run(test())
#!/usr/bin/env python3
"""
Script to reanalyze assets that have transcripts but were previously analyzed without AI.
This will add AI-generated summaries, engagement scores, and other metadata.
"""

import logging
import sys
from datetime import datetime
from database import db_manager
from psycopg2.extras import RealDictCursor
from ai_analyzer import ai_analyzer
from config_manager import ConfigManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_assets_needing_ai_analysis(limit=None):
    """Get assets that have transcripts but no AI analysis"""
    db_manager.connect()
    conn = db_manager._get_connection()
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
        SELECT 
            id,
            guid,
            content_type,
            content_title,
            transcript,
            summary,
            engagement_score,
            ai_analysis_enabled,
            created_at
        FROM assets
        WHERE 
            LENGTH(transcript) > 500
            AND ai_analysis_enabled = FALSE
            AND (summary = '' OR summary IS NULL)
        ORDER BY LENGTH(transcript) DESC
        """
        
        if limit:
            query += f" LIMIT {limit}"
            
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()
        
        return results
        
    finally:
        db_manager._put_connection(conn)


def reanalyze_asset_with_ai(asset):
    """Reanalyze a single asset with AI enabled"""
    try:
        asset_id = asset['id']
        transcript = asset['transcript']
        
        logger.info(f"Reanalyzing asset {asset_id}: {asset['content_title']}")
        logger.info(f"  Transcript length: {len(transcript)} chars")
        
        # Analyze with AI
        ai_result = ai_analyzer.analyze_transcript(transcript)
        
        if not ai_result:
            logger.error(f"  Failed to get AI analysis for asset {asset_id}")
            return False
            
        # Update database with AI results
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            
            update_query = """
            UPDATE assets
            SET 
                summary = %s,
                engagement_score = %s,
                topics = %s,
                locations = %s,
                people = %s,
                events = %s,
                engagement_score_reasons = %s,
                shelf_life_score = %s,
                shelf_life_reasons = %s,
                ai_analysis_enabled = TRUE,
                updated_at = %s
            WHERE id = %s
            """
            
            cursor.execute(update_query, (
                ai_result.get('summary', ''),
                ai_result.get('engagement_score', 0),
                ai_result.get('topics', []),
                ai_result.get('locations', []),
                ai_result.get('people', []),
                ai_result.get('events', []),
                ai_result.get('engagement_score_reasons', ''),
                ai_result.get('shelf_life_score', 'medium'),
                ai_result.get('shelf_life_reasons', ''),
                datetime.now(),
                asset_id
            ))
            
            conn.commit()
            cursor.close()
            
            logger.info(f"  ✅ Successfully updated with AI analysis")
            logger.info(f"  Summary: {ai_result.get('summary', '')[:100]}...")
            logger.info(f"  Engagement score: {ai_result.get('engagement_score', 0)}")
            
            return True
            
        finally:
            db_manager._put_connection(conn)
            
    except Exception as e:
        logger.error(f"Error reanalyzing asset {asset.get('id')}: {str(e)}")
        return False


def main():
    """Main function to reanalyze assets"""
    # Check command line arguments
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
            logger.info(f"Limiting to {limit} assets")
        except ValueError:
            logger.error("Usage: python reanalyze_assets_with_ai.py [limit]")
            sys.exit(1)
    
    # Load AI configuration
    config_mgr = ConfigManager()
    ai_config = config_mgr.get_ai_analysis_settings()
    
    if not ai_config.get('enabled', False):
        logger.error("AI analysis is not enabled in configuration. Please enable it first.")
        sys.exit(1)
        
    # Configure AI analyzer
    ai_analyzer.api_provider = ai_config.get('provider', 'openai')
    
    # Get the correct API key based on provider
    if ai_analyzer.api_provider == 'openai':
        ai_analyzer.api_key = ai_config.get('openai_api_key')
    elif ai_analyzer.api_provider == 'anthropic':
        ai_analyzer.api_key = ai_config.get('anthropic_api_key')
    elif ai_analyzer.api_provider == 'ollama':
        ai_analyzer.ollama_url = ai_config.get('ollama_url', 'http://localhost:11434')
    
    ai_analyzer.model = ai_config.get('model')
    ai_analyzer.setup_client()
    
    if not ai_analyzer.client:
        logger.error("Failed to setup AI client. Check your configuration and API keys.")
        sys.exit(1)
    
    # Get assets needing AI analysis
    logger.info("Fetching assets that need AI analysis...")
    assets = get_assets_needing_ai_analysis(limit)
    
    if not assets:
        logger.info("No assets found that need AI analysis.")
        return
        
    logger.info(f"Found {len(assets)} assets needing AI analysis")
    
    # Process each asset
    success_count = 0
    failure_count = 0
    
    for i, asset in enumerate(assets, 1):
        logger.info(f"\nProcessing {i}/{len(assets)}...")
        
        if reanalyze_asset_with_ai(asset):
            success_count += 1
        else:
            failure_count += 1
            
        # Add a small delay to avoid overwhelming the AI API
        if i < len(assets):
            import time
            time.sleep(1)
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info(f"Reanalysis complete!")
    logger.info(f"  Successful: {success_count}")
    logger.info(f"  Failed: {failure_count}")
    logger.info(f"  Total: {len(assets)}")


if __name__ == "__main__":
    main()
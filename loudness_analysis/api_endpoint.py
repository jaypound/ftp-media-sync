#!/usr/bin/env python3
"""
Flask API endpoint for loudness analysis integration
To be added to the main app.py
"""

from flask import jsonify, request
import asyncio
from loudness_metadata_integration import (
    analyze_loudness_for_asset,
    get_loudness_metadata,
    LoudnessMetadataProcessor
)

# Add these routes to your main Flask app.py

@app.route('/api/analyze-loudness/<int:asset_id>', methods=['POST'])
async def api_analyze_loudness(asset_id):
    """
    Analyze loudness for a specific asset
    Called from the File Scanning and Analysis interface
    """
    try:
        # Get database config from your app config
        db_config = {
            'host': app.config['DB_HOST'],
            'port': app.config['DB_PORT'],
            'database': app.config['DB_NAME'],
            'user': app.config['DB_USER'],
            'password': app.config['DB_PASSWORD']
        }
        
        # Run loudness analysis
        result = await analyze_loudness_for_asset(asset_id, db_config)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'Loudness analysis completed',
                'data': result['loudness_data']
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Loudness analysis failed: {result.get("error", "Unknown error")}'
            }), 500
            
    except Exception as e:
        logger.error(f"Error in loudness analysis API: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/loudness-metadata/<int:asset_id>', methods=['GET'])
async def api_get_loudness_metadata(asset_id):
    """Get loudness metadata for an asset"""
    try:
        db_config = {
            'host': app.config['DB_HOST'],
            'port': app.config['DB_PORT'],
            'database': app.config['DB_NAME'],
            'user': app.config['DB_USER'],
            'password': app.config['DB_PASSWORD']
        }
        
        metadata = await get_loudness_metadata(asset_id, db_config)
        
        return jsonify({
            'success': True,
            'data': metadata
        })
        
    except Exception as e:
        logger.error(f"Error getting loudness metadata: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/batch-analyze-loudness', methods=['POST'])
async def api_batch_analyze_loudness():
    """
    Batch analyze loudness for multiple assets
    Can be triggered from admin interface or scheduled
    """
    try:
        max_assets = request.json.get('max_assets', 10)
        
        db_config = {
            'host': app.config['DB_HOST'],
            'port': app.config['DB_PORT'],
            'database': app.config['DB_NAME'],
            'user': app.config['DB_USER'],
            'password': app.config['DB_PASSWORD']
        }
        
        processor = LoudnessMetadataProcessor(db_config)
        results = await processor.batch_process_loudness(max_assets)
        
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        
        return jsonify({
            'success': True,
            'message': f'Processed {len(results)} assets: {successful} successful, {failed} failed',
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error in batch loudness analysis: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


# Frontend JavaScript to add to script.js
"""
// Add this function to script.js for the File Scanning and Analysis interface

async function analyzeLoudnessForFile(fileId) {
    const button = event.target;
    const originalText = button.innerHTML;
    
    // Show loading state
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analyzing...';
    button.disabled = true;
    
    try {
        const response = await fetch(`/api/analyze-loudness/${fileId}`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.success) {
            log(`✅ Loudness analysis completed for file ${fileId}`, 'success');
            
            // Display results
            const loudnessInfo = `
                Integrated: ${result.data.integrated_lufs?.toFixed(1)} LKFS
                Range: ${result.data.loudness_range?.toFixed(1)} LU
                True Peak: ${result.data.true_peak?.toFixed(1)} dBTP
                ATSC A/85 Compliant: ${result.data.atsc_compliant ? '✓' : '✗'}
            `;
            
            // Update UI to show loudness info
            updateFileCardWithLoudness(fileId, result.data);
            
        } else {
            log(`❌ Loudness analysis failed: ${result.message}`, 'error');
        }
    } catch (error) {
        log(`❌ Error analyzing loudness: ${error.message}`, 'error');
    } finally {
        // Restore button
        button.innerHTML = originalText;
        button.disabled = false;
    }
}

function updateFileCardWithLoudness(fileId, loudnessData) {
    // Find the file card element
    const fileCard = document.querySelector(`[data-file-id="${fileId}"]`);
    if (!fileCard) return;
    
    // Remove existing loudness info if any
    const existingInfo = fileCard.querySelector('.loudness-info');
    if (existingInfo) existingInfo.remove();
    
    // Create loudness info element
    const loudnessInfo = document.createElement('div');
    loudnessInfo.className = 'loudness-info';
    loudnessInfo.innerHTML = `
        <div class="loudness-badge ${loudnessData.atsc_compliant ? 'compliant' : 'non-compliant'}">
            <i class="fas fa-volume-up"></i>
            ${loudnessData.integrated_lufs?.toFixed(1)} LKFS
            ${loudnessData.atsc_compliant ? '<i class="fas fa-check-circle"></i>' : '<i class="fas fa-exclamation-triangle"></i>'}
        </div>
        <div class="loudness-details" style="display: none;">
            <small>
                Range: ${loudnessData.loudness_range?.toFixed(1)} LU | 
                True Peak: ${loudnessData.true_peak?.toFixed(1)} dBTP |
                Target Offset: ${loudnessData.target_offset?.toFixed(1)} LU |
                ATSC: ${loudnessData.atsc_compliant ? '✓' : '✗'} |
                EBU: ${loudnessData.ebu_compliant ? '✓' : '✗'}
            </small>
        </div>
    `;
    
    // Add click handler to toggle details
    loudnessInfo.querySelector('.loudness-badge').onclick = () => {
        const details = loudnessInfo.querySelector('.loudness-details');
        details.style.display = details.style.display === 'none' ? 'block' : 'none';
    };
    
    // Insert after file info
    const fileInfo = fileCard.querySelector('.file-info');
    if (fileInfo) {
        fileInfo.appendChild(loudnessInfo);
    }
}
"""

# CSS to add to styles.css
"""
/* Loudness analysis styles */
.loudness-info {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border-color);
}

.loudness-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0.75rem;
    border-radius: var(--radius-small);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: var(--transition);
}

.loudness-badge.compliant {
    background-color: rgba(40, 167, 69, 0.1);
    color: #28a745;
}

.loudness-badge.non-compliant {
    background-color: rgba(220, 53, 69, 0.1);
    color: #dc3545;
}

.loudness-badge:hover {
    background-color: rgba(0, 0, 0, 0.1);
}

.loudness-details {
    margin-top: 0.5rem;
    padding: 0.5rem;
    background-color: var(--background-secondary);
    border-radius: var(--radius-small);
}

.analyze-loudness-btn {
    font-size: 0.75rem;
    padding: 0.25rem 0.5rem;
}

/* Add loudness column to file analysis table */
.file-analysis-table th.loudness-column,
.file-analysis-table td.loudness-column {
    text-align: center;
    min-width: 100px;
}
"""
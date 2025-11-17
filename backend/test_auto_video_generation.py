#!/usr/bin/env python3
"""
Test automatic video generation with actual FFmpeg generation and FTP delivery
"""
import os
import sys
import requests
import json
from datetime import datetime

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def test_auto_video_generation():
    """Test video generation through the API"""
    
    print("=== Testing Automatic Video Generation ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Base URL for API
    base_url = "http://127.0.0.1:5000"
    
    # First, get the active graphics
    print("1. Getting active graphics from database...")
    response = requests.get(f"{base_url}/api/default-graphics/active")
    
    if not response.ok:
        print(f"❌ Failed to get active graphics: {response.text}")
        return False
    
    graphics_data = response.json()
    if not graphics_data.get('success') or not graphics_data.get('graphics'):
        print("❌ No active graphics found")
        return False
    
    graphics = graphics_data['graphics']
    print(f"✅ Found {len(graphics)} active graphics")
    
    # Select all graphics for region 1
    graphic_ids = [g['id'] for g in graphics]
    
    # Prepare video generation request
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    video_params = {
        'file_name': f'TEST_AUTO_VIDEO_{timestamp}.mp4',
        'export_path': '/Videos',
        'export_to_source': True,
        'export_to_target': True,
        'video_format': 'mp4',
        'max_length': 360,  # 6 minutes
        'sort_order': 'newest',
        'graphic_ids': graphic_ids,
        # Region 2 - static overlay
        'region2_file': 'ATL26 SQUEEZEBACK SKYLINE WITH SOCIAL HANDLES.png',
        'region2_path': '/mnt/main/ATL26 On-Air Content/DEFAULT ROTATION',
        'region2_server': 'target',
        # Region 3 - music (would need actual file list)
        'region3_files': [],  # Empty for now
        'region3_path': '/mnt/main/Music',
        'region3_server': 'target'
    }
    
    print("\n2. Generating video with parameters:")
    print(f"   File name: {video_params['file_name']}")
    print(f"   Export to source: {video_params['export_to_source']}")
    print(f"   Export to target: {video_params['export_to_target']}")
    print(f"   Graphics count: {len(graphic_ids)}")
    print(f"   Region 2 overlay: {video_params['region2_file']}")
    print()
    
    # Call the video generation endpoint
    print("3. Calling video generation API...")
    response = requests.post(
        f"{base_url}/api/default-graphics/generate-video",
        json=video_params,
        headers={'Content-Type': 'application/json'}
    )
    
    if not response.ok:
        print(f"❌ Failed to generate video: {response.text}")
        return False
    
    result = response.json()
    if not result.get('success'):
        print(f"❌ Video generation failed: {result.get('message')}")
        return False
    
    print(f"✅ Video generation completed!")
    print(f"   Video ID: {result.get('video_id')}")
    print(f"   Duration: {result.get('duration')} seconds")
    print(f"   Graphics included: {result.get('graphics_count')}")
    
    # Check the history
    print("\n4. Checking generation history...")
    response = requests.get(f"{base_url}/api/default-graphics/history?limit=1")
    
    if response.ok:
        history = response.json()
        if history.get('success') and history.get('history'):
            latest = history['history'][0]
            print(f"✅ Latest video in history:")
            print(f"   File: {latest.get('file_name')}")
            print(f"   Export server: {latest.get('export_server')}")
            print(f"   Graphics count: {latest.get('graphics_count')}")
            print(f"   Date: {latest.get('generation_date')}")
    
    print("\n✅ Test completed successfully!")
    print("\nNOTE: Check the FTP servers to verify the video was delivered:")
    print("  - Source: /Videos/TEST_AUTO_VIDEO_*.mp4")
    print("  - Target: /Videos/TEST_AUTO_VIDEO_*.mp4")
    
    return True

if __name__ == "__main__":
    try:
        success = test_auto_video_generation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
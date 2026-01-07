#!/usr/bin/env python3
"""
Test syncing a single file's expiration metadata from Castus and storing in database
"""

import requests
import json
from database_postgres import PostgreSQLDatabaseManager

# File to test
TEST_FILE = "250827_AN_Mayors Cup Golf Tournament_v3.mp4"

def find_asset_in_database():
    """Find the asset ID for our test file"""
    db = PostgreSQLDatabaseManager()
    
    if not db.connect():
        print("❌ Failed to connect to database")
        return None
    
    try:
        conn = db._get_connection()
        with conn.cursor() as cursor:
            # First, let's find the asset
            cursor.execute("""
                SELECT a.id, a.content_title, i.file_path, sm.content_expiry_date, sm.metadata_synced_at
                FROM assets a
                JOIN instances i ON a.id = i.asset_id
                LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                WHERE i.file_name = %s
                LIMIT 1
            """, (TEST_FILE,))
            
            result = cursor.fetchone()
            
            if result:
                print(f"✅ Found asset in database:")
                print(f"   Asset ID: {result['id']}")
                print(f"   Title: {result['content_title']}")
                print(f"   Path: {result['file_path']}")
                print(f"   Current expiry: {result['content_expiry_date']}")
                print(f"   Last synced: {result['metadata_synced_at']}")
                return result['id'], result['file_path']
            else:
                print(f"❌ Asset not found in database: {TEST_FILE}")
                return None
                
    finally:
        db._put_connection(conn)
        db.disconnect()


def sync_expiration_via_api(asset_id, file_path):
    """Call the API to sync expiration date from Castus"""
    print(f"\n📡 Calling API to sync metadata...")
    
    # API endpoint - assuming app is running on default port
    url = "http://localhost:5000/api/sync-castus-expiration"
    
    payload = {
        "asset_id": asset_id,
        "file_path": file_path,
        "server": "source"  # or "target" depending on your setup
    }
    
    try:
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API call successful!")
            print(f"   Expiration date: {data.get('expiration_date')}")
            print(f"   Message: {data.get('message')}")
            return True
        else:
            print(f"❌ API call failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error calling API: {str(e)}")
        print("   Make sure the Flask app is running (python app.py)")
        return False


def verify_stored_data(asset_id):
    """Verify the data was stored correctly"""
    print(f"\n🔍 Verifying stored data...")
    
    db = PostgreSQLDatabaseManager()
    
    if not db.connect():
        print("❌ Failed to connect to database")
        return
    
    try:
        conn = db._get_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT content_expiry_date, metadata_synced_at
                FROM scheduling_metadata
                WHERE asset_id = %s
            """, (asset_id,))
            
            result = cursor.fetchone()
            
            if result:
                print(f"✅ Data successfully stored:")
                print(f"   Expiration date: {result['content_expiry_date']}")
                print(f"   Synced at: {result['metadata_synced_at']}")
                
                # Calculate days until expiration
                if result['content_expiry_date']:
                    from datetime import datetime
                    if result['content_expiry_date'].tzinfo:
                        now = datetime.now(result['content_expiry_date'].tzinfo)
                    else:
                        now = datetime.now()
                    days_left = (result['content_expiry_date'] - now).days
                    print(f"   Days until expiration: {days_left}")
            else:
                print(f"❌ No scheduling metadata found for asset {asset_id}")
                
    finally:
        db._put_connection(conn)
        db.disconnect()


def main():
    print(f"🚀 Testing Castus metadata sync for: {TEST_FILE}")
    print("=" * 80)
    
    # Step 1: Find the asset in database
    result = find_asset_in_database()
    
    if not result:
        print("\n⚠️  Cannot proceed without asset ID")
        return
    
    asset_id, file_path = result
    
    # Step 2: Sync via API
    if sync_expiration_via_api(asset_id, file_path):
        # Step 3: Verify the data was stored
        verify_stored_data(asset_id)
    
    print("\n✅ Test complete!")


if __name__ == "__main__":
    main()
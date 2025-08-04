#!/usr/bin/env python3
"""
Script to create playlist tables in the database
"""

import psycopg2
from psycopg2 import sql
import logging
import os
import getpass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_playlist_tables():
    """Create the playlist and playlist_items tables"""
    
    # Use the same connection string as the app
    USE_POSTGRESQL = os.getenv('USE_POSTGRESQL', 'false').lower() == 'true'
    
    if USE_POSTGRESQL:
        connection_string = os.getenv(
            'DATABASE_URL',
            f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
        )
    else:
        logger.error("This script requires PostgreSQL. Please set USE_POSTGRESQL=true")
        return
    
    try:
        # Connect to database
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()
        
        logger.info("Connected to database successfully")
        
        # Read and execute SQL script
        with open('create_playlist_tables.sql', 'r') as f:
            sql_script = f.read()
        
        cursor.execute(sql_script)
        conn.commit()
        
        logger.info("Playlist tables created successfully")
        
        # Verify tables were created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('playlists', 'playlist_items')
        """)
        
        tables = cursor.fetchall()
        logger.info(f"Verified tables: {[t[0] for t in tables]}")
        
        cursor.close()
        conn.close()
        
        logger.info("Migration completed successfully")
        
    except Exception as e:
        logger.error(f"Error creating playlist tables: {str(e)}")
        raise

if __name__ == "__main__":
    create_playlist_tables()
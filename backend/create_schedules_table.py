#!/usr/bin/env python3
"""
Database migration script to create the schedules table in the castus database.

Requirements:
- Store scheduled items in a schedules table in the castus database
- Items for each day should have a unique item_id
- All items for a day should have the same schedule_id

Table Structure:
- schedule_id: VARCHAR(36) - UUID for the schedule (same for all items in a day)
- item_id: INT AUTO_INCREMENT - Unique identifier for each scheduled item
- date: DATE - The broadcast date
- timeslot: VARCHAR(20) - The timeslot (overnight, early_morning, etc.)
- start_time: TIME(3) - Start time as HH:MM:SS.mmm
- end_time: TIME(3) - End time as HH:MM:SS.mmm  
- content_type: VARCHAR(10) - Content type code (AN, BMP, etc.)
- file_title: VARCHAR(255) - Extracted file title
- file_name: VARCHAR(255) - Original file name
- file_duration: TIME(3) - Duration as HH:MM:SS.mmm
- content_id: VARCHAR(24) - MongoDB ObjectId reference
- engagement_score: FLOAT - AI engagement score
- priority_score: FLOAT - Scheduling priority score
- created_at: TIMESTAMP - When the schedule was created
- created_by: VARCHAR(50) - Who created the schedule
"""

import pymongo
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SchedulesTableManager:
    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None
        
    def connect(self) -> bool:
        """Connect to MongoDB database"""
        try:
            # Connect to MongoDB
            self.client = pymongo.MongoClient("mongodb://localhost:27017/")
            self.db = self.client["castus"]
            self.collection = self.db["schedules"]
            
            logger.info("Connected to MongoDB castus database")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            return False
    
    def create_schedules_collection(self) -> bool:
        """Create the schedules collection with proper indexes"""
        try:
            # Check if collection already exists
            if "schedules" in self.db.list_collection_names():
                logger.info("Schedules collection already exists")
                return True
            
            # Create the collection
            self.collection = self.db.create_collection("schedules")
            
            # Create indexes for better performance
            indexes = [
                # Compound index for schedule queries
                [("schedule_id", pymongo.ASCENDING), ("date", pymongo.ASCENDING)],
                
                # Index for date-based queries
                [("date", pymongo.ASCENDING)],
                
                # Index for timeslot queries
                [("timeslot", pymongo.ASCENDING)],
                
                # Unique index for item_id to ensure uniqueness
                [("item_id", pymongo.ASCENDING)],
                
                # Index for content type queries
                [("content_type", pymongo.ASCENDING)],
                
                # Index for creation time queries
                [("created_at", pymongo.DESCENDING)]
            ]
            
            for index_spec in indexes:
                if index_spec[0][0] == "item_id":
                    # Create unique index for item_id
                    self.collection.create_index(index_spec, unique=True)
                else:
                    self.collection.create_index(index_spec)
            
            logger.info("Successfully created schedules collection with indexes")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create schedules collection: {str(e)}")
            return False
    
    def get_next_item_id(self) -> int:
        """Get the next available item_id"""
        try:
            # Find the highest existing item_id
            result = self.collection.find().sort("item_id", -1).limit(1)
            last_item = list(result)
            
            if last_item:
                return last_item[0]["item_id"] + 1
            else:
                return 1  # Start with 1 if no items exist
                
        except Exception as e:
            logger.error(f"Error getting next item_id: {str(e)}")
            return 1
    
    def insert_schedule_items(self, schedule_data: Dict[str, Any]) -> bool:
        """
        Insert schedule items into the schedules table
        
        Args:
            schedule_data: Dictionary containing schedule information
        """
        try:
            if not schedule_data.get("items"):
                logger.warning("No items to insert")
                return True
            
            # Generate schedule_id (UUID)
            schedule_id = str(uuid.uuid4())
            
            # Prepare documents for insertion
            documents = []
            current_time_seconds = 0
            
            for item in schedule_data["items"]:
                # Calculate start and end times
                start_seconds = current_time_seconds
                end_seconds = current_time_seconds + item.get("duration", 0)
                
                # Convert seconds to HH:MM:SS.mmm format
                start_time = self.seconds_to_time_string(start_seconds)
                end_time = self.seconds_to_time_string(end_seconds)
                duration_time = self.seconds_to_time_string(item.get("duration", 0))
                
                # Extract file title (remove date and type prefix)
                file_title = self.extract_file_title(
                    item.get("file_name", ""), 
                    item.get("content_title", "")
                )
                
                # Create document
                document = {
                    "schedule_id": schedule_id,
                    "item_id": self.get_next_item_id(),
                    "date": schedule_data.get("date"),
                    "timeslot": schedule_data.get("timeslot"),
                    "start_time": start_time,
                    "end_time": end_time,
                    "content_type": item.get("content_type", ""),
                    "file_title": file_title,
                    "file_name": item.get("file_name", ""),
                    "file_duration": duration_time,
                    "content_id": item.get("content_id", ""),
                    "engagement_score": float(item.get("engagement_score", 0)),
                    "priority_score": float(item.get("priority_score", 0)),
                    "created_at": datetime.utcnow(),
                    "created_by": schedule_data.get("created_by", "ATL26_Scheduler")
                }
                
                documents.append(document)
                current_time_seconds = end_seconds
            
            # Insert all documents
            if documents:
                result = self.collection.insert_many(documents)
                logger.info(f"Inserted {len(result.inserted_ids)} schedule items with schedule_id: {schedule_id}")
                return True
            else:
                logger.warning("No documents to insert")
                return False
                
        except Exception as e:
            logger.error(f"Error inserting schedule items: {str(e)}")
            return False
    
    def seconds_to_time_string(self, total_seconds: float) -> str:
        """Convert seconds to HH:MM:SS.mmm format"""
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int((total_seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    
    def extract_file_title(self, file_name: str, content_title: str) -> str:
        """Extract file title from filename and content_title"""
        # If we have a content_title, use that
        if content_title and content_title.strip():
            return content_title.strip()
        
        # Otherwise, extract from filename by removing date and type prefix
        # Expected format: YYMMDD_TYPE_Title.ext
        if file_name:
            name_without_ext = file_name.rsplit('.', 1)[0]  # Remove extension
            parts = name_without_ext.split('_', 2)  # Split into max 3 parts
            
            if len(parts) >= 3:
                # Join everything after the first two parts (date and type)
                return '_'.join(parts[2:])
            
            # Fallback to full filename without extension
            return name_without_ext
        
        return "Unknown Title"
    
    def get_schedule_items(self, date: str, timeslot: str = None) -> list:
        """Get schedule items for a specific date and optional timeslot"""
        try:
            query = {"date": date}
            if timeslot:
                query["timeslot"] = timeslot
            
            cursor = self.collection.find(query).sort("start_time", 1)
            return list(cursor)
            
        except Exception as e:
            logger.error(f"Error getting schedule items: {str(e)}")
            return []
    
    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete all items for a specific schedule_id"""
        try:
            result = self.collection.delete_many({"schedule_id": schedule_id})
            logger.info(f"Deleted {result.deleted_count} items for schedule_id: {schedule_id}")
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"Error deleting schedule: {str(e)}")
            return False
    
    def disconnect(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from database")

# Global instance
schedules_db = SchedulesTableManager()

def main():
    """Main function to create the schedules collection"""
    logger.info("Starting schedules table creation...")
    
    # Connect to database
    if not schedules_db.connect():
        logger.error("Failed to connect to database")
        return False
    
    # Create schedules collection
    if not schedules_db.create_schedules_collection():
        logger.error("Failed to create schedules collection")
        return False
    
    logger.info("Successfully created schedules table structure")
    
    # Test the collection
    test_data = {
        "date": "2025-07-21",
        "timeslot": "morning",
        "created_by": "ATL26_Scheduler",
        "items": [
            {
                "file_name": "250721_AN_Atlanta Morning News.mp4",
                "content_title": "Atlanta Morning News",
                "content_type": "AN",
                "duration": 1800,  # 30 minutes
                "content_id": "507f1f77bcf86cd799439011",
                "engagement_score": 8.5,
                "priority_score": 85.0
            },
            {
                "file_name": "250721_BMP_Station ID Bump.mp4", 
                "content_title": "Station ID Bump",
                "content_type": "BMP",
                "duration": 15,  # 15 seconds
                "content_id": "507f1f77bcf86cd799439012",
                "engagement_score": 6.0,
                "priority_score": 70.0
            }
        ]
    }
    
    logger.info("Testing schedule insertion...")
    if schedules_db.insert_schedule_items(test_data):
        logger.info("✅ Test schedule inserted successfully")
    else:
        logger.error("❌ Failed to insert test schedule")
    
    # Test retrieval
    logger.info("Testing schedule retrieval...")
    items = schedules_db.get_schedule_items("2025-07-21", "morning")
    logger.info(f"Retrieved {len(items)} schedule items")
    
    for item in items:
        logger.info(f"  Item {item['item_id']}: {item['start_time']} - {item['end_time']} | {item['content_type']} | {item['file_title']}")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        if success:
            logger.info("✅ Schedules table setup completed successfully")
        else:
            logger.error("❌ Schedules table setup failed")
    except KeyboardInterrupt:
        logger.info("Setup interrupted by user")
    finally:
        schedules_db.disconnect()
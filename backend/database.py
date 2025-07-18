import os
import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import uuid
from datetime import datetime
from bson import ObjectId

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, connection_string="mongodb://localhost:27017/", database_name="castus"):
        self.connection_string = connection_string
        self.database_name = database_name
        self.client = None
        self.db = None
        self.collection = None
    
    def _convert_objectid_to_string(self, doc):
        """Convert MongoDB ObjectId to string for JSON serialization"""
        if doc is None:
            return None
        
        if isinstance(doc, list):
            return [self._convert_objectid_to_string(item) for item in doc]
        
        if isinstance(doc, dict):
            converted = {}
            for key, value in doc.items():
                if isinstance(value, ObjectId):
                    converted[key] = str(value)
                elif isinstance(value, datetime):
                    converted[key] = value.isoformat()
                elif isinstance(value, dict):
                    converted[key] = self._convert_objectid_to_string(value)
                elif isinstance(value, list):
                    converted[key] = self._convert_objectid_to_string(value)
                else:
                    converted[key] = value
            return converted
        
        return doc
        
    def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = MongoClient(self.connection_string, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client[self.database_name]
            self.collection = self.db['analysis']
            logger.info(f"Connected to MongoDB: {self.database_name}")
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")
    
    def check_analysis_status(self, files):
        """Check which files have already been analyzed"""
        if self.collection is None:
            return []
        
        try:
            file_paths = [file.get('path') or file.get('name') for file in files]
            analyzed_files = list(self.collection.find(
                {"file_path": {"$in": file_paths}},
                {"file_path": 1, "file_name": 1, "guid": 1, "created_at": 1}
            ))
            return self._convert_objectid_to_string(analyzed_files)
        except Exception as e:
            logger.error(f"Error checking analysis status: {str(e)}")
            return []
    
    def get_analysis_by_path(self, file_path):
        """Get analysis result for a specific file path"""
        if self.collection is None:
            return None
        
        try:
            result = self.collection.find_one({"file_path": file_path})
            return self._convert_objectid_to_string(result)
        except Exception as e:
            logger.error(f"Error getting analysis for {file_path}: {str(e)}")
            return None
    
    def upsert_analysis(self, analysis_data):
        """Insert or update analysis result"""
        if self.collection is None:
            return False
        
        try:
            # Make a copy to avoid mutating the original data
            data_copy = analysis_data.copy()
            
            # Check if file already exists
            existing = self.collection.find_one({"file_path": data_copy["file_path"]})
            
            if existing:
                # Update existing record, keep the same GUID
                data_copy["guid"] = existing["guid"]
                data_copy["updated_at"] = datetime.utcnow()
                result = self.collection.replace_one(
                    {"file_path": data_copy["file_path"]},
                    data_copy
                )
                logger.info(f"Updated analysis for {data_copy['file_name']}")
            else:
                # Insert new record with new GUID
                data_copy["guid"] = str(uuid.uuid4())
                data_copy["created_at"] = datetime.utcnow()
                data_copy["updated_at"] = datetime.utcnow()
                result = self.collection.insert_one(data_copy)
                logger.info(f"Inserted new analysis for {data_copy['file_name']}")
            
            return True
        except Exception as e:
            logger.error(f"Error upserting analysis: {str(e)}")
            return False
    
    def get_all_analyses(self, limit=1000):
        """Get all analysis results"""
        if self.collection is None:
            return []
        
        try:
            results = list(self.collection.find().limit(limit))
            return self._convert_objectid_to_string(results)
        except Exception as e:
            logger.error(f"Error getting all analyses: {str(e)}")
            return []
    
    def delete_analysis(self, file_path):
        """Delete analysis result"""
        if self.collection is None:
            return False
        
        try:
            result = self.collection.delete_one({"file_path": file_path})
            if result.deleted_count > 0:
                logger.info(f"Deleted analysis for {file_path}")
                return True
            else:
                logger.warning(f"No analysis found for {file_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting analysis: {str(e)}")
            return False

# Global database manager instance
db_manager = DatabaseManager()
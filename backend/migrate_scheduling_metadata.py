#!/usr/bin/env python3
"""
Migration script to add scheduling metadata to existing analyzed content in MongoDB.
This script will update all existing content documents with the new scheduling fields.
"""

import logging
from datetime import datetime, timedelta
from database import db_manager
from file_analyzer import file_analyzer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SchedulingMigration:
    def __init__(self):
        self.analyzer = file_analyzer
    
    def migrate_all_content(self):
        """Migrate all existing analyzed content to include scheduling metadata"""
        logger.info("Starting scheduling metadata migration...")
        
        try:
            # Connect to database
            if not db_manager.connect():
                logger.error("Failed to connect to database")
                return False
            
            # Find all analyzed content without scheduling metadata
            query = {
                "analysis_completed": True,
                "$or": [
                    {"scheduling": {"$exists": False}},
                    {"duration_category": {"$exists": False}}
                ]
            }
            
            cursor = db_manager.collection.find(query)
            content_list = list(cursor)
            
            logger.info(f"Found {len(content_list)} content items to migrate")
            
            if len(content_list) == 0:
                logger.info("No content items need migration")
                return True
            
            updated_count = 0
            error_count = 0
            
            for content in content_list:
                try:
                    # Get basic info
                    file_name = content.get('file_name', '')
                    duration = content.get('file_duration', 0)
                    content_type = content.get('content_type', '')
                    engagement_score = content.get('engagement_score', 0)
                    shelf_life_score = content.get('shelf_life_score', 'medium')
                    
                    logger.info(f"Migrating: {file_name}")
                    
                    # Calculate scheduling metadata
                    duration_category = self.analyzer.get_duration_category(duration)
                    priority_score = self.analyzer.calculate_priority_score(engagement_score, duration_category)
                    optimal_timeslots = self.analyzer.get_optimal_timeslots(content_type, duration_category)
                    expiry_date = self.analyzer.calculate_expiry_date(duration_category, shelf_life_score)
                    
                    # Create scheduling metadata
                    scheduling_metadata = {
                        "available_for_scheduling": True,
                        "content_expiry_date": expiry_date,
                        "last_scheduled_date": None,
                        "total_airings": 0,
                        "created_for_scheduling": datetime.utcnow(),
                        
                        # Timeslot scheduling tracking
                        "last_scheduled_in_overnight": None,
                        "last_scheduled_in_early_morning": None,
                        "last_scheduled_in_morning": None,
                        "last_scheduled_in_afternoon": None,
                        "last_scheduled_in_prime_time": None,
                        "last_scheduled_in_evening": None,
                        
                        # Replay count tracking per timeslot
                        "replay_count_for_overnight": 0,
                        "replay_count_for_early_morning": 0,
                        "replay_count_for_morning": 0,
                        "replay_count_for_afternoon": 0,
                        "replay_count_for_prime_time": 0,
                        "replay_count_for_evening": 0,
                        
                        # Engagement and priority scoring
                        "priority_score": priority_score,
                        "optimal_timeslots": optimal_timeslots
                    }
                    
                    # Update document
                    update_data = {
                        "$set": {
                            "duration_category": duration_category,
                            "scheduling": scheduling_metadata
                        }
                    }
                    
                    result = db_manager.collection.update_one(
                        {"_id": content["_id"]},
                        update_data
                    )
                    
                    if result.modified_count > 0:
                        updated_count += 1
                        logger.info(f"  ✅ Updated {file_name} - Category: {duration_category}, Priority: {priority_score:.1f}, Timeslots: {optimal_timeslots}")
                    else:
                        logger.warning(f"  ⚠️ No changes made to {file_name}")
                    
                except Exception as e:
                    error_count += 1
                    logger.error(f"  ❌ Error migrating {file_name}: {str(e)}")
            
            logger.info(f"Migration completed: {updated_count} updated, {error_count} errors")
            return error_count == 0
            
        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            return False
    
    def verify_migration(self):
        """Verify that all content has been migrated correctly"""
        logger.info("Verifying migration...")
        
        try:
            # Count total analyzed content
            total_content = db_manager.collection.count_documents({"analysis_completed": True})
            
            # Count content with scheduling metadata
            migrated_content = db_manager.collection.count_documents({
                "analysis_completed": True,
                "duration_category": {"$exists": True},
                "scheduling": {"$exists": True}
            })
            
            logger.info(f"Total analyzed content: {total_content}")
            logger.info(f"Content with scheduling metadata: {migrated_content}")
            
            if total_content == migrated_content:
                logger.info("✅ All content has been migrated successfully!")
                
                # Show some statistics
                self.show_migration_stats()
                return True
            else:
                logger.error(f"❌ Migration incomplete: {total_content - migrated_content} items still need migration")
                return False
                
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            return False
    
    def show_migration_stats(self):
        """Show statistics about migrated content"""
        logger.info("Migration Statistics:")
        
        try:
            # Duration category stats
            duration_stats = db_manager.collection.aggregate([
                {"$match": {"analysis_completed": True, "duration_category": {"$exists": True}}},
                {"$group": {"_id": "$duration_category", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ])
            
            logger.info("  Duration Categories:")
            for stat in duration_stats:
                logger.info(f"    {stat['_id']}: {stat['count']} items")
            
            # Content type stats
            content_type_stats = db_manager.collection.aggregate([
                {"$match": {"analysis_completed": True, "content_type": {"$ne": ""}}},
                {"$group": {"_id": "$content_type", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ])
            
            logger.info("  Content Types:")
            for stat in content_type_stats:
                logger.info(f"    {stat['_id']}: {stat['count']} items")
            
            # Available for scheduling
            available_count = db_manager.collection.count_documents({
                "analysis_completed": True,
                "scheduling.available_for_scheduling": True
            })
            
            logger.info(f"  Available for scheduling: {available_count} items")
            
        except Exception as e:
            logger.error(f"Error showing stats: {str(e)}")

def main():
    """Run the migration"""
    migration = SchedulingMigration()
    
    print("=" * 60)
    print("SCHEDULING METADATA MIGRATION")
    print("=" * 60)
    
    # Run migration
    success = migration.migrate_all_content()
    
    if success:
        print("\n" + "=" * 60)
        print("VERIFYING MIGRATION")
        print("=" * 60)
        
        # Verify migration
        verification_success = migration.verify_migration()
        
        if verification_success:
            print("\n🎉 Migration completed successfully!")
            print("✅ All content is now ready for scheduling")
        else:
            print("\n⚠️ Migration verification failed")
            print("❌ Some content may not be ready for scheduling")
    else:
        print("\n❌ Migration failed")
        print("Please check the logs for errors")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Enhanced get_content_with_progressive_delays that resets delays when content is exhausted
"""

def _get_content_with_progressive_delays_enhanced(self, duration_category: str, exclude_ids: List[int], 
                                                  schedule_date: str, scheduled_asset_times: dict = None,
                                                  allow_reset: bool = True) -> List[Dict[str, Any]]:
    """Get available content, progressively relaxing delay requirements if needed
    
    This enhanced version adds a reset mechanism when all content is exhausted.
    
    This method tries to get content with increasingly relaxed delay requirements:
    1. Full delays (100%)
    2. 75% of configured delays
    3. 50% of configured delays
    4. 25% of configured delays
    5. No delays (0%)
    6. If still no content and allow_reset=True, clear category-specific exclusions
    
    Args:
        duration_category: Category to get content for
        exclude_ids: List of asset IDs to exclude
        schedule_date: Date being scheduled
        scheduled_asset_times: Dict tracking when assets were scheduled
        allow_reset: If True, reset exclusions when all content exhausted
    
    Returns:
        List of available content items
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Try with progressive delay reduction
    delay_factors = [1.0, 0.75, 0.5, 0.25, 0.0]
    
    for factor in delay_factors:
        available_content = self.get_available_content(
            duration_category,
            exclude_ids=exclude_ids,
            schedule_date=schedule_date,
            delay_reduction_factor=factor,
            scheduled_asset_times=scheduled_asset_times
        )
        if available_content and factor < 1.0:
            logger.warning(f"⚠️ Found {len(available_content)} items for {duration_category} with REDUCED {factor*100:.0f}% delay requirements")
        
        if available_content:
            # Mark content items with the delay factor used to retrieve them
            for item in available_content:
                item['_delay_factor_used'] = factor
            return available_content
    
    # If we get here, no content is available even with 0% delays
    if allow_reset and exclude_ids:
        # Get all assets in this category to see what we're excluding
        conn = db_manager._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM assets 
                WHERE duration_category = %s 
                AND analysis_completed = TRUE
            """, [duration_category])
            
            category_asset_ids = {row[0] for row in cursor}
            cursor.close()
            
            # Find which category assets are being excluded
            excluded_category_assets = set(exclude_ids) & category_asset_ids
            
            if excluded_category_assets:
                logger.error(f"❌ No content available for {duration_category} even with all delay restrictions removed")
                logger.error(f"   Total {duration_category} content in database: {len(category_asset_ids)}")
                logger.error(f"   Excluded items: {len(excluded_category_assets)}")
                
                # RESET: Remove category-specific exclusions
                logger.warning(f"🔄 RESETTING exclusions for {duration_category} content to allow reuse")
                
                # Create a new exclude list without this category's assets
                reset_exclude_ids = [aid for aid in exclude_ids if aid not in excluded_category_assets]
                
                # Also reset the scheduled times for this category's assets
                if scheduled_asset_times:
                    for asset_id in excluded_category_assets:
                        if asset_id in scheduled_asset_times:
                            # Keep only the most recent scheduling time
                            if scheduled_asset_times[asset_id]:
                                scheduled_asset_times[asset_id] = [scheduled_asset_times[asset_id][-1]]
                
                # Try again with reset exclusions
                available_content = self.get_available_content(
                    duration_category,
                    exclude_ids=reset_exclude_ids,
                    schedule_date=schedule_date,
                    delay_reduction_factor=0.0,  # Still use 0% delays
                    scheduled_asset_times=scheduled_asset_times
                )
                
                if available_content:
                    logger.info(f"✅ After reset: Found {len(available_content)} items for {duration_category}")
                    for item in available_content:
                        item['_delay_factor_used'] = 0.0
                        item['_was_reset'] = True
                    return available_content
                
        finally:
            db_manager._put_connection(conn)
    
    # Still no content after reset attempt
    conn = db_manager._get_connection()
    try:
        cursor = conn.cursor()
        
        # Log diagnostic information
        cursor.execute("""
            SELECT COUNT(*) FROM assets 
            WHERE duration_category = %s 
            AND analysis_completed = TRUE
        """, [duration_category])
        total_count = cursor.fetchone()[0]
        
        cursor.close()
        
        logger.error(f"❌ No content available for {duration_category} even after reset attempt")
        logger.error(f"   Total {duration_category} content in database: {total_count}")
        logger.error(f"   This may indicate all content is expired or unavailable")
        
    finally:
        db_manager._put_connection(conn)
    
    return []


# Alternative approach: Implement a smarter exclusion system
class CategoryAwareExclusionTracker:
    """Track exclusions by category to enable category-specific resets"""
    
    def __init__(self):
        self.global_exclusions = set()  # Never reset
        self.category_exclusions = {
            'id': set(),
            'spots': set(),
            'short_form': set(),
            'long_form': set()
        }
        self.reset_counts = {cat: 0 for cat in self.category_exclusions}
    
    def add_exclusion(self, asset_id: int, category: str):
        """Add an asset to the exclusion list"""
        if category in self.category_exclusions:
            self.category_exclusions[category].add(asset_id)
    
    def get_exclusions_for_category(self, category: str) -> List[int]:
        """Get all exclusions that should apply for a category lookup"""
        # Always include global exclusions
        exclusions = self.global_exclusions.copy()
        
        # Add category-specific exclusions
        if category in self.category_exclusions:
            exclusions.update(self.category_exclusions[category])
        
        return list(exclusions)
    
    def reset_category(self, category: str):
        """Reset exclusions for a specific category"""
        if category in self.category_exclusions:
            count = len(self.category_exclusions[category])
            self.category_exclusions[category].clear()
            self.reset_counts[category] += 1
            return count
        return 0
    
    def get_stats(self) -> dict:
        """Get statistics about exclusions and resets"""
        return {
            'global_exclusions': len(self.global_exclusions),
            'category_exclusions': {cat: len(excl) for cat, excl in self.category_exclusions.items()},
            'reset_counts': self.reset_counts.copy()
        }


print("=== DELAY RESET ENHANCEMENT ===")
print("\nThe current implementation has a critical flaw:")
print("- Once all content in a category is used, it stays excluded forever")
print("- This causes infinite loops even when content could be reused")
print("\n✅ Solution 1: Enhanced Progressive Delays with Reset")
print("- Tries delays: 100% → 75% → 50% → 25% → 0%")
print("- If still no content, RESETS category-specific exclusions")
print("- Allows content to be reused when necessary")
print("\n✅ Solution 2: Category-Aware Exclusion Tracking")
print("- Track exclusions separately by category")
print("- Reset only the exhausted category, not all content")
print("- Maintains better content diversity")
print("\nBoth solutions prevent infinite loops while maximizing content variety.")
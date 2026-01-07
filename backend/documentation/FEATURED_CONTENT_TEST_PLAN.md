# Featured Content System Test Plan

## Summary

The enhanced featured content system has been successfully implemented with the following features:

### 1. Backend Implementation (scheduler_postgres.py)
- ✅ Daytime priority scheduling (75% chance during 6am-6pm)
- ✅ Meeting relevance decay (fresh → relevant → archive → expired)
- ✅ Auto-featuring based on content type and engagement scores
- ✅ Configurable minimum spacing between featured plays

### 2. Configuration Schema (config_manager.py)
- ✅ Featured content settings (daytime hours, probability, spacing)
- ✅ Meeting relevance tiers (fresh_days, relevant_days, archive_days)
- ✅ Content type priorities (MTG, PSA, MAF with specific rules)

### 3. Frontend UI (script.js + index.html)
- ✅ New "Featured Content" configuration button
- ✅ Configuration dialog with all settings
- ✅ Save functionality to persist settings
- ✅ Automatic loading of saved configuration

## Testing Steps

### 1. Configure Featured Content Settings
1. Open the scheduling panel
2. Click "Featured Content" button
3. Adjust settings:
   - Set daytime hours: 6am to 6pm
   - Set daytime priority: 75%
   - Set minimum spacing: 2 hours
   - Enable meeting relevance decay
   - Configure meeting tiers (3/7/14/18 days)

### 2. Create Test Schedule
1. Create a weekly schedule
2. Monitor logs for featured content scheduling:
   - Look for "Scheduling featured content" messages
   - Verify daytime vs nighttime distribution
   - Check spacing between featured plays

### 3. Verify Meeting Decay
1. Add meetings with different ages
2. Create schedule and verify:
   - Fresh meetings (< 3 days) are featured frequently
   - Relevant meetings (3-7 days) are featured less
   - Archive meetings (7-14 days) rarely featured
   - Expired meetings (> 18 days) not featured

### 4. Test Engagement-Based Featuring
1. Add MAF content with high engagement scores (> 80%)
2. Verify auto-featuring in schedule
3. Add low engagement content and verify it's not featured

## Expected Results

1. **Daytime Bias**: ~75% of featured content during 6am-6pm
2. **Spacing**: At least 2 hours between featured plays
3. **Meeting Decay**: Newer meetings play more frequently
4. **PSAs**: Always featured when available
5. **MAF**: Featured only if engagement > 80%

## Configuration Persistence

The system saves all settings to `backend/config.json` under the `scheduling` section:
- `featured_content`: Daytime settings
- `meeting_relevance`: Age-based tiers
- `content_priorities`: Type-specific rules

## Monitoring

Check backend logs for:
- "Using rotation order" - Shows active configuration
- "Scheduling featured content" - Featured content being placed
- "daytime" vs "nighttime" indicators
- Meeting relevance tier assignments
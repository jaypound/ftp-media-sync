# Featured Content Scheduling Guide

## Overview
The Featured content flag is a powerful tool for increasing the scheduling frequency and visibility of specific content items. This guide explains how the Featured flag affects content scheduling, particularly for Special Projects (SPP) and other content types.

## What is Featured Content?
Featured content is content that has been marked for priority scheduling. This can happen in two ways:
1. **Manual flagging**: Content explicitly marked as "Featured" in the scheduling metadata
2. **Auto-featuring**: Content automatically featured based on rules (e.g., high engagement scores, recent meetings)

## Impact of the Featured Flag

### 1. Reduced Replay Delays
The most significant impact of marking content as Featured is the dramatic reduction in replay delays:

| Content State | Minimum Time Between Plays |
|--------------|---------------------------|
| Regular SPP  | 3+ hours                  |
| Featured SPP | 2 hours                   |

This represents a **50% increase** in potential scheduling opportunities.

### 2. Scheduling Priority
Featured content receives several scheduling advantages:
- **Priority selection**: Featured content is checked first before regular content
- **Round-robin distribution**: All featured items are cycled through evenly
- **Gap filling preference**: Featured content is preferred when filling schedule gaps
- **Rotation interruption**: Featured content can interrupt the normal duration category rotation

### 3. Daytime Scheduling Preference
Featured content is intelligently scheduled with time-of-day preferences:
- **75% probability** of scheduling during daytime hours (6 AM - 6 PM)
- **25% probability** of scheduling during overnight hours
- This ensures featured content appears when viewership is typically highest

### 4. How Featured Content is Selected
The scheduler uses this process for featured content:
1. Checks if minimum spacing (2 hours) has elapsed since last featured item
2. Evaluates daytime preference based on current time slot
3. Retrieves all available featured content
4. Selects next item using round-robin to ensure fair distribution
5. Falls back to regular content if no featured items available

## Use Case: Holiday Greetings Campaign
When you have multiple SPP items with the same theme (e.g., "HolidayGreeting"), marking them as Featured provides:

### Benefits:
- **Increased frequency**: Play every 2 hours instead of 3+ hours
- **Better visibility**: 75% chance of daytime scheduling
- **Even distribution**: All holiday greetings get equal airtime
- **Campaign control**: Easy to feature/unfeature for seasonal campaigns

### Example Schedule Impact:
**Without Featured flag (Regular SPP):**
- Maximum 8 plays per day (every 3 hours)
- Random time distribution
- Competes with all other content

**With Featured flag:**
- Maximum 12 plays per day (every 2 hours)
- Concentrated in daytime hours
- Priority over non-featured content

## Configuration Settings
The Featured content system is controlled by these configuration parameters:

```json
{
  "scheduling": {
    "featured_content": {
      "minimum_spacing": 2.0,        // Hours between featured content
      "daytime_hours": {
        "start": 6,                  // 6 AM
        "end": 18                    // 6 PM
      },
      "daytime_probability": 0.75    // 75% chance during daytime
    }
  }
}
```

## Content Types and Default Replay Delays
For reference, here are the standard replay delays by content type when NOT featured:

| Content Type | Description | Standard Delay | Featured Delay |
|-------------|-------------|----------------|----------------|
| AN | Atlanta Now | 2 hours | 2 hours |
| BMP | Bumps | 3 hours | 2 hours |
| SPP | Special Projects | 3 hours | 2 hours |
| MTG | Meetings | 8 hours | 2 hours |
| IM | Inclusion Months | 3 hours | 2 hours |
| PSA | Public Service Announcements | 2 hours | 2 hours |

## Best Practices

### When to Use Featured Flag:
1. **Seasonal campaigns** (holiday greetings, special events)
2. **Time-sensitive content** (announcements, urgent PSAs)
3. **High-value content** (sponsor messages, important meetings)
4. **New content launches** (premieres, fresh productions)

### When NOT to Use Featured Flag:
1. **Evergreen content** that doesn't need priority
2. **Large content libraries** (featuring too many items dilutes the effect)
3. **Content with natural high rotation** (already plays frequently)

## Technical Implementation
The Featured flag is stored in the `scheduling_metadata` table:
```sql
UPDATE scheduling_metadata 
SET featured = TRUE 
WHERE asset_id IN (SELECT id FROM assets WHERE theme = 'HolidayGreeting');
```

## Monitoring Featured Content
Track the effectiveness of featured content by monitoring:
1. Actual plays vs. potential plays
2. Time-of-day distribution
3. Overall schedule balance
4. Viewer engagement metrics

## Related Documentation
- [Content Rotation System](./CONTENT_ROTATION.md) - General rotation configuration
- [Scheduling Metadata Guide](./SCHEDULING_METADATA.md) - Metadata management
- [CLAUDE.md](./CLAUDE.md) - Project documentation
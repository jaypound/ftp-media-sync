# PSA Selection System Documentation

## Executive Overview

The PSA (Public Service Announcement) selection system is a sophisticated content scheduling mechanism that **combines deterministic scoring with minimal randomization** to ensure fair, diverse, and contextually appropriate PSA placement throughout broadcast schedules. Contrary to common perception, PSAs are **not selected randomly** but through a carefully designed algorithm that balances multiple factors to achieve optimal distribution.

### Key Principles
- **Deterministic Selection**: PSAs are chosen based on calculated scores, not random chance
- **Smart Distribution**: Ensures PSAs don't cluster or repeat themes
- **Fairness Through Rotation**: All PSAs get airtime through systematic rotation
- **Context Awareness**: Considers surrounding content to avoid theme conflicts

## PSA Classification

### Content Type Definition
PSAs are identified by the content type code `PSA` in the database. They typically fall into the **"spots"** duration category (30-120 seconds), though some may be classified as **"id"** (5-30 seconds) for very brief announcements.

### Common PSA Themes
- Public Safety (gun safety, emergency preparedness)
- Health Awareness (vaccination, medical screenings)
- Community Services (housing assistance, job programs)
- Environmental Messages (recycling, conservation)
- Civic Engagement (voting, census participation)

## Selection Algorithm

### 1. Base Score Calculation
Every PSA starts with a base score of **100 points** plus a small random variation (-5 to +5 points) to break ties between otherwise identical content.

```python
score = 100 + random.uniform(-5, 5)  # Base score with minimal randomization
```

### 2. Scoring Factors

#### Freshness Component (Implicit)
- Newer PSAs receive priority through lower play counts
- Recently encoded content appears higher in initial queries

#### Play History Penalties
PSAs that have aired recently receive progressive penalties:
- **Within 1 hour**: -100 points (heavy penalty)
- **1-2 hours**: -50 points (medium penalty)
- **2-4 hours**: -25 points (light penalty)
- **4-6 hours**: -10 points (very light penalty)
- **3+ plays in schedule**: -50 points × (plays - 2)

#### Content Type Specific Rules
PSAs have a **2-hour minimum replay delay** by default, which is shorter than most content types, allowing them to rotate more frequently throughout the day.

#### Theme Conflict Prevention
PSAs in the "spots" category are subject to strict theme checking:
- **Same theme back-to-back**: -200 points (heavy penalty)
- Prevents viewer fatigue from repetitive messaging
- Ensures diverse public service messages

#### Featured Content Boost
PSAs can be marked as "featured" for time-sensitive campaigns:
- **Featured boost**: +150 points
- Used for urgent public safety messages
- Emergency announcements get priority placement

### 3. Selection Process

1. **Query Available PSAs**: System retrieves PSAs that:
   - Haven't exceeded replay delays
   - Aren't expired
   - Match the requested duration category
   - Haven't been explicitly excluded

2. **Calculate Scores**: Each candidate PSA receives a score based on:
   - Base score (100 ± 5)
   - Play history penalties
   - Theme conflict penalties
   - Featured status bonuses

3. **Select Best Candidate**: The PSA with the highest score is selected
   - Ties broken by the small random component
   - If all scores are negative, first available is used

4. **Update Tracking**: Selected PSA is recorded to prevent immediate replay

## Randomization Elements

### Minimal Random Components

1. **Tie Breaking**: ±5 points added to base score
   - Prevents identical content from always appearing in same order
   - Ensures variety when multiple PSAs have similar scores

2. **Query Ordering**: SQL queries include `ORDER BY RANDOM()` as final sort
   - Only affects items with identical priority
   - Provides variety in candidate pool

3. **No Pure Random Selection**: System never randomly picks from available PSAs
   - Every selection based on calculated scores
   - Randomness only provides minor variations

## Diversity Mechanisms

### 1. Rotation Through Inventory
- All PSAs get airtime through score-based rotation
- Recently played content penalized, giving others opportunity
- Natural cycling through entire PSA library

### 2. Theme Distribution
- Strict theme conflict prevention for spots category
- Ensures variety of public service messages
- Prevents clustering of similar topics

### 3. Time-Based Distribution
- 2-hour minimum spacing between same PSA
- Shorter delay allows more frequent rotation than other content
- Ensures important messages reach different audiences

### 4. Category Mixing
- PSAs scheduled as part of "spots" rotation
- Mixed with other short-form content
- Prevents PSA clustering

## Special Handling

### 1. Emergency PSAs
- Can be marked as "featured" for immediate priority
- Bypass normal rotation for urgent messages
- Still subject to minimum replay delays

### 2. Campaign PSAs
- Time-sensitive campaigns use expiration dates
- Automatically removed from rotation when expired
- Featured status for launch periods

### 3. Themed Periods
- Special handling during awareness months
- Increased priority for relevant PSAs
- Manual featuring of campaign content

## Configuration Parameters

### Default PSA Settings
```json
{
  "content_type_delays": {
    "psa": 2  // 2-hour minimum between plays
  },
  "scoring_weights": {
    "base_score": 100,
    "featured_boost": 150,
    "theme_conflict_penalty": 200,
    "recent_play_penalty": 100
  }
}
```

### Tunable Parameters
- **Replay Delay**: Minimum hours between same PSA (default: 2)
- **Featured Boost**: Score bonus for featured PSAs (default: 150)
- **Theme Penalties**: Penalty for theme conflicts (default: 200)

## Common Misconceptions

### "PSAs are selected randomly"
**Reality**: PSAs are selected through deterministic scoring with only minimal randomization for tie-breaking. The selection process is highly predictable and based on objective criteria.

### "Some PSAs never get played"
**Reality**: The scoring system ensures all active PSAs eventually play through natural rotation as others accumulate penalties from recent plays.

### "PSAs cluster together"
**Reality**: Theme conflict prevention and category rotation specifically prevent PSA clustering, ensuring they're distributed throughout the schedule.

### "Important PSAs can't be prioritized"
**Reality**: The featured content system allows urgent or important PSAs to receive significant scoring boosts while still maintaining fair rotation.

## Best Practices

### 1. Content Preparation
- Assign clear themes to enable conflict prevention
- Set appropriate expiration dates for campaigns
- Use descriptive titles for better tracking

### 2. Campaign Management
- Mark time-sensitive PSAs as featured
- Set expiration dates to auto-remove outdated content
- Monitor play counts to ensure distribution

### 3. Inventory Balance
- Maintain diverse PSA library (15+ active PSAs)
- Regular content refresh to prevent staleness
- Balance themes across inventory

### 4. Performance Optimization
- Monitor replay delays to ensure adequate rotation
- Adjust featuring based on campaign needs
- Review theme conflicts in reports

## Monitoring and Reporting

### Available Metrics
- PSA play frequency by content
- Theme distribution analysis
- Replay delay compliance
- Featured content performance

### Key Performance Indicators
- **Unique PSA Ratio**: Variety of PSAs played daily
- **Theme Diversity Score**: Distribution of different themes
- **Replay Compliance**: Adherence to minimum delays
- **Coverage Metrics**: Reach across different dayparts

## Technical Implementation

### Database Structure
PSAs are stored in the `assets` table with:
- `content_type = 'PSA'`
- `duration_category` (usually 'spots')
- Theme information in metadata
- Featured flags in `scheduling_metadata`

### Selection Query
The system uses sophisticated SQL queries that:
- Filter by availability and expiration
- Calculate play history
- Order by multiple factors
- Include slight randomization

### Score Calculation
Implemented in Python with:
- Clear scoring logic
- Extensive logging for debugging
- Configurable parameters
- Performance optimization

## Conclusion

The PSA selection system represents a careful balance between predictability and variety. While not truly random, it achieves the appearance of randomness through intelligent rotation and scoring that ensures:

1. **Fair Distribution**: All PSAs receive airtime
2. **Contextual Appropriateness**: Theme conflicts avoided
3. **Campaign Effectiveness**: Priority content gets visibility
4. **Viewer Experience**: Diverse messaging without repetition

The system's sophistication ensures that public service messages reach their intended audiences effectively while maintaining the quality and variety expected in professional broadcast operations.
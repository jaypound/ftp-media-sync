# Package Selection System Documentation

## Executive Overview

Packages (PKG) represent a critical content category in the ATL26 broadcast system, typically containing news segments, feature stories, and produced content pieces. The package selection system employs an **enhanced rotation algorithm** that gives packages **dedicated slots** in the scheduling rotation, ensuring they receive prominent placement and adequate visibility throughout the broadcast day.

### Key Features
- **Enhanced Rotation System**: Packages get two dedicated slots per rotation cycle
- **Strategic Placement**: Optimized for prime time and high-viewership periods  
- **Balanced Distribution**: 3-hour minimum replay delays prevent oversaturation
- **Quality-Driven Selection**: Multi-factor scoring ensures best content airs first

## What Are Packages?

### Content Definition
Packages are professionally produced video segments that typically include:
- News stories with reporter narration
- Feature segments on community topics
- Special interest pieces
- Investigative reports
- Human interest stories

### Technical Characteristics
- **Content Type Code**: `PKG`
- **Duration Category**: Usually `short_form` (2-10 minutes)
- **File Naming**: Contains `_PKG_` in filename
- **Production Quality**: Fully edited with graphics, narration, and b-roll

## Enhanced Package Rotation

### The Innovation
Unlike other content types that compete within general duration categories, packages benefit from an **enhanced rotation system** specifically designed to increase their visibility:

```python
# Standard rotation (old system)
DEFAULT_ROTATION = ['id', 'spots', 'short_form', 'long_form']

# Enhanced rotation (current system)
ENHANCED_ROTATION = ['id', 'spots', 'pkg', 'short_form', 'pkg', 'long_form']
```

### Impact on Package Visibility
1. **Guaranteed Slots**: Packages appear twice in each rotation cycle
2. **Reduced Competition**: Dedicated PKG slots mean packages don't compete with all short_form content
3. **Better Distribution**: Ensures packages are spread throughout the schedule
4. **Increased Airtime**: Roughly 33% more package airtime compared to standard rotation

## Selection Algorithm

### 1. Rotation Position
When the scheduler reaches a `pkg` slot in the rotation:
1. System specifically requests package content
2. Only assets with `content_type = 'PKG'` are considered
3. If no packages available, system falls back to general `short_form` content

### 2. Scoring System

#### Base Score
Every package starts with **100 points** plus small randomization:
```python
score = 100 + random.uniform(-5, 5)  # Base score with tie-breaking
```

#### Scoring Factors

**Freshness Bonus**
- Never aired: +30 points
- Recently encoded content prioritized through query ordering

**Featured Content**
- Featured packages: +150 points
- Used for breaking news or priority stories

**Play History Penalties**
Progressive penalties based on recency:
- Within 1 hour: -100 points
- 1-2 hours: -50 points  
- 2-4 hours: -25 points
- 4-6 hours: -10 points
- 3+ plays today: -50 × (plays - 2)

**Replay Delay Enforcement**
- Minimum 3-hour gap between same package
- Violations heavily penalized (-200 points per hour under minimum)

### 3. Content Retrieval Query

The system uses sophisticated SQL queries that:
1. Filter for available packages not exceeding replay delays
2. Check expiration dates and go-live dates
3. Exclude packages already in the schedule
4. Order by multiple factors including play count and encoding date
5. Apply final randomization to prevent predictable ordering

## Time-of-Day Optimization

### Preferred Timeslots
Packages are optimized for specific dayparts:
- **Prime Time** (6-10 PM): Highest priority
- **Evening** (5-11 PM): High priority  
- **Afternoon** (12-5 PM): Medium priority
- **Morning** (6-12 PM): Lower priority
- **Late Night** (11 PM-6 AM): Lowest priority

### Daypart Influence
While not enforced as hard rules, the system subtly favors packages during their preferred timeslots through:
- Featured content scheduling bias
- Manual scheduling preferences
- Rotation timing alignment

## Diversity Mechanisms

### 1. Enhanced Rotation Benefits
- **Predictable Spacing**: Packages appear regularly, not clustered
- **Fair Distribution**: All packages get airtime through systematic rotation
- **Genre Balance**: Different package types distributed throughout day

### 2. Theme Variation
- Packages typically have rich metadata including themes
- System avoids scheduling similar themes consecutively
- Ensures variety in story topics and subjects

### 3. Duration Mix
- Packages vary from 2-10 minutes typically
- System selects appropriate durations for available gaps
- Prevents monotonous pacing

## Special Package Types

### 1. Breaking News Packages
- Marked as `featured` for immediate priority
- Can override normal rotation rules
- Still subject to minimum replay delays

### 2. Series Packages
- Multi-part stories scheduled strategically
- Episodes spaced appropriately
- Series metadata preserved for continuity

### 3. Evergreen Packages
- Human interest and feature stories
- Lower decay rate in scoring
- Used to fill gaps when fresh content limited

### 4. Seasonal Packages
- Holiday or event-specific content
- Expiration dates prevent out-of-season airing
- Featured during relevant periods

## Configuration Parameters

### Package-Specific Settings
```json
{
  "rotation_order": ["id", "spots", "pkg", "short_form", "pkg", "long_form"],
  "content_type_delays": {
    "pkg": 3  // 3-hour minimum between replays
  },
  "scoring_weights": {
    "featured_boost": 150,
    "never_played_bonus": 30,
    "recent_play_penalties": {
      "1_hour": 100,
      "2_hours": 50,
      "4_hours": 25,
      "6_hours": 10
    }
  }
}
```

### Tunable Parameters
- **Replay Delay**: Minimum hours between same package (default: 3)
- **Rotation Slots**: Number of dedicated PKG slots (default: 2)
- **Featured Boost**: Priority boost for featured packages (default: 150)

## Performance Metrics

### Key Performance Indicators

1. **Package Unique Ratio**: Variety of packages aired daily
   - Target: >70% unique packages per day
   - Indicates healthy rotation

2. **Prime Time Fill Rate**: Percentage of prime slots with packages
   - Target: >40% during 6-10 PM
   - Measures strategic placement

3. **Average Replay Gap**: Hours between package replays
   - Target: >6 hours
   - Shows distribution effectiveness

4. **Genre Distribution**: Variety of package topics
   - Balanced across news, features, community
   - Prevents topic fatigue

## Selection Process Flow

1. **Rotation Trigger**
   - Scheduler reaches 'pkg' slot in rotation
   - System initiates package selection

2. **Candidate Retrieval**
   - Query available packages from database
   - Apply replay delay filters
   - Check expiration dates

3. **Scoring Phase**
   - Calculate base scores
   - Apply all bonuses and penalties
   - Rank candidates by total score

4. **Selection Decision**
   - Choose highest scoring package
   - If tie, random component breaks it
   - If no valid packages, fall back to short_form

5. **Scheduling Confirmation**
   - Add to schedule
   - Update play history
   - Log selection decision

## Best Practices

### 1. Content Management
- Maintain diverse package inventory (20+ active)
- Regular content refresh with new packages
- Proper metadata tagging for themes and topics

### 2. Strategic Featuring
- Feature breaking news packages immediately
- Use featuring sparingly to maintain effectiveness
- Remove featuring after initial priority period

### 3. Inventory Balance
- Mix of package durations (2-10 minutes)
- Balance hard news vs. features
- Include evergreen content for stability

### 4. Monitoring
- Review package distribution reports
- Check for underperforming content
- Adjust replay delays if needed

## Common Issues and Solutions

### "Same packages playing too often"
**Causes**: Limited inventory, short replay delays
**Solution**: Add more packages, increase replay delay to 4-6 hours

### "Packages clustered in schedule"
**Causes**: Rotation timing, gap patterns
**Solution**: Adjust rotation order, review gap distribution

### "Important packages not airing"
**Causes**: Not featured, poor scoring
**Solution**: Mark as featured, check metadata quality

### "Package gaps during prime time"  
**Causes**: Insufficient prime-appropriate content
**Solution**: Tag packages with timeslot preferences, increase inventory

## Advantages Over Standard Selection

### Enhanced Rotation Benefits
1. **33% More Airtime**: Two dedicated slots vs. competing in general pool
2. **Predictable Placement**: Regular rotation ensures consistent visibility
3. **Reduced Competition**: Not competing with all short_form content
4. **Strategic Distribution**: Spread throughout schedule, not clustered

### Quality Improvements
1. **Better Content Mix**: Packages break up other content types
2. **Viewer Engagement**: Regular feature content maintains interest
3. **Professional Appearance**: Produced packages enhance channel quality
4. **News Currency**: Fresh packages get priority placement

## Technical Implementation

### Database Schema
Packages stored in standard tables:
- `assets`: Core content data
- `scheduling_metadata`: Featured flags, play history
- Package identification via `content_type = 'PKG'`

### Selection Queries
Complex SQL leveraging:
- Window functions for play history
- CTEs for performance
- Multiple ordering criteria
- Slight randomization

### Logging and Debugging
- Detailed selection logs
- Score breakdowns available
- Rotation tracking
- Performance metrics

## Future Enhancements

### Under Consideration
1. **AI-Driven Placement**: Use engagement scores for optimal timing
2. **Series Intelligence**: Automatic episode ordering and spacing
3. **Dynamic Delays**: Adjust based on inventory levels
4. **Audience Analytics**: Place packages when viewership peaks

### Potential Improvements
1. **Sub-genre Rotation**: Rotate within package types
2. **Cross-Day Planning**: Ensure variety across multiple days
3. **Producer Preferences**: Allow producer-specified scheduling hints
4. **Breaking News Mode**: Emergency override for urgent packages

## Conclusion

The package selection system represents a sophisticated evolution in automated content scheduling. By providing **dedicated rotation slots**, the system ensures that produced content receives the visibility it deserves while maintaining the variety and pacing essential to quality broadcasting.

The combination of enhanced rotation, intelligent scoring, and strategic placement creates a system that serves both operational efficiency and viewer engagement, making packages a cornerstone of the ATL26 programming strategy.
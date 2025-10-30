"""
Schedule Replay Analysis Reports
"""

import logging
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import statistics
import numpy as np
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class ScheduleReplayAnalysisReport:
    """Generate detailed replay analysis reports with visualizations"""
    
    def __init__(self, db_manager):
        self.db = db_manager
    
    def generate_diversity_dashboard(self, schedule_id: int, include_expired: bool = False) -> Dict[str, Any]:
        """Generate diversity dashboard with option to include expired content"""
        # Get schedule and items
        schedule = self._get_schedule(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")
        
        items = self._get_scheduled_items(schedule_id)
        
        # Generate diversity dashboard with include_expired flag
        return self._generate_content_diversity_dashboard(schedule, items, include_expired)
    
    def generate(self, schedule_id: int, report_type: str, day_filter: Optional[int] = None) -> Dict[str, Any]:
        """Generate specific replay analysis report"""
        # Get schedule and items
        schedule = self._get_schedule(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")
        
        items = self._get_scheduled_items(schedule_id)
        
        # Filter by day if specified (for weekly schedules)
        if day_filter is not None:
            filtered_items = []
            for item in items:
                # Check metadata first for weekly schedules
                metadata = item.get('metadata', {})
                if isinstance(metadata, str):
                    try:
                        import json
                        metadata = json.loads(metadata)
                    except:
                        metadata = {}
                
                # Use metadata day_offset if available, otherwise calculate from time
                if metadata and 'day_offset' in metadata:
                    item_day = metadata['day_offset']
                else:
                    start_seconds = item.get('start_seconds', 0)
                    item_day = int(start_seconds // 86400)
                
                if item_day == day_filter:
                    filtered_items.append(item)
            items = filtered_items
            
            # Add day info to schedule
            schedule['filtered_day'] = day_filter
            day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            schedule['filtered_day_name'] = day_names[day_filter % 7]
        
        # Generate report based on type
        if report_type == 'content-replay-distribution':
            return self._generate_replay_distribution(schedule, items)
        elif report_type == 'replay-heatmap':
            return self._generate_replay_heatmap(schedule, items)
        elif report_type == 'replay-frequency-boxplot':
            return self._generate_replay_frequency_boxplot(schedule, items)
        elif report_type == 'content-freshness':
            return self._generate_content_freshness(schedule, items)
        elif report_type == 'pareto-chart':
            return self._generate_pareto_chart(schedule, items)
        elif report_type == 'replay-gaps':
            return self._generate_replay_gaps(schedule, items)
        elif report_type == 'comprehensive-analysis':
            return self._generate_comprehensive_analysis(schedule, items)
        elif report_type == 'content-diversity-dashboard':
            return self._generate_content_diversity_dashboard(schedule, items)
        else:
            raise ValueError(f"Unknown report type: {report_type}")
    
    def _get_schedule(self, schedule_id: int) -> Optional[Dict]:
        """Get schedule details from database"""
        conn = self.db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id, 
                    schedule_name as name, 
                    air_date, 
                    channel as schedule_type,
                    total_duration_seconds as total_duration, 
                    created_date as created_at
                FROM schedules
                WHERE id = %s
            """, (schedule_id,))
            
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
            
        finally:
            cursor.close()
            self.db._put_connection(conn)
    
    def _get_scheduled_items(self, schedule_id: int) -> List[Dict]:
        """Get all items in the schedule with full details"""
        conn = self.db._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    si.*,
                    a.content_type,
                    a.content_title,
                    a.duration_category,
                    a.theme,
                    a.engagement_score,
                    i.encoded_date
                FROM scheduled_items si
                LEFT JOIN assets a ON si.asset_id = a.id
                LEFT JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                WHERE si.schedule_id = %s
                ORDER BY si.scheduled_start_time
            """, (schedule_id,))
            
            items = []
            for row in cursor.fetchall():
                item = dict(row)
                # Convert timedelta to seconds for JSON serialization
                if 'scheduled_start_time' in item and hasattr(item['scheduled_start_time'], 'total_seconds'):
                    item['start_seconds'] = item['scheduled_start_time'].total_seconds()
                    item['scheduled_start_time'] = str(item['scheduled_start_time'])
                items.append(item)
            
            return items
            
        finally:
            cursor.close()
            self.db._put_connection(conn)
    
    def _generate_replay_distribution(self, schedule: Dict, items: List[Dict]) -> Dict[str, Any]:
        """Generate content replay distribution (bell curve) data"""
        # Check if this is a weekly schedule
        schedule_name = schedule.get('name', '').lower()
        is_weekly = 'weekly' in schedule_name or '[weekly]' in schedule_name
        
        # Count replays by content and category
        replay_counts_by_category = defaultdict(lambda: defaultdict(int))
        
        # For ALL schedules, count total plays
        # (Weekly schedules may be compressed into one day during import)
        for item in items:
            if item.get('asset_id'):
                category = item.get('duration_category', 'unknown')
                replay_counts_by_category[category][item['asset_id']] += 1
        
        # Create distribution data for each category
        distributions = {}
        for category, content_counts in replay_counts_by_category.items():
            counts = list(content_counts.values())
            if counts:
                # Create histogram data
                max_count = max(counts)
                distribution = []
                for i in range(1, max_count + 1):
                    distribution.append({
                        'replay_count': i,
                        'content_count': sum(1 for c in counts if c == i)
                    })
                
                distributions[category] = {
                    'data': distribution,
                    'stats': {
                        'mean': statistics.mean(counts),
                        'median': statistics.median(counts),
                        'std_dev': statistics.stdev(counts) if len(counts) > 1 else 0,
                        'total_content': len(counts)
                    }
                }
        
        # Add explanation for weekly schedules
        explanation = None
        if is_weekly:
            explanation = "This weekly schedule contains 7 days of content. The chart shows how many times each unique content item is played across the entire week."
        
        return {
            'schedule': self._schedule_summary(schedule),
            'distributions': distributions,
            'chart_type': 'line',
            'x_axis': 'Number of Plays',
            'y_axis': 'Number of Unique Content Items',
            'explanation': explanation,
            'is_weekly': is_weekly
        }
    
    def _generate_replay_heatmap(self, schedule: Dict, items: List[Dict]) -> Dict[str, Any]:
        """Generate replay timeline heatmap data"""
        # Check if this is a weekly schedule
        schedule_name = schedule.get('name', '').lower()
        is_weekly = 'weekly' in schedule_name or '[weekly]' in schedule_name
        
        # Create hourly buckets
        hourly_content = defaultdict(lambda: defaultdict(int))
        content_info = {}
        
        for item in items:
            if item.get('asset_id'):
                # For weekly schedules, use metadata to reconstruct actual hour
                if is_weekly:
                    metadata = item.get('metadata', {})
                    if isinstance(metadata, str):
                        try:
                            import json
                            metadata = json.loads(metadata)
                        except:
                            metadata = {}
                    
                    day_offset = metadata.get('day_offset', 0)
                    
                    # Get the scheduled_start_time which contains the time portion
                    scheduled_time = item.get('scheduled_start_time')
                    if scheduled_time:
                        # Extract hours, minutes, seconds from the time
                        import datetime
                        if isinstance(scheduled_time, str):
                            # Parse time string like "00:10:42.308000"
                            time_parts = scheduled_time.split(':')
                            hours = int(time_parts[0])
                            minutes = int(time_parts[1]) if len(time_parts) > 1 else 0
                            seconds = float(time_parts[2]) if len(time_parts) > 2 else 0
                            hour_in_day = hours
                        else:
                            # If it's a datetime/time object
                            hour_in_day = scheduled_time.hour
                    else:
                        # Fallback to start_seconds if no scheduled_start_time
                        start_seconds = item.get('start_seconds', 0)
                        hour_in_day = int(start_seconds // 3600)
                    
                    # Calculate the actual hour in the week
                    hour = day_offset * 24 + hour_in_day
                else:
                    # For daily schedules, use normal calculation
                    start_seconds = item.get('start_seconds', 0)
                    hour = int(start_seconds // 3600)
                
                asset_id = item['asset_id']
                hourly_content[hour][asset_id] += 1
                
                if asset_id not in content_info:
                    content_info[asset_id] = {
                        'title': item.get('content_title', 'Unknown'),
                        'type': item.get('content_type', 'unknown'),
                        'category': item.get('duration_category', 'unknown')
                    }
        
        # Create heatmap data
        heatmap_data = []
        all_content = set()
        for hour, content_counts in hourly_content.items():
            all_content.update(content_counts.keys())
        
        # Sort content by total play count
        content_totals = defaultdict(int)
        for hour_counts in hourly_content.values():
            for asset_id, count in hour_counts.items():
                content_totals[asset_id] += count
        
        sorted_content = sorted(all_content, key=lambda x: content_totals[x], reverse=True)
        
        # Build heatmap matrix
        max_hours = 168 if is_weekly else 24  # 7 days * 24 hours for weekly
        
        for i, asset_id in enumerate(sorted_content[:50]):  # Top 50 content items
            for hour in range(max_hours):
                count = hourly_content[hour].get(asset_id, 0)
                if count > 0:
                    heatmap_data.append({
                        'hour': hour,
                        'content_index': i,
                        'content_id': asset_id,
                        'content_title': content_info[asset_id]['title'],
                        'play_count': count
                    })
        
        # Add metadata about schedule type
        x_axis_label = 'Hour of Week' if is_weekly else 'Hour of Day'
        
        return {
            'schedule': self._schedule_summary(schedule),
            'heatmap_data': heatmap_data,
            'content_info': {i: content_info[aid] for i, aid in enumerate(sorted_content[:50])},
            'chart_type': 'heatmap',
            'x_axis': x_axis_label,
            'y_axis': 'Content (sorted by total plays)',
            'max_plays': max((d['play_count'] for d in heatmap_data), default=0),
            'is_weekly': is_weekly,
            'max_hours': max_hours
        }
    
    def _generate_replay_frequency_boxplot(self, schedule: Dict, items: List[Dict]) -> Dict[str, Any]:
        """Generate replay frequency box plot data by duration category"""
        # Count replays by content and category
        replay_counts_by_category = defaultdict(lambda: defaultdict(int))
        
        for item in items:
            if item.get('asset_id'):
                category = item.get('duration_category', 'unknown')
                replay_counts_by_category[category][item['asset_id']] += 1
        
        # Calculate box plot statistics for each category
        boxplot_data = []
        for category in ['id', 'spots', 'short_form', 'long_form']:
            counts = list(replay_counts_by_category[category].values())
            if counts:
                # Calculate quartiles
                sorted_counts = sorted(counts)
                n = len(sorted_counts)
                
                q1_idx = n // 4
                q2_idx = n // 2
                q3_idx = 3 * n // 4
                
                q1 = sorted_counts[q1_idx]
                q2 = sorted_counts[q2_idx]  # median
                q3 = sorted_counts[q3_idx]
                
                # Calculate IQR and outlier bounds
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                
                # Find outliers
                outliers = [c for c in counts if c < lower_bound or c > upper_bound]
                
                boxplot_data.append({
                    'category': category.upper(),
                    'min': min(counts),
                    'q1': q1,
                    'median': q2,
                    'q3': q3,
                    'max': max(counts),
                    'outliers': outliers,
                    'mean': statistics.mean(counts),
                    'count': len(counts)
                })
        
        return {
            'schedule': self._schedule_summary(schedule),
            'boxplot_data': boxplot_data,
            'chart_type': 'boxplot',
            'x_axis': 'Duration Category',
            'y_axis': 'Number of Replays'
        }
    
    def _generate_content_freshness(self, schedule: Dict, items: List[Dict]) -> Dict[str, Any]:
        """Generate content freshness dashboard data"""
        # Count replays and categorize content
        content_plays = defaultdict(int)
        content_by_type = defaultdict(list)
        
        for item in items:
            if item.get('asset_id'):
                asset_id = item['asset_id']
                content_plays[asset_id] += 1
                content_by_type[item.get('content_type', 'unknown')].append(asset_id)
        
        # Calculate freshness metrics
        total_slots = len([i for i in items if i.get('asset_id')])
        fresh_plays = sum(1 for i in items if i.get('asset_id') and content_plays[i['asset_id']] == 1)
        unique_content = len(content_plays)
        
        # Categorize by replay count
        replay_categories = {
            'fresh': sum(1 for count in content_plays.values() if count == 1),
            '2-3_plays': sum(1 for count in content_plays.values() if 2 <= count <= 3),
            '4-5_plays': sum(1 for count in content_plays.values() if 4 <= count <= 5),
            '6+_plays': sum(1 for count in content_plays.values() if count >= 6)
        }
        
        # Calculate average replays by content type
        type_stats = {}
        for content_type, asset_ids in content_by_type.items():
            type_plays = [content_plays[aid] for aid in asset_ids]
            if type_plays:
                type_stats[content_type] = {
                    'average_replays': statistics.mean(type_plays),
                    'max_replays': max(type_plays),
                    'unique_content': len(set(asset_ids))
                }
        
        # Find most replayed content
        most_replayed = []
        for asset_id, count in sorted(content_plays.items(), key=lambda x: x[1], reverse=True)[:5]:
            # Find content details
            for item in items:
                if item.get('asset_id') == asset_id:
                    most_replayed.append({
                        'title': item.get('content_title', 'Unknown'),
                        'type': item.get('content_type', 'unknown'),
                        'play_count': count
                    })
                    break
        
        return {
            'schedule': self._schedule_summary(schedule),
            'metrics': {
                'total_slots': total_slots,
                'unique_content': unique_content,
                'fresh_content_percentage': (fresh_plays / total_slots * 100) if total_slots > 0 else 0,
                'content_diversity_index': (unique_content / total_slots) if total_slots > 0 else 0
            },
            'replay_categories': replay_categories,
            'type_statistics': type_stats,
            'most_replayed': most_replayed,
            'chart_type': 'dashboard'
        }
    
    def _generate_pareto_chart(self, schedule: Dict, items: List[Dict]) -> Dict[str, Any]:
        """Generate Pareto chart data for most replayed content"""
        # Count plays by content
        content_plays = defaultdict(int)
        content_info = {}
        
        for item in items:
            if item.get('asset_id'):
                asset_id = item['asset_id']
                content_plays[asset_id] += 1
                
                if asset_id not in content_info:
                    content_info[asset_id] = {
                        'title': item.get('content_title', 'Unknown'),
                        'type': item.get('content_type', 'unknown'),
                        'category': item.get('duration_category', 'unknown')
                    }
        
        # Sort by play count
        sorted_content = sorted(content_plays.items(), key=lambda x: x[1], reverse=True)
        
        # Calculate cumulative percentage
        total_plays = sum(content_plays.values())
        pareto_data = []
        cumulative_plays = 0
        
        for i, (asset_id, count) in enumerate(sorted_content[:20]):  # Top 20
            cumulative_plays += count
            pareto_data.append({
                'rank': i + 1,
                'asset_id': asset_id,
                'title': content_info[asset_id]['title'],
                'type': content_info[asset_id]['type'],
                'category': content_info[asset_id]['category'],
                'play_count': count,
                'percentage': (count / total_plays * 100) if total_plays > 0 else 0,
                'cumulative_percentage': (cumulative_plays / total_plays * 100) if total_plays > 0 else 0
            })
        
        # Calculate 80/20 insight
        eighty_percent_plays = total_plays * 0.8
        content_for_80_percent = 0
        cumulative = 0
        for asset_id, count in sorted_content:
            cumulative += count
            content_for_80_percent += 1
            if cumulative >= eighty_percent_plays:
                break
        
        return {
            'schedule': self._schedule_summary(schedule),
            'pareto_data': pareto_data,
            'insights': {
                'total_unique_content': len(content_plays),
                'total_plays': total_plays,
                'content_for_80_percent': content_for_80_percent,
                'percentage_of_content_for_80_percent': (content_for_80_percent / len(content_plays) * 100) if len(content_plays) > 0 else 0
            },
            'chart_type': 'pareto',
            'primary_axis': 'Play Count',
            'secondary_axis': 'Cumulative Percentage'
        }
    
    def _generate_replay_gaps(self, schedule: Dict, items: List[Dict]) -> Dict[str, Any]:
        """Generate time-between-replays distribution data"""
        # Track play times for each content
        content_play_times = defaultdict(list)
        
        for item in items:
            if item.get('asset_id'):
                content_play_times[item['asset_id']].append(item.get('start_seconds', 0))
        
        # Calculate gaps
        all_gaps = []
        gaps_by_category = defaultdict(list)
        
        for asset_id, play_times in content_play_times.items():
            if len(play_times) > 1:
                sorted_times = sorted(play_times)
                for i in range(1, len(sorted_times)):
                    gap_seconds = sorted_times[i] - sorted_times[i-1]
                    all_gaps.append(gap_seconds)
                    
                    # Find category for this content
                    for item in items:
                        if item.get('asset_id') == asset_id:
                            category = item.get('duration_category', 'unknown')
                            gaps_by_category[category].append(gap_seconds)
                            break
        
        # Create histogram bins
        if all_gaps:
            # Define bins (in minutes)
            bins = [0, 5, 15, 30, 60, 120, 240, 480, 720, 1440]  # up to 24 hours
            bin_labels = ['0-5m', '5-15m', '15-30m', '30m-1h', '1-2h', '2-4h', '4-8h', '8-12h', '12-24h', '24h+']
            
            histogram_data = []
            for i in range(len(bins) - 1):
                count = sum(1 for gap in all_gaps if bins[i] * 60 <= gap < bins[i+1] * 60)
                histogram_data.append({
                    'bin': bin_labels[i],
                    'count': count,
                    'min_seconds': bins[i] * 60,
                    'max_seconds': bins[i+1] * 60
                })
            
            # Add 24h+ bin
            count_24h_plus = sum(1 for gap in all_gaps if gap >= 1440 * 60)
            histogram_data.append({
                'bin': '24h+',
                'count': count_24h_plus,
                'min_seconds': 1440 * 60,
                'max_seconds': float('inf')
            })
            
            # Calculate violations (gaps less than recommended)
            violations = {
                'under_5min': sum(1 for gap in all_gaps if gap < 300),
                'under_15min': sum(1 for gap in all_gaps if gap < 900),
                'under_30min': sum(1 for gap in all_gaps if gap < 1800)
            }
        else:
            histogram_data = []
            violations = {'under_5min': 0, 'under_15min': 0, 'under_30min': 0}
        
        return {
            'schedule': self._schedule_summary(schedule),
            'histogram_data': histogram_data,
            'statistics': {
                'total_gaps': len(all_gaps),
                'average_gap_minutes': (statistics.mean(all_gaps) / 60) if all_gaps else 0,
                'median_gap_minutes': (statistics.median(all_gaps) / 60) if all_gaps else 0,
                'min_gap_minutes': (min(all_gaps) / 60) if all_gaps else 0,
                'max_gap_minutes': (max(all_gaps) / 60) if all_gaps else 0
            },
            'violations': violations,
            'category_stats': {
                cat: {
                    'average_gap_minutes': (statistics.mean(gaps) / 60) if gaps else 0,
                    'gap_count': len(gaps)
                }
                for cat, gaps in gaps_by_category.items()
            },
            'chart_type': 'histogram',
            'x_axis': 'Time Between Replays',
            'y_axis': 'Number of Occurrences'
        }
    
    def _generate_comprehensive_analysis(self, schedule: Dict, items: List[Dict]) -> Dict[str, Any]:
        """Generate comprehensive analysis combining all reports"""
        # Generate all sub-reports
        replay_dist = self._generate_replay_distribution(schedule, items)
        freshness = self._generate_content_freshness(schedule, items)
        pareto = self._generate_pareto_chart(schedule, items)
        gaps = self._generate_replay_gaps(schedule, items)
        
        # Add schedule health score
        health_score = self._calculate_schedule_health_score(items, freshness, gaps)
        
        return {
            'schedule': self._schedule_summary(schedule),
            'health_score': health_score,
            'replay_distribution': replay_dist['distributions'],
            'freshness_metrics': freshness['metrics'],
            'top_replayed': pareto['pareto_data'][:10],
            'gap_statistics': gaps['statistics'],
            'recommendations': self._generate_recommendations(health_score, freshness, gaps),
            'chart_type': 'comprehensive'
        }
    
    def _schedule_summary(self, schedule: Dict) -> Dict[str, Any]:
        """Create schedule summary for reports"""
        return {
            'id': schedule['id'],
            'name': schedule['name'],
            'air_date': schedule['air_date'].isoformat() if hasattr(schedule['air_date'], 'isoformat') else str(schedule['air_date']),
            'type': schedule.get('schedule_type', 'unknown')
        }
    
    def _calculate_schedule_health_score(self, items: List[Dict], freshness: Dict, gaps: Dict) -> Dict[str, Any]:
        """Calculate overall schedule health score"""
        scores = {
            'diversity': min(freshness['metrics']['content_diversity_index'] * 100, 100),
            'freshness': freshness['metrics']['fresh_content_percentage'],
            'spacing': 100 - (gaps['violations']['under_30min'] / max(gaps['statistics']['total_gaps'], 1) * 100),
            'balance': self._calculate_balance_score(items)
        }
        
        # Weighted average
        weights = {'diversity': 0.3, 'freshness': 0.3, 'spacing': 0.2, 'balance': 0.2}
        overall = sum(scores[k] * weights[k] for k in scores)
        
        return {
            'overall': round(overall, 1),
            'components': scores,
            'grade': 'A' if overall >= 90 else 'B' if overall >= 80 else 'C' if overall >= 70 else 'D' if overall >= 60 else 'F'
        }
    
    def _calculate_balance_score(self, items: List[Dict]) -> float:
        """Calculate how well balanced the content categories are"""
        category_counts = defaultdict(int)
        total = 0
        
        for item in items:
            if item.get('duration_category'):
                category_counts[item['duration_category']] += 1
                total += 1
        
        if total == 0:
            return 0
        
        # Calculate entropy as a measure of balance
        entropy = 0
        for count in category_counts.values():
            if count > 0:
                p = count / total
                entropy -= p * np.log2(p)
        
        # Normalize to 0-100 scale (max entropy for 4 categories is 2)
        max_entropy = 2
        return min(entropy / max_entropy * 100, 100)
    
    def _generate_recommendations(self, health_score: Dict, freshness: Dict, gaps: Dict) -> List[str]:
        """Generate recommendations based on analysis"""
        recommendations = []
        
        if health_score['overall'] < 70:
            recommendations.append("Schedule health is below optimal. Consider the following improvements:")
        
        if health_score['components']['diversity'] < 70:
            recommendations.append("• Increase content variety - too much repetition detected")
        
        if health_score['components']['freshness'] < 60:
            recommendations.append("• Add more unique content to reduce repetitive scheduling")
        
        if gaps['violations']['under_30min'] > gaps['statistics']['total_gaps'] * 0.2:
            recommendations.append("• Increase spacing between content replays (20%+ violations detected)")
        
        if health_score['components']['balance'] < 70:
            recommendations.append("• Better balance content across duration categories")
        
        if not recommendations:
            recommendations.append("Schedule is well-optimized with good content rotation!")
        
        return recommendations
    
    def _generate_content_diversity_dashboard(self, schedule: Dict, items: List[Dict], include_expired: bool = False) -> Dict[str, Any]:
        """Generate content diversity dashboard showing available vs used content"""
        from collections import defaultdict
        import datetime
        
        # Get schedule date range
        schedule_date = schedule.get('air_date')
        
        # Get all available content from the assets table
        conn = self.db._get_connection()
        try:
            from psycopg2.extras import RealDictCursor
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Debug: Check table structure and data
            logger.info(f"Checking assets for schedule date: {schedule_date}")
            
            # First, get total count without any filters
            cursor.execute("SELECT COUNT(*) as total_count FROM assets")
            total_all = cursor.fetchone()
            logger.info(f"Total assets in database (no filter): {total_all['total_count']}")
            
            # Check analysis_completed assets
            cursor.execute("SELECT COUNT(*) as total_count FROM assets WHERE analysis_completed = TRUE")
            total_active = cursor.fetchone()
            logger.info(f"Total analyzed assets: {total_active['total_count']}")
            
            # Check if we're in the wrong schema/database
            cursor.execute("SELECT current_database(), current_schema()")
            db_info = cursor.fetchone()
            logger.info(f"Current database: {db_info['current_database']}, schema: {db_info['current_schema']}")
            
            # Get all available content using same criteria as Schedule Analysis Report
            # Join with instances table to get primary file paths
            if include_expired:
                # Include all content regardless of expiry date
                cursor.execute("""
                    SELECT 
                        a.id as asset_id,
                        i.file_path as content_title,
                        a.duration_category,
                        a.content_type,
                        a.created_at as created_date,
                        a.updated_at as last_updated,
                        sm.content_expiry_date as expiration_date,
                        CASE 
                            WHEN sm.content_expiry_date IS NOT NULL AND sm.content_expiry_date < %s::date 
                            THEN TRUE 
                            ELSE FALSE 
                        END as is_expired
                    FROM assets a
                    JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                    WHERE a.analysis_completed = TRUE
                        AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
                        AND i.file_path NOT LIKE 'FILL%%'
                    ORDER BY a.duration_category, i.file_path
                """, (schedule_date,))
            else:
                # Exclude expired content (original behavior)
                cursor.execute("""
                    SELECT 
                        a.id as asset_id,
                        i.file_path as content_title,
                        a.duration_category,
                        a.content_type,
                        a.created_at as created_date,
                        a.updated_at as last_updated,
                        sm.content_expiry_date as expiration_date,
                        FALSE as is_expired
                    FROM assets a
                    JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
                    LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
                    WHERE a.analysis_completed = TRUE
                        AND COALESCE(sm.available_for_scheduling, TRUE) = TRUE
                        AND COALESCE(sm.content_expiry_date, %s::date + INTERVAL '1 year') > %s::date
                        AND i.file_path NOT LIKE 'FILL%%'
                    ORDER BY a.duration_category, i.file_path
                """, (schedule_date, schedule_date))
            
            all_assets = cursor.fetchall()
            cursor.close()
            logger.info(f"Query returned {len(all_assets)} available assets")
            
            # Log sample of what we got
            if all_assets:
                logger.info(f"Sample asset: ID={all_assets[0]['asset_id']}, Title={all_assets[0]['content_title'][:30]}")
        except Exception as e:
            logger.error(f"Error fetching available assets: {e}")
            all_assets = []
        finally:
            conn.commit()
        
        # Build usage tracking
        used_assets = set()
        usage_by_category = defaultdict(lambda: {'available': set(), 'used': set()})
        usage_by_type = defaultdict(lambda: {'available': set(), 'used': set()})
        asset_play_counts = defaultdict(int)
        
        # Track what was actually used in the schedule
        for item in items:
            if item.get('asset_id'):
                asset_id = item['asset_id']
                used_assets.add(asset_id)
                asset_play_counts[asset_id] += 1
                
                category = item.get('duration_category', 'unknown')
                content_type = item.get('content_type', 'unknown')
                usage_by_category[category]['used'].add(asset_id)
                usage_by_type[content_type]['used'].add(asset_id)
        
        # Track what was available
        for asset in all_assets:
            asset_id = asset['asset_id']
            category = asset.get('duration_category', 'unknown')
            content_type = asset.get('content_type', 'unknown')
            usage_by_category[category]['available'].add(asset_id)
            usage_by_type[content_type]['available'].add(asset_id)
        
        # Calculate usage rates
        category_usage_rates = {}
        for category, data in usage_by_category.items():
            available_count = len(data['available'])
            used_count = len(data['used'])
            category_usage_rates[category] = {
                'available': available_count,
                'used': used_count,
                'usage_rate': (used_count / available_count * 100) if available_count > 0 else 0,
                'unused': available_count - used_count
            }
        
        type_usage_rates = {}
        for content_type, data in usage_by_type.items():
            available_count = len(data['available'])
            used_count = len(data['used'])
            type_usage_rates[content_type] = {
                'available': available_count,
                'used': used_count,
                'usage_rate': (used_count / available_count * 100) if available_count > 0 else 0,
                'unused': available_count - used_count
            }
        
        # Find underutilized content (available but never or rarely used)
        underutilized = []
        never_used = []
        
        for asset in all_assets:
            asset_id = asset['asset_id']
            play_count = asset_play_counts.get(asset_id, 0)
            
            asset_info = {
                'asset_id': asset_id,
                'title': asset['content_title'],
                'category': asset['duration_category'],
                'type': asset['content_type'],
                'created_date': asset['created_date'].isoformat() if asset['created_date'] else None,
                'days_in_library': (schedule_date - asset['created_date'].date()).days if asset['created_date'] and schedule_date else 999,
                'play_count': play_count
            }
            
            if play_count == 0:
                never_used.append(asset_info)
            elif play_count <= 2:  # Arbitrary threshold for "underutilized"
                underutilized.append(asset_info)
        
        # Sort by days in library (oldest first)
        never_used.sort(key=lambda x: x['days_in_library'], reverse=True)
        underutilized.sort(key=lambda x: x['play_count'])
        
        # Calculate overall metrics
        total_available = len(all_assets)
        total_used = len(used_assets)
        overall_usage_rate = (total_used / total_available * 100) if total_available > 0 else 0
        
        # Count expired content if including expired
        expired_count = 0
        if include_expired:
            expired_count = sum(1 for asset in all_assets if asset.get('is_expired', False))
        
        # Generate insights
        insights = []
        
        # Find categories with worst usage rates
        worst_categories = sorted(
            [(cat, data) for cat, data in category_usage_rates.items() if data['available'] > 0],
            key=lambda x: x[1]['usage_rate']
        )[:3]
        
        for category, data in worst_categories:
            if data['usage_rate'] < 50:
                insights.append(f"{category.upper()} content is underutilized - only {data['usage_rate']:.1f}% used ({data['used']}/{data['available']} items)")
        
        if len(never_used) > 10:
            insights.append(f"{len(never_used)} content items have NEVER been used in this schedule")
        
        if overall_usage_rate < 30:
            insights.append(f"Only {overall_usage_rate:.1f}% of available content library is being utilized")
        
        # Find content that's been in library longest without use
        if never_used:
            # Find first item with valid days_in_library
            for unused in never_used:
                if unused['days_in_library'] < 999 and unused['days_in_library'] > 30:
                    insights.append(f"'{unused['title']}' has been in library for {unused['days_in_library']} days without being scheduled")
                    break
        
        return {
            'schedule': self._schedule_summary(schedule),
            'overall_metrics': {
                'total_available': total_available,
                'total_used': total_used,
                'usage_rate': overall_usage_rate,
                'diversity_score': total_used / len(items) * 100 if len(items) > 0 else 0,
                'include_expired': include_expired,
                'expired_count': expired_count,
                'active_count': total_available - expired_count
            },
            'category_usage': category_usage_rates,
            'type_usage': type_usage_rates,
            'never_used': never_used[:20],  # Top 20 never used
            'underutilized': underutilized[:20],  # Top 20 underutilized
            'insights': insights,
            'chart_type': 'diversity-dashboard'
        }
#!/usr/bin/env python3
"""
Test Harness for Holiday Greeting Fair Rotation System
This script tests the rotation algorithm without affecting production data
"""

import sys
import random
from datetime import datetime, timedelta
from collections import defaultdict
from holiday_greeting_scheduler import HolidayGreetingScheduler

# Test data - simulating the 27 holiday greetings mentioned
TEST_HOLIDAY_GREETINGS = [
    {"asset_id": 1, "file_name": "251210_SSP_Strategy Office Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 2, "file_name": "251210_SSP_Watershed Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 3, "file_name": "251210_SSP_ParksRec Holiday Greetings_24_v1.mp4", "duration_category": "spots"},
    {"asset_id": 4, "file_name": "251210_SSP_HR Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 5, "file_name": "251209_SPP_Mayor Holiday Greeting.mp4", "duration_category": "id"},
    {"asset_id": 6, "file_name": "251210_SSP_APD Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 7, "file_name": "251210_SSP_ACRB Holiday Greetings_16_v1.mp4", "duration_category": "spots"},
    {"asset_id": 8, "file_name": "251210_SSP_ATL Housing Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 9, "file_name": "251210_SSP_ATLDOT Holiday Greetings_15_v1.mp4", "duration_category": "spots"},
    {"asset_id": 10, "file_name": "251210_SSP_COO Burks Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 11, "file_name": "251210_SSP_DPW Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 12, "file_name": "251210_SSP_EXE Holiday Greetings_6_v1.mp4", "duration_category": "spots"},
    {"asset_id": 13, "file_name": "251210_SSP_Violence Reduction Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 14, "file_name": "251210_SSP_City Council Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 15, "file_name": "251210_SSP_Fire Rescue Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 16, "file_name": "251210_SSP_Legal Affairs Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 17, "file_name": "251210_SSP_Innovation Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 18, "file_name": "251210_SSP_Procurement Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 19, "file_name": "251210_SSP_Finance Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 20, "file_name": "251210_SSP_Aviation Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 21, "file_name": "251210_SSP_Planning Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 22, "file_name": "251210_SSP_Corrections Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 23, "file_name": "251210_SSP_Ethics Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 24, "file_name": "251210_SSP_Solicitor Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 25, "file_name": "251210_SSP_Youth Affairs Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 26, "file_name": "251210_SSP_Senior Affairs Holiday Greeting.mp4", "duration_category": "spots"},
    {"asset_id": 27, "file_name": "251210_SSP_Sustainability Holiday Greeting.mp4", "duration_category": "spots"},
]


class TestScheduler:
    """Test harness for the holiday greeting scheduler"""
    
    def __init__(self):
        # Create scheduler with test config
        config = {
            'enabled': True,  # Enable for testing
            'min_time_between_plays': {'hours': 2},
            'max_plays_per_day': 3,
            'fair_rotation_weight': 0.9,
            'date_range': {
                'start': '2025-12-01',
                'end': '2026-01-15'
            },
            'priority_boost_unplayed': 1000,
            'replay_delay_minutes': 120
        }
        self.scheduler = HolidayGreetingScheduler(config=config)
        self.test_greetings = TEST_HOLIDAY_GREETINGS.copy()
        
    def simulate_fair_selection(self, num_selections=100):
        """Simulate fair selection algorithm"""
        print(f"\n=== Simulating {num_selections} Fair Selections ===\n")
        
        selection_count = defaultdict(int)
        excluded_recently = set()  # Simulate replay delay
        
        for i in range(num_selections):
            # Get priorities for all greetings not recently played
            candidates = []
            for greeting in self.test_greetings:
                if greeting['asset_id'] not in excluded_recently:
                    priority = self.scheduler.get_scheduling_priority(
                        greeting['asset_id'], 
                        greeting['file_name']
                    )
                    candidates.append((greeting, priority))
            
            if not candidates:
                # All have been played recently, clear exclusions
                excluded_recently.clear()
                continue
            
            # Sort by priority (highest first)
            candidates.sort(key=lambda x: x[1], reverse=True)
            
            # Select based on fair rotation weight
            if random.random() < self.scheduler.config['fair_rotation_weight']:
                # Fair selection - pick highest priority
                selected = candidates[0][0]
            else:
                # Random selection from top 5
                top_candidates = candidates[:5]
                selected = random.choice(top_candidates)[0]
            
            # Record the selection
            self.scheduler.record_scheduling(selected['asset_id'], selected['file_name'])
            selection_count[selected['file_name']] += 1
            
            # Simulate replay delay (2 hours = skip next 8 selections)
            excluded_recently.add(selected['asset_id'])
            if len(excluded_recently) > 8:
                # Remove oldest exclusion
                excluded_recently.pop()
        
        # Print results
        print("Selection Distribution:")
        print("-" * 60)
        for filename, count in sorted(selection_count.items(), key=lambda x: x[1], reverse=True):
            short_name = filename.replace("251210_SSP_", "").replace("251209_SPP_", "").replace(".mp4", "")
            bar = "█" * count
            print(f"{short_name:30} {count:3d} {bar}")
        
        # Calculate statistics
        counts = list(selection_count.values())
        avg = sum(counts) / len(counts) if counts else 0
        min_count = min(counts) if counts else 0
        max_count = max(counts) if counts else 0
        
        print("\nStatistics:")
        print(f"Total greetings: {len(self.test_greetings)}")
        print(f"Greetings scheduled: {len(selection_count)}")
        print(f"Average plays: {avg:.1f}")
        print(f"Min plays: {min_count}")
        print(f"Max plays: {max_count}")
        print(f"Fairness ratio: {min_count/max_count:.2%}" if max_count > 0 else "N/A")
        
        return selection_count
    
    def simulate_current_behavior(self, num_selections=100):
        """Simulate current problematic behavior for comparison"""
        print(f"\n=== Simulating {num_selections} Current (Problematic) Selections ===\n")
        
        # Simulate the current behavior that over-schedules certain files
        problematic_weights = {
            "Strategy Office": 42,
            "Watershed": 29,
            "ParksRec": 17,
            "HR": 7,
            "Mayor": 7,
            "APD": 1
        }
        
        weighted_pool = []
        for greeting in self.test_greetings:
            for key, weight in problematic_weights.items():
                if key in greeting['file_name']:
                    weighted_pool.extend([greeting] * weight)
                    break
        
        selection_count = defaultdict(int)
        for i in range(num_selections):
            if weighted_pool:
                selected = random.choice(weighted_pool)
                selection_count[selected['file_name']] += 1
        
        # Print results
        print("Current Behavior Distribution:")
        print("-" * 60)
        for filename, count in sorted(selection_count.items(), key=lambda x: x[1], reverse=True):
            short_name = filename.replace("251210_SSP_", "").replace("251209_SPP_", "").replace(".mp4", "")
            bar = "█" * count
            print(f"{short_name:30} {count:3d} {bar}")
        
        unscheduled = len(self.test_greetings) - len(selection_count)
        print(f"\nUnscheduled greetings: {unscheduled} out of {len(self.test_greetings)}")
        
        return selection_count
    
    def test_priority_calculation(self):
        """Test priority calculation logic"""
        print("\n=== Testing Priority Calculation ===\n")
        
        # Test cases
        test_cases = [
            {"asset_id": 100, "name": "Never Played", "count": 0, "last": None},
            {"asset_id": 101, "name": "Played Once Yesterday", "count": 1, 
             "last": datetime.now() - timedelta(days=1)},
            {"asset_id": 102, "name": "Played 5 Times, Last Week", "count": 5, 
             "last": datetime.now() - timedelta(days=7)},
            {"asset_id": 103, "name": "Played 10 Times, 2 Hours Ago", "count": 10, 
             "last": datetime.now() - timedelta(hours=2)},
        ]
        
        for case in test_cases:
            # Set up history
            if case["count"] > 0:
                self.scheduler.rotation_history[case["asset_id"]] = {
                    'scheduled_count': case["count"],
                    'last_scheduled': case["last"]
                }
            
            priority = self.scheduler.get_scheduling_priority(case["asset_id"], "test.mp4")
            print(f"{case['name']:30} Priority: {priority:8.2f}")


def main():
    """Run the test harness"""
    print("Holiday Greeting Rotation Test Harness")
    print("=" * 70)
    
    tester = TestScheduler()
    
    # Test 1: Priority calculation
    tester.test_priority_calculation()
    
    # Test 2: Current problematic behavior
    current_dist = tester.simulate_current_behavior(103)  # Simulate actual schedule length
    
    # Test 3: Fair rotation behavior
    fair_dist = tester.simulate_fair_selection(103)
    
    # Compare
    print("\n=== COMPARISON ===")
    print("With fair rotation, all 27 greetings get scheduled vs only 6 currently")
    
    # Generate final report
    print("\n" + tester.scheduler.generate_rotation_report())


if __name__ == "__main__":
    main()
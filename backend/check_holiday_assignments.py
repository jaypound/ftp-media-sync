#!/usr/bin/env python3
"""Check holiday greetings daily assignments"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_postgres import PostgreSQLDatabaseManager
from datetime import datetime, timedelta

def check_holiday_assignments():
    """Check database for recent holiday assignments and schedules"""
    db = PostgreSQLDatabaseManager()
    db.connect()
    
    try:
        # 1. Query holiday_greetings_days table
        print("=== HOLIDAY GREETINGS DAYS (Recent 20) ===")
        query1 = """
            SELECT hgd.*, s.name as schedule_name
            FROM holiday_greetings_days hgd
            LEFT JOIN schedules s ON hgd.schedule_id = s.id
            ORDER BY hgd.schedule_day DESC
            LIMIT 20;
        """
        result1 = db.execute_query(query1)
        if result1:
            for row in result1:
                print(f"Day: {row['schedule_day']}, Schedule: {row['schedule_name']} (ID: {row['schedule_id']}), "
                      f"Package: {row['package_id']}, Created: {row.get('created_at', 'N/A')}")
        else:
            print("No rows found in holiday_greetings_days table")
        
        print("\n=== RECENT SCHEDULES (Last 30 minutes) ===")
        # 2. Check schedules created in last 30 minutes
        query2 = """
            SELECT id, name, created_at, schedule_type, start_date, end_date
            FROM schedules 
            WHERE created_at > NOW() - INTERVAL '30 minutes'
            ORDER BY created_at DESC;
        """
        result2 = db.execute_query(query2)
        if result2:
            for row in result2:
                print(f"ID: {row['id']}, Name: {row['name']}, Type: {row['schedule_type']}, "
                      f"Start: {row['start_date']}, End: {row['end_date']}, Created: {row['created_at']}")
        else:
            print("No schedules created in the last 30 minutes")
        
        print("\n=== ALL SCHEDULES (Last 24 hours) ===")
        # 3. Check schedules created in last 24 hours for broader view
        query3 = """
            SELECT id, name, created_at, schedule_type, start_date, end_date
            FROM schedules 
            WHERE created_at > NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 20;
        """
        result3 = db.execute_query(query3)
        if result3:
            for row in result3:
                print(f"ID: {row['id']}, Name: {row['name']}, Type: {row['schedule_type']}, "
                      f"Start: {row['start_date']}, End: {row['end_date']}, Created: {row['created_at']}")
        else:
            print("No schedules created in the last 24 hours")
        
        print("\n=== HOLIDAY GREETINGS DAYS COUNT BY SCHEDULE ===")
        # 4. Check count of assignments per schedule
        query4 = """
            SELECT s.id, s.name, s.created_at, COUNT(hgd.id) as assignment_count
            FROM schedules s
            LEFT JOIN holiday_greetings_days hgd ON s.id = hgd.schedule_id
            WHERE s.created_at > NOW() - INTERVAL '24 hours'
            GROUP BY s.id, s.name, s.created_at
            ORDER BY s.created_at DESC;
        """
        result4 = db.execute_query(query4)
        if result4:
            for row in result4:
                print(f"Schedule ID: {row['id']}, Name: {row['name']}, "
                      f"Assignments: {row['assignment_count']}, Created: {row['created_at']}")
        else:
            print("No schedule assignment counts found")
            
    except Exception as e:
        print(f"Error checking database: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.disconnect()

if __name__ == "__main__":
    check_holiday_assignments()
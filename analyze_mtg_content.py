#!/usr/bin/env python3
"""Analyze MTG content to recommend expiration dates"""

import os
import psycopg2
from datetime import datetime, timedelta

# Database connection
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://jay:macmini@localhost:5432/ftp_sync')

def analyze_mtg_content():
    """Analyze MTG content and recommend expiration dates"""
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Get all MTG content with file names
    cursor.execute('''
        SELECT 
            a.id,
            a.content_title,
            i.file_name,
            i.file_path,
            sm.content_expiry_date,
            CASE 
                WHEN i.file_name ~ '^[0-9]{6}_' THEN 
                    SUBSTRING(i.file_name FROM 1 FOR 6)
                ELSE NULL
            END as date_prefix
        FROM assets a
        JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
        LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
        WHERE a.content_type = 'mtg'
        AND i.file_name ~ '^[0-9]{6}_'  -- Only files with date prefix
        ORDER BY i.file_name
    ''')
    
    results = cursor.fetchall()
    print(f"Found {len(results)} MTG assets with date prefixes")
    print("="*100)
    
    # Group by month
    months = {}
    for asset_id, title, file_name, file_path, expiry_date, date_prefix in results:
        if date_prefix:
            year = '20' + date_prefix[:2]
            month = int(date_prefix[2:4])
            month_key = f"{year}-{month:02d}"
            
            if month_key not in months:
                months[month_key] = []
            
            months[month_key].append({
                'id': asset_id,
                'file_name': file_name,
                'title': title,
                'expiry_date': expiry_date,
                'date_prefix': date_prefix
            })
    
    # Print summary and recommendations
    print("\nCONTENT SUMMARY BY MONTH:")
    print("-" * 100)
    
    # Current date for reference
    now = datetime.now()
    jan_2025 = datetime(2025, 1, 1)
    jan_26_2025 = datetime(2025, 1, 26)
    
    for month_key in sorted(months.keys()):
        items = months[month_key]
        month_year = datetime.strptime(month_key + "-01", "%Y-%m-%d")
        print(f"\n{month_key}: {len(items)} meetings")
        
        # Sample items
        for item in items[:2]:
            expiry = item['expiry_date'].strftime('%Y-%m-%d') if item['expiry_date'] else 'Not set'
            print(f"  - {item['file_name'][:60]}... (Expires: {expiry})")
        if len(items) > 2:
            print(f"  ... and {len(items) - 2} more")
        
        # Recommendations based on management requirements
        year = int(month_key.split('-')[0])
        month = int(month_key.split('-')[1])
        
        if year == 2024:
            if month in [9, 10, 11]:  # September, October, November 2024
                print(f"  📌 RECOMMENDATION: Set expiration to 2024-12-31 (must not air in January 2025)")
            elif month == 12:  # December 2024
                print(f"  📌 RECOMMENDATION: Set expiration to 2025-01-25 (must not air after January 26, 2025)")
    
    # Generate SQL update statements
    print("\n" + "="*100)
    print("RECOMMENDED SQL UPDATE STATEMENTS:")
    print("-" * 100)
    
    # September, October, November 2024
    print("\n-- Update September, October, November 2024 meetings to expire by end of December 2024")
    print("UPDATE scheduling_metadata sm")
    print("SET content_expiry_date = '2024-12-31'::timestamp with time zone")
    print("FROM assets a")
    print("JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE")
    print("WHERE sm.asset_id = a.id")
    print("  AND a.content_type = 'mtg'")
    print("  AND i.file_name ~ '^(2409|2410|2411)[0-9]{2}_'")
    print("  AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > '2024-12-31');")
    
    # December 2024
    print("\n-- Update December 2024 meetings to expire by January 25, 2025")
    print("UPDATE scheduling_metadata sm")
    print("SET content_expiry_date = '2025-01-25'::timestamp with time zone")
    print("FROM assets a")
    print("JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE")
    print("WHERE sm.asset_id = a.id")
    print("  AND a.content_type = 'mtg'")
    print("  AND i.file_name ~ '^2412[0-9]{2}_'")
    print("  AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > '2025-01-25');")
    
    # Count affected items
    cursor.execute('''
        SELECT COUNT(DISTINCT a.id)
        FROM assets a
        JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
        LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
        WHERE a.content_type = 'mtg'
        AND i.file_name ~ '^(2409|2410|2411)[0-9]{2}_'
        AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > '2024-12-31')
    ''')
    sept_nov_count = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT COUNT(DISTINCT a.id)
        FROM assets a
        JOIN instances i ON a.id = i.asset_id AND i.is_primary = TRUE
        LEFT JOIN scheduling_metadata sm ON a.id = sm.asset_id
        WHERE a.content_type = 'mtg'
        AND i.file_name ~ '^2412[0-9]{2}_'
        AND (sm.content_expiry_date IS NULL OR sm.content_expiry_date > '2025-01-25')
    ''')
    dec_count = cursor.fetchone()[0]
    
    print(f"\n-- September-November 2024 meetings needing update: {sept_nov_count}")
    print(f"-- December 2024 meetings needing update: {dec_count}")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    analyze_mtg_content()
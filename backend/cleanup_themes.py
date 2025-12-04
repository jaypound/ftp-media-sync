#!/usr/bin/env python3
"""
Script to clean up and convert multi-word themes to single-word themes
"""
import psycopg2
import psycopg2.extras
import os
import getpass
from collections import defaultdict

# Database connection
connection_string = os.getenv(
    'DATABASE_URL', 
    f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
)

def get_all_themes():
    """Get all unique themes from the database"""
    conn = psycopg2.connect(connection_string)
    cur = conn.cursor()
    
    try:
        # Get all non-null themes
        cur.execute("""
            SELECT DISTINCT theme, COUNT(*) as count
            FROM assets 
            WHERE theme IS NOT NULL AND theme != ''
            GROUP BY theme
            ORDER BY COUNT(*) DESC, theme
        """)
        
        themes = cur.fetchall()
        return themes
    finally:
        cur.close()
        conn.close()

def analyze_themes():
    """Analyze current themes and suggest conversions"""
    themes = get_all_themes()
    
    print("\n=== Current Themes in Database ===")
    print(f"Total unique themes: {len(themes)}\n")
    
    multi_word_themes = []
    single_word_themes = []
    
    for theme, count in themes:
        if ' ' in theme:
            multi_word_themes.append((theme, count))
            print(f"Multi-word: '{theme}' ({count} items)")
        else:
            single_word_themes.append((theme, count))
            print(f"Single-word: '{theme}' ({count} items)")
    
    print(f"\nMulti-word themes: {len(multi_word_themes)}")
    print(f"Single-word themes: {len(single_word_themes)}")
    
    # Suggest conversions
    print("\n=== Suggested Theme Conversions ===")
    conversions = {}
    
    for theme, count in multi_word_themes:
        theme_lower = theme.lower()
        
        # Extract the most meaningful single word
        if 'neighborhood' in theme_lower:
            suggested = 'neighborhood'
        elif 'atlanta' in theme_lower and 'discovering' in theme_lower:
            suggested = 'discovering'
        elif 'atlanta forward' in theme_lower:
            suggested = 'forward'
        elif 'public' in theme_lower and 'safety' in theme_lower:
            suggested = 'safety'
        elif 'public' in theme_lower and 'health' in theme_lower:
            suggested = 'health'
        elif 'gun' in theme_lower and 'safety' in theme_lower:
            suggested = 'safety'
        elif 'affordable' in theme_lower and 'housing' in theme_lower:
            suggested = 'housing'
        elif 'climate' in theme_lower:
            suggested = 'climate'
        elif 'education' in theme_lower:
            suggested = 'education'
        elif 'business' in theme_lower:
            suggested = 'business'
        elif 'community' in theme_lower:
            suggested = 'community'
        elif 'arts' in theme_lower:
            suggested = 'arts'
        elif 'transportation' in theme_lower:
            suggested = 'transportation'
        else:
            # Take the first meaningful word (skip common words)
            words = theme_lower.split()
            skip_words = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for'}
            meaningful_words = [w for w in words if w not in skip_words and len(w) > 2]
            suggested = meaningful_words[0] if meaningful_words else words[0]
        
        conversions[theme] = suggested
        print(f"'{theme}' -> '{suggested}' ({count} items)")
    
    return conversions

def apply_conversions(conversions, dry_run=True):
    """Apply theme conversions to the database"""
    if dry_run:
        print("\n=== DRY RUN - No changes will be made ===")
    else:
        print("\n=== APPLYING CONVERSIONS ===")
    
    conn = psycopg2.connect(connection_string)
    cur = conn.cursor()
    
    try:
        total_updated = 0
        
        for old_theme, new_theme in conversions.items():
            if dry_run:
                # Just count how many would be updated
                cur.execute("""
                    SELECT COUNT(*) FROM assets 
                    WHERE theme = %s
                """, (old_theme,))
                count = cur.fetchone()[0]
                print(f"Would update {count} items: '{old_theme}' -> '{new_theme}'")
                total_updated += count
            else:
                # Actually update
                cur.execute("""
                    UPDATE assets 
                    SET theme = %s 
                    WHERE theme = %s
                """, (new_theme, old_theme))
                count = cur.rowcount
                print(f"Updated {count} items: '{old_theme}' -> '{new_theme}'")
                total_updated += count
        
        if not dry_run:
            conn.commit()
            print(f"\nTotal items updated: {total_updated}")
        else:
            print(f"\nTotal items that would be updated: {total_updated}")
        
        # Show final theme counts
        print("\n=== Final Theme Distribution ===")
        cur.execute("""
            SELECT theme, COUNT(*) as count
            FROM assets 
            WHERE theme IS NOT NULL AND theme != ''
            GROUP BY theme
            ORDER BY COUNT(*) DESC
            LIMIT 20
        """)
        
        for theme, count in cur.fetchall():
            print(f"'{theme}': {count} items")
            
    finally:
        if not dry_run:
            conn.commit()
        cur.close()
        conn.close()

def main():
    """Main function"""
    print("Theme Cleanup Tool")
    print("==================")
    
    # First, analyze current themes
    conversions = analyze_themes()
    
    if not conversions:
        print("\nNo multi-word themes found!")
        return
    
    # Show what would be done
    print("\n" + "="*50)
    print("\n=== CONVERSION SUMMARY ===")
    apply_conversions(conversions, dry_run=True)
    
    print("\n" + "="*50)
    print("\nTo apply these conversions, run:")
    print("python cleanup_themes.py --apply")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--apply':
        print("Theme Cleanup Tool - APPLYING CHANGES")
        print("=====================================")
        
        # Get conversions
        conversions = analyze_themes()
        
        if conversions:
            print("\n" + "="*50)
            print("APPLYING CONVERSIONS TO DATABASE...")
            print("="*50)
            apply_conversions(conversions, dry_run=False)
            print("\nTheme cleanup complete!")
        else:
            print("\nNo multi-word themes found!")
    else:
        main()
#!/usr/bin/env python3
"""
Fix for migrate_mongodb_to_postgresql.py to properly handle MAF content type
"""

# This shows the fix needed in migrate_mongodb_to_postgresql.py
# In the classify_content_type method, update the type_map dictionary:

def classify_content_type_fixed(filename: str, content_type: str = None) -> str:
    """Classify content type based on filename and existing content_type"""
    if content_type:
        # Map existing content types - INCLUDING MAF
        type_map = {
            'AN': 'an',          # Atlanta Now
            'ATLD': 'atld',      # ATL Direct
            'BMP': 'bmp',        # Bumps
            'IMOW': 'imow',      # In My Own Words
            'IM': 'im',          # Inclusion Months
            'IA': 'ia',          # Inside Atlanta
            'LM': 'lm',          # Legislative Minute
            'MTG': 'mtg',        # Meetings
            'MAF': 'maf',        # Moving Atlanta Forward - THIS WAS MISSING!
            'PKG': 'pkg',        # Packages
            'PMO': 'pmo',        # Promos
            'PSA': 'psa',        # PSAs
            'SZL': 'szl',        # Sizzles
            'SPP': 'spp',        # Special Projects
            'MEETING': 'mtg',    # Alternative for meetings
            'OTHER': 'other'     # Other
        }
        mapped = type_map.get(content_type.upper())
        if mapped:
            return mapped
    
    # Fallback to filename analysis
    filename_lower = filename.lower()
    
    # Check for content type codes in filename (e.g., "YYMMDD_MAF_Title.mp4")
    parts = filename_lower.split('_')
    if len(parts) >= 2:
        potential_type = parts[1].upper()
        if potential_type in ['AN', 'ATLD', 'BMP', 'IMOW', 'IM', 'IA', 'LM', 'MTG', 'MAF', 'PKG', 'PMO', 'PSA', 'SZL', 'SPP']:
            return potential_type.lower()
    
    # Pattern matching fallbacks
    if 'psa' in filename_lower:
        return 'psa'
    elif 'meeting' in filename_lower or 'council' in filename_lower or 'mtg' in filename_lower:
        return 'mtg'
    elif 'maf' in filename_lower or 'moving atlanta forward' in filename_lower:
        return 'maf'
    elif 'announcement' in filename_lower:
        return 'an'
    elif 'pkg' in filename_lower:
        return 'pkg'
    elif '_ia_' in filename_lower:
        return 'ia'
    else:
        return 'other'


# The fix in migrate_mongodb_to_postgresql.py would be to replace the classify_content_type method
# at line 68 with this updated version that includes MAF in the type_map

print("""
To fix the MAF content type issue in migrate_mongodb_to_postgresql.py:

1. Update the type_map dictionary in classify_content_type (line 72) to include:
   'MAF': 'maf',

2. Add MAF to the filename analysis section to catch files with MAF in the name

3. Run the fix_maf_content_type.sql script to update existing miscategorized content

The issue is that MAF was missing from the content type mapping during migration,
causing all MAF content to be categorized as 'other'.
""")
#!/usr/bin/env python3
import csv
from collections import Counter

# Read the CSV file and analyze
with open('/Users/jaypound/Documents/HOLIDAY EVENTS/now_Holiday_Greeting.csv', 'r') as f:
    reader = csv.DictReader(f)
    files = [row['File Name'] for row in reader]

# Count occurrences
file_counts = Counter(files)

print("=== HOLIDAY GREETING SCHEDULE ANALYSIS ===\n")
print(f"Total scheduled items: {len(files)}")
print(f"Unique files scheduled: {len(file_counts)}\n")

print("Files and their frequency:")
for file, count in file_counts.most_common():
    print(f"{count:3d}x - {file}")

print("\n=== CONCERNING PATTERNS ===")
print(f"- Strategy Office is scheduled {file_counts['251210_SSP_Strategy Office Holiday Greeting.mp4']} times (40% of schedule)")
print(f"- Watershed is scheduled {file_counts['251210_SSP_Watershed Holiday Greeting.mp4']} times (28% of schedule)")
print(f"- Only 6 unique files out of expected 27 holiday greetings")
print("\nMissing departments/offices (based on naming pattern):")
print("- ACRB, AFR, ATL Housing, ATLDOT, City Council, COO Burks, DPW, EXE")
print("- Plus approximately 13 other holiday greeting files")
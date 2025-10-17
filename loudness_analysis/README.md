# BS.1770-5 Loudness Analysis

This module implements ITU-R BS.1770-5 loudness measurement and true-peak level detection for media files.

## Overview

The ITU-R BS.1770-5 standard defines algorithms for measuring audio programme loudness and true-peak audio level. This is essential for broadcast compliance and ensuring consistent audio levels across media content.

## Key Measurements

- **Integrated Loudness (LUFS/LKFS)**: Overall loudness of the entire program
- **Short-term Loudness**: 3-second moving window
- **Momentary Loudness**: 400ms moving window
- **Loudness Range (LU)**: Dynamic range measurement
- **True Peak (dBTP)**: Maximum true-peak level
- **Maximum Short-term Loudness**: Highest 3-second loudness value
- **Maximum Momentary Loudness**: Highest 400ms loudness value

## Requirements

- Python 3.8+
- ffmpeg with libebur128 support
- NumPy for numerical processing
- matplotlib for visualization (optional)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```python
from loudness_analyzer import analyze_loudness

results = analyze_loudness('path/to/media/file.mp4')
print(results)
```
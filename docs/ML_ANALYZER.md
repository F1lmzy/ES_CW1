# Machine Learning Sleep Pattern Analysis

This module adds ML-based sleep pattern analysis and recommendations to the SleepSense project.

## Overview

The ML analyzer (`firmware/processing/ml_analyzer.py`) provides:

- **K-Means Clustering**: Automatically categorizes nights into quality buckets
- **Trend Analysis**: Linear regression to detect sleep pattern trends
- **Smart Recommendations**: Data-driven suggestions

## Files Added

1. **firmware/processing/ml_analyzer.py** - Main ML analyzer
2. **tests/test_ml_analyzer.py** - Unit tests
3. **requirements-ml.txt** - Python dependencies

## Installation

```bash
pip3 install -r requirements-ml.txt
```

## Raspberry Pi 2 Compatibility

**YES, this can run on Raspberry Pi 2.**

Performance characteristics:
- K-Means clustering: Fast (O(n) inference)
- Linear regression: Very fast (O(n))
- Memory usage: ~50-100MB for week of data
- No GPU required - all CPU-based
- Single-threaded operations

Installation on Pi 2:
```bash
# If memory issues during install:
sudo pip3 install numpy pandas scikit-learn --no-cache-dir

# Or increase swap:
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

## Usage

```python
from firmware.communication.supabase_client import SupabaseClient
from firmware.processing.ml_analyzer import SleepMLAnalyzer, format_analysis_report

# Fetch data
client = SupabaseClient(url="...", key="...")
readings = client.fetch_history(days=7)

# Analyze
analyzer = SleepMLAnalyzer()
analysis = analyzer.analyze(readings)

# View results
print(format_analysis_report(analysis))
```

## ML Features

1. **Nightly Aggregation**: Groups readings into nightly summaries
2. **K-Means Clustering**: Categorizes nights as Excellent/Good/Poor/Restless
3. **Trend Analysis**: Detects improving/declining/stable patterns
4. **Insights**: Best/worst nights, consistency score, weekend patterns
5. **Recommendations**: Context-aware sleep advice

## Test

```bash
python3 -m pytest tests/test_ml_analyzer.py -v
```

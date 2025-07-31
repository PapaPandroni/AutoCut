# AutoCut Prototype Usage Guide

This guide provides comprehensive instructions for using the AutoCut End-to-End Video Editing Prototype.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Installation](#installation)
3. [Basic Usage](#basic-usage)
4. [Advanced Usage](#advanced-usage)
5. [Configuration](#configuration)
6. [Editing Styles](#editing-styles)
7. [Quality Profiles](#quality-profiles)
8. [Performance Modes](#performance-modes)
9. [Export Options](#export-options)
10. [Demo and Testing](#demo-and-testing)
11. [Troubleshooting](#troubleshooting)
12. [Performance Optimization](#performance-optimization)

## Quick Start

```bash
# Basic usage with folder of videos and external music
python autocut_prototype.py video_folder/ --music song.mp3

# Single video with external music
python autocut_prototype.py input_video.mp4 --music song.mp3

# Specify output file and quality
python autocut_prototype.py video_folder/ --music song.mp3 --output highlight_reel.mp4 --quality high

# Use aggressive editing style for music videos
python autocut_prototype.py video_folder/ --music song.mp3 --style musical --profile action

# Export timeline only for review
python autocut_prototype.py video_folder/ --music song.mp3 --export timeline --no-render
```

## Installation

### Prerequisites

1. **Python 3.8+** with required packages:
   ```bash
   pip install -r requirements.txt
   ```

2. **FFmpeg** (required for video processing):
   ```bash
   # macOS
   brew install ffmpeg
   
   # Ubuntu/Debian
   sudo apt update && sudo apt install ffmpeg
   
   # Windows
   # Download from https://ffmpeg.org/download.html
   ```

3. **Optional dependencies** for enhanced features:
   ```bash
   # For face detection (requires MediaPipe)
   pip install mediapipe
   
   # For advanced audio analysis
   pip install madmom
   ```

### Environment Setup

Always activate the virtual environment before running:
```bash
source env/bin/activate
```

## Basic Usage

### Simple Video Processing

#### Folder-based Processing (Recommended)
```bash
# Process folder of videos with external music
python autocut_prototype.py video_folder/ --music background_song.mp3
```

This will:
- Discover all video files in the folder
- Analyze external music for beat detection
- Select best clips from all videos
- Generate timeline synced to music beats
- Render highlight reel as `video_folder_highlight.mp4`

#### Single Video Processing
```bash
# Process single video with external music
python autocut_prototype.py my_video.mp4 --music song.mp3
```

This will:
- Analyze external music for beat detection
- Detect scene changes in the video
- Generate timeline with clips synced to music
- Render edited video as `my_video_edited.mp4`

### Specify Output Location

```bash
# Folder processing with custom output
python autocut_prototype.py video_folder/ --music song.mp3 --output /path/to/highlight_reel.mp4

# Single video with custom output  
python autocut_prototype.py input.mp4 --music song.mp3 --output /path/to/output.mp4
```

### Choose Quality Preset

```bash
# Lossless (fastest, largest file)
python autocut_prototype.py video_folder/ --music song.mp3 --quality lossless

# High quality (slower, smaller file)
python autocut_prototype.py video_folder/ --music song.mp3 --quality high

# Medium quality (balanced)
python autocut_prototype.py video_folder/ --music song.mp3 --quality medium

# Draft quality (fastest encoding)
python autocut_prototype.py video_folder/ --music song.mp3 --quality draft
```

## Advanced Usage

### Editing Styles

Choose how the algorithm decides where to make cuts:

```bash
# Aggressive: Frequent cuts, strong beat alignment
python autocut_prototype.py music_videos/ --music upbeat_song.mp3 --style aggressive

# Smooth: Longer clips, respect scene boundaries
python autocut_prototype.py documentary_clips/ --music ambient_music.mp3 --style smooth

# Musical: Strict beat alignment, musical phrasing (recommended for external music)
python autocut_prototype.py concert_footage/ --music concert_track.mp3 --style musical

# Cinematic: Story-driven, minimal beat sync
python autocut_prototype.py narrative_clips/ --music soundtrack.mp3 --style cinematic

# Adaptive: Dynamic adjustment (default)
python autocut_prototype.py any_videos/ --music any_song.mp3 --style adaptive
```

### Quality Profiles

Optimize analysis for different video content types:

```bash
# Talking head videos (emphasize face quality)
python autocut_prototype.py interview_clips/ --music background_music.mp3 --profile talking_head

# Action videos (handle motion and exposure)
python autocut_prototype.py sports_footage/ --music energetic_track.mp3 --profile action

# Landscape videos (emphasize composition)
python autocut_prototype.py nature_clips/ --music ambient_sounds.mp3 --profile landscape

# Documentary style (balanced approach)
python autocut_prototype.py documentary_footage/ --music documentary_score.mp3 --profile documentary
```

### Performance Modes

Balance speed vs. quality:

```bash
# Speed: 15x+ real-time, basic quality
python autocut_prototype.py video_folder/ --music song.mp3 --performance speed

# Balanced: 10x real-time, good quality (default)
python autocut_prototype.py video_folder/ --music song.mp3 --performance balanced

# Quality: 5x real-time, high quality
python autocut_prototype.py video_folder/ --music song.mp3 --performance quality

# Precision: 2x real-time, maximum quality
python autocut_prototype.py video_folder/ --music song.mp3 --performance precision
```

### Output Format and Resolution

```bash
# Change output format
python autocut_prototype.py input.mp4 --format mov

# Set target resolution
python autocut_prototype.py input.mp4 --resolution 720p
python autocut_prototype.py input.mp4 --resolution 1920x1080

# Set target frame rate
python autocut_prototype.py input.mp4 --fps 24
```

### Combined Advanced Options

```bash
# Complete advanced workflow with folder and music
python autocut_prototype.py vacation_videos/ \
  --music summer_hit.mp3 \
  --style musical \
  --profile action \
  --performance quality \
  --quality high \
  --format mp4 \
  --resolution 1080p \
  --fps 30 \
  --output vacation_highlight_reel.mp4
```

## Configuration

### Using Configuration Files

1. **Copy the example configuration:**
   ```bash
   mkdir -p ~/.autocut
   cp autocut_config_example.yaml ~/.autocut/config.yaml
   ```

2. **Edit configuration:**
   ```bash
   # Edit with your preferred editor
   nano ~/.autocut/config.yaml
   ```

3. **Use custom configuration:**
   ```bash
   python autocut_prototype.py input.mp4 --config my_config.yaml
   ```

### Key Configuration Sections

- **Processing**: Worker threads, memory limits, timeouts
- **Audio**: Sample rates, beat detection parameters
- **Video**: File size limits, hardware acceleration
- **Scene Detection**: Algorithm thresholds, processing modes
- **Quality Scoring**: Profile weights, analysis parameters
- **Timeline**: Cut timing, style configurations
- **Rendering**: Quality presets, hardware encoders

## Export Options

### Export Timeline Data

```bash
# Export timeline as JSON
python autocut_prototype.py input.mp4 --export timeline --timeline-format json

# Export timeline as CSV
python autocut_prototype.py input.mp4 --export timeline --timeline-format csv

# Export timeline as EDL (Edit Decision List)
python autocut_prototype.py input.mp4 --export timeline --timeline-format edl
```

### Export Analysis Data

```bash
# Export audio analysis
python autocut_prototype.py input.mp4 --export audio

# Export quality scoring data
python autocut_prototype.py input.mp4 --export quality --quality-format json

# Export processing statistics
python autocut_prototype.py input.mp4 --export stats

# Export everything
python autocut_prototype.py input.mp4 --export timeline audio quality stats
```

### Analysis Only (No Rendering)

```bash
# Generate timeline without rendering video
python autocut_prototype.py input.mp4 --no-render --export timeline

# Complete analysis export
python autocut_prototype.py input.mp4 --no-render --export timeline audio quality stats
```

### Custom Export Directory

```bash
python autocut_prototype.py input.mp4 \
  --export timeline audio quality \
  --export-dir ./my_analysis_data/
```

## Demo and Testing

### Demo Mode

Test the pipeline without video files:

```bash
# Run demo with default 60-second mock video
python autocut_prototype.py --demo

# Specify mock video duration
python autocut_prototype.py --demo --mock-duration 120
```

### Performance Benchmarking

```bash
# Run performance benchmark with default test cases
python autocut_prototype.py --benchmark

# Export benchmark results
python autocut_prototype.py --benchmark --export stats --export-dir ./benchmarks/
```

### Verbose Output

```bash
# Enable verbose logging
python autocut_prototype.py input.mp4 --verbose

# Set specific log level
python autocut_prototype.py input.mp4 --log-level DEBUG

# Log to file
python autocut_prototype.py input.mp4 --log-file autocut.log
```

## Feature Control

### Disable Specific Features

```bash
# Disable face detection (faster processing)
python autocut_prototype.py input.mp4 --no-face-detection

# Disable quality scoring
python autocut_prototype.py input.mp4 --no-quality-scoring

# Skip rendering (analysis only)
python autocut_prototype.py input.mp4 --no-render
```

### Enable All Features

```bash
python autocut_prototype.py input.mp4 \
  --style adaptive \
  --profile adaptive \
  --performance quality \
  --export timeline audio quality stats
```

## Troubleshooting

### Common Issues

1. **FFmpeg not found:**
   ```bash
   # Verify FFmpeg installation
   ffmpeg -version
   
   # Install if missing (see installation section)
   ```

2. **Out of memory errors:**
   ```bash
   # Use speed mode for large files
   python autocut_prototype.py large_video.mp4 --performance speed
   
   # Disable memory-intensive features
   python autocut_prototype.py large_video.mp4 --no-face-detection --no-quality-scoring
   ```

3. **Slow processing:**
   ```bash
   # Check hardware acceleration
   python autocut_prototype.py input.mp4 --verbose
   
   # Use speed mode
   python autocut_prototype.py input.mp4 --performance speed
   ```

4. **Audio analysis fails:**
   ```bash
   # Check audio stream in video
   ffprobe -v quiet -show_streams input.mp4
   
   # Some formats may need conversion
   ffmpeg -i input.mkv -c copy input.mp4
   ```

### Debug Mode

```bash
# Enable debug logging
python autocut_prototype.py input.mp4 --log-level DEBUG --verbose

# Log to file for analysis
python autocut_prototype.py input.mp4 --log-level DEBUG --log-file debug.log
```

## Performance Optimization

### Hardware Acceleration

The prototype automatically detects and uses hardware acceleration:

- **macOS**: VideoToolbox (M1/M2 Macs, Intel Macs with T2)
- **Windows/Linux**: NVENC (NVIDIA GPUs), QSV (Intel GPUs)

### Memory Usage

```bash
# For large videos (>4GB), use speed mode
python autocut_prototype.py large_video.mp4 --performance speed

# Monitor memory usage
python autocut_prototype.py input.mp4 --verbose --log-level DEBUG
```

### Processing Speed

Expected performance targets:

| Mode | Analysis Speed | Lossless Render | Encoded Render |
|------|---------------|-----------------|----------------|
| Speed | 15x+ real-time | 15x+ real-time | 3-5x real-time |
| Balanced | 10x real-time | 10x+ real-time | 2-3x real-time |
| Quality | 5x real-time | 10x+ real-time | 1-2x real-time |
| Precision | 2x real-time | 10x+ real-time | 0.5-1x real-time |

### Batch Processing

For multiple videos, process them sequentially to avoid memory issues:

```bash
# Process multiple videos
for video in *.mp4; do
  python autocut_prototype.py "$video" --performance balanced
done
```

## Integration Examples

### Python Script Integration

```python
from autocut_prototype import AutoCutPrototype
from src.core.timeline import EditingStyle
from src.core.quality_scoring import QualityProfile

# Initialize prototype
prototype = AutoCutPrototype()

# Process video
results = prototype.process_video(
    input_path=Path("input.mp4"),
    output_path=Path("output.mp4"),
    editing_style=EditingStyle.AGGRESSIVE,
    quality_profile=QualityProfile.TALKING_HEAD,
    performance_mode="balanced",
    export_options={
        'export_timeline': True,
        'export_stats': True
    }
)

if results['success']:
    print(f"Processing completed in {results['processing_stats']['total_time']:.2f}s")
    print(f"Speed factor: {results['processing_stats']['overall_speed_factor']:.1f}x")
else:
    print(f"Processing failed: {results['error']}")
```

### Workflow Integration

```bash
#!/bin/bash
# Workflow script for processing multiple videos

INPUT_DIR="./raw_videos"
OUTPUT_DIR="./edited_videos"
STYLE="adaptive"
PROFILE="adaptive"
QUALITY="high"

mkdir -p "$OUTPUT_DIR"

for video in "$INPUT_DIR"/*.mp4; do
    filename=$(basename "$video" .mp4)
    
    echo "Processing: $filename"
    
    python autocut_prototype.py "$video" \
        --output "$OUTPUT_DIR/${filename}_edited.mp4" \
        --style "$STYLE" \
        --profile "$PROFILE" \
        --quality "$QUALITY" \
        --export timeline stats \
        --export-dir "$OUTPUT_DIR/${filename}_analysis"
    
    if [ $? -eq 0 ]; then
        echo "✅ $filename completed successfully"
    else
        echo "❌ $filename failed"
    fi
done

echo "Batch processing completed"
```

## Getting Help

```bash
# Show help message
python autocut_prototype.py --help

# Show version info
python autocut_prototype.py --version

# Run demo to understand capabilities
python autocut_prototype.py --demo

# Run benchmark to test performance
python autocut_prototype.py --benchmark
```

For additional support, check the logs and use verbose mode to diagnose issues.
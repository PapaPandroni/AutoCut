# AutoCut Project Instructions

## Project Overview

AutoCut is a high-performance, AI-powered automated video editing system that creates professional-quality highlight videos by intelligently synchronizing cuts with musical beats while analyzing video content for optimal editing decisions.

## Environment Setup

- ALWAYS work within our virtual environment. activate with command: source env/bin/activate
- Always use context7 mcp server for documentation for frameworks, languages etc.

## System Architecture

The AutoCut system consists of the following main components:

### Core Modules
- **Audio Analysis** (`src/audio/`): Beat detection and rhythm analysis using librosa
- **Video Processing** (`src/video/`): Video ingestion, scene detection, face detection, and rendering
- **Core Algorithms** (`src/core/`): Timeline generation and quality scoring algorithms
- **Performance Optimization** (`src/performance/`): Hardware acceleration and optimization suite
- **Utilities** (`src/utils/`): Configuration management and logging

### Key Features Implemented
- 15x real-time processing on M1/M2 Macs
- Beat-synchronized video editing
- Multi-factor quality scoring (faces, blur, exposure, composition, color)
- Hardware-accelerated rendering with FFmpeg stream copying
- Multiple editing styles (aggressive, smooth, adaptive, musical, cinematic)
- Quality profiles for different content types (talking_head, action, landscape, documentary)

## Development Guidelines

### Testing
- Comprehensive test suite with 400+ unit tests
- Run tests with: `python -m pytest tests/ -v`
- Performance validation: `python validate_performance.py --quick-test`

### Performance Targets
- Speed Mode: 15x+ real-time processing
- Balanced Mode: 10x real-time processing  
- Quality Mode: 5x real-time processing
- Precision Mode: 2x real-time processing

### Code Quality Standards
- Full type hints throughout codebase
- Comprehensive error handling and logging
- Modular architecture with clear separation of concerns
- Configuration-driven behavior using YAML configs

## Main Entry Points

### CLI Application
```bash
python autocut_prototype.py input_video.mp4 --style musical --profile talking_head
```

### Programmatic Usage
```python
from src.audio.analyzer import AudioAnalyzer
from src.video.ingestion import VideoIngestion
from src.core.timeline import BeatSyncTimelineGenerator
from src.video.renderer import VideoRenderer
```

### Performance Monitoring
```python
from src.performance import create_performance_optimizer, create_performance_monitor
```

## Configuration

The system uses YAML configuration files:
- Main config: `autocut_config_example.yaml`
- Performance tuning parameters
- Quality thresholds and weights
- Hardware acceleration settings

## Dependencies

### Core Dependencies
- librosa: Audio analysis and beat detection
- opencv-python: Computer vision and video processing
- mediapipe: Face detection and analysis
- ffmpeg-python: Video rendering and processing
- numpy, scipy: Numerical computing

### Performance Dependencies
- Hardware acceleration via VideoToolbox (M1/M2 Macs)
- Multi-threading optimization for Apple Silicon
- Memory-efficient streaming processing

## Deployment Notes

- Optimized for M1/M2 Mac hardware
- Requires FFmpeg installation for video processing
- MediaPipe models downloaded automatically on first use
- Virtual environment required for dependency isolation
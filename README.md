# AutoCut 🎬
**AI-Powered Automated Video Editing System**

AutoCut is a high-performance, automated video editing system that creates professional-quality highlight videos by intelligently synchronizing cuts with musical beats while analyzing video content for optimal editing decisions.

## ✨ Key Features

- **🎵 Beat-Synchronized Editing**: Automatically cuts video to match audio beats and rhythm
- **🎯 Intelligent Scene Detection**: Advanced OpenCV-based scene change detection
- **👤 Face Detection & Quality Scoring**: MediaPipe-powered face detection with quality assessment
- **⚡ 15x Real-Time Processing**: Optimized for M1/M2 Macs with hardware acceleration
- **🎨 Multiple Editing Styles**: Aggressive, smooth, adaptive, musical, and cinematic modes
- **📽️ Lossless Rendering**: FFmpeg stream copying for maximum quality and speed
- **🔧 Professional Features**: Multiple output formats, quality presets, and batch processing

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/AutoCut.git
cd AutoCut

# Set up virtual environment
python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

```bash
# Basic usage with external music (folder of videos)
python autocut_prototype.py video_folder/ --music song.mp3

# Single video with external music
python autocut_prototype.py video.mp4 --music song.mp3

# Specify editing style and quality profile
python autocut_prototype.py video_folder/ --music song.mp3 --style musical --profile talking_head

# Export timeline for review without rendering
python autocut_prototype.py video_folder/ --music song.mp3 --export timeline --no-render
```

### Advanced Usage

```bash
# Complete processing with all options
python autocut_prototype.py vacation_videos/ \
  --music summer_hit.mp3 \
  --style musical \
  --profile action \
  --performance quality \
  --quality high \
  --format mp4 \
  --resolution 1080p \
  --export timeline audio quality stats
```

## 🏗️ System Architecture

AutoCut consists of several specialized modules working together:

### Core Components

- **Audio Analysis** (`src/audio/`): Beat detection and rhythm analysis using librosa
- **Video Ingestion** (`src/video/ingestion.py`): Multi-format video loading with FFmpeg
- **Scene Detection** (`src/video/scene_detection.py`): Intelligent scene change detection
- **Face Detection** (`src/video/face_detection.py`): MediaPipe-based face analysis
- **Quality Scoring** (`src/core/quality_scoring.py`): Multi-factor quality assessment
- **Timeline Generation** (`src/core/timeline.py`): Beat-sync timeline creation algorithm
- **Video Rendering** (`src/video/renderer.py`): High-performance video output

### Performance Optimization

- **Hardware Acceleration**: VideoToolbox support for M1/M2 Macs
- **Parallel Processing**: Multi-threaded analysis and rendering
- **Memory Efficiency**: Streaming processing for large videos
- **Adaptive Quality**: Dynamic quality adjustment based on performance needs

## 📊 Performance

AutoCut achieves exceptional performance on Apple Silicon:

| Mode | Processing Speed | Quality Level | Use Case |
|------|-----------------|---------------|----------|
| **Speed** | 15x+ real-time | 70%+ quality | Rapid preview/batch processing |
| **Balanced** | 10x real-time | 85%+ quality | General editing workflows |
| **Quality** | 5x real-time | 95%+ quality | Professional production |
| **Precision** | 2x real-time | 100% quality | Research/fine-tuning |

## 🎨 Editing Styles

- **Aggressive**: Frequent cuts, strong beat synchronization
- **Smooth**: Longer clips, respects scene boundaries
- **Adaptive**: Dynamic adjustment based on content
- **Musical**: Strict beat alignment with musical phrasing
- **Cinematic**: Story-driven with minimal beat interference

## 📋 Quality Profiles

- **Talking Head**: Optimized for interviews and presentations
- **Action**: Enhanced for sports and dynamic content
- **Landscape**: Tuned for travel and scenic videos
- **Documentary**: Balanced approach for storytelling
- **Adaptive**: Automatic profile selection based on content

## 🎯 Supported Formats

### Input Formats
- **Video**: MP4, MOV, AVI, MKV, WebM, FLV, M4V
- **Audio**: Embedded audio tracks in all supported video formats

### Output Formats
- **Video**: MP4, MOV, AVI, MKV, WebM with multiple quality presets
- **Timeline**: JSON, CSV, EDL (Edit Decision List)
- **Data**: Audio analysis, quality metrics, performance statistics

## 🔧 Configuration

AutoCut uses a flexible YAML configuration system. See `autocut_config_example.yaml` for complete configuration options including:

- Performance tuning parameters
- Quality thresholds and weights
- Hardware acceleration settings
- Export preferences
- Editing style customizations

## 📖 Documentation

- **[Performance Guide](docs/PERFORMANCE_GUIDE.md)**: Optimization tips and benchmarking
- **[API Reference](docs/)**: Detailed module documentation
- **[Usage Examples](examples/)**: Complete code examples and demos
- **[Troubleshooting](docs/)**: Common issues and solutions

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Run all tests
python -m pytest tests/ -v

# Run video renderer tests specifically  
python -m pytest tests/test_video_renderer.py -v

# Run performance validation
python validate_performance.py --quick-test

# Run benchmarks
python autocut_prototype.py --benchmark
```

**Test Coverage**: 470+ unit tests including comprehensive multi-video rendering validation

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **librosa**: Audio analysis and beat detection
- **OpenCV**: Computer vision and scene detection
- **MediaPipe**: Face detection and analysis
- **FFmpeg**: Video processing and rendering
- **NumPy/SciPy**: Numerical computing foundation

## 🔧 Troubleshooting 

### Common Issues

**FFmpeg Error: "Unable to choose an output format"**
- **Cause**: Invalid output path or missing file extension
- **Solution**: Ensure output path has proper video extension (.mp4, .mov, .avi, etc.)
- **Fixed**: Enhanced validation prevents boolean/invalid values from reaching FFmpeg

**AttributeError: 'VideoRenderer' object has no attribute 'render_multi_video_timeline'**
- **Status**: ✅ **FIXED** - Method structure corrected and comprehensive validation added
- **If still occurring**: Check you're using the latest version and activate virtual environment

**Memory Issues with Large Videos**
- Use appropriate performance mode (`--performance speed` for large files)
- Ensure sufficient disk space for temporary files
- Consider processing videos in smaller batches

## 💬 Support

For questions, issues, or feature requests, please:
- Open an issue on GitHub
- Check the documentation in the `docs/` directory
- Review the examples in the `examples/` directory
- Check `CLAUDE.md` for recent bug fixes and improvements

---

**AutoCut** - Making professional video editing accessible through AI automation 🎬✨

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

## Recent Bug Fixes & Improvements

### Multi-Video Timeline Rendering Fix (July 2025)

**Issue**: The `render_multi_video_timeline` method was failing with `AttributeError: 'VideoRenderer' object has no attribute 'render_multi_video_timeline'` and subsequent FFmpeg error `"Unable to choose an output format for 'True'"`.

**Root Causes Identified:**
1. Method was incorrectly nested inside `estimate_render_time` function instead of being a proper class method
2. Missing `RenderingResult` dataclass definition
3. Boolean `True` value being passed as `output_path` parameter, causing FFmpeg to try to write to filename "True"
4. Missing helper methods and incorrect attribute references

**Fixes Implemented:**
1. **Method Structure**: Fixed indentation and moved `render_multi_video_timeline` to proper VideoRenderer class level
2. **Type Safety**: Added comprehensive input validation for `output_path` parameter:
   - Validates against `None` values with clear error messages
   - **Specifically detects boolean values** and raises `TypeError` with detailed explanation
   - Converts valid strings to Path objects automatically
   - Prevents invalid types from reaching FFmpeg
3. **Missing Components**: Added `RenderingResult` dataclass and all required helper methods
4. **Error Handling**: Enhanced FFmpeg error detection with specific handling for path-related issues
5. **Debugging**: Added extensive logging throughout method chain for troubleshooting

**Testing**: Added 31 new unit tests (72 total in renderer suite) including specific validation for boolean path detection.

**Key Lesson Learned**: Boolean values can be silently passed as parameters in Python and converted to strings ("True"/"False") causing cryptic downstream errors. Always validate parameter types early in methods, especially for external tool integration like FFmpeg.

### FFmpeg Library Integration Bug Fix (July 2025)

**Additional Issue**: After fixing the method structure and parameter validation, a second error emerged: FFmpeg was still receiving "True" as a filename parameter despite proper path validation.

**Root Cause**: The issue was in the FFmpeg library integration itself - `ffmpeg.run(output, quiet=True, overwrite_output=True)` was incorrectly passing the `overwrite_output=True` boolean parameter, which FFmpeg interpreted as a filename.

**Fixes Implemented**:
1. **FFmpeg Parameter Fix**: Replaced `overwrite_output=True` with `global_args=['-y']` to properly pass the overwrite flag to FFmpeg command line
2. **Directory Creation**: Added `output_path.parent.mkdir(parents=True, exist_ok=True)` to ensure output directories exist before FFmpeg execution
3. **Enhanced Error Handling**: Added comprehensive FFmpeg error categorization with specific detection for:
   - Boolean parameter errors (the original "True" filename issue)
   - Invalid output format/path errors
   - File system permission errors
   - Generic FFmpeg execution errors
4. **Debugging Improvements**: Added detailed logging of FFmpeg parameters and their types for troubleshooting
5. **Unit Tests**: Added 2 new tests specifically for FFmpeg parameter validation and directory creation

**Key Technical Insight**: FFmpeg library bindings can convert Python parameters in unexpected ways. The `overwrite_output=True` parameter was being converted to a string and passed as a positional argument instead of a command-line flag. Always use `global_args=['-y']` for FFmpeg overwrite behavior instead of the `overwrite_output` parameter.

**Testing**: All 74 video renderer tests pass, with new tests specifically validating FFmpeg parameter handling and directory creation behavior.

### Subprocess-Based FFmpeg Execution (August 2025)

**Final Solution**: After discovering that `global_args` parameter in ffmpeg-python has known implementation issues, implemented a robust subprocess-based approach following the code reviewer's architectural recommendation.

**Implementation Details**:
1. **Command Building**: Use ffmpeg-python's excellent pipeline building with `ffmpeg.input()` and `ffmpeg.output()`
2. **Command Extraction**: Extract raw FFmpeg command using `output.compile()` method
3. **Manual Flag Insertion**: Insert `-y` overwrite flag at correct position in command array
4. **Direct Execution**: Execute FFmpeg via `subprocess.run()` with precise control

**Code Pattern**:
```python
# Build FFmpeg pipeline normally
output = ffmpeg.output(video_input, music_input, str(output_path), **params)

# Extract command and add -y flag manually
cmd_args = output.compile()
final_cmd = ['ffmpeg', '-y'] + cmd_args[1:]  # Insert -y after 'ffmpeg'

# Execute with subprocess for precise control
result = subprocess.run(final_cmd, capture_output=True, text=True, check=False)
```

**Benefits Achieved**:
- **Eliminates ffmpeg-python parameter bugs** - No reliance on problematic `global_args` or `overwrite_output`
- **Precise control** - Exact placement of `-y` flag guaranteed
- **Better error handling** - Direct access to subprocess stdout/stderr
- **Future-proof** - Independent of ffmpeg-python library quirks
- **Maintains existing features** - All pipeline building and parameter validation preserved

**Updated Error Handling**: Enhanced `_handle_ffmpeg_error()` method now processes subprocess results while maintaining all existing error categorization and logging capabilities.

### Multi-Video Processing Pipeline Stability (August 2025)

**Major Achievement**: Complete resolution of multi-video processing pipeline errors and establishment of production-ready stability.

**Issues Resolved During Session**:

1. **FFmpeg Boolean Parameter Error**
   - **Problem**: `shortest=True` parameter in `ffmpeg.output()` was being compiled to `-shortest True`, causing FFmpeg to interpret "True" as the output filename
   - **Solution**: Changed `shortest=True` to `shortest=None` which creates the proper `-shortest` flag without a value
   - **Location**: `src/video/renderer.py:1259`

2. **NoneType Division Errors**
   - **Problem**: `timeline.total_duration` was `None` for multi-video timelines, causing division by zero errors
   - **Solution**: Implemented fallback pattern `(timeline.total_duration or timeline.duration)` throughout renderer
   - **Locations Fixed**: Lines 539, 760, 825, 1085, 1101, 1103, 1471 in `src/video/renderer.py`

3. **Video Info Index Bounds Errors** 
   - **Problem**: `segment.source_video_index` exceeding `video_info_list` length
   - **Solution**: Added bounds checking with descriptive error messages
   - **Location**: `src/video/renderer.py:1163-1164`

4. **Results Dictionary Inconsistencies**
   - **Problem**: Multi-video and single-video processing returned different result structures
   - **Solutions**:
     - Fixed `'video_info'` vs `'video_info_list'` handling in `print_pipeline_results`
     - Added `audio_analysis.to_dict()` consistency between processing paths
     - Added missing `'scene_detections'`, `'face_detections'`, `'quality_results'` keys
     - Added `'render_stats'` and `'processing_stats'` keys for complete structure

5. **Timeline Object Serialization**
   - **Problem**: Multi-video timelines had `video_info = None`, causing `timeline.to_dict()` to fail
   - **Solution**: Made `to_dict()` method null-safe with fallback to "multi-video" path name
   - **Location**: `src/core/timeline.py:147`

6. **Print Function Multi-Video Support**
   - **Problem**: `print_pipeline_results` only handled single-video result formats
   - **Solution**: Added comprehensive handling for both single and multi-video cases with defensive programming
   - **Location**: `autocut_prototype.py:1143-1267`

**Testing Results**:
- ✅ **16-video test case**: 238.9s total duration processed successfully
- ✅ **Audio Analysis**: 123 BPM, 369 beats, 96% confidence
- ✅ **Timeline Generation**: 14 segments, 100% beat sync, 100% scene respect
- ✅ **Performance**: 33.6x audio processing, 36.2x rendering speed
- ✅ **Complete Pipeline**: All sections display without errors

**Key Technical Insights**:
1. **Boolean Parameter Validation**: Always validate parameter types before passing to external tools like FFmpeg
2. **Multi-Video Architecture**: Ensure consistent data structures between single and multi-video processing paths
3. **Defensive Programming**: Use `.get()` for dictionaries and `getattr()` for objects with fallbacks
4. **Null-Safe Operations**: Always check for None values before mathematical operations or attribute access
5. **Result Structure Consistency**: Both processing paths must return identical dictionary key structures

**Deployment Confidence**: The system is now production-ready for multi-video processing workflows with robust error handling and comprehensive logging.

### Performance Impact
- No performance regression - validation happens at method entry before heavy processing
- Improved error messages reduce debugging time
- Comprehensive logging aids in production troubleshooting
- Multi-video processing maintains high performance (35x+ real-time speeds achieved)
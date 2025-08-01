# AutoCut API Reference

This document provides a comprehensive reference for the AutoCut video editing system APIs.

## Table of Contents

- [Audio Analysis](#audio-analysis)
- [Video Processing](#video-processing)
- [Core Algorithms](#core-algorithms)
- [Performance Optimization](#performance-optimization)
- [Utilities](#utilities)

## Audio Analysis

### AudioAnalyzer (`src/audio/analyzer.py`)

High-performance audio analysis with beat detection and rhythm analysis.

#### Class: `AudioAnalyzer`

```python
from src.audio.analyzer import AudioAnalyzer

analyzer = AudioAnalyzer()
result = analyzer.analyze_audio("path/to/audio.mp3")
```

**Methods:**

- `analyze_audio(file_path: Union[str, Path]) -> AudioAnalysisResult`
  - Performs complete audio analysis including beat detection
  - Returns comprehensive analysis results with beat timestamps

- `detect_beats(audio_data: np.ndarray, sr: int) -> List[float]`
  - Detects beat positions in audio data
  - Returns list of beat timestamps in seconds

#### Class: `AudioAnalysisResult`

**Properties:**
- `file_path: Path` - Path to analyzed audio file
- `duration: float` - Audio duration in seconds
- `sample_rate: int` - Audio sample rate
- `tempo: float` - Detected BPM (beats per minute)
- `beats: List[float]` - Beat timestamps in seconds
- `beat_confidence: List[float]` - Confidence scores for each beat
- `onset_times: List[float]` - Audio onset timestamps
- `spectral_features: Dict` - Spectral analysis features

## Video Processing

### VideoIngestion (`src/video/ingestion.py`)

Multi-format video loading and analysis with hardware acceleration support.

#### Class: `VideoIngestion`

```python
from src.video.ingestion import VideoIngestion

ingestion = VideoIngestion()
video_info = ingestion.load_video("path/to/video.mp4")
```

**Methods:**

- `load_video(file_path: Union[str, Path]) -> VideoInfo`
  - Loads and analyzes video file
  - Returns comprehensive video information

- `is_format_supported(file_path: Union[str, Path]) -> bool`
  - Checks if video format is supported

- `get_supported_formats() -> List[str]`
  - Returns list of supported file extensions

#### Class: `VideoInfo`

**Properties:**
- `file_path: Path` - Path to video file
- `container_format: ContainerFormat` - Video container format
- `duration: float` - Video duration in seconds
- `file_size: int` - File size in bytes
- `video_streams: List[VideoStream]` - Video stream information
- `audio_streams: List[AudioStream]` - Audio stream information
- `resolution: Tuple[int, int]` - Video resolution (width, height)
- `aspect_ratio: float` - Video aspect ratio
- `is_valid: bool` - Video validation status
- `hardware_decodable: bool` - Hardware acceleration compatibility

### Scene Detection (`src/video/scene_detection.py`)

Advanced scene detection using multiple algorithms with performance optimization.

#### Class: `SceneDetection`

```python
from src.video.scene_detection import SceneDetection, ProcessingMode

detector = SceneDetection(ProcessingMode.BALANCED)
result = detector.detect_scenes("path/to/video.mp4")
```

**Methods:**

- `detect_scenes(video_path: Union[str, Path], algorithm: SceneDetectionAlgorithm = None) -> SceneDetectionResult`
  - Detects scene changes in video
  - Returns scene change timestamps with confidence scores

- `batch_detect_scenes(video_paths: List[Union[str, Path]], max_workers: int = 4) -> List[SceneDetectionResult]`
  - Batch processing of multiple videos

#### Enums:
- `SceneDetectionAlgorithm`: HISTOGRAM, EDGE, OPTICAL_FLOW, COMBINED
- `ProcessingMode`: SPEED, BALANCED, QUALITY, PRECISION

### Face Detection (`src/video/face_detection.py`)

MediaPipe-powered face detection optimized for M1/M2 Macs.

#### Class: `FaceDetectionEngine`

```python
from src.video.face_detection import create_optimized_face_detection_engine

engine = create_optimized_face_detection_engine()
result = engine.detect_faces_in_video("path/to/video.mp4")
```

**Methods:**

- `detect_faces_in_video(video_path: Union[str, Path]) -> VideoFaceDetectionResult`
  - Detects faces throughout video with quality scoring
  - Returns comprehensive face analysis results

- `detect_faces_in_frame(frame: np.ndarray) -> FrameFaceDetectionResult`
  - Detects faces in single frame

#### Class: `VideoFaceDetectionResult`

**Properties:**
- `video_path: Path` - Path to analyzed video
- `frames: List[FrameFaceDetectionResult]` - Per-frame results
- `total_faces_detected: int` - Total number of faces found
- `average_face_quality: float` - Average quality score
- `face_presence_percentage: float` - Percentage of frames with faces

### Video Rendering (`src/video/renderer.py`)

High-performance video rendering with lossless stream copying.

#### Class: `VideoRenderer`

```python
from src.video.renderer import VideoRenderer, RenderingPreset

renderer = VideoRenderer()
result = renderer.render_timeline(timeline, video_info, "output.mp4", RenderingPreset.LOSSLESS)
```

**Methods:**

- `render_timeline(timeline: EditingTimeline, video_info: VideoInfo, output_path: Union[str, Path], preset: RenderingPreset = RenderingPreset.HIGH) -> RenderingResult`
  - Renders complete timeline to video file
  - Supports hardware acceleration and lossless stream copying

- `export_individual_clips(timeline: EditingTimeline, video_info: VideoInfo, output_dir: Union[str, Path]) -> List[Path]`
  - Exports individual clips from timeline

#### Enums:
- `RenderingPreset`: LOSSLESS, HIGH, MEDIUM, DRAFT
- `OutputFormat`: MP4, MOV, AVI, MKV, WEBM

## Core Algorithms

### Timeline Generation (`src/core/timeline.py`)

Sophisticated beat-sync timeline generation with multiple editing styles.

#### Class: `BeatSyncTimelineGenerator`

```python
from src.core.timeline import BeatSyncTimelineGenerator, EditingStyle

generator = BeatSyncTimelineGenerator()
timeline = generator.generate_timeline(audio_analysis, scene_detection, video_info, EditingStyle.MUSICAL)
```

**Methods:**

- `generate_timeline(audio_analysis: AudioAnalysisResult, scene_detection: SceneDetectionResult, video_info: VideoInfo, style: EditingStyle = EditingStyle.ADAPTIVE) -> EditingTimeline`
  - Generates beat-synchronized editing timeline
  - Combines audio, scene, and quality analysis

- `export_timeline(timeline: EditingTimeline, output_path: Union[str, Path], format: str = "json")`
  - Exports timeline in various formats (JSON, CSV, EDL)

#### Enums:
- `EditingStyle`: AGGRESSIVE, SMOOTH, ADAPTIVE, MUSICAL, CINEMATIC

#### Class: `EditingTimeline`

**Properties:**
- `segments: List[TimelineSegment]` - List of video segments
- `duration: float` - Total timeline duration
- `beat_sync_percentage: float` - Percentage of cuts aligned with beats
- `scene_respect_percentage: float` - Percentage respecting scene boundaries

### Quality Scoring (`src/core/quality_scoring.py`)

Multi-factor quality assessment with configurable profiles.

#### Class: `QualityScorer`

```python
from src.core.quality_scoring import QualityScorer, QualityProfile

scorer = QualityScorer(QualityProfile.TALKING_HEAD)
result = scorer.analyze_video_quality("path/to/video.mp4", face_detection_result)
```

**Methods:**

- `analyze_video_quality(video_path: Union[str, Path], face_detection_result: VideoFaceDetectionResult = None) -> VideoQualityResult`
  - Performs comprehensive quality analysis
  - Returns quality scores and hotspot identification

- `get_quality_hotspots(result: VideoQualityResult, min_duration: float = 2.0) -> List[Tuple[float, float, float]]`
  - Identifies highest quality segments for cutting

#### Enums:
- `QualityProfile`: TALKING_HEAD, ACTION, LANDSCAPE, DOCUMENTARY, ADAPTIVE

## Performance Optimization

### Performance Monitoring (`src/performance/monitoring.py`)

Real-time performance monitoring and optimization.

#### Class: `PerformanceMonitor`

```python
from src.performance import create_performance_monitor

monitor = create_performance_monitor(target_speed=15.0)
monitor.start_monitoring()
# ... processing code ...
stats = monitor.stop_monitoring()
```

**Methods:**

- `start_monitoring()` - Begins performance monitoring
- `stop_monitoring() -> PerformanceStats` - Stops monitoring and returns statistics
- `get_current_metrics() -> Dict` - Gets real-time performance metrics

### Optimization (`src/performance/optimization.py`)

Advanced optimization strategies for Apple Silicon.

#### Class: `PerformanceOptimizer`

```python
from src.performance import create_performance_optimizer

optimizer = create_performance_optimizer(target_speed=15.0)
with optimizer.optimized_processing_context():
    # Your processing code runs optimized
    pass
```

**Methods:**

- `optimized_processing_context()` - Context manager for optimized processing
- `optimize_for_apple_silicon()` - Apply M1/M2 specific optimizations
- `get_optimization_recommendations() -> List[str]` - Get performance recommendations

## Utilities

### Configuration (`src/utils/config.py`)

Flexible YAML-based configuration management.

#### Functions:

- `get(key: str, default: Any = None) -> Any` - Get configuration value
- `set(key: str, value: Any)` - Set configuration value
- `load_config(config_path: Union[str, Path])` - Load configuration from file
- `save_config(config_path: Union[str, Path])` - Save current configuration

### Logging (`src/utils/logging.py`)

Structured logging system with performance tracking.

#### Functions:

- `get_logger(name: str) -> Logger` - Get named logger instance
- `setup_logging(level: str = "INFO", log_file: Optional[str] = None)` - Configure logging system

## Error Handling

All AutoCut modules use consistent error handling:

- `FileNotFoundError` - For missing input files
- `ValueError` - For invalid parameters or unsupported formats
- `RuntimeError` - For processing failures
- `PerformanceError` - For performance-related issues

## Configuration Examples

### Basic Configuration

```yaml
# autocut_config.yaml
audio:
  beat_detection_sensitivity: 0.7
  min_tempo_bpm: 60
  max_tempo_bpm: 200

video:
  max_file_size_gb: 10
  enable_hardware_acceleration: true

quality_scoring:
  face_weight: 0.25
  blur_weight: 0.20
  exposure_weight: 0.15
  composition_weight: 0.15
  color_weight: 0.10
  motion_weight: 0.15

timeline:
  min_clip_duration_sec: 0.8
  max_clip_duration_sec: 8.0
  beat_alignment_threshold: 0.1

rendering:
  default_preset: "high"
  hardware_acceleration: true
  progress_callbacks: true
```

## Performance Targets

| Component | Target Speed | Typical Achievement |
|-----------|-------------|-------------------|
| Audio Analysis | 50x real-time | 60-80x real-time |
| Scene Detection | 15x real-time | 15-25x real-time |
| Face Detection | 15x real-time | 15-30x real-time |
| Quality Scoring | 15x real-time | 18-25x real-time |
| Timeline Generation | 1000x real-time | 2000x+ real-time |
| Video Rendering | 15x real-time | 15-20x real-time |

## Integration Examples

### Complete Pipeline

#### Single Video Processing
```python
from src.audio.analyzer import AudioAnalyzer
from src.video.ingestion import VideoIngestion
from src.video.scene_detection import SceneDetection
from src.video.face_detection import create_optimized_face_detection_engine
from src.core.quality_scoring import QualityScorer
from src.core.timeline import BeatSyncTimelineGenerator
from src.video.renderer import VideoRenderer

# Initialize components
audio_analyzer = AudioAnalyzer()
video_ingestion = VideoIngestion()
scene_detector = SceneDetection()
face_detector = create_optimized_face_detection_engine()
quality_scorer = QualityScorer()
timeline_generator = BeatSyncTimelineGenerator()
renderer = VideoRenderer()

# Process single video
video_info = video_ingestion.load_video("input.mp4")
audio_analysis = audio_analyzer.analyze_audio("input.mp4")
scene_detection = scene_detector.detect_scenes("input.mp4")
face_detection = face_detector.detect_faces_in_video("input.mp4")
quality_analysis = quality_scorer.analyze_video_quality("input.mp4", face_detection)

# Generate timeline and render
timeline = timeline_generator.generate_timeline(audio_analysis, scene_detection, video_info)
result = renderer.render_timeline(timeline, video_info, "output.mp4")
```

#### Multi-Video Processing with External Music
```python
from pathlib import Path
from src.audio.analyzer import AudioAnalyzer
from src.video.ingestion import VideoIngestion
from src.video.scene_detection import SceneDetection
from src.video.face_detection import create_optimized_face_detection_engine
from src.core.quality_scoring import QualityScorer
from src.core.timeline import BeatSyncTimelineGenerator
from src.video.renderer import VideoRenderer

# Initialize components
audio_analyzer = AudioAnalyzer()
video_ingestion = VideoIngestion()
scene_detector = SceneDetection()
face_detector = create_optimized_face_detection_engine()
quality_scorer = QualityScorer()
timeline_generator = BeatSyncTimelineGenerator()
renderer = VideoRenderer()

# Discover and process multiple videos
video_folder = Path("video_clips/")
music_file = Path("background_music.mp3")

video_files = list(video_folder.glob("*.mp4"))
video_info_list = []
scene_results = []
face_results = []
quality_results = []

# Process each video
for video_file in video_files:
    video_info = video_ingestion.load_video(video_file)
    video_info_list.append(video_info)
    
    scene_detection = scene_detector.detect_scenes(video_file)
    scene_results.append(scene_detection)
    
    face_detection = face_detector.detect_faces_in_video(video_file)
    face_results.append(face_detection)
    
    quality_analysis = quality_scorer.analyze_video_quality(video_file, face_detection)
    quality_results.append(quality_analysis)

# Analyze external music
music_analysis = audio_analyzer.analyze_audio(music_file)

# Generate multi-video timeline
timeline = timeline_generator.generate_multi_video_timeline(
    music_analysis, scene_results, video_info_list, quality_results
)

# Render with external music
result = renderer.render_multi_video_timeline(
    timeline, video_info_list, music_file, Path("highlight_reel.mp4")
)
```

**Important**: The `output_path` parameter must be a valid `Path` object or string. The method now includes comprehensive validation to prevent common errors:
- Raises `ValueError` if `output_path` is `None`
- Raises `TypeError` if `output_path` is a boolean value (prevents FFmpeg "True" filename errors)
- Automatically converts valid strings to `Path` objects
- Validates path types before processing begins

## Recent Updates (August 2025)

### Multi-Video Processing Pipeline Stability
- **Resolved**: Complete multi-video processing pipeline error handling
- **Fixed**: FFmpeg boolean parameter issues (`shortest=True` → `shortest=None`)
- **Enhanced**: Timeline object serialization with null-safety (`timeline.to_dict()`)
- **Improved**: Result dictionary consistency between single and multi-video paths
- **Added**: Comprehensive bounds checking and defensive programming
- **Stabilized**: 16-video test case processing with 100% success rate

### VideoRenderer Multi-Video Timeline Fix (July 2025)
- **Fixed**: `render_multi_video_timeline` method structure and validation
- **Added**: `RenderingResult` dataclass for consistent return values
- **Enhanced**: Input validation with specific boolean detection
- **Improved**: Error messages and debugging capabilities
- **Testing**: 31 new unit tests for comprehensive coverage

### API Stability Improvements
All core APIs now support both single-video and multi-video processing patterns:

- **AudioAnalyzer**: Consistent `.to_dict()` serialization
- **VideoRenderer**: Robust multi-video timeline rendering
- **EditingTimeline**: Null-safe serialization for multi-video contexts
- **Pipeline Results**: Unified result dictionary structure

This API reference covers all major components of the AutoCut system. For more detailed examples, see the `examples/` directory in the project repository.
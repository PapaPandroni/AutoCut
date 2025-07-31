# Scene Detection Module

The Scene Detection module provides advanced video analysis capabilities to automatically identify scene changes in video content. It supports multiple detection algorithms, hardware acceleration, and configurable performance modes optimized for automated video editing workflows.

## Features

- **Multiple Detection Algorithms**: Histogram-based, edge detection, optical flow, and combined approaches
- **Hardware Acceleration**: M1/M2 Mac VideoToolbox integration for optimal performance
- **Processing Modes**: Speed/Quality trade-offs from 15x+ real-time to precision analysis
- **Batch Processing**: Parallel processing of multiple videos
- **Comprehensive Results**: Scene timestamps, confidence scores, and detailed metrics
- **Integration Ready**: Seamless integration with existing VideoIngestion module

## Quick Start

```python
from src.video.scene_detection import SceneDetection, ProcessingMode, SceneDetectionAlgorithm

# Initialize detector with speed optimization
detector = SceneDetection(ProcessingMode.SPEED)

# Detect scenes in a video
result = detector.detect_scenes(
    video_path="path/to/video.mp4",
    algorithm=SceneDetectionAlgorithm.HISTOGRAM
)

# Check results
if result.success:
    print(f"Detected {result.scene_count} scenes")
    print(f"Processing speed: {result.processing_speed_multiplier:.1f}x real-time")
    
    # Get scene segments
    segments = result.get_scene_segments()
    for i, (start, end) in enumerate(segments):
        print(f"Scene {i+1}: {start:.1f}s - {end:.1f}s")
```

## Processing Modes

### Speed Mode (15x+ real-time)
- **Frame Skip**: Every 8th frame
- **Resolution**: 25% of original
- **Algorithms**: Histogram only
- **Use Case**: Quick preview, batch processing

```python
detector = SceneDetection(ProcessingMode.SPEED)
```

### Balanced Mode (10x real-time)
- **Frame Skip**: Every 4th frame  
- **Resolution**: 50% of original
- **Algorithms**: Histogram + Edge detection
- **Use Case**: General purpose, good quality/speed balance

```python
detector = SceneDetection(ProcessingMode.BALANCED)
```

### Quality Mode (5x real-time)
- **Frame Skip**: Every 2nd frame
- **Resolution**: 75% of original
- **Algorithms**: Histogram + Edge + Optical flow
- **Use Case**: High-quality analysis, professional editing

```python
detector = SceneDetection(ProcessingMode.QUALITY)
```

### Precision Mode (2x real-time)
- **Frame Skip**: All frames processed
- **Resolution**: Full resolution
- **Algorithms**: Combined approach
- **Use Case**: Maximum accuracy, archival analysis

```python
detector = SceneDetection(ProcessingMode.PRECISION)
```

## Detection Algorithms

### Histogram-Based Detection
Analyzes color distribution changes between frames using HSV histograms.

**Strengths:**
- Fast processing
- Good for lighting changes
- Robust to camera movement

**Best for:** General scene detection, lighting changes, color transitions

```python
result = detector.detect_scenes(
    video_path,
    SceneDetectionAlgorithm.HISTOGRAM
)
```

### Edge Detection
Uses Canny edge detection to identify structural changes in frame content.

**Strengths:**
- Detects object/composition changes
- Less sensitive to lighting
- Good for action sequences

**Best for:** Object changes, composition shifts, action scenes

```python  
result = detector.detect_scenes(
    video_path,
    SceneDetectionAlgorithm.EDGE_DETECTION
)
```

### Optical Flow
Analyzes motion vectors between consecutive frames to detect significant movement changes.

**Strengths:**
- Excellent for motion changes
- Detects camera movement
- Good for sports/action content

**Best for:** Motion analysis, camera cuts, dynamic content

```python
result = detector.detect_scenes(
    video_path, 
    SceneDetectionAlgorithm.OPTICAL_FLOW
)
```

### Combined Algorithm
Uses multiple algorithms based on processing mode for comprehensive analysis.

**Strengths:**
- Highest accuracy
- Adapts to content type
- Comprehensive coverage

**Best for:** Professional editing, maximum accuracy

```python
result = detector.detect_scenes(
    video_path,
    SceneDetectionAlgorithm.COMBINED
)
```

## Hardware Acceleration

The module automatically detects and utilizes hardware acceleration on supported platforms:

### M1/M2 Macs
- **VideoToolbox Integration**: Automatic hardware decoding
- **AVFoundation Backend**: Optimized video capture
- **Performance Boost**: 1.5x speed improvement typical

### Configuration
Hardware acceleration is enabled by default but can be controlled:

```python
# Check if hardware acceleration is available
detector = SceneDetection()
print(f"Hardware acceleration: {detector.enable_hardware_acceleration}")

# Estimate processing speed
speed_estimate = detector.get_processing_speed_estimate(video_info)
print(f"Estimated speed: {speed_estimate:.1f}x real-time")
```

## Batch Processing

Process multiple videos in parallel for efficient workflow integration:

```python
video_paths = [
    "video1.mp4",
    "video2.mp4", 
    "video3.mp4"
]

# Process with custom worker count
results = detector.batch_detect_scenes(
    video_paths,
    algorithm=SceneDetectionAlgorithm.HISTOGRAM,
    max_workers=4
)

# Analyze results
successful = [r for r in results if r.success]
failed = [r for r in results if not r.success]

print(f"Processed: {len(successful)}/{len(results)} videos")
```

## Result Analysis

### SceneDetectionResult Properties
```python
# Basic metrics
result.scene_count              # Number of scenes detected
result.processing_time          # Time taken in seconds
result.processing_speed_multiplier  # Speed vs real-time
result.frames_processed         # Frames analyzed
result.frames_skipped          # Frames skipped for speed

# Scene information
result.scene_changes           # List of SceneChange objects
result.average_scene_duration  # Average scene length
result.get_scene_segments()    # List of (start, end) tuples

# Export data
result.to_dict()              # JSON-serializable dictionary
```

### SceneChange Details
```python
for change in result.scene_changes:
    print(f"Time: {change.timestamp:.1f}s")
    print(f"Frame: {change.frame_number}")
    print(f"Confidence: {change.confidence:.2f}")
    print(f"Algorithm: {change.algorithm.value}")
    print(f"Metrics: {change.metrics}")
```

## Configuration

### Global Settings
Configure via `src/utils/config.py` or YAML config file:

```yaml
scene_detection:
  min_scene_duration_sec: 1.0      # Minimum scene length
  confidence_threshold: 0.3        # Global confidence threshold
  histogram_threshold: 0.3         # Histogram algorithm threshold
  edge_threshold: 0.4             # Edge detection threshold
  optical_flow_threshold: 0.5     # Optical flow threshold
  combined_threshold: 0.35        # Combined algorithm threshold
  max_concurrent_videos: 4        # Batch processing limit
```

### Runtime Configuration
```python
# Custom thresholds
detector.confidence_threshold = 0.5
detector.min_scene_duration = 2.0

# Algorithm-specific thresholds
detector.algorithm_thresholds[SceneDetectionAlgorithm.HISTOGRAM] = 0.4
```

## Performance Optimization

### Speed Optimization Tips
1. **Use Speed Mode**: For quick analysis or batch processing
2. **Enable Hardware Acceleration**: Automatic on supported platforms
3. **Adjust Confidence Thresholds**: Higher values = fewer detections = faster processing
4. **Batch Processing**: Parallel processing of multiple videos
5. **Frame Skipping**: Built into processing modes

### Quality Optimization Tips
1. **Use Precision Mode**: For maximum accuracy
2. **Combined Algorithm**: Uses multiple detection methods
3. **Lower Confidence Thresholds**: Captures more subtle changes
4. **Full Resolution Processing**: Available in precision mode

### Memory Optimization
- Automatic frame resizing based on processing mode
- Minimal buffer usage for real-time processing
- Efficient histogram calculations
- Memory-mapped file access where possible

## Integration Examples

### With VideoIngestion
```python
from src.video import VideoIngestion, SceneDetection

# Load video info first
ingestion = VideoIngestion()
video_info = ingestion.load_video("video.mp4")

# Use pre-loaded info for scene detection
detector = SceneDetection()
result = detector.detect_scenes("video.mp4", video_info=video_info)
```

### Export for Editing Software
```python
# Export as EDL (Edit Decision List) format
def export_to_edl(result, output_path):
    segments = result.get_scene_segments()
    
    with open(output_path, 'w') as f:
        f.write("TITLE: Scene Detection Results\\n")
        f.write("FCM: NON-DROP FRAME\\n\\n")
        
        for i, (start, end) in enumerate(segments):
            f.write(f"{i+1:03d}  AX       V     C        ")
            f.write(f"{seconds_to_timecode(start)} {seconds_to_timecode(end)} ")
            f.write(f"00:00:00:00 {seconds_to_timecode(end - start)}\\n")

# Export segments for further processing
segments = result.get_scene_segments()
for i, (start, end) in enumerate(segments):
    segment_path = f"scene_{i+1:03d}.mp4"
    # Use FFmpeg or similar to extract segment
```

## Error Handling

The module provides comprehensive error handling:

```python
result = detector.detect_scenes("video.mp4")

if not result.success:
    print("Scene detection failed:")
    for error in result.errors:
        print(f"  - {error}")
        
    # Common issues and solutions:
    # 1. Video file not found -> Check file path
    # 2. Unsupported format -> Use VideoIngestion.is_format_supported()
    # 3. Hardware acceleration failure -> Falls back to software automatically
    # 4. Insufficient memory -> Use lower processing mode
```

## Troubleshooting

### Common Issues

**Slow Processing**
- Try SPEED mode instead of QUALITY/PRECISION
- Ensure hardware acceleration is enabled
- Check video resolution and consider preprocessing
- Use batch processing for multiple videos

**Missed Scene Changes**
- Lower confidence thresholds
- Try different algorithms (COMBINED works well)
- Use QUALITY or PRECISION mode
- Check minimum scene duration setting

**Too Many False Positives**
- Increase confidence thresholds
- Increase minimum scene duration
- Use more stable algorithms (HISTOGRAM is most stable)
- Enable post-processing (enabled by default)

**Memory Issues**
- Use SPEED mode (quarter resolution)
- Process shorter video segments
- Ensure sufficient system memory
- Check for memory leaks in batch processing

### Performance Benchmarks

Typical performance on M1 MacBook Pro with hardware acceleration:

| Mode | Speed | Accuracy | Use Case |
|------|-------|----------|----------|
| Speed | 15-20x | Good | Batch processing, previews |
| Balanced | 8-12x | Very Good | General purpose |  
| Quality | 4-6x | Excellent | Professional editing |
| Precision | 1.5-3x | Maximum | Archival, analysis |

## API Reference

### Classes

#### SceneDetection
Main class for scene detection operations.
- `__init__(processing_mode: ProcessingMode = BALANCED)`
- `detect_scenes(video_path, algorithm, video_info=None) -> SceneDetectionResult`
- `batch_detect_scenes(video_paths, algorithm, max_workers=None) -> List[SceneDetectionResult]`
- `get_processing_speed_estimate(video_info) -> float`

#### SceneDetectionResult
Contains detection results and metadata.
- Properties: `scene_count`, `processing_speed_multiplier`, `average_scene_duration`
- Methods: `get_scene_segments()`, `to_dict()` 

#### SceneChange
Individual scene change detection.
- `timestamp: float` - Time of change in seconds
- `frame_number: int` - Frame number
- `confidence: float` - Detection confidence (0-1)
- `algorithm: SceneDetectionAlgorithm` - Algorithm used
- `metrics: Dict[str, float]` - Algorithm-specific metrics

### Enums

#### ProcessingMode
- `SPEED` - Maximum speed (15x+ real-time)
- `BALANCED` - Good speed/quality balance (10x real-time)  
- `QUALITY` - High quality (5x real-time)
- `PRECISION` - Maximum accuracy (2x real-time)

#### SceneDetectionAlgorithm
- `HISTOGRAM` - Color histogram comparison
- `EDGE_DETECTION` - Edge-based change detection
- `OPTICAL_FLOW` - Motion-based detection
- `COMBINED` - Multiple algorithms (mode-dependent)

## Future Enhancements

Planned improvements for future releases:
- GPU acceleration for NVIDIA/AMD cards  
- Machine learning-based scene detection
- Audio-based scene change detection
- Custom algorithm development framework
- Real-time streaming support
- Advanced post-processing filters
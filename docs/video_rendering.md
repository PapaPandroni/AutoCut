# Video Rendering Engine

The AutoCut video rendering engine is a high-performance system optimized for speed and quality, capable of achieving 15x real-time performance through FFmpeg stream copying.

## Features

### Core Capabilities
- **Lossless Stream Copying**: Up to 15x real-time performance with no quality loss
- **Hardware Acceleration**: Automatic detection and utilization of VideoToolbox, NVENC, and QSV
- **Multiple Quality Presets**: Lossless, High, Medium, and Draft presets for different use cases
- **Multiple Output Formats**: MP4, MOV, AVI, MKV, and WebM support
- **Frame-Accurate Cutting**: Precise cuts with audio-video synchronization preservation

### Performance Optimizations
- **Parallel Processing**: Concurrent rendering for batch operations
- **Memory Efficiency**: Optimized for large video files
- **Automatic Hardware Detection**: Uses best available encoders
- **Temporary File Management**: Automatic cleanup with error recovery

### Integration Features
- **Progress Callbacks**: Real-time progress updates for UI integration
- **Individual Clip Export**: Export timeline segments as separate files
- **Comprehensive Statistics**: Detailed performance metrics and render stats
- **Error Handling**: Robust error recovery and logging

## Quick Start

```python
from src.video.renderer import VideoRenderer, create_render_options

# Initialize renderer
renderer = VideoRenderer()

# Create render options
options = create_render_options(
    quality="lossless",      # or "high", "medium", "draft"
    output_format="mp4",     # or "mov", "avi", "mkv", "webm"  
    resolution="1080p"       # optional resolution override
)

# Render timeline
stats = renderer.render_timeline(
    timeline=your_timeline,
    output_path="output.mp4",
    options=options,
    progress_callback=lambda p: print(f"Progress: {p.progress_percentage:.1f}%")
)

print(f"Rendered in {stats.processing_time:.1f}s ({stats.speed_factor:.1f}x real-time)")
```

## Quality Presets

### Lossless (Recommended for final output)
- **Method**: Stream copying (no re-encoding)
- **Speed**: 15x real-time
- **Quality**: Perfect (no quality loss)
- **Use Case**: Final exports, archival

### High (Visually lossless)
- **Method**: H.264 CRF 18, slower preset
- **Speed**: 1-3x real-time  
- **Quality**: Visually lossless
- **Use Case**: High-quality exports

### Medium (Balanced)
- **Method**: H.264 CRF 23, medium preset
- **Speed**: 2-5x real-time
- **Quality**: High quality, smaller files
- **Use Case**: General purpose exports

### Draft (Fast preview)
- **Method**: H.264 CRF 28, ultrafast preset
- **Speed**: 3-8x real-time
- **Quality**: Good for previews
- **Use Case**: Quick previews, drafts

## Output Formats

| Format | Container | Video Codec | Audio Codec | Use Case |
|--------|-----------|-------------|-------------|----------|
| MP4    | MP4       | H.264       | AAC         | Universal compatibility (recommended) |
| MOV    | QuickTime | H.264       | AAC         | Apple ecosystem, professional workflows |
| AVI    | AVI       | H.264       | MP3         | Legacy Windows compatibility |
| MKV    | Matroska  | H.264       | AAC         | Advanced features, open source |
| WebM   | WebM      | VP9         | Opus        | Web optimization |

## Hardware Acceleration

The renderer automatically detects and uses available hardware acceleration:

### VideoToolbox (macOS)
- **Encoders**: H.264, H.265, ProRes
- **Performance**: 3-5x real-time encoding
- **Platform**: macOS with Apple Silicon or Intel

### NVENC (NVIDIA)
- **Encoders**: H.264, H.265  
- **Performance**: 4-8x real-time encoding
- **Platform**: NVIDIA GPUs with NVENC support

### Quick Sync Video (Intel)
- **Encoders**: H.264, H.265
- **Performance**: 2-4x real-time encoding  
- **Platform**: Intel CPUs with integrated graphics

## Performance Benchmarks

### Expected Performance (1080p 30fps video)

| Operation | Speed | Quality | Use Case |
|-----------|-------|---------|----------|
| Stream Copy | 15x real-time | Lossless | Final exports |
| Hardware Encode | 3-5x real-time | High/Medium | Quality exports |
| Software Encode | 0.5-2x real-time | All presets | Fallback |
| Analysis | 10x real-time | N/A | Timeline generation |

### Memory Usage
- **1080p video**: ~2-4GB peak memory usage
- **4K video**: ~6-8GB peak memory usage  
- **Optimization**: Chunked processing for very large files

## Advanced Usage

### Individual Clip Export
```python
# Export each timeline segment as individual clips
stats_list = renderer.export_individual_clips(
    timeline=timeline,
    output_dir="clips/",
    options=options
)

for i, stats in enumerate(stats_list):
    print(f"Clip {i+1}: {stats.processing_time:.1f}s")
```

### Segment Range Rendering
```python
# Render only segments 2-5 from the timeline
stats = renderer.render_segment_range(
    timeline=timeline,
    start_segment=2,
    end_segment=5,
    output_path="segment_range.mp4",
    options=options
)
```

### Custom Resolution and Frame Rate
```python
options = create_render_options(
    quality="high",
    resolution="1280x720",  # Custom resolution
    fps=24.0               # Custom frame rate
)
```

### Progress Monitoring
```python
def detailed_progress(progress):
    print(f"Segment {progress.current_segment}/{progress.total_segments}")
    print(f"Progress: {progress.progress_percentage:.1f}%")
    print(f"Speed: {progress.current_fps:.1f} FPS")
    print(f"ETA: {progress.estimated_remaining:.1f}s")

stats = renderer.render_timeline(timeline, output_path, options, detailed_progress)
```

## Configuration

The renderer uses configuration settings from `src/utils/config.py`:

```python
'rendering': {
    'max_concurrent_renders': 2,        # Concurrent render jobs
    'chunk_duration_sec': 30.0,         # Processing chunk size
    'enable_hardware_acceleration': True, # Hardware acceleration
    'prefer_stream_copy': True,          # Prefer lossless when possible
    'frame_accurate_cuts': True          # Frame-accurate cutting
}
```

## Error Handling

The renderer provides comprehensive error handling:

```python
try:
    stats = renderer.render_timeline(timeline, output_path, options)
    print(f"Success: {stats.speed_factor:.1f}x real-time")
except ValueError as e:
    print(f"Invalid parameters: {e}")
except RuntimeError as e:
    print(f"Rendering failed: {e}")
except FileNotFoundError as e:
    print(f"File not found: {e}")
```

## Best Practices

### For Maximum Speed
1. Use **lossless** preset for stream copying
2. Ensure output format matches input format
3. Avoid resolution or frame rate changes
4. Enable hardware acceleration

### For Best Quality
1. Use **high** preset with slower encoding
2. Choose appropriate bitrates for target resolution
3. Consider two-pass encoding for critical content
4. Preserve original color space and HDR when possible

### For Batch Processing
1. Enable parallel processing for multiple clips
2. Use appropriate number of worker threads
3. Monitor memory usage for large batches
4. Implement proper error recovery

### For Production Use
1. Validate input files before rendering
2. Implement comprehensive logging
3. Provide user progress feedback
4. Handle cancellation gracefully
5. Clean up temporary files properly

## Troubleshooting

### Common Issues

**Slow rendering performance:**
- Check if hardware acceleration is enabled
- Verify FFmpeg installation and codec support
- Monitor system resources (CPU, memory, GPU)
- Consider using draft preset for testing

**Audio sync issues:**
- Ensure frame-accurate cuts are enabled
- Check input video for variable frame rate
- Verify audio codec compatibility

**Memory usage:**
- Enable chunked processing for large files
- Reduce concurrent render job count
- Monitor temporary disk space usage

**Codec compatibility:**
- Verify FFmpeg codec support
- Check hardware encoder availability
- Use software fallback when needed

### Getting Help

1. Check the logs for detailed error information
2. Verify FFmpeg installation: `ffmpeg -version`
3. Test with different quality presets
4. Run the included demo scripts for validation
5. Consult the AutoCut documentation for advanced topics
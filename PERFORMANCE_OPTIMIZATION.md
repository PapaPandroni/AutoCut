# AutoCut Performance Optimization Suite

A comprehensive performance optimization system designed to achieve **15x real-time video processing** on M1/M2 Macs. This suite provides advanced memory management, intelligent frame sampling, hardware acceleration, and adaptive optimization to maximize AutoCut's video editing performance.

## 🎯 Performance Targets

| Mode | Target Speed | Quality Level | Use Case |
|------|-------------|---------------|----------|
| **Speed** | 15x+ real-time | 70%+ quality | Production editing, real-time preview |
| **Balanced** | 10x real-time | 85%+ quality | Most editing workflows |
| **Quality** | 5x real-time | 95%+ quality | High-quality output |
| **Precision** | 2x real-time | 100% quality | Research, development |

## 🚀 Key Features

### 1. Comprehensive Performance Benchmarking
- **Component-level profiling** with detailed timing and memory analysis
- **End-to-end pipeline benchmarks** for different video resolutions and durations
- **Stress testing** with long videos and high resolutions
- **Performance regression detection** to catch performance degradations
- **Detailed reporting** with bottleneck identification and optimization suggestions

### 2. Advanced Memory Optimization
- **Memory pools** for efficient frame buffer management
- **Streaming processing** for large video files without memory pressure
- **Intelligent garbage collection** tuning for video processing workloads
- **Memory-mapped files** for ultra-large video processing
- **Adaptive memory limits** based on available system memory

### 3. Intelligent Frame Sampling
- **Dynamic sampling rates** that adapt to performance targets
- **Content-aware sampling** that preserves important frames
- **Quality-preserving algorithms** that maintain visual fidelity
- **Adaptive adjustment** based on real-time performance feedback

### 4. Real-Time Performance Monitoring
- **Live performance tracking** with bottleneck detection
- **Adaptive optimization** that adjusts settings in real-time
- **Resource monitoring** (CPU, memory, GPU utilization)
- **Performance state management** with automatic interventions
- **Comprehensive dashboards** for performance visualization

### 5. Apple Silicon Hardware Optimization
- **VideoToolbox integration** for hardware-accelerated encoding/decoding
- **Metal Performance Shaders** for GPU-accelerated image processing
- **Optimized threading** for M1/M2 performance and efficiency cores
- **Neural Engine utilization** for ML-based processing
- **Hardware-specific tuning** for different Apple Silicon variants

### 6. Performance Regression Testing
- **Automated test suites** for all performance modes
- **Baseline management** with git integration
- **Quality vs. performance validation** to ensure optimization doesn't degrade quality
- **CI/CD integration** for continuous performance monitoring

## 📦 Installation

The performance optimization suite is included with AutoCut. Ensure you have the required dependencies:

```bash
# Install AutoCut with performance optimization dependencies
pip install -r requirements.txt

# For Apple Silicon optimizations, ensure you have:
# - FFmpeg with VideoToolbox support
# - Latest OpenCV with optimization support
brew install ffmpeg
```

## 🔧 Quick Start

### Basic Usage

```python
from src.performance import create_performance_optimizer, create_performance_monitor

# Create performance optimizer for 15x real-time target
optimizer = create_performance_optimizer(
    target_speed=15.0,
    max_memory_mb=4096.0,
    strategy='aggressive'
)

# Start real-time monitoring
monitor = create_performance_monitor(target_speed=15.0)
monitor.start_monitoring()

# Use optimized processing context
with optimizer.optimized_processing_context():
    # Your AutoCut pipeline code here
    result = process_video_optimized(input_path, output_path)

monitor.stop_monitoring()
```

### Hardware-Optimized Processing

```python
from src.performance.hardware_optimization import create_apple_silicon_optimizer

# Initialize Apple Silicon optimizations
hardware_optimizer = create_apple_silicon_optimizer()

# Get optimal settings for your video
video_settings = hardware_optimizer.get_optimal_video_settings(
    resolution=(1920, 1080),
    fps=30.0,
    codec='h264'
)

# Apply component-specific optimizations
for component in ['video_ingestion', 'scene_detection', 'face_detection']:
    opts = hardware_optimizer.optimize_component_for_hardware(component)
    configure_component(component, opts)
```

### Performance Benchmarking

```python
from src.performance.benchmarking import create_benchmark_suite

# Create and run comprehensive benchmarks
benchmark_suite = create_benchmark_suite()
results = benchmark_suite.run_full_suite(max_scenarios=10)

# Analyze results
for result in results:
    print(f"{result.benchmark_id}: {result.achieved_speed_factor:.1f}x speed")
    if not result.target_met:
        print(f"  Bottlenecks: {result.bottlenecks}")
        print(f"  Suggestions: {result.optimization_suggestions}")
```

## 🎛️ Configuration

### Optimization Configuration

```python
from src.performance.optimization import OptimizationConfig, OptimizationStrategy

config = OptimizationConfig(
    target_speed_multiplier=15.0,    # 15x real-time target
    max_memory_mb=4096.0,           # Memory limit
    max_cpu_cores=8,                # CPU core limit
    enable_gpu_acceleration=True,    # Use GPU/Metal when available
    optimization_strategy=OptimizationStrategy.AGGRESSIVE,
    
    # Advanced settings
    adaptive_quality=True,           # Dynamically adjust quality for speed
    dynamic_sampling=True,           # Adaptive frame sampling
    memory_pool_size_mb=512.0,      # Memory pool size
    gc_frequency=100                 # Garbage collection frequency
)
```

### Performance Modes

Configure AutoCut to use different performance modes:

```python
# Speed mode: Maximum performance, good quality
autocut_pipeline.set_performance_mode('speed', {
    'frame_sampling_rate': 0.3,      # Process 30% of frames
    'quality_threshold': 0.7,        # 70% quality acceptable
    'hardware_acceleration': True,
    'parallel_workers': 8
})

# Balanced mode: Good performance and quality
autocut_pipeline.set_performance_mode('balanced', {
    'frame_sampling_rate': 0.6,      # Process 60% of frames
    'quality_threshold': 0.85,       # 85% quality target
    'hardware_acceleration': True,
    'parallel_workers': 6
})
```

## 📊 Monitoring and Analytics

### Real-Time Performance Dashboard

```python
from src.performance.monitoring import create_performance_monitor

monitor = create_performance_monitor()
monitor.start_monitoring()

# Add custom performance callback
def performance_callback(event_type, data):
    if event_type == 'bottleneck_detected':
        print(f"Bottleneck detected: {data['bottleneck_type']}")
        print(f"Suggested actions: {data['suggested_actions']}")

monitor.add_performance_callback(performance_callback)

# Get performance dashboard
dashboard = monitor.get_performance_dashboard()
print(f"Current state: {dashboard['current_state']}")
print(f"Speed factor: {dashboard['recent_performance']['mean']:.1f}x")
```

### Performance Regression Testing

```python
from src.performance.regression_testing import create_regression_test_suite

# Create regression test suite
test_suite = create_regression_test_suite()

# Run full regression test suite
results = test_suite.run_full_regression_suite()

# Check for regressions
regressions = [r for r in results if r.is_performance_regression]
if regressions:
    print(f"⚠️  {len(regressions)} performance regressions detected!")
    for regression in regressions:
        print(f"  {regression.test_id}: {regression.performance_ratio:.3f}x baseline")

# Update baselines after confirming performance improvements
test_suite.update_baselines(force=True)
```

## 🖥️ Apple Silicon Optimization

### Automatic Hardware Detection

The system automatically detects your Apple Silicon hardware and optimizes accordingly:

```python
from src.performance.hardware_optimization import create_apple_silicon_optimizer

optimizer = create_apple_silicon_optimizer()
hardware_summary = optimizer.get_hardware_summary()

print(f"Processor: {hardware_summary['processor_type']}")
print(f"Performance cores: {hardware_summary['core_configuration']['performance_cores']}")
print(f"GPU cores: {hardware_summary['gpu_configuration']['gpu_cores']}")
```

### VideoToolbox Integration

Automatic hardware acceleration for supported codecs:

```python
# VideoToolbox automatically used for:
# - H.264 decode/encode
# - HEVC/H.265 decode/encode  
# - ProRes decode/encode (on supported hardware)

# Get optimal encoder/decoder for your codec
decoder = optimizer.videotoolbox.get_optimal_decoder('h264')
encoder = optimizer.videotoolbox.get_optimal_encoder('h264')

if decoder:
    print(f"Using hardware decoder: {decoder}")
if encoder:
    print(f"Using hardware encoder: {encoder}")
```

### Metal GPU Acceleration

GPU acceleration for compute-intensive operations:

```python
# Metal automatically accelerates:
# - Image resizing and filtering
# - Color space conversions
# - Blur and edge detection operations
# - Custom compute shaders

# Check Metal availability
if optimizer.metal.metal_available:
    print("Metal GPU acceleration enabled")
else:
    print("Metal not available, using CPU fallback")
```

## 🔬 Benchmarking and Testing

### Running Comprehensive Benchmarks

```bash
# Run the complete benchmark suite
python examples/performance_optimization_demo.py --benchmark

# Run specific benchmark categories
python examples/performance_optimization_demo.py --hardware
python examples/performance_optimization_demo.py --regression
```

### Custom Benchmarks

```python
from src.performance.benchmarking import benchmark_autocut_component

# Benchmark individual components
def my_audio_analyzer(audio_path):
    # Your audio analysis code
    return analysis_result

# Benchmark the component
metrics = benchmark_autocut_component(
    my_audio_analyzer,
    'audio_analysis',
    target=PerformanceTarget.SPEED,
    '/path/to/test/audio.wav'
)

print(f"Execution time: {metrics.execution_time:.3f}s")
print(f"Memory usage: {metrics.memory_peak_mb:.1f} MB")
print(f"Throughput: {metrics.throughput:.1f} items/sec")
```

## 📈 Performance Tuning Tips

### For M1/M2 Base Models
- Use `balanced` or `speed` performance modes
- Enable aggressive frame sampling (30-50% of frames)
- Limit batch sizes to 4-6 frames to avoid memory pressure
- Enable VideoToolbox acceleration for supported codecs

### For M1/M2 Pro/Max/Ultra Models
- Can use `quality` mode for better output
- Increase batch sizes to 8-12 frames for better throughput
- Use all available performance cores
- Enable Metal GPU acceleration for image processing

### Memory Optimization
```python
# For videos > 5 minutes, use streaming processing
if video_duration > 300:  # 5 minutes
    config.memory_strategy = MemoryStrategy.STREAMING
    config.chunk_size_mb = 32.0  # Smaller chunks

# For high-resolution videos (4K+), reduce memory usage
if resolution[0] >= 3840:  # 4K width
    config.max_memory_mb = min(config.max_memory_mb, 2048.0)
    config.optimization_strategy = OptimizationStrategy.AGGRESSIVE
```

### Quality vs Speed Trade-offs
```python
# Adjust quality thresholds based on your needs
quality_thresholds = {
    'preview_editing': 0.6,      # 60% quality for fast preview
    'rough_cut': 0.75,           # 75% quality for rough cuts
    'final_output': 0.95,        # 95% quality for final delivery
    'archival': 1.0              # 100% quality for archival
}
```

## 🐛 Troubleshooting

### Performance Issues

1. **Not reaching 15x real-time target:**
   - Check `hardware_summary` to ensure all optimizations are enabled
   - Run regression tests to identify bottlenecks
   - Increase frame sampling aggressiveness
   - Reduce quality thresholds temporarily

2. **High memory usage:**
   - Enable streaming processing mode
   - Reduce batch sizes
   - Increase garbage collection frequency
   - Use memory pools for frequent allocations

3. **Hardware acceleration not working:**
   ```bash
   # Check FFmpeg VideoToolbox support
   ffmpeg -hwaccels
   
   # Should show "videotoolbox" in the list
   ```

### Common Configuration Issues

```python
# Issue: Performance monitor showing CPU saturation
# Solution: Reduce parallel workers
optimizer_config.max_cpu_cores = hardware_profile.performance_cores

# Issue: Memory pressure warnings
# Solution: Enable streaming mode and reduce memory limits
optimizer_config.memory_strategy = MemoryStrategy.STREAMING
optimizer_config.max_memory_mb = available_memory * 0.6  # 60% of available

# Issue: GPU not being utilized
# Solution: Check Metal availability and enable GPU operations
if hardware_optimizer.metal.metal_available:
    enable_metal_acceleration()
```

## 📚 API Reference

### Core Classes

- **`PerformanceOptimizer`**: Main optimization coordinator
- **`PerformanceMonitor`**: Real-time performance monitoring
- **`BenchmarkSuite`**: Comprehensive benchmarking framework
- **`AppleSiliconOptimizer`**: Hardware-specific optimizations
- **`RegressionTestSuite`**: Performance regression testing

### Key Methods

```python
# Performance optimization
optimizer.optimize_component_execution(func, *args, **kwargs)
optimizer.get_optimization_stats()

# Monitoring
monitor.record_component_performance(component, execution_time)
monitor.get_performance_dashboard()

# Benchmarking
benchmark_suite.run_component_benchmark(component, target)
benchmark_suite.run_pipeline_benchmark(scenario)

# Hardware optimization
hardware_optimizer.get_optimal_video_settings(resolution, fps, codec)
hardware_optimizer.optimize_component_for_hardware(component)
```

## 🤝 Contributing

When contributing performance optimizations:

1. **Always run regression tests** before submitting changes
2. **Include benchmark results** showing performance improvements
3. **Test on different Apple Silicon variants** when possible
4. **Document any quality trade-offs** made for performance gains
5. **Update baselines** after confirming improvements

```bash
# Before submitting PR, run:
python examples/performance_optimization_demo.py --regression
python examples/performance_optimization_demo.py --benchmark
```

## 📄 License

This performance optimization suite is part of AutoCut and subject to the same license terms.

---

## 🎯 Achieving 15x Real-Time Performance

The ultimate goal of this optimization suite is to achieve **15x real-time video processing** on M1/M2 Macs. This means:

- A **60-second video** should process in **4 seconds or less**
- A **10-minute video** should process in **40 seconds or less**
- **4K videos** should maintain at least **5x real-time** processing

With proper configuration and optimal hardware utilization, these targets are achievable while maintaining high video quality suitable for professional editing workflows.

**Ready to optimize your AutoCut performance? Start with the demo:**

```bash
python examples/performance_optimization_demo.py --all
```
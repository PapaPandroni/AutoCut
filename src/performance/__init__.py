"""
Performance optimization and monitoring module for AutoCut.

This module provides comprehensive performance analysis, optimization, and monitoring
capabilities designed to achieve 15x real-time processing for video editing workflows.

Key Features:
- Detailed performance profiling and bottleneck detection
- Memory optimization and resource management
- Intelligent frame sampling and parallel processing
- Real-time performance monitoring and adaptive optimization
- Hardware acceleration optimization for M1/M2 Macs
"""

from .benchmarking import (
    PerformanceBenchmark,
    BenchmarkSuite,
    ComponentProfiler,
    create_benchmark_suite
)

from .optimization import (
    PerformanceOptimizer,
    MemoryManager,
    FrameSamplingOptimizer,
    HardwareAcceleration
)

from .monitoring import (
    PerformanceMonitor,
    ResourceMonitor,
    BottleneckDetector,
    create_performance_monitor
)

__all__ = [
    'PerformanceBenchmark',
    'BenchmarkSuite', 
    'ComponentProfiler',
    'create_benchmark_suite',
    'PerformanceOptimizer',
    'MemoryManager',
    'FrameSamplingOptimizer',
    'HardwareAcceleration',
    'PerformanceMonitor',
    'ResourceMonitor',
    'BottleneckDetector',
    'create_performance_monitor'
]
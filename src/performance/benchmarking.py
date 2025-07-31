"""
Comprehensive performance benchmarking framework for AutoCut.

This module provides detailed performance analysis and profiling capabilities
for each component of the video editing pipeline, with focus on achieving
15x real-time processing performance.
"""

import time
import psutil
import threading
import gc
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable, NamedTuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import json
import csv
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import tracemalloc
import cProfile
import pstats
import io

from ..utils.logging import get_logger
from ..utils.config import config

logger = get_logger(__name__)


class BenchmarkType(Enum):
    """Types of performance benchmarks"""
    COMPONENT = "component"       # Individual component benchmark
    PIPELINE = "pipeline"         # End-to-end pipeline benchmark
    STRESS = "stress"            # Stress testing with various loads
    REGRESSION = "regression"     # Performance regression testing
    MEMORY = "memory"            # Memory usage analysis
    HARDWARE = "hardware"        # Hardware acceleration testing


class PerformanceTarget(Enum):
    """Performance targets for different use cases"""
    SPEED = "speed"              # 15x+ real-time
    BALANCED = "balanced"        # 10x real-time
    QUALITY = "quality"          # 5x real-time
    PRECISION = "precision"      # 2x real-time


@dataclass
class ResourceMetrics:
    """System resource utilization metrics"""
    timestamp: float
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    gpu_utilization: Optional[float] = None
    disk_io_mb: float = 0.0
    network_io_mb: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'cpu_percent': self.cpu_percent,
            'memory_mb': self.memory_mb,
            'memory_percent': self.memory_percent,
            'gpu_utilization': self.gpu_utilization,
            'disk_io_mb': self.disk_io_mb,
            'network_io_mb': self.network_io_mb
        }


@dataclass
class ComponentPerformanceMetrics:
    """Performance metrics for a single component"""
    component_name: str
    execution_time: float
    memory_peak_mb: float
    memory_delta_mb: float
    cpu_utilization: float
    throughput: float  # Items processed per second
    
    # Detailed timing breakdown
    initialization_time: float = 0.0
    processing_time: float = 0.0
    cleanup_time: float = 0.0
    
    # Quality metrics
    accuracy_score: Optional[float] = None
    quality_degradation: Optional[float] = None
    
    # Resource efficiency
    memory_efficiency: float = 0.0  # Throughput per MB
    cpu_efficiency: float = 0.0     # Throughput per CPU %
    
    def __post_init__(self):
        """Calculate efficiency metrics"""
        if self.memory_peak_mb > 0:
            self.memory_efficiency = self.throughput / self.memory_peak_mb
        if self.cpu_utilization > 0:
            self.cpu_efficiency = self.throughput / self.cpu_utilization
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'component_name': self.component_name,
            'execution_time': self.execution_time,
            'memory_peak_mb': self.memory_peak_mb,
            'memory_delta_mb': self.memory_delta_mb,
            'cpu_utilization': self.cpu_utilization,
            'throughput': self.throughput,
            'initialization_time': self.initialization_time,
            'processing_time': self.processing_time,
            'cleanup_time': self.cleanup_time,
            'accuracy_score': self.accuracy_score,
            'quality_degradation': self.quality_degradation,
            'memory_efficiency': self.memory_efficiency,
            'cpu_efficiency': self.cpu_efficiency
        }


@dataclass
class BenchmarkResult:
    """Complete benchmark result with detailed analysis"""
    benchmark_id: str
    benchmark_type: BenchmarkType
    target_performance: PerformanceTarget
    test_configuration: Dict[str, Any]
    
    # Overall metrics
    total_execution_time: float
    achieved_speed_factor: float
    target_met: bool
    
    # Component metrics
    component_metrics: List[ComponentPerformanceMetrics]
    
    # Resource usage
    resource_timeline: List[ResourceMetrics]
    peak_memory_mb: float
    average_cpu_percent: float
    
    # Bottleneck analysis
    bottlenecks: List[str]
    optimization_suggestions: List[str]
    
    # Quality assessment
    quality_score: Optional[float] = None
    quality_vs_speed_ratio: Optional[float] = None
    
    def __post_init__(self):
        """Analyze results and generate insights"""
        self._analyze_bottlenecks()
        self._generate_optimization_suggestions()
    
    def _analyze_bottlenecks(self):
        """Identify performance bottlenecks"""
        self.bottlenecks = []
        
        # Find slowest component
        if self.component_metrics:
            slowest = max(self.component_metrics, key=lambda m: m.execution_time)
            if slowest.execution_time > self.total_execution_time * 0.3:
                self.bottlenecks.append(f"Slow component: {slowest.component_name}")
        
        # Check memory usage
        if self.peak_memory_mb > 8000:  # 8GB threshold
            self.bottlenecks.append("High memory usage")
        
        # Check CPU utilization
        if self.average_cpu_percent > 90:
            self.bottlenecks.append("CPU saturation")
        elif self.average_cpu_percent < 50:
            self.bottlenecks.append("Underutilized CPU")
    
    def _generate_optimization_suggestions(self):
        """Generate optimization suggestions based on analysis"""
        self.optimization_suggestions = []
        
        # Speed optimization suggestions
        if self.achieved_speed_factor < 10:
            self.optimization_suggestions.append("Consider more aggressive frame sampling")
            self.optimization_suggestions.append("Enable hardware acceleration if available")
        
        # Memory optimization suggestions
        if self.peak_memory_mb > 4000:
            self.optimization_suggestions.append("Implement streaming processing for large videos")
            self.optimization_suggestions.append("Use memory pools for frequent allocations")
        
        # Parallelization suggestions
        if self.average_cpu_percent < 60:
            self.optimization_suggestions.append("Increase parallel processing workers")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'benchmark_id': self.benchmark_id,
            'benchmark_type': self.benchmark_type.value,
            'target_performance': self.target_performance.value,
            'test_configuration': self.test_configuration,
            'total_execution_time': self.total_execution_time,
            'achieved_speed_factor': self.achieved_speed_factor,
            'target_met': self.target_met,
            'component_metrics': [m.to_dict() for m in self.component_metrics],
            'resource_timeline': [r.to_dict() for r in self.resource_timeline],
            'peak_memory_mb': self.peak_memory_mb,
            'average_cpu_percent': self.average_cpu_percent,
            'bottlenecks': self.bottlenecks,
            'optimization_suggestions': self.optimization_suggestions,
            'quality_score': self.quality_score,
            'quality_vs_speed_ratio': self.quality_vs_speed_ratio
        }


class ResourceMonitor:
    """Real-time system resource monitoring"""
    
    def __init__(self, sampling_interval: float = 0.1):
        self.sampling_interval = sampling_interval
        self.monitoring = False
        self.metrics: List[ResourceMetrics] = []
        self.monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Initialize process monitoring
        self.process = psutil.Process()
        self.initial_memory = self.process.memory_info().rss / (1024 * 1024)
    
    def start_monitoring(self):
        """Start resource monitoring in background thread"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.metrics = []
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        logger.debug("Resource monitoring started")
    
    def stop_monitoring(self) -> List[ResourceMetrics]:
        """Stop monitoring and return collected metrics"""
        if not self.monitoring:
            return self.metrics
        
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
        
        logger.debug(f"Resource monitoring stopped, collected {len(self.metrics)} samples")
        return self.metrics
    
    def _monitoring_loop(self):
        """Background monitoring loop"""
        while self.monitoring:
            try:
                # Collect system metrics
                cpu_percent = self.process.cpu_percent()
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)
                memory_percent = self.process.memory_percent()
                
                # Try to get GPU utilization (M1/M2 specific)
                gpu_util = self._get_gpu_utilization()
                
                metric = ResourceMetrics(
                    timestamp=time.time(),
                    cpu_percent=cpu_percent,
                    memory_mb=memory_mb,
                    memory_percent=memory_percent,
                    gpu_utilization=gpu_util
                )
                
                with self._lock:
                    self.metrics.append(metric)
                
                time.sleep(self.sampling_interval)
                
            except Exception as e:
                logger.debug(f"Error in resource monitoring: {e}")
                break
    
    def _get_gpu_utilization(self) -> Optional[float]:
        """Attempt to get GPU utilization (platform-specific)"""
        try:
            # This is a placeholder - actual implementation would depend on
            # available GPU monitoring tools for M1/M2 Macs
            # Could use Metal Performance Shaders or other Apple tools
            return None
        except:
            return None
    
    def get_peak_memory(self) -> float:
        """Get peak memory usage in MB"""
        if not self.metrics:
            return 0.0
        return max(m.memory_mb for m in self.metrics)
    
    def get_average_cpu(self) -> float:
        """Get average CPU utilization"""
        if not self.metrics:
            return 0.0
        return sum(m.cpu_percent for m in self.metrics) / len(self.metrics)


class ComponentProfiler:
    """Detailed profiler for individual components"""
    
    def __init__(self, component_name: str):
        self.component_name = component_name
        self.resource_monitor = ResourceMonitor()
        self.start_time = 0.0
        self.end_time = 0.0
        self.profiler: Optional[cProfile.Profile] = None
        
        # Memory tracking
        self.memory_tracking = False
        self.memory_snapshots = []
    
    @contextmanager
    def profile_execution(self, enable_memory_tracking: bool = True):
        """Context manager for profiling component execution"""
        try:
            # Start monitoring
            self.resource_monitor.start_monitoring()
            self.start_time = time.time()
            
            # Start memory tracking if requested
            if enable_memory_tracking:
                tracemalloc.start()
                self.memory_tracking = True
            
            # Start CPU profiling
            self.profiler = cProfile.Profile()
            self.profiler.enable()
            
            yield self
            
        finally:
            # Stop profiling
            if self.profiler:
                self.profiler.disable()
            
            self.end_time = time.time()
            
            # Stop memory tracking
            if self.memory_tracking:
                current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                self.memory_snapshots.append((current, peak))
            
            # Stop resource monitoring
            self.resource_monitor.stop_monitoring()
    
    def get_metrics(self, throughput: float = 0.0) -> ComponentPerformanceMetrics:
        """Generate performance metrics for the component"""
        execution_time = self.end_time - self.start_time
        
        # Get resource metrics
        resource_metrics = self.resource_monitor.metrics
        peak_memory = self.resource_monitor.get_peak_memory()
        avg_cpu = self.resource_monitor.get_average_cpu()
        
        # Calculate memory delta
        memory_delta = 0.0
        if self.memory_snapshots:
            current, peak = self.memory_snapshots[-1]
            memory_delta = peak / (1024 * 1024)  # Convert to MB
        
        return ComponentPerformanceMetrics(
            component_name=self.component_name,
            execution_time=execution_time,
            memory_peak_mb=peak_memory,
            memory_delta_mb=memory_delta,
            cpu_utilization=avg_cpu,
            throughput=throughput,
            processing_time=execution_time  # Simplified for now
        )
    
    def get_profile_stats(self) -> Optional[str]:
        """Get detailed profiling statistics"""
        if not self.profiler:
            return None
        
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s)
        ps.sort_stats('cumulative').print_stats(20)  # Top 20 functions
        return s.getvalue()


class PerformanceBenchmark:
    """Individual performance benchmark for specific scenarios"""
    
    def __init__(self, 
                 benchmark_id: str,
                 benchmark_type: BenchmarkType,
                 target_performance: PerformanceTarget):
        self.benchmark_id = benchmark_id
        self.benchmark_type = benchmark_type
        self.target_performance = target_performance
        self.component_profilers: Dict[str, ComponentProfiler] = {}
        self.global_resource_monitor = ResourceMonitor()
        
        # Performance targets mapping
        self.speed_targets = {
            PerformanceTarget.SPEED: 15.0,
            PerformanceTarget.BALANCED: 10.0,
            PerformanceTarget.QUALITY: 5.0,
            PerformanceTarget.PRECISION: 2.0
        }
    
    def create_component_profiler(self, component_name: str) -> ComponentProfiler:
        """Create a profiler for a specific component"""
        profiler = ComponentProfiler(component_name)
        self.component_profilers[component_name] = profiler
        return profiler
    
    def start_benchmark(self):
        """Start global benchmark monitoring"""
        self.global_resource_monitor.start_monitoring()
        self.start_time = time.time()
        logger.info(f"Started benchmark: {self.benchmark_id}")
    
    def end_benchmark(self, video_duration: float = 0.0) -> BenchmarkResult:
        """End benchmark and generate results"""
        end_time = time.time()
        total_time = end_time - self.start_time
        
        # Stop global monitoring
        resource_timeline = self.global_resource_monitor.stop_monitoring()
        
        # Calculate performance metrics
        achieved_speed = video_duration / total_time if total_time > 0 else 0.0
        target_speed = self.speed_targets[self.target_performance]
        target_met = achieved_speed >= target_speed
        
        # Collect component metrics
        component_metrics = []
        for profiler in self.component_profilers.values():
            # Calculate throughput based on component type
            throughput = 1.0 / profiler.end_time - profiler.start_time if profiler.end_time > profiler.start_time else 0.0
            metrics = profiler.get_metrics(throughput)
            component_metrics.append(metrics)
        
        # Calculate resource statistics
        peak_memory = max((m.memory_mb for m in resource_timeline), default=0.0)
        avg_cpu = sum(m.cpu_percent for m in resource_timeline) / len(resource_timeline) if resource_timeline else 0.0
        
        # Create benchmark result
        result = BenchmarkResult(
            benchmark_id=self.benchmark_id,
            benchmark_type=self.benchmark_type,
            target_performance=self.target_performance,
            test_configuration={
                'video_duration': video_duration,
                'target_speed': target_speed
            },
            total_execution_time=total_time,
            achieved_speed_factor=achieved_speed,
            target_met=target_met,
            component_metrics=component_metrics,
            resource_timeline=resource_timeline,
            peak_memory_mb=peak_memory,
            average_cpu_percent=avg_cpu,
            bottlenecks=[],
            optimization_suggestions=[]
        )
        
        logger.info(f"Benchmark completed: {self.benchmark_id}, "
                   f"Speed: {achieved_speed:.1f}x, Target met: {target_met}")
        
        return result


class BenchmarkSuite:
    """Comprehensive benchmark suite for AutoCut performance testing"""
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path("./benchmark_results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: List[BenchmarkResult] = []
        
        # Test scenarios
        self.test_scenarios = self._create_test_scenarios()
    
    def _create_test_scenarios(self) -> List[Dict[str, Any]]:
        """Create comprehensive test scenarios"""
        scenarios = []
        
        # Component benchmarks
        for component in ['video_ingestion', 'audio_analysis', 'scene_detection', 
                         'face_detection', 'quality_scoring', 'timeline_generation']:
            scenarios.append({
                'name': f'{component}_speed',
                'type': BenchmarkType.COMPONENT,
                'target': PerformanceTarget.SPEED,
                'component': component,
                'description': f'Speed benchmark for {component}'
            })
        
        # Pipeline benchmarks
        for target in PerformanceTarget:
            for duration in [30, 60, 120, 300]:  # Test different video lengths
                for resolution in ['720p', '1080p', '4k']:
                    scenarios.append({
                        'name': f'pipeline_{target.value}_{duration}s_{resolution}',
                        'type': BenchmarkType.PIPELINE,
                        'target': target,
                        'duration': duration,
                        'resolution': resolution,
                        'description': f'Pipeline benchmark {target.value} mode, {duration}s {resolution} video'
                    })
        
        # Stress tests
        scenarios.extend([
            {
                'name': 'stress_long_video',
                'type': BenchmarkType.STRESS,
                'target': PerformanceTarget.SPEED,
                'duration': 1800,  # 30 minutes
                'description': 'Stress test with very long video'
            },
            {
                'name': 'stress_high_resolution',
                'type': BenchmarkType.STRESS,
                'target': PerformanceTarget.SPEED,
                'resolution': '8k',
                'description': 'Stress test with ultra-high resolution'
            }
        ])
        
        return scenarios
    
    def run_component_benchmark(self, component_name: str, target: PerformanceTarget) -> BenchmarkResult:
        """Run benchmark for a specific component"""
        benchmark_id = f"{component_name}_{target.value}_{int(time.time())}"
        benchmark = PerformanceBenchmark(benchmark_id, BenchmarkType.COMPONENT, target)
        
        # This would integrate with actual component testing
        # For now, simulate component execution
        benchmark.start_benchmark()
        
        profiler = benchmark.create_component_profiler(component_name)
        with profiler.profile_execution():
            # Simulate component work
            self._simulate_component_work(component_name, target)
        
        result = benchmark.end_benchmark(video_duration=60.0)  # Simulate 60s video
        self.results.append(result)
        return result
    
    def run_pipeline_benchmark(self, scenario: Dict[str, Any]) -> BenchmarkResult:
        """Run end-to-end pipeline benchmark"""
        benchmark_id = f"pipeline_{scenario['target'].value}_{int(time.time())}"
        benchmark = PerformanceBenchmark(benchmark_id, BenchmarkType.PIPELINE, scenario['target'])
        
        # This would integrate with the actual AutoCut pipeline
        # For now, simulate pipeline execution
        benchmark.start_benchmark()
        
        # Profile each component in the pipeline
        components = ['video_ingestion', 'audio_analysis', 'scene_detection', 
                     'face_detection', 'quality_scoring', 'timeline_generation', 'rendering']
        
        for component in components:
            profiler = benchmark.create_component_profiler(component)
            with profiler.profile_execution():
                self._simulate_component_work(component, scenario['target'])
        
        video_duration = scenario.get('duration', 60.0)
        result = benchmark.end_benchmark(video_duration=video_duration)
        self.results.append(result)
        return result
    
    def _simulate_component_work(self, component: str, target: PerformanceTarget):
        """Simulate component work for benchmarking"""
        # Simulate different processing times based on component and target
        base_times = {
            'video_ingestion': 0.1,
            'audio_analysis': 2.0,
            'scene_detection': 1.5,
            'face_detection': 3.0,
            'quality_scoring': 2.5,
            'timeline_generation': 0.5,
            'rendering': 4.0
        }
        
        speed_multipliers = {
            PerformanceTarget.SPEED: 0.2,
            PerformanceTarget.BALANCED: 0.5,
            PerformanceTarget.QUALITY: 1.0,
            PerformanceTarget.PRECISION: 2.0
        }
        
        base_time = base_times.get(component, 1.0)
        multiplier = speed_multipliers[target]
        sleep_time = base_time * multiplier
        
        # Simulate CPU work
        end_time = time.time() + sleep_time
        while time.time() < end_time:
            # Light CPU work to simulate processing
            _ = sum(i * i for i in range(1000))
    
    def run_full_suite(self, max_scenarios: Optional[int] = None) -> List[BenchmarkResult]:
        """Run the complete benchmark suite"""
        logger.info("Starting comprehensive benchmark suite")
        
        scenarios_to_run = self.test_scenarios[:max_scenarios] if max_scenarios else self.test_scenarios
        results = []
        
        for i, scenario in enumerate(scenarios_to_run, 1):
            logger.info(f"Running benchmark {i}/{len(scenarios_to_run)}: {scenario['name']}")
            
            try:
                if scenario['type'] == BenchmarkType.COMPONENT:
                    result = self.run_component_benchmark(scenario['component'], scenario['target'])
                else:
                    result = self.run_pipeline_benchmark(scenario)
                
                results.append(result)
                
                # Save intermediate results
                self._save_result(result)
                
            except Exception as e:
                logger.error(f"Benchmark failed: {scenario['name']}, error: {e}")
                continue
        
        # Generate comprehensive report
        self._generate_suite_report(results)
        
        logger.info(f"Benchmark suite completed, {len(results)} tests run")
        return results
    
    def _save_result(self, result: BenchmarkResult):
        """Save individual benchmark result"""
        filename = f"{result.benchmark_id}.json"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)
    
    def _generate_suite_report(self, results: List[BenchmarkResult]):
        """Generate comprehensive benchmark suite report"""
        # Generate summary statistics
        summary = {
            'total_tests': len(results),
            'tests_passed': sum(1 for r in results if r.target_met),
            'average_speed_factor': np.mean([r.achieved_speed_factor for r in results]),
            'performance_targets_met': {},
            'component_performance': {},
            'bottlenecks_summary': {},
            'optimization_recommendations': []
        }
        
        # Analyze by performance target
        for target in PerformanceTarget:
            target_results = [r for r in results if r.target_performance == target]
            if target_results:
                summary['performance_targets_met'][target.value] = {
                    'total': len(target_results),
                    'passed': sum(1 for r in target_results if r.target_met),
                    'average_speed': np.mean([r.achieved_speed_factor for r in target_results])
                }
        
        # Analyze component performance
        for result in results:
            for comp_metric in result.component_metrics:
                comp_name = comp_metric.component_name
                if comp_name not in summary['component_performance']:
                    summary['component_performance'][comp_name] = {
                        'execution_times': [],
                        'memory_usage': [],
                        'throughput': []
                    }
                
                summary['component_performance'][comp_name]['execution_times'].append(comp_metric.execution_time)
                summary['component_performance'][comp_name]['memory_usage'].append(comp_metric.memory_peak_mb)
                summary['component_performance'][comp_name]['throughput'].append(comp_metric.throughput)
        
        # Calculate component averages
        for comp_name, metrics in summary['component_performance'].items():
            metrics['avg_execution_time'] = np.mean(metrics['execution_times'])
            metrics['avg_memory_usage'] = np.mean(metrics['memory_usage'])
            metrics['avg_throughput'] = np.mean(metrics['throughput'])
        
        # Collect bottlenecks
        all_bottlenecks = []
        for result in results:
            all_bottlenecks.extend(result.bottlenecks)
        
        # Count bottleneck frequency
        bottleneck_counts = {}
        for bottleneck in all_bottlenecks:
            bottleneck_counts[bottleneck] = bottleneck_counts.get(bottleneck, 0) + 1
        
        summary['bottlenecks_summary'] = dict(sorted(bottleneck_counts.items(), 
                                                   key=lambda x: x[1], reverse=True))
        
        # Generate optimization recommendations
        if summary['average_speed_factor'] < 10:
            summary['optimization_recommendations'].append(
                "Overall performance below 10x target - consider aggressive optimization"
            )
        
        # Save comprehensive report
        report_path = self.output_dir / "benchmark_suite_report.json"
        with open(report_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Generate CSV report for analysis
        self._generate_csv_report(results)
        
        logger.info(f"Benchmark suite report saved to {report_path}")
    
    def _generate_csv_report(self, results: List[BenchmarkResult]):
        """Generate CSV report for detailed analysis"""
        csv_path = self.output_dir / "benchmark_results.csv"
        
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'benchmark_id', 'type', 'target', 'execution_time', 
                'achieved_speed', 'target_met', 'peak_memory_mb', 
                'avg_cpu_percent', 'component_count', 'bottlenecks'
            ])
            
            # Data rows
            for result in results:
                writer.writerow([
                    result.benchmark_id,
                    result.benchmark_type.value,
                    result.target_performance.value,
                    result.total_execution_time,
                    result.achieved_speed_factor,
                    result.target_met,
                    result.peak_memory_mb,
                    result.average_cpu_percent,
                    len(result.component_metrics),
                    '; '.join(result.bottlenecks)
                ])


def create_benchmark_suite(output_dir: Optional[Path] = None) -> BenchmarkSuite:
    """Create a configured benchmark suite"""
    return BenchmarkSuite(output_dir)


# Usage example and integration helpers
def benchmark_autocut_component(component_function: Callable, 
                               component_name: str,
                               target: PerformanceTarget = PerformanceTarget.SPEED,
                               *args, **kwargs) -> ComponentPerformanceMetrics:
    """
    Helper function to benchmark any AutoCut component
    
    Args:
        component_function: The component function to benchmark
        component_name: Name of the component for reporting
        target: Performance target
        *args, **kwargs: Arguments to pass to the component function
    
    Returns:
        ComponentPerformanceMetrics with detailed analysis
    """
    profiler = ComponentProfiler(component_name)
    
    with profiler.profile_execution():
        result = component_function(*args, **kwargs)
    
    # Calculate throughput based on result
    throughput = 1.0  # Default throughput, could be calculated based on result
    metrics = profiler.get_metrics(throughput)
    
    return metrics
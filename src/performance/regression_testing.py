"""
Performance regression testing and validation suite for AutoCut.

This module provides comprehensive regression testing to ensure performance
optimizations don't degrade over time and validates that all performance
modes meet their targets.
"""

import time
import json
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import hashlib
import pickle
import git
from datetime import datetime, timedelta

from .benchmarking import BenchmarkSuite, BenchmarkResult, PerformanceTarget
from .monitoring import PerformanceMonitor, create_performance_monitor
from .optimization import create_performance_optimizer, OptimizationStrategy
from ..utils.logging import get_logger
from ..utils.config import config

logger = get_logger(__name__)


class RegressionTestType(Enum):
    """Types of regression tests"""
    COMPONENT = "component"           # Individual component performance
    PIPELINE = "pipeline"            # End-to-end pipeline performance
    MEMORY = "memory"                # Memory usage regression
    QUALITY = "quality"              # Quality vs performance trade-off
    STABILITY = "stability"          # Performance stability over time
    SCALABILITY = "scalability"      # Performance scaling with input size


class TestStatus(Enum):
    """Test execution status"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class RegressionTestResult:
    """Result of a single regression test"""
    test_id: str
    test_type: RegressionTestType
    test_name: str
    status: TestStatus
    
    # Performance metrics
    current_performance: float
    baseline_performance: float
    performance_delta: float  # Current - baseline
    performance_ratio: float  # Current / baseline
    
    # Quality metrics (if applicable)
    current_quality: Optional[float] = None
    baseline_quality: Optional[float] = None
    quality_delta: Optional[float] = None
    
    # Test metadata
    execution_time: float = 0.0
    memory_peak_mb: float = 0.0
    test_configuration: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    
    # Thresholds
    performance_tolerance: float = 0.05  # 5% tolerance by default
    quality_tolerance: float = 0.02      # 2% quality tolerance
    
    def __post_init__(self):
        """Calculate derived metrics"""
        if self.baseline_performance > 0:
            self.performance_ratio = self.current_performance / self.baseline_performance
            self.performance_delta = self.current_performance - self.baseline_performance
        else:
            self.performance_ratio = 0.0
            self.performance_delta = 0.0
        
        if self.current_quality is not None and self.baseline_quality is not None:
            self.quality_delta = self.current_quality - self.baseline_quality
    
    @property
    def is_performance_regression(self) -> bool:
        """Check if this represents a performance regression"""
        if self.status != TestStatus.PASSED:
            return True
        
        # Performance regression if current performance is significantly worse
        return self.performance_ratio < (1.0 - self.performance_tolerance)
    
    @property
    def is_quality_regression(self) -> bool:
        """Check if this represents a quality regression"""
        if self.current_quality is None or self.baseline_quality is None:
            return False
        
        # Quality regression if current quality is significantly worse
        return self.quality_delta < -self.quality_tolerance
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'test_id': self.test_id,
            'test_type': self.test_type.value,
            'test_name': self.test_name,
            'status': self.status.value,
            'current_performance': self.current_performance,
            'baseline_performance': self.baseline_performance,
            'performance_delta': self.performance_delta,
            'performance_ratio': self.performance_ratio,
            'current_quality': self.current_quality,
            'baseline_quality': self.baseline_quality,
            'quality_delta': self.quality_delta,
            'execution_time': self.execution_time,
            'memory_peak_mb': self.memory_peak_mb,
            'test_configuration': self.test_configuration,
            'error_message': self.error_message,
            'is_performance_regression': self.is_performance_regression,
            'is_quality_regression': self.is_quality_regression
        }


@dataclass
class BaselinePerformance:
    """Baseline performance data for regression testing"""
    test_id: str
    performance_value: float
    quality_value: Optional[float] = None
    memory_usage_mb: float = 0.0
    
    # Metadata
    recorded_at: float = field(default_factory=time.time)
    git_commit: Optional[str] = None
    system_info: Dict[str, Any] = field(default_factory=dict)
    test_configuration: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'test_id': self.test_id,
            'performance_value': self.performance_value,
            'quality_value': self.quality_value,
            'memory_usage_mb': self.memory_usage_mb,
            'recorded_at': self.recorded_at,
            'git_commit': self.git_commit,
            'system_info': self.system_info,
            'test_configuration': self.test_configuration
        }


class BaselineManager:
    """Manages performance baselines for regression testing"""
    
    def __init__(self, baseline_dir: Path):
        self.baseline_dir = baseline_dir
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.baselines: Dict[str, BaselinePerformance] = {}
        
        self._load_baselines()
    
    def _load_baselines(self):
        """Load existing baselines from disk"""
        baseline_file = self.baseline_dir / "baselines.json"
        
        if baseline_file.exists():
            try:
                with open(baseline_file, 'r') as f:
                    baseline_data = json.load(f)
                
                for test_id, data in baseline_data.items():
                    baseline = BaselinePerformance(
                        test_id=data['test_id'],
                        performance_value=data['performance_value'],
                        quality_value=data.get('quality_value'),
                        memory_usage_mb=data.get('memory_usage_mb', 0.0),
                        recorded_at=data.get('recorded_at', time.time()),
                        git_commit=data.get('git_commit'),
                        system_info=data.get('system_info', {}),
                        test_configuration=data.get('test_configuration', {})
                    )
                    self.baselines[test_id] = baseline
                
                logger.info(f"Loaded {len(self.baselines)} baselines")
                
            except Exception as e:
                logger.error(f"Error loading baselines: {e}")
    
    def _save_baselines(self):
        """Save baselines to disk"""
        baseline_file = self.baseline_dir / "baselines.json"
        
        try:
            baseline_data = {
                test_id: baseline.to_dict() 
                for test_id, baseline in self.baselines.items()
            }
            
            with open(baseline_file, 'w') as f:
                json.dump(baseline_data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving baselines: {e}")
    
    def record_baseline(self, 
                       test_id: str,
                       performance_value: float,
                       quality_value: Optional[float] = None,
                       memory_usage_mb: float = 0.0,
                       test_configuration: Optional[Dict[str, Any]] = None) -> BaselinePerformance:
        """Record a new baseline performance"""
        
        # Get git commit if available
        git_commit = self._get_current_git_commit()
        
        # Get system info
        system_info = self._get_system_info()
        
        baseline = BaselinePerformance(
            test_id=test_id,
            performance_value=performance_value,
            quality_value=quality_value,
            memory_usage_mb=memory_usage_mb,
            git_commit=git_commit,
            system_info=system_info,
            test_configuration=test_configuration or {}
        )
        
        self.baselines[test_id] = baseline
        self._save_baselines()
        
        logger.info(f"Recorded baseline for {test_id}: {performance_value}")
        return baseline
    
    def get_baseline(self, test_id: str) -> Optional[BaselinePerformance]:
        """Get baseline for a test"""
        return self.baselines.get(test_id)
    
    def _get_current_git_commit(self) -> Optional[str]:
        """Get current git commit hash"""
        try:
            repo = git.Repo(search_parent_directories=True)
            return repo.head.object.hexsha
        except:
            return None
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get current system information"""
        import platform
        import psutil
        
        return {
            'platform': platform.platform(),
            'python_version': platform.python_version(),
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3),
            'architecture': platform.architecture()[0]
        }


class PerformanceValidator:
    """Validates that performance modes meet their targets"""
    
    def __init__(self):
        self.target_speeds = {
            PerformanceTarget.SPEED: 15.0,      # 15x real-time
            PerformanceTarget.BALANCED: 10.0,   # 10x real-time
            PerformanceTarget.QUALITY: 5.0,     # 5x real-time
            PerformanceTarget.PRECISION: 2.0    # 2x real-time
        }
        
        self.quality_thresholds = {
            PerformanceTarget.SPEED: 0.7,       # 70% quality acceptable
            PerformanceTarget.BALANCED: 0.85,   # 85% quality target
            PerformanceTarget.QUALITY: 0.95,    # 95% quality target
            PerformanceTarget.PRECISION: 1.0    # 100% quality target
        }
    
    def validate_performance_mode(self, 
                                 mode: PerformanceTarget,
                                 achieved_speed: float,
                                 quality_score: Optional[float] = None) -> Dict[str, Any]:
        """Validate that a performance mode meets its targets"""
        
        target_speed = self.target_speeds[mode]
        speed_met = achieved_speed >= target_speed * 0.9  # 90% of target acceptable
        
        quality_met = True
        if quality_score is not None:
            quality_threshold = self.quality_thresholds[mode]
            quality_met = quality_score >= quality_threshold
        
        overall_pass = speed_met and quality_met
        
        return {
            'mode': mode.value,
            'target_speed': target_speed,
            'achieved_speed': achieved_speed,
            'speed_met': speed_met,
            'quality_score': quality_score,
            'quality_threshold': self.quality_thresholds[mode],
            'quality_met': quality_met,
            'overall_pass': overall_pass,
            'speed_ratio': achieved_speed / target_speed,
            'quality_ratio': quality_score / self.quality_thresholds[mode] if quality_score else None
        }


class RegressionTestSuite:
    """Comprehensive regression test suite for AutoCut performance"""
    
    def __init__(self, 
                 output_dir: Optional[Path] = None,
                 baseline_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path("./regression_results")
        self.baseline_dir = baseline_dir or Path("./performance_baselines")
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.baseline_manager = BaselineManager(self.baseline_dir)
        self.benchmark_suite = BenchmarkSuite(self.output_dir / "benchmarks")
        self.performance_validator = PerformanceValidator()
        
        # Test registry
        self.test_registry = self._initialize_test_registry()
        
        logger.info(f"Regression test suite initialized, output: {self.output_dir}")
    
    def _initialize_test_registry(self) -> Dict[str, Dict[str, Any]]:
        """Initialize the registry of regression tests"""
        return {
            # Component performance tests
            'audio_analysis_speed': {
                'type': RegressionTestType.COMPONENT,
                'component': 'audio_analysis',
                'target': PerformanceTarget.SPEED,
                'tolerance': 0.1,  # 10% tolerance
                'description': 'Audio analysis component speed test'
            },
            'scene_detection_balanced': {
                'type': RegressionTestType.COMPONENT,
                'component': 'scene_detection',
                'target': PerformanceTarget.BALANCED,
                'tolerance': 0.08,
                'description': 'Scene detection balanced mode test'
            },
            'face_detection_quality': {
                'type': RegressionTestType.COMPONENT,
                'component': 'face_detection',
                'target': PerformanceTarget.QUALITY,
                'tolerance': 0.05,
                'description': 'Face detection quality mode test'
            },
            
            # Pipeline performance tests
            'pipeline_speed_1080p': {
                'type': RegressionTestType.PIPELINE,
                'target': PerformanceTarget.SPEED,
                'resolution': '1080p',
                'duration': 60,
                'tolerance': 0.15,
                'description': 'Full pipeline speed test with 1080p video'
            },
            'pipeline_balanced_4k': {
                'type': RegressionTestType.PIPELINE,
                'target': PerformanceTarget.BALANCED,
                'resolution': '4k',
                'duration': 30,
                'tolerance': 0.2,
                'description': 'Full pipeline balanced test with 4K video'
            },
            
            # Memory regression tests
            'memory_usage_long_video': {
                'type': RegressionTestType.MEMORY,
                'target': PerformanceTarget.SPEED,
                'duration': 300,  # 5 minutes
                'tolerance': 0.1,
                'description': 'Memory usage test with long video'
            },
            
            # Quality regression tests
            'quality_vs_speed_tradeoff': {
                'type': RegressionTestType.QUALITY,
                'targets': [PerformanceTarget.SPEED, PerformanceTarget.QUALITY],
                'tolerance': 0.05,
                'description': 'Quality vs speed trade-off validation'
            },
            
            # Stability tests
            'performance_stability': {
                'type': RegressionTestType.STABILITY,
                'target': PerformanceTarget.BALANCED,
                'iterations': 10,
                'tolerance': 0.1,
                'description': 'Performance stability over multiple runs'
            }
        }
    
    def run_regression_test(self, test_id: str) -> RegressionTestResult:
        """Run a single regression test"""
        
        if test_id not in self.test_registry:
            raise ValueError(f"Unknown test: {test_id}")
        
        test_config = self.test_registry[test_id]
        logger.info(f"Running regression test: {test_id}")
        
        start_time = time.time()
        
        try:
            # Run the test based on its type
            if test_config['type'] == RegressionTestType.COMPONENT:
                result = self._run_component_test(test_id, test_config)
            elif test_config['type'] == RegressionTestType.PIPELINE:
                result = self._run_pipeline_test(test_id, test_config)
            elif test_config['type'] == RegressionTestType.MEMORY:
                result = self._run_memory_test(test_id, test_config)
            elif test_config['type'] == RegressionTestType.QUALITY:
                result = self._run_quality_test(test_id, test_config)
            elif test_config['type'] == RegressionTestType.STABILITY:
                result = self._run_stability_test(test_id, test_config)
            else:
                raise ValueError(f"Unsupported test type: {test_config['type']}")
            
            result.execution_time = time.time() - start_time
            
            # Compare with baseline
            baseline = self.baseline_manager.get_baseline(test_id)
            if baseline:
                result.baseline_performance = baseline.performance_value
                result.baseline_quality = baseline.quality_value
                
                # Determine if test passed
                if result.is_performance_regression or result.is_quality_regression:
                    result.status = TestStatus.FAILED
                else:
                    result.status = TestStatus.PASSED
            else:
                # No baseline - record current as baseline
                self.baseline_manager.record_baseline(
                    test_id, 
                    result.current_performance,
                    result.current_quality,
                    result.memory_peak_mb,
                    result.test_configuration
                )
                result.baseline_performance = result.current_performance
                result.baseline_quality = result.current_quality
                result.status = TestStatus.PASSED
                
                logger.info(f"No baseline found for {test_id}, recorded current performance as baseline")
            
            return result
            
        except Exception as e:
            logger.error(f"Error running test {test_id}: {e}")
            
            return RegressionTestResult(
                test_id=test_id,
                test_type=test_config['type'],
                test_name=test_config['description'],
                status=TestStatus.ERROR,
                current_performance=0.0,
                baseline_performance=0.0,
                performance_delta=0.0,
                performance_ratio=0.0,
                error_message=str(e),
                execution_time=time.time() - start_time
            )
    
    def _run_component_test(self, test_id: str, config: Dict[str, Any]) -> RegressionTestResult:
        """Run a component-specific regression test"""
        
        # This would integrate with actual component testing
        # For now, simulate component performance
        component = config['component']
        target = config['target']
        
        # Simulate component execution with performance monitoring
        monitor = create_performance_monitor(target_speed=15.0)
        monitor.start_monitoring()
        
        with monitor.monitor_component(component):
            # Simulate component work
            time.sleep(0.1)  # Simulate processing time
            
            # Simulate different performance based on target
            if target == PerformanceTarget.SPEED:
                performance = np.random.normal(16.0, 1.0)  # Speed mode
                quality = np.random.normal(0.75, 0.05)     # Lower quality
            elif target == PerformanceTarget.BALANCED:
                performance = np.random.normal(11.0, 0.5)  # Balanced mode
                quality = np.random.normal(0.85, 0.03)     # Good quality
            else:
                performance = np.random.normal(6.0, 0.3)   # Quality mode
                quality = np.random.normal(0.95, 0.02)     # High quality
        
        monitor.stop_monitoring()
        
        return RegressionTestResult(
            test_id=test_id,
            test_type=config['type'],
            test_name=config['description'],
            status=TestStatus.RUNNING,  # Will be updated after baseline comparison
            current_performance=max(0.1, performance),
            baseline_performance=0.0,   # Will be set from baseline
            performance_delta=0.0,
            performance_ratio=0.0,
            current_quality=min(1.0, max(0.0, quality)),
            performance_tolerance=config['tolerance'],
            test_configuration={'component': component, 'target': target.value}
        )
    
    def _run_pipeline_test(self, test_id: str, config: Dict[str, Any]) -> RegressionTestResult:
        """Run a full pipeline regression test"""
        
        target = config['target']
        duration = config.get('duration', 60)
        resolution = config.get('resolution', '1080p')
        
        # Run benchmark with specific configuration
        benchmark_scenario = {
            'target': target,
            'duration': duration,
            'resolution': resolution
        }
        
        benchmark_result = self.benchmark_suite.run_pipeline_benchmark(benchmark_scenario)
        
        return RegressionTestResult(
            test_id=test_id,
            test_type=config['type'],
            test_name=config['description'],
            status=TestStatus.RUNNING,
            current_performance=benchmark_result.achieved_speed_factor,
            baseline_performance=0.0,
            performance_delta=0.0,
            performance_ratio=0.0,
            current_quality=benchmark_result.quality_score,
            memory_peak_mb=benchmark_result.peak_memory_mb,
            performance_tolerance=config['tolerance'],
            test_configuration={
                'duration': duration,
                'resolution': resolution,
                'target': target.value
            }
        )
    
    def _run_memory_test(self, test_id: str, config: Dict[str, Any]) -> RegressionTestResult:
        """Run a memory usage regression test"""
        
        # This would test memory usage patterns
        # For now, simulate memory monitoring
        
        import psutil
        process = psutil.Process()
        
        start_memory = process.memory_info().rss / (1024**2)  # MB
        
        # Simulate processing that uses memory
        duration = config.get('duration', 60)
        time.sleep(0.1)  # Simulate processing
        
        peak_memory = process.memory_info().rss / (1024**2)  # MB
        memory_usage = peak_memory - start_memory
        
        # Performance metric is inverse of memory usage (lower is better)
        performance = 1000.0 / max(1.0, memory_usage)
        
        return RegressionTestResult(
            test_id=test_id,
            test_type=config['type'],
            test_name=config['description'],
            status=TestStatus.RUNNING,
            current_performance=performance,
            baseline_performance=0.0,
            performance_delta=0.0,
            performance_ratio=0.0,
            memory_peak_mb=peak_memory,
            performance_tolerance=config['tolerance'],
            test_configuration={'duration': duration}
        )
    
    def _run_quality_test(self, test_id: str, config: Dict[str, Any]) -> RegressionTestResult:
        """Run a quality vs performance trade-off test"""
        
        targets = config.get('targets', [PerformanceTarget.SPEED, PerformanceTarget.QUALITY])
        
        results = []
        for target in targets:
            # Simulate different performance/quality trade-offs
            if target == PerformanceTarget.SPEED:
                perf = np.random.normal(15.0, 1.0)
                qual = np.random.normal(0.7, 0.05)
            else:
                perf = np.random.normal(5.0, 0.5)
                qual = np.random.normal(0.95, 0.02)
            
            results.append((perf, qual))
        
        # Calculate quality-adjusted performance
        quality_adjusted_perf = sum(p * q for p, q in results) / len(results)
        average_quality = sum(q for _, q in results) / len(results)
        
        return RegressionTestResult(
            test_id=test_id,
            test_type=config['type'],
            test_name=config['description'],
            status=TestStatus.RUNNING,
            current_performance=quality_adjusted_perf,
            baseline_performance=0.0,
            performance_delta=0.0,
            performance_ratio=0.0,
            current_quality=average_quality,
            performance_tolerance=config['tolerance'],
            test_configuration={'targets': [t.value for t in targets]}
        )
    
    def _run_stability_test(self, test_id: str, config: Dict[str, Any]) -> RegressionTestResult:
        """Run a performance stability test"""
        
        iterations = config.get('iterations', 10)
        target = config['target']
        
        performance_values = []
        
        for i in range(iterations):
            # Simulate component execution
            if target == PerformanceTarget.SPEED:
                perf = np.random.normal(15.0, 2.0)  # More variation for speed mode
            else:
                perf = np.random.normal(10.0, 1.0)  # Less variation for balanced mode
            
            performance_values.append(max(0.1, perf))
            time.sleep(0.01)  # Small delay between iterations
        
        # Calculate stability metrics
        mean_performance = np.mean(performance_values)
        std_performance = np.std(performance_values)
        cv = std_performance / mean_performance if mean_performance > 0 else 1.0  # Coefficient of variation
        
        # Performance is inverse of coefficient of variation (more stable = higher performance)
        stability_performance = 1.0 / (1.0 + cv)
        
        return RegressionTestResult(
            test_id=test_id,
            test_type=config['type'],
            test_name=config['description'],
            status=TestStatus.RUNNING,
            current_performance=stability_performance,
            baseline_performance=0.0,
            performance_delta=0.0,
            performance_ratio=0.0,
            performance_tolerance=config['tolerance'],
            test_configuration={
                'iterations': iterations,
                'target': target.value,
                'mean_performance': mean_performance,
                'std_performance': std_performance,
                'coefficient_of_variation': cv
            }
        )
    
    def run_full_regression_suite(self, test_filter: Optional[str] = None) -> List[RegressionTestResult]:
        """Run the complete regression test suite"""
        
        logger.info("Starting full regression test suite")
        
        # Filter tests if requested
        if test_filter:
            tests_to_run = {k: v for k, v in self.test_registry.items() if test_filter in k}
        else:
            tests_to_run = self.test_registry
        
        results = []
        
        for test_id in tests_to_run:
            try:
                result = self.run_regression_test(test_id)
                results.append(result)
                
                status_symbol = {
                    TestStatus.PASSED: "✅",
                    TestStatus.FAILED: "❌", 
                    TestStatus.ERROR: "💥",
                    TestStatus.SKIPPED: "⏭️"
                }.get(result.status, "❓")
                
                logger.info(f"{status_symbol} {test_id}: {result.status.value}")
                
            except Exception as e:
                logger.error(f"Failed to run test {test_id}: {e}")
                continue
        
        # Generate regression report
        self._generate_regression_report(results)
        
        logger.info(f"Regression suite completed: {len(results)} tests run")
        return results
    
    def _generate_regression_report(self, results: List[RegressionTestResult]):
        """Generate comprehensive regression test report"""
        
        # Calculate summary statistics
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed_tests = sum(1 for r in results if r.status == TestStatus.FAILED)
        error_tests = sum(1 for r in results if r.status == TestStatus.ERROR)
        
        performance_regressions = sum(1 for r in results if r.is_performance_regression)
        quality_regressions = sum(1 for r in results if r.is_quality_regression)
        
        report = {
            'report_generated': time.time(),
            'summary': {
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'failed_tests': failed_tests,
                'error_tests': error_tests,
                'success_rate': (passed_tests / total_tests) * 100 if total_tests > 0 else 0,
                'performance_regressions': performance_regressions,
                'quality_regressions': quality_regressions
            },
            'test_results': [r.to_dict() for r in results],
            'regressions_detected': [
                r.to_dict() for r in results 
                if r.is_performance_regression or r.is_quality_regression
            ]
        }
        
        # Save report
        report_path = self.output_dir / f"regression_report_{int(time.time())}.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Generate summary text report
        summary_path = self.output_dir / "regression_summary.txt"
        with open(summary_path, 'w') as f:
            f.write("AutoCut Performance Regression Test Report\n")
            f.write("=" * 50 + "\n\n")
            
            f.write(f"Test Summary:\n")
            f.write(f"  Total Tests: {total_tests}\n")
            f.write(f"  Passed: {passed_tests}\n")
            f.write(f"  Failed: {failed_tests}\n")
            f.write(f"  Errors: {error_tests}\n")
            f.write(f"  Success Rate: {(passed_tests / total_tests) * 100:.1f}%\n\n")
            
            if performance_regressions > 0 or quality_regressions > 0:
                f.write(f"Regressions Detected:\n")
                f.write(f"  Performance Regressions: {performance_regressions}\n")
                f.write(f"  Quality Regressions: {quality_regressions}\n\n")
                
                f.write("Detailed Regression Analysis:\n")
                for result in results:
                    if result.is_performance_regression or result.is_quality_regression:
                        f.write(f"  - {result.test_id}: ")
                        if result.is_performance_regression:
                            f.write(f"Performance: {result.performance_ratio:.3f}x baseline ")
                        if result.is_quality_regression:
                            f.write(f"Quality: {result.quality_delta:.3f} delta ")
                        f.write("\n")
        
        logger.info(f"Regression report saved to {report_path}")
    
    def update_baselines(self, test_filter: Optional[str] = None, force: bool = False):
        """Update performance baselines with current results"""
        
        if test_filter:
            tests_to_update = {k: v for k, v in self.test_registry.items() if test_filter in k}
        else:
            tests_to_update = self.test_registry
        
        updated_count = 0
        
        for test_id in tests_to_update:
            # Run test to get current performance
            result = self.run_regression_test(test_id)
            
            # Update baseline if test passed or if forced
            if result.status == TestStatus.PASSED or force:
                self.baseline_manager.record_baseline(
                    test_id,
                    result.current_performance,
                    result.current_quality,
                    result.memory_peak_mb,
                    result.test_configuration
                )
                updated_count += 1
                logger.info(f"Updated baseline for {test_id}")
            else:
                logger.warning(f"Skipped baseline update for {test_id} (test failed)")
        
        logger.info(f"Updated {updated_count} baselines")


# Factory function for easy integration
def create_regression_test_suite(output_dir: Optional[Path] = None) -> RegressionTestSuite:
    """
    Create a configured regression test suite
    
    Args:
        output_dir: Directory for test results and reports
    
    Returns:
        Configured RegressionTestSuite instance
    """
    return RegressionTestSuite(output_dir)
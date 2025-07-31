"""
Real-time performance monitoring and adaptive optimization for AutoCut.

This module provides comprehensive real-time performance monitoring, bottleneck
detection, and adaptive optimization to maintain 15x real-time processing targets.
"""

import time
import threading
import queue
import psutil
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable, NamedTuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import json
import weakref
from contextlib import contextmanager

from ..utils.logging import get_logger
from ..utils.config import config

logger = get_logger(__name__)


class PerformanceState(Enum):
    """Current performance state of the system"""
    OPTIMAL = "optimal"           # Performance above target
    ACCEPTABLE = "acceptable"     # Performance at target
    DEGRADED = "degraded"        # Performance below target but manageable
    CRITICAL = "critical"        # Performance significantly below target


class BottleneckType(Enum):
    """Types of performance bottlenecks"""
    CPU = "cpu"                  # CPU-bound bottleneck
    MEMORY = "memory"            # Memory-bound bottleneck
    IO = "io"                    # I/O-bound bottleneck
    GPU = "gpu"                  # GPU-bound bottleneck
    ALGORITHM = "algorithm"      # Algorithm efficiency bottleneck
    THREADING = "threading"      # Thread contention bottleneck


@dataclass
class PerformanceMetric:
    """Individual performance metric measurement"""
    timestamp: float
    component: str
    metric_name: str
    value: float
    target_value: Optional[float] = None
    unit: str = ""
    
    @property
    def performance_ratio(self) -> Optional[float]:
        """Ratio of actual to target performance"""
        if self.target_value and self.target_value > 0:
            return self.value / self.target_value
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'component': self.component,
            'metric_name': self.metric_name,
            'value': self.value,
            'target_value': self.target_value,
            'unit': self.unit,
            'performance_ratio': self.performance_ratio
        }


@dataclass
class BottleneckInfo:
    """Information about a detected bottleneck"""
    bottleneck_type: BottleneckType
    component: str
    severity: float  # 0.0 to 1.0, where 1.0 is most severe
    description: str
    suggested_actions: List[str]
    detected_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    
    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None
    
    @property
    def duration(self) -> float:
        end_time = self.resolved_at or time.time()
        return end_time - self.detected_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'bottleneck_type': self.bottleneck_type.value,
            'component': self.component,
            'severity': self.severity,
            'description': self.description,
            'suggested_actions': self.suggested_actions,
            'detected_at': self.detected_at,
            'resolved_at': self.resolved_at,
            'duration': self.duration,
            'is_resolved': self.is_resolved
        }


class PerformanceBuffer:
    """Circular buffer for performance metrics with statistical analysis"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.buffer = deque(maxlen=max_size)
        self._lock = threading.Lock()
    
    def add_metric(self, metric: PerformanceMetric):
        """Add a performance metric to the buffer"""
        with self._lock:
            self.buffer.append(metric)
    
    def get_recent_metrics(self, seconds: float = 60.0) -> List[PerformanceMetric]:
        """Get metrics from the last N seconds"""
        cutoff_time = time.time() - seconds
        with self._lock:
            return [m for m in self.buffer if m.timestamp >= cutoff_time]
    
    def get_statistics(self, 
                      component: Optional[str] = None,
                      metric_name: Optional[str] = None,
                      seconds: float = 60.0) -> Dict[str, float]:
        """Get statistical analysis of metrics"""
        
        # Filter metrics
        metrics = self.get_recent_metrics(seconds)
        if component:
            metrics = [m for m in metrics if m.component == component]
        if metric_name:
            metrics = [m for m in metrics if m.metric_name == metric_name]
        
        if not metrics:
            return {}
        
        values = [m.value for m in metrics]
        
        return {
            'count': len(values),
            'mean': np.mean(values),
            'median': np.median(values),
            'std': np.std(values),
            'min': np.min(values),
            'max': np.max(values),
            'p95': np.percentile(values, 95),
            'p99': np.percentile(values, 99)
        }
    
    def detect_trends(self, 
                     component: str,
                     metric_name: str,
                     window_size: int = 10) -> Dict[str, Any]:
        """Detect trends in performance metrics"""
        
        metrics = [m for m in self.buffer 
                  if m.component == component and m.metric_name == metric_name]
        
        if len(metrics) < window_size:
            return {'trend': 'insufficient_data'}
        
        # Get recent values
        recent_values = [m.value for m in metrics[-window_size:]]
        timestamps = [m.timestamp for m in metrics[-window_size:]]
        
        # Calculate trend using linear regression
        if len(recent_values) > 1:
            coeffs = np.polyfit(timestamps, recent_values, 1)
            slope = coeffs[0]
            
            # Determine trend direction
            if abs(slope) < 0.01:  # Threshold for stable trend
                trend = 'stable'
            elif slope > 0:
                trend = 'improving'
            else:
                trend = 'degrading'
            
            return {
                'trend': trend,
                'slope': slope,
                'recent_mean': np.mean(recent_values),
                'change_rate': slope * 100  # Percentage change per unit time
            }
        
        return {'trend': 'unknown'}


class BottleneckDetector:
    """Advanced bottleneck detection with machine learning-inspired analysis"""
    
    def __init__(self):
        self.active_bottlenecks: Dict[str, BottleneckInfo] = {}
        self.resolved_bottlenecks: List[BottleneckInfo] = []
        self.detection_rules = self._initialize_detection_rules()
        self._lock = threading.Lock()
    
    def _initialize_detection_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize bottleneck detection rules"""
        return {
            'cpu_saturation': {
                'threshold': 90.0,
                'duration': 5.0,  # seconds
                'severity_multiplier': 1.0,
                'bottleneck_type': BottleneckType.CPU,
                'description': 'CPU utilization consistently above 90%',
                'actions': [
                    'Reduce processing quality settings',
                    'Increase frame sampling interval',
                    'Enable hardware acceleration if available'
                ]
            },
            'memory_pressure': {
                'threshold': 85.0,
                'duration': 3.0,
                'severity_multiplier': 1.2,
                'bottleneck_type': BottleneckType.MEMORY,
                'description': 'Memory utilization above 85%',
                'actions': [
                    'Enable streaming processing mode',
                    'Reduce batch sizes',
                    'Clear unnecessary caches'
                ]
            },
            'processing_slowdown': {
                'threshold': 0.7,  # 70% of target performance
                'duration': 10.0,
                'severity_multiplier': 1.5,
                'bottleneck_type': BottleneckType.ALGORITHM,
                'description': 'Processing speed below 70% of target',
                'actions': [
                    'Switch to speed-optimized algorithms',
                    'Increase frame sampling',
                    'Reduce processing resolution'
                ]
            },
            'thread_contention': {
                'threshold': 50.0,  # Context switches per second
                'duration': 5.0,
                'severity_multiplier': 0.8,
                'bottleneck_type': BottleneckType.THREADING,
                'description': 'High thread contention detected',
                'actions': [
                    'Reduce number of worker threads',
                    'Optimize critical section locks',
                    'Use lock-free data structures where possible'
                ]
            }
        }
    
    def analyze_metrics(self, 
                       performance_buffer: PerformanceBuffer,
                       system_metrics: Dict[str, float]) -> List[BottleneckInfo]:
        """Analyze metrics and detect bottlenecks"""
        
        detected_bottlenecks = []
        current_time = time.time()
        
        # Check CPU bottlenecks
        cpu_usage = system_metrics.get('cpu_percent', 0.0)
        if self._check_threshold_breach('cpu_saturation', cpu_usage, current_time):
            bottleneck = self._create_bottleneck('cpu_saturation', 'system', cpu_usage / 100.0)
            detected_bottlenecks.append(bottleneck)
        
        # Check memory bottlenecks
        memory_usage = system_metrics.get('memory_percent', 0.0)
        if self._check_threshold_breach('memory_pressure', memory_usage, current_time):
            bottleneck = self._create_bottleneck('memory_pressure', 'system', memory_usage / 100.0)
            detected_bottlenecks.append(bottleneck)
        
        # Check processing speed bottlenecks
        processing_stats = performance_buffer.get_statistics(
            metric_name='processing_speed', seconds=30.0
        )
        if processing_stats and 'mean' in processing_stats:
            speed_ratio = processing_stats['mean']
            if self._check_threshold_breach('processing_slowdown', speed_ratio, current_time):
                bottleneck = self._create_bottleneck('processing_slowdown', 'pipeline', 1.0 - speed_ratio)
                detected_bottlenecks.append(bottleneck)
        
        # Update active bottlenecks
        with self._lock:
            for bottleneck in detected_bottlenecks:
                bottleneck_key = f"{bottleneck.bottleneck_type.value}_{bottleneck.component}"
                
                if bottleneck_key not in self.active_bottlenecks:
                    self.active_bottlenecks[bottleneck_key] = bottleneck
                    logger.warning(f"Bottleneck detected: {bottleneck.description}")
        
        return detected_bottlenecks
    
    def _check_threshold_breach(self, rule_name: str, value: float, timestamp: float) -> bool:
        """Check if a metric breaches its threshold for sufficient duration"""
        rule = self.detection_rules[rule_name]
        threshold = rule['threshold']
        required_duration = rule['duration']
        
        # Check if threshold is breached
        if rule_name == 'processing_slowdown':
            # For processing slowdown, value should be below threshold
            breach = value < threshold
        else:
            # For other metrics, value should be above threshold
            breach = value > threshold
        
        if not breach:
            return False
        
        # Check duration (simplified - in a real implementation, you'd track breach duration)
        return True  # For now, assume duration check passes
    
    def _create_bottleneck(self, rule_name: str, component: str, severity: float) -> BottleneckInfo:
        """Create a bottleneck info object"""
        rule = self.detection_rules[rule_name]
        
        return BottleneckInfo(
            bottleneck_type=rule['bottleneck_type'],
            component=component,
            severity=min(1.0, severity * rule['severity_multiplier']),
            description=rule['description'],
            suggested_actions=rule['actions'].copy()
        )
    
    def resolve_bottleneck(self, bottleneck_type: BottleneckType, component: str):
        """Mark a bottleneck as resolved"""
        bottleneck_key = f"{bottleneck_type.value}_{component}"
        
        with self._lock:
            if bottleneck_key in self.active_bottlenecks:
                bottleneck = self.active_bottlenecks[bottleneck_key]
                bottleneck.resolved_at = time.time()
                
                self.resolved_bottlenecks.append(bottleneck)
                del self.active_bottlenecks[bottleneck_key]
                
                logger.info(f"Bottleneck resolved: {bottleneck.description} "
                           f"(duration: {bottleneck.duration:.1f}s)")
    
    def get_active_bottlenecks(self) -> List[BottleneckInfo]:
        """Get currently active bottlenecks"""
        with self._lock:
            return list(self.active_bottlenecks.values())
    
    def get_bottleneck_history(self, hours: float = 24.0) -> List[BottleneckInfo]:
        """Get bottleneck history for the last N hours"""
        cutoff_time = time.time() - (hours * 3600)
        
        with self._lock:
            recent_resolved = [b for b in self.resolved_bottlenecks 
                             if b.detected_at >= cutoff_time]
            active = list(self.active_bottlenecks.values())
            
            return recent_resolved + active


class AdaptiveOptimizer:
    """Adaptive optimization engine that responds to performance feedback"""
    
    def __init__(self):
        self.optimization_history = []
        self.current_settings = {
            'frame_sampling_rate': 1.0,
            'processing_quality': 1.0,
            'parallel_workers': 4,
            'memory_usage_target': 0.8
        }
        self.adaptation_rules = self._initialize_adaptation_rules()
        self._lock = threading.Lock()
    
    def _initialize_adaptation_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize adaptation rules for different bottleneck types"""
        return {
            BottleneckType.CPU.value: {
                'frame_sampling_rate': {'adjustment': -0.2, 'min': 0.2, 'max': 1.0},
                'processing_quality': {'adjustment': -0.1, 'min': 0.3, 'max': 1.0},
                'parallel_workers': {'adjustment': -1, 'min': 1, 'max': 8}
            },
            BottleneckType.MEMORY.value: {
                'memory_usage_target': {'adjustment': -0.1, 'min': 0.5, 'max': 0.9},
                'parallel_workers': {'adjustment': -1, 'min': 1, 'max': 8},
                'frame_sampling_rate': {'adjustment': -0.1, 'min': 0.2, 'max': 1.0}
            },
            BottleneckType.ALGORITHM.value: {
                'frame_sampling_rate': {'adjustment': -0.3, 'min': 0.1, 'max': 1.0},
                'processing_quality': {'adjustment': -0.2, 'min': 0.2, 'max': 1.0}
            }
        }
    
    def adapt_to_bottlenecks(self, bottlenecks: List[BottleneckInfo]) -> Dict[str, float]:
        """Adapt optimization settings based on detected bottlenecks"""
        
        if not bottlenecks:
            return self.current_settings.copy()
        
        new_settings = self.current_settings.copy()
        adaptations_made = []
        
        with self._lock:
            for bottleneck in bottlenecks:
                bottleneck_type = bottleneck.bottleneck_type.value
                
                if bottleneck_type in self.adaptation_rules:
                    rules = self.adaptation_rules[bottleneck_type]
                    
                    for setting, rule in rules.items():
                        if setting in new_settings:
                            current_value = new_settings[setting]
                            adjustment = rule['adjustment'] * bottleneck.severity
                            new_value = current_value + adjustment
                            
                            # Apply bounds
                            new_value = max(rule['min'], min(rule['max'], new_value))
                            
                            if abs(new_value - current_value) > 0.01:  # Minimum change threshold
                                new_settings[setting] = new_value
                                adaptations_made.append(f"{setting}: {current_value:.2f} -> {new_value:.2f}")
            
            # Record adaptation
            if adaptations_made:
                adaptation_record = {
                    'timestamp': time.time(),
                    'bottlenecks': [b.bottleneck_type.value for b in bottlenecks],
                    'adaptations': adaptations_made,
                    'old_settings': self.current_settings.copy(),
                    'new_settings': new_settings.copy()
                }
                self.optimization_history.append(adaptation_record)
                self.current_settings = new_settings
                
                logger.info(f"Adaptive optimization applied: {', '.join(adaptations_made)}")
        
        return new_settings
    
    def get_adaptation_history(self, hours: float = 24.0) -> List[Dict[str, Any]]:
        """Get adaptation history for the last N hours"""
        cutoff_time = time.time() - (hours * 3600)
        
        with self._lock:
            return [record for record in self.optimization_history 
                   if record['timestamp'] >= cutoff_time]


class PerformanceMonitor:
    """Main performance monitoring system coordinating all monitoring components"""
    
    def __init__(self, 
                 target_speed_multiplier: float = 15.0,
                 monitoring_interval: float = 1.0):
        self.target_speed_multiplier = target_speed_multiplier
        self.monitoring_interval = monitoring_interval
        
        # Initialize components
        self.performance_buffer = PerformanceBuffer()
        self.bottleneck_detector = BottleneckDetector()
        self.adaptive_optimizer = AdaptiveOptimizer()
        
        # Monitoring state
        self.monitoring_active = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.performance_callbacks: List[Callable] = []
        
        # Current state
        self.current_state = PerformanceState.OPTIMAL
        self.state_history = deque(maxlen=100)
        
        logger.info(f"Performance monitor initialized with {target_speed_multiplier}x target speed")
    
    def start_monitoring(self):
        """Start real-time performance monitoring"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("Performance monitoring started")
    
    def stop_monitoring(self):
        """Stop performance monitoring"""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        
        logger.info("Performance monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # Collect system metrics
                system_metrics = self._collect_system_metrics()
                
                # Detect bottlenecks
                bottlenecks = self.bottleneck_detector.analyze_metrics(
                    self.performance_buffer, system_metrics
                )
                
                # Update performance state
                self._update_performance_state(system_metrics, bottlenecks)
                
                # Adaptive optimization
                if bottlenecks:
                    new_settings = self.adaptive_optimizer.adapt_to_bottlenecks(bottlenecks)
                    self._notify_performance_callbacks('settings_updated', new_settings)
                
                # Notify callbacks of current state
                self._notify_performance_callbacks('state_update', {
                    'state': self.current_state,
                    'bottlenecks': bottlenecks,
                    'system_metrics': system_metrics
                })
                
                time.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.monitoring_interval)
    
    def _collect_system_metrics(self) -> Dict[str, float]:
        """Collect current system performance metrics"""
        try:
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_mb': memory.available / (1024**2),
                'timestamp': time.time()
            }
        except Exception as e:
            logger.debug(f"Error collecting system metrics: {e}")
            return {}
    
    def _update_performance_state(self, 
                                system_metrics: Dict[str, float],
                                bottlenecks: List[BottleneckInfo]):
        """Update current performance state"""
        
        # Determine state based on bottlenecks and metrics
        if not bottlenecks:
            new_state = PerformanceState.OPTIMAL
        else:
            max_severity = max(b.severity for b in bottlenecks)
            
            if max_severity >= 0.8:
                new_state = PerformanceState.CRITICAL
            elif max_severity >= 0.6:
                new_state = PerformanceState.DEGRADED
            else:
                new_state = PerformanceState.ACCEPTABLE
        
        # Update state if changed
        if new_state != self.current_state:
            logger.info(f"Performance state changed: {self.current_state.value} -> {new_state.value}")
            self.current_state = new_state
        
        # Record state history
        self.state_history.append({
            'timestamp': time.time(),
            'state': new_state,
            'bottleneck_count': len(bottlenecks)
        })
    
    def _notify_performance_callbacks(self, event_type: str, data: Any):
        """Notify registered performance callbacks"""
        for callback in self.performance_callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                logger.debug(f"Error in performance callback: {e}")
    
    def add_performance_callback(self, callback: Callable):
        """Add a callback for performance events"""
        self.performance_callbacks.append(callback)
    
    def remove_performance_callback(self, callback: Callable):
        """Remove a performance callback"""
        if callback in self.performance_callbacks:
            self.performance_callbacks.remove(callback)
    
    def record_component_performance(self, 
                                   component: str,
                                   execution_time: float,
                                   target_time: Optional[float] = None):
        """Record performance metrics for a component"""
        
        # Calculate performance metrics
        if target_time:
            speed_multiplier = target_time / execution_time if execution_time > 0 else 0
        else:
            # Use default target based on desired speed multiplier
            target_time = 1.0 / self.target_speed_multiplier  # seconds per frame at target speed
            speed_multiplier = target_time / execution_time if execution_time > 0 else 0
        
        # Record metrics
        metrics = [
            PerformanceMetric(
                timestamp=time.time(),
                component=component,
                metric_name='execution_time',
                value=execution_time,
                target_value=target_time,
                unit='seconds'
            ),
            PerformanceMetric(
                timestamp=time.time(),
                component=component,
                metric_name='speed_multiplier',
                value=speed_multiplier,
                target_value=self.target_speed_multiplier,
                unit='x'
            )
        ]
        
        for metric in metrics:
            self.performance_buffer.add_metric(metric)
    
    @contextmanager
    def monitor_component(self, component_name: str):
        """Context manager for monitoring component performance"""
        start_time = time.time()
        
        try:
            yield
        finally:
            execution_time = time.time() - start_time
            self.record_component_performance(component_name, execution_time)
    
    def get_performance_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive performance dashboard data"""
        
        recent_stats = self.performance_buffer.get_statistics(seconds=300.0)  # Last 5 minutes
        active_bottlenecks = self.bottleneck_detector.get_active_bottlenecks()
        current_settings = self.adaptive_optimizer.current_settings.copy()
        
        return {
            'current_state': self.current_state.value,
            'target_speed_multiplier': self.target_speed_multiplier,
            'recent_performance': recent_stats,
            'active_bottlenecks': [b.to_dict() for b in active_bottlenecks],
            'current_optimization_settings': current_settings,
            'state_history': list(self.state_history)[-20:],  # Last 20 state changes
            'monitoring_active': self.monitoring_active
        }
    
    def export_performance_report(self, output_path: str, hours: float = 24.0):
        """Export detailed performance report"""
        
        report_data = {
            'report_generated': time.time(),
            'monitoring_period_hours': hours,
            'target_speed_multiplier': self.target_speed_multiplier,
            'performance_statistics': {},
            'bottleneck_history': [b.to_dict() for b in self.bottleneck_detector.get_bottleneck_history(hours)],
            'adaptation_history': self.adaptive_optimizer.get_adaptation_history(hours),
            'state_history': list(self.state_history)
        }
        
        # Get performance statistics for each component
        components = set()
        for metric in self.performance_buffer.buffer:
            components.add(metric.component)
        
        for component in components:
            stats = self.performance_buffer.get_statistics(component=component, seconds=hours*3600)
            trends = self.performance_buffer.detect_trends(component, 'execution_time')
            
            report_data['performance_statistics'][component] = {
                'statistics': stats,
                'trends': trends
            }
        
        # Save report
        with open(output_path, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        logger.info(f"Performance report exported to {output_path}")


# Factory function for easy integration
def create_performance_monitor(target_speed: float = 15.0,
                             monitoring_interval: float = 1.0) -> PerformanceMonitor:
    """
    Create a configured performance monitor
    
    Args:
        target_speed: Target speed multiplier (15x = 15x real-time)
        monitoring_interval: How often to check performance (seconds)
    
    Returns:
        Configured PerformanceMonitor instance
    """
    return PerformanceMonitor(target_speed, monitoring_interval)


# Integration helpers for AutoCut components
class ComponentPerformanceTracker:
    """Helper class for tracking individual component performance"""
    
    def __init__(self, component_name: str, monitor: PerformanceMonitor):
        self.component_name = component_name
        self.monitor = monitor
        self.execution_count = 0
        self.total_time = 0.0
    
    @contextmanager
    def track_execution(self):
        """Context manager for tracking component execution"""
        with self.monitor.monitor_component(self.component_name):
            start_time = time.time()
            yield
            execution_time = time.time() - start_time
            
            self.execution_count += 1
            self.total_time += execution_time
    
    def get_average_execution_time(self) -> float:
        """Get average execution time for this component"""
        return self.total_time / self.execution_count if self.execution_count > 0 else 0.0
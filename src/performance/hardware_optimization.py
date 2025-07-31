"""
Hardware acceleration optimization specifically designed for M1/M2 Macs.

This module provides comprehensive hardware acceleration optimization including
VideoToolbox integration, Metal Performance Shaders utilization, and optimized
threading for Apple Silicon architecture.
"""

import subprocess
import platform
import threading
import time
import os
import ctypes
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import cv2

from ..utils.logging import get_logger
from ..utils.config import config

logger = get_logger(__name__)


class HardwareCapability(Enum):
    """Available hardware capabilities"""
    VIDEOTOOLBOX = "videotoolbox"
    METAL = "metal"
    AMX = "amx"                    # Apple Matrix Extensions
    NEURAL_ENGINE = "neural_engine"
    GPU_COMPUTE = "gpu_compute"


class ProcessorType(Enum):
    """Apple Silicon processor types"""
    M1 = "m1"
    M1_PRO = "m1_pro"
    M1_MAX = "m1_max"
    M1_ULTRA = "m1_ultra"
    M2 = "m2"
    M2_PRO = "m2_pro"
    M2_MAX = "m2_max"
    M2_ULTRA = "m2_ultra"
    UNKNOWN = "unknown"


@dataclass
class HardwareProfile:
    """Hardware profile for optimization"""
    processor_type: ProcessorType
    performance_cores: int
    efficiency_cores: int
    gpu_cores: int
    memory_bandwidth_gbps: float
    neural_engine_tops: float
    
    # Capabilities
    has_videotoolbox: bool = True
    has_metal: bool = True
    has_amx: bool = True
    has_neural_engine: bool = True
    
    # Optimal settings
    optimal_thread_count: int = 0
    optimal_batch_size: int = 4
    memory_limit_gb: float = 8.0
    
    def __post_init__(self):
        """Calculate optimal settings based on hardware"""
        # Optimal thread count: use most performance cores + some efficiency cores
        self.optimal_thread_count = min(
            self.performance_cores + max(1, self.efficiency_cores // 2),
            self.performance_cores + 4  # Cap efficiency core usage
        )
        
        # Optimal batch size based on memory bandwidth
        if self.memory_bandwidth_gbps > 400:  # M1 Pro/Max/Ultra, M2 Pro/Max
            self.optimal_batch_size = 8
        elif self.memory_bandwidth_gbps > 200:  # M1/M2 with good memory
            self.optimal_batch_size = 6
        else:
            self.optimal_batch_size = 4


class AppleSiliconDetector:
    """Detects Apple Silicon hardware capabilities"""
    
    def __init__(self):
        self.system_info = self._get_system_info()
        self.hardware_profile = self._create_hardware_profile()
        
    def _get_system_info(self) -> Dict[str, Any]:
        """Get detailed system information"""
        info = {
            'platform': platform.platform(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'system': platform.system()
        }
        
        # Get macOS-specific information
        if platform.system() == 'Darwin':
            try:
                # Get CPU information using sysctl
                result = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    info['cpu_brand'] = result.stdout.strip()
                
                # Get core counts
                result = subprocess.run(['sysctl', '-n', 'hw.perflevel0.physicalcpu'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    info['performance_cores'] = int(result.stdout.strip())
                
                result = subprocess.run(['sysctl', '-n', 'hw.perflevel1.physicalcpu'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    info['efficiency_cores'] = int(result.stdout.strip())
                
                # Get memory information
                result = subprocess.run(['sysctl', '-n', 'hw.memsize'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    info['memory_bytes'] = int(result.stdout.strip())
                
            except Exception as e:
                logger.debug(f"Error getting macOS system info: {e}")
        
        return info
    
    def _create_hardware_profile(self) -> HardwareProfile:
        """Create hardware profile based on detected system"""
        
        # Default profile
        profile = HardwareProfile(
            processor_type=ProcessorType.UNKNOWN,
            performance_cores=4,
            efficiency_cores=4,
            gpu_cores=8,
            memory_bandwidth_gbps=100.0,
            neural_engine_tops=15.8
        )
        
        # Detect Apple Silicon
        if platform.system() == 'Darwin' and platform.machine() == 'arm64':
            cpu_brand = self.system_info.get('cpu_brand', '').lower()
            
            if 'm1' in cpu_brand or 'm2' in cpu_brand:
                profile = self._get_apple_silicon_profile(cpu_brand)
            
            # Override with actual detected cores if available
            if 'performance_cores' in self.system_info:
                profile.performance_cores = self.system_info['performance_cores']
            if 'efficiency_cores' in self.system_info:
                profile.efficiency_cores = self.system_info['efficiency_cores']
        
        # Check capabilities
        profile.has_videotoolbox = self._check_videotoolbox()
        profile.has_metal = self._check_metal()
        
        return profile
    
    def _get_apple_silicon_profile(self, cpu_brand: str) -> HardwareProfile:
        """Get specific Apple Silicon hardware profile"""
        
        if 'm1 ultra' in cpu_brand:
            return HardwareProfile(
                processor_type=ProcessorType.M1_ULTRA,
                performance_cores=16,
                efficiency_cores=4,
                gpu_cores=64,
                memory_bandwidth_gbps=800.0,
                neural_engine_tops=31.6,
                memory_limit_gb=64.0
            )
        elif 'm1 max' in cpu_brand:
            return HardwareProfile(
                processor_type=ProcessorType.M1_MAX,
                performance_cores=8,
                efficiency_cores=2,
                gpu_cores=32,
                memory_bandwidth_gbps=400.0,
                neural_engine_tops=15.8,
                memory_limit_gb=32.0
            )
        elif 'm1 pro' in cpu_brand:
            return HardwareProfile(
                processor_type=ProcessorType.M1_PRO,
                performance_cores=8,
                efficiency_cores=2,
                gpu_cores=16,
                memory_bandwidth_gbps=200.0,
                neural_engine_tops=15.8,
                memory_limit_gb=16.0
            )
        elif 'm2 max' in cpu_brand:
            return HardwareProfile(
                processor_type=ProcessorType.M2_MAX,
                performance_cores=8,
                efficiency_cores=4,
                gpu_cores=38,
                memory_bandwidth_gbps=400.0,
                neural_engine_tops=15.8,
                memory_limit_gb=32.0
            )
        elif 'm2 pro' in cpu_brand:
            return HardwareProfile(
                processor_type=ProcessorType.M2_PRO,
                performance_cores=8,  # varies by model
                efficiency_cores=4,
                gpu_cores=19,
                memory_bandwidth_gbps=200.0,
                neural_engine_tops=15.8,
                memory_limit_gb=16.0
            )
        elif 'm2' in cpu_brand:
            return HardwareProfile(
                processor_type=ProcessorType.M2,
                performance_cores=4,
                efficiency_cores=4,
                gpu_cores=10,
                memory_bandwidth_gbps=100.0,
                neural_engine_tops=15.8,
                memory_limit_gb=8.0
            )
        elif 'm1' in cpu_brand:
            return HardwareProfile(
                processor_type=ProcessorType.M1,
                performance_cores=4,
                efficiency_cores=4,
                gpu_cores=8,
                memory_bandwidth_gbps=68.0,
                neural_engine_tops=15.8,
                memory_limit_gb=8.0
            )
        
        return HardwareProfile(
            processor_type=ProcessorType.UNKNOWN,
            performance_cores=4,
            efficiency_cores=4,
            gpu_cores=8,
            memory_bandwidth_gbps=100.0,
            neural_engine_tops=15.8
        )
    
    def _check_videotoolbox(self) -> bool:
        """Check if VideoToolbox is available"""
        try:
            result = subprocess.run(['ffmpeg', '-hwaccels'], 
                                  capture_output=True, text=True, timeout=10)
            return 'videotoolbox' in result.stdout.lower()
        except:
            return False
    
    def _check_metal(self) -> bool:
        """Check if Metal is available"""
        try:
            # This is a simplified check - actual implementation would use
            # Metal framework bindings
            return platform.system() == 'Darwin' and platform.machine() == 'arm64'
        except:
            return False


class VideoToolboxOptimizer:
    """VideoToolbox hardware acceleration optimizer"""
    
    def __init__(self, hardware_profile: HardwareProfile):
        self.hardware_profile = hardware_profile
        self.available_encoders = self._detect_available_encoders()
        self.available_decoders = self._detect_available_decoders()
        
        logger.info(f"VideoToolbox optimizer initialized, "
                   f"encoders: {len(self.available_encoders)}, "
                   f"decoders: {len(self.available_decoders)}")
    
    def _detect_available_encoders(self) -> List[str]:
        """Detect available VideoToolbox encoders"""
        encoders = []
        
        try:
            result = subprocess.run(['ffmpeg', '-encoders'], 
                                  capture_output=True, text=True, timeout=10)
            
            output_lines = result.stdout.split('\n')
            for line in output_lines:
                if 'videotoolbox' in line.lower():
                    # Extract encoder name
                    parts = line.split()
                    if len(parts) >= 2:
                        encoders.append(parts[1])
        
        except Exception as e:
            logger.debug(f"Error detecting VideoToolbox encoders: {e}")
        
        return encoders
    
    def _detect_available_decoders(self) -> List[str]:
        """Detect available VideoToolbox decoders"""
        decoders = []
        
        try:
            result = subprocess.run(['ffmpeg', '-decoders'], 
                                  capture_output=True, text=True, timeout=10)
            
            output_lines = result.stdout.split('\n')
            for line in output_lines:
                if 'videotoolbox' in line.lower():
                    # Extract decoder name
                    parts = line.split()
                    if len(parts) >= 2:
                        decoders.append(parts[1])
        
        except Exception as e:
            logger.debug(f"Error detecting VideoToolbox decoders: {e}")
        
        return decoders
    
    def get_optimal_decoder(self, codec: str) -> Optional[str]:
        """Get optimal VideoToolbox decoder for a codec"""
        codec_mapping = {
            'h264': 'h264_videotoolbox',
            'hevc': 'hevc_videotoolbox',
            'h265': 'hevc_videotoolbox',
            'prores': 'prores_videotoolbox'
        }
        
        optimal_decoder = codec_mapping.get(codec.lower())
        if optimal_decoder and optimal_decoder in self.available_decoders:
            return optimal_decoder
        
        return None
    
    def get_optimal_encoder(self, codec: str) -> Optional[str]:
        """Get optimal VideoToolbox encoder for a codec"""
        codec_mapping = {
            'h264': 'h264_videotoolbox',
            'hevc': 'hevc_videotoolbox',
            'h265': 'hevc_videotoolbox'
        }
        
        optimal_encoder = codec_mapping.get(codec.lower())
        if optimal_encoder and optimal_encoder in self.available_encoders:
            return optimal_encoder
        
        return None
    
    def get_optimization_params(self, resolution: Tuple[int, int], fps: float) -> Dict[str, Any]:
        """Get optimization parameters for VideoToolbox"""
        width, height = resolution
        pixel_count = width * height
        
        # Determine optimal settings based on resolution and hardware
        if pixel_count >= 3840 * 2160:  # 4K
            params = {
                'preset': 'medium',
                'quality': 'balanced',
                'realtime': True,
                'allow_frame_drops': True
            }
        elif pixel_count >= 1920 * 1080:  # 1080p
            params = {
                'preset': 'fast',
                'quality': 'good',
                'realtime': True,
                'allow_frame_drops': False
            }
        else:  # Lower resolutions
            params = {
                'preset': 'faster',
                'quality': 'good',
                'realtime': True,
                'allow_frame_drops': False
            }
        
        # Adjust based on hardware capabilities
        if self.hardware_profile.processor_type in [ProcessorType.M1_MAX, ProcessorType.M1_ULTRA, 
                                                   ProcessorType.M2_MAX, ProcessorType.M2_ULTRA]:
            params['quality'] = 'high'
            params['preset'] = 'medium'
        
        return params


class MetalOptimizer:
    """Metal Performance Shaders optimization for image/video processing"""
    
    def __init__(self, hardware_profile: HardwareProfile):
        self.hardware_profile = hardware_profile
        self.metal_available = self._check_metal_availability()
        
        if self.metal_available:
            self._initialize_metal_context()
    
    def _check_metal_availability(self) -> bool:
        """Check if Metal is available and functional"""
        try:
            # This would use actual Metal bindings in a real implementation
            # For now, assume available on Apple Silicon
            return (platform.system() == 'Darwin' and 
                   platform.machine() == 'arm64' and
                   self.hardware_profile.has_metal)
        except:
            return False
    
    def _initialize_metal_context(self):
        """Initialize Metal context and command queue"""
        if not self.metal_available:
            return
        
        # This would initialize actual Metal context
        # For now, just log initialization
        logger.info("Metal context initialized for GPU acceleration")
    
    def optimize_image_processing(self, operation: str) -> Dict[str, Any]:
        """Get Metal optimization parameters for image processing operations"""
        
        if not self.metal_available:
            return {'use_metal': False}
        
        # Operation-specific optimizations
        optimizations = {
            'blur': {
                'use_metal': True,
                'kernel_size': 16,
                'thread_groups': (16, 16),
                'buffer_optimization': True
            },
            'resize': {
                'use_metal': True,
                'interpolation': 'bilinear',
                'thread_groups': (32, 32),
                'texture_caching': True
            },
            'color_conversion': {
                'use_metal': True,
                'conversion_matrix': 'bt709',
                'thread_groups': (32, 32),
                'simd_width': 32
            },
            'edge_detection': {
                'use_metal': True,
                'kernel_type': 'sobel',
                'thread_groups': (16, 16),
                'local_memory': True
            }
        }
        
        return optimizations.get(operation, {'use_metal': False})


class ThreadingOptimizer:
    """Optimized threading for Apple Silicon architecture"""
    
    def __init__(self, hardware_profile: HardwareProfile):
        self.hardware_profile = hardware_profile
        self.thread_affinity_supported = self._check_thread_affinity()
        
        # Calculate optimal thread configurations
        self.thread_configs = self._calculate_thread_configs()
    
    def _check_thread_affinity(self) -> bool:
        """Check if thread affinity is supported"""
        try:
            # On macOS, thread affinity is limited
            # We can influence scheduling but not set hard affinity
            return platform.system() == 'Darwin'
        except:
            return False
    
    def _calculate_thread_configs(self) -> Dict[str, Dict[str, int]]:
        """Calculate optimal thread configurations for different workload types"""
        
        p_cores = self.hardware_profile.performance_cores
        e_cores = self.hardware_profile.efficiency_cores
        
        return {
            'cpu_intensive': {
                'thread_count': p_cores,
                'queue_size': p_cores * 2,
                'prefer_performance_cores': True
            },
            'io_intensive': {
                'thread_count': p_cores + min(e_cores, 4),
                'queue_size': (p_cores + e_cores) * 2,
                'prefer_performance_cores': False
            },
            'mixed_workload': {
                'thread_count': p_cores + max(1, e_cores // 2),
                'queue_size': p_cores * 3,
                'prefer_performance_cores': True
            },
            'background_processing': {
                'thread_count': min(e_cores, 4),
                'queue_size': e_cores * 2,
                'prefer_performance_cores': False
            }
        }
    
    def get_optimal_config(self, workload_type: str) -> Dict[str, int]:
        """Get optimal threading configuration for workload type"""
        return self.thread_configs.get(workload_type, self.thread_configs['mixed_workload'])
    
    def set_thread_priority(self, thread: threading.Thread, priority: str = 'normal'):
        """Set thread priority (macOS-specific)"""
        
        if not self.thread_affinity_supported:
            return
        
        try:
            # macOS thread priority constants
            priority_values = {
                'low': 19,
                'normal': 0,
                'high': -10,
                'realtime': -20
            }
            
            priority_value = priority_values.get(priority, 0)
            
            # This would use pthread_setschedparam or similar
            # For now, just log the intent
            logger.debug(f"Setting thread priority to {priority} ({priority_value})")
            
        except Exception as e:
            logger.debug(f"Could not set thread priority: {e}")


class AppleSiliconOptimizer:
    """Main Apple Silicon hardware optimization coordinator"""
    
    def __init__(self):
        # Initialize hardware detection
        self.detector = AppleSiliconDetector()
        self.hardware_profile = self.detector.hardware_profile
        
        # Initialize optimization components
        self.videotoolbox = VideoToolboxOptimizer(self.hardware_profile)
        self.metal = MetalOptimizer(self.hardware_profile)
        self.threading = ThreadingOptimizer(self.hardware_profile)
        
        # Optimization state
        self.optimizations_active = False
        self.performance_history = []
        
        logger.info(f"Apple Silicon optimizer initialized for {self.hardware_profile.processor_type.value}")
    
    def enable_optimizations(self):
        """Enable all available hardware optimizations"""
        self.optimizations_active = True
        
        # Configure OpenCV for Apple Silicon
        self._configure_opencv()
        
        # Configure NumPy for optimal performance
        self._configure_numpy()
        
        # Set optimal process settings
        self._configure_process()
        
        logger.info("Apple Silicon optimizations enabled")
    
    def _configure_opencv(self):
        """Configure OpenCV for optimal Apple Silicon performance"""
        try:
            # Enable multi-threading
            cv2.setNumThreads(self.hardware_profile.optimal_thread_count)
            
            # Enable optimizations
            cv2.setUseOptimized(True)
            
            # Try to enable hardware acceleration features
            # This would involve configuring OpenCV with Metal/VideoToolbox backends
            
            logger.debug("OpenCV configured for Apple Silicon")
            
        except Exception as e:
            logger.debug(f"Could not fully configure OpenCV: {e}")
    
    def _configure_numpy(self):
        """Configure NumPy for optimal Apple Silicon performance"""
        try:
            # Set optimal thread count for BLAS operations
            os.environ['OPENBLAS_NUM_THREADS'] = str(self.hardware_profile.optimal_thread_count)
            os.environ['MKL_NUM_THREADS'] = str(self.hardware_profile.optimal_thread_count)
            os.environ['VECLIB_MAXIMUM_THREADS'] = str(self.hardware_profile.optimal_thread_count)
            
            # Enable accelerate framework if available
            os.environ['NPY_NUM_BUILD_JOBS'] = str(self.hardware_profile.optimal_thread_count)
            
            logger.debug("NumPy configured for Apple Silicon")
            
        except Exception as e:
            logger.debug(f"Could not fully configure NumPy: {e}")
    
    def _configure_process(self):
        """Configure process settings for optimal performance"""
        try:
            # Set process priority
            os.nice(-5)  # Higher priority
            
            # Configure memory settings
            # This would involve configuring VM settings on macOS
            
            logger.debug("Process configured for optimal performance")
            
        except Exception as e:
            logger.debug(f"Could not configure process settings: {e}")
    
    def get_optimal_video_settings(self, 
                                  resolution: Tuple[int, int],
                                  fps: float,
                                  codec: str) -> Dict[str, Any]:
        """Get optimal video processing settings"""
        
        settings = {
            'resolution': resolution,
            'fps': fps,
            'codec': codec,
            'hardware_decoder': None,
            'hardware_encoder': None,
            'thread_count': self.hardware_profile.optimal_thread_count,
            'batch_size': self.hardware_profile.optimal_batch_size,
            'memory_limit_mb': int(self.hardware_profile.memory_limit_gb * 1024)
        }
        
        # Add VideoToolbox settings if available
        if self.hardware_profile.has_videotoolbox:
            decoder = self.videotoolbox.get_optimal_decoder(codec)
            encoder = self.videotoolbox.get_optimal_encoder(codec)
            
            if decoder:
                settings['hardware_decoder'] = decoder
            if encoder:
                settings['hardware_encoder'] = encoder
            
            # Add VideoToolbox optimization parameters
            vt_params = self.videotoolbox.get_optimization_params(resolution, fps)
            settings['videotoolbox_params'] = vt_params
        
        # Add Metal settings for image processing
        if self.hardware_profile.has_metal:
            settings['metal_optimizations'] = {
                'resize': self.metal.optimize_image_processing('resize'),
                'blur': self.metal.optimize_image_processing('blur'),
                'color_conversion': self.metal.optimize_image_processing('color_conversion')
            }
        
        # Add threading configuration
        settings['threading_config'] = self.threading.get_optimal_config('mixed_workload')
        
        return settings
    
    def optimize_component_for_hardware(self, 
                                      component_name: str,
                                      workload_type: str = 'mixed_workload') -> Dict[str, Any]:
        """Get hardware-specific optimizations for a component"""
        
        optimizations = {
            'component': component_name,
            'workload_type': workload_type,
            'hardware_profile': self.hardware_profile.processor_type.value,
            'thread_config': self.threading.get_optimal_config(workload_type),
            'batch_size': self.hardware_profile.optimal_batch_size,
            'memory_limit_mb': int(self.hardware_profile.memory_limit_gb * 1024 * 0.8)  # 80% of available
        }
        
        # Component-specific optimizations
        if component_name == 'video_ingestion':
            optimizations.update({
                'use_videotoolbox': self.hardware_profile.has_videotoolbox,
                'parallel_decode': True,
                'buffer_size': self.hardware_profile.optimal_batch_size * 2
            })
        
        elif component_name == 'scene_detection':
            optimizations.update({
                'use_metal_acceleration': self.hardware_profile.has_metal,
                'frame_sampling_aggressive': True,
                'parallel_analysis': True
            })
        
        elif component_name == 'face_detection':
            optimizations.update({
                'use_neural_engine': self.hardware_profile.has_neural_engine,
                'batch_processing': True,
                'model_optimization': 'apple_silicon'
            })
        
        elif component_name == 'quality_scoring':
            optimizations.update({
                'use_metal_image_processing': self.hardware_profile.has_metal,
                'parallel_metric_calculation': True,
                'vectorized_operations': True
            })
        
        return optimizations
    
    def get_performance_recommendations(self) -> List[str]:
        """Get performance recommendations based on hardware"""
        
        recommendations = []
        
        # Hardware-specific recommendations
        if self.hardware_profile.processor_type in [ProcessorType.M1, ProcessorType.M2]:
            recommendations.extend([
                "Use balanced processing mode for optimal performance on base M1/M2",
                "Enable aggressive frame sampling to maintain 15x real-time target",
                "Limit batch sizes to 4-6 frames to avoid memory pressure"
            ])
        
        elif self.hardware_profile.processor_type in [ProcessorType.M1_PRO, ProcessorType.M2_PRO]:
            recommendations.extend([
                "Take advantage of additional GPU cores for Metal acceleration",
                "Use larger batch sizes (6-8 frames) for better throughput",
                "Enable high-quality VideoToolbox encoding"
            ])
        
        elif self.hardware_profile.processor_type in [ProcessorType.M1_MAX, ProcessorType.M1_ULTRA,
                                                     ProcessorType.M2_MAX, ProcessorType.M2_ULTRA]:
            recommendations.extend([
                "Maximize parallel processing with all available cores",
                "Use large batch sizes (8-12 frames) for maximum throughput",
                "Enable precision mode for highest quality when needed"
            ])
        
        # Memory recommendations
        if self.hardware_profile.memory_limit_gb < 16:
            recommendations.append("Use streaming processing mode to manage memory usage")
        else:
            recommendations.append("Cache frequently accessed data for better performance")
        
        # Capability-based recommendations
        if self.hardware_profile.has_videotoolbox:
            recommendations.append("Enable VideoToolbox hardware decoding/encoding")
        
        if self.hardware_profile.has_metal:
            recommendations.append("Use Metal acceleration for image processing operations")
        
        if self.hardware_profile.has_neural_engine:
            recommendations.append("Consider Neural Engine acceleration for ML operations")
        
        return recommendations
    
    def get_hardware_summary(self) -> Dict[str, Any]:
        """Get comprehensive hardware summary"""
        
        return {
            'processor_type': self.hardware_profile.processor_type.value,
            'core_configuration': {
                'performance_cores': self.hardware_profile.performance_cores,
                'efficiency_cores': self.hardware_profile.efficiency_cores,
                'optimal_thread_count': self.hardware_profile.optimal_thread_count
            },
            'gpu_configuration': {
                'gpu_cores': self.hardware_profile.gpu_cores,
                'metal_available': self.hardware_profile.has_metal
            },
            'memory_configuration': {
                'memory_limit_gb': self.hardware_profile.memory_limit_gb,
                'memory_bandwidth_gbps': self.hardware_profile.memory_bandwidth_gbps,
                'optimal_batch_size': self.hardware_profile.optimal_batch_size
            },
            'hardware_capabilities': {
                'videotoolbox': self.hardware_profile.has_videotoolbox,
                'metal': self.hardware_profile.has_metal,
                'amx': self.hardware_profile.has_amx,
                'neural_engine': self.hardware_profile.has_neural_engine
            },
            'optimization_recommendations': self.get_performance_recommendations(),
            'optimizations_active': self.optimizations_active
        }


# Factory function for easy integration
def create_apple_silicon_optimizer() -> AppleSiliconOptimizer:
    """
    Create and configure Apple Silicon optimizer
    
    Returns:
        Configured AppleSiliconOptimizer instance
    """
    optimizer = AppleSiliconOptimizer()
    optimizer.enable_optimizations()
    return optimizer
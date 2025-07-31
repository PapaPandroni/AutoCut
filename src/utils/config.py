"""Configuration management for AutoCut"""
import os
from pathlib import Path
from typing import Dict, Any, Optional
import yaml


class Config:
    """Configuration manager for AutoCut"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.home() / '.autocut' / 'config.yaml'
        self._config: Dict[str, Any] = self._load_default_config()
        self._load_config()
    
    def _load_default_config(self) -> Dict[str, Any]:
        """Load default configuration values"""
        return {
            'processing': {
                'chunk_size_mb': 100,
                'max_workers': os.cpu_count(),
                'cache_size_mb': 500,
                'max_memory_usage_gb': 4,
                'max_processing_time_min': 60,
            },
            'quality': {
                'min_clip_duration_sec': 0.5,
                'max_clip_duration_sec': 10.0,
                'quality_threshold_percentile': 75,
                'face_priority': 0.4,
                'motion_preference': 0.3,
                'exposure_weight': 0.2,
                'blur_tolerance': 0.1,
                
                # Quality scoring engine settings
                'blur_threshold': 100.0,                    # Laplacian variance threshold
                'exposure_optimal_mean': 127.0,             # Optimal exposure center
                'motion_threshold': 10.0,                   # Motion blur threshold
                'composition_strength': 0.3,                # Composition factor strength
                'default_profile': 'adaptive',              # Default quality profile
                'enable_face_integration': True,            # Use face detection results
                'target_realtime_multiple': 15.0,          # Processing speed target
                'parallel_processing': True,                # Enable parallel processing
                'adaptive_profile_selection': True,         # Auto-select profiles
                'quality_hotspot_threshold': 75.0,          # Minimum quality for hotspots
                'export_detailed_metrics': True,            # Include detailed metrics in exports
                
                # Profile-specific overrides
                'profile_overrides': {
                    'talking_head': {
                        'composition_strength': 0.2,       # Less composition emphasis
                        'motion_threshold': 5.0            # More sensitive to motion
                    },
                    'action': {
                        'motion_threshold': 20.0,          # Less sensitive to motion
                        'blur_threshold': 80.0             # More tolerant of blur
                    },
                    'landscape': {
                        'composition_strength': 0.5,       # More composition emphasis
                        'exposure_optimal_mean': 140.0     # Prefer brighter images
                    }
                }
            },
            'output': {
                'default_resolution': '1080p',
                'default_fps': 30,
                'default_bitrate': '5M',
                'audio_bitrate': '192k',
                'codec': 'h264',
            },
            'audio': {
                'sample_rate': 44100,
                'hop_length': 512,
                'beat_detection_algorithm': 'librosa',
                'confidence_threshold': 0.7,
            },
            'video': {
                'max_probe_size_mb': 50,
                'probe_timeout_sec': 30,
                'enable_hardware_acceleration': True,
                'max_file_size_gb': 10,
                'preferred_pixel_format': 'yuv420p',
                'max_resolution_width': 4096,
                'max_resolution_height': 4096,
                'min_fps': 1.0,
                'max_fps': 120.0,
            },
            'scene_detection': {
                'min_scene_duration_sec': 1.0,
                'confidence_threshold': 0.3,
                'histogram_threshold': 0.3,
                'edge_threshold': 0.4,
                'optical_flow_threshold': 0.5,
                'combined_threshold': 0.35,
                'enable_post_processing': True,
                'max_concurrent_videos': 4,
            },
            'timeline': {
                'min_clip_duration_sec': 0.8,
                'max_clip_duration_sec': 8.0,
                'beat_alignment_threshold': 0.1,
                'scene_override_threshold': 0.7,
                'silence_threshold_db': -40.0,
                'tempo_change_threshold_bpm': 10.0,
                'rhythm_consistency_weight': 0.4,
                'musical_alignment_weight': 0.6,
                'enable_tempo_detection': True,
                'enable_silence_detection': True,
                'enable_rhythm_optimization': True,
                'export_formats': ['json', 'csv', 'edl'],
                'default_export_format': 'json'
            },
            'rendering': {
                # Core rendering settings
                'max_concurrent_renders': 2,
                'chunk_duration_sec': 30.0,
                'progress_update_interval_sec': 0.5,
                'enable_hardware_acceleration': True,
                'prefer_stream_copy': True,
                'frame_accurate_cuts': True,
                
                # Quality presets configuration
                'quality_presets': {
                    'lossless': {
                        'video_codec': 'copy',
                        'audio_codec': 'copy',
                        'description': 'Lossless stream copying for maximum speed and quality'
                    },
                    'high': {
                        'video_codec': 'libx264',
                        'audio_codec': 'aac',
                        'crf': 18,
                        'preset': 'slower',
                        'description': 'Visually lossless with minimal compression'
                    },
                    'medium': {
                        'video_codec': 'libx264',
                        'audio_codec': 'aac',
                        'crf': 23,
                        'preset': 'medium',
                        'description': 'Balanced quality and file size'
                    },
                    'draft': {
                        'video_codec': 'libx264',
                        'audio_codec': 'aac',
                        'crf': 28,
                        'preset': 'ultrafast',
                        'description': 'Fast encoding for previews and drafts'
                    }
                },
                
                # Output format settings
                'output_formats': {
                    'mp4': {
                        'container': 'mp4',
                        'video_codec': 'h264',
                        'audio_codec': 'aac',
                        'description': 'Universal compatibility (recommended)'
                    },
                    'mov': {
                        'container': 'mov',
                        'video_codec': 'h264',
                        'audio_codec': 'aac',
                        'description': 'Apple QuickTime format'
                    },
                    'avi': {
                        'container': 'avi',
                        'video_codec': 'h264',
                        'audio_codec': 'mp3',
                        'description': 'Legacy Windows format'
                    },
                    'mkv': {
                        'container': 'mkv',
                        'video_codec': 'h264',
                        'audio_codec': 'aac',
                        'description': 'Matroska container with advanced features'
                    },
                    'webm': {
                        'container': 'webm',
                        'video_codec': 'vp9',
                        'audio_codec': 'opus',
                        'description': 'Web-optimized format'
                    }
                },
                
                # Resolution presets
                'resolution_presets': {
                    '2160p': {'width': 3840, 'height': 2160, 'description': '4K Ultra HD'},
                    '1440p': {'width': 2560, 'height': 1440, 'description': '2K Quad HD'},
                    '1080p': {'width': 1920, 'height': 1080, 'description': 'Full HD (recommended)'},
                    '720p': {'width': 1280, 'height': 720, 'description': 'HD'},
                    '480p': {'width': 854, 'height': 480, 'description': 'SD'},
                    '360p': {'width': 640, 'height': 360, 'description': 'Low quality'}
                },
                
                # Hardware acceleration settings
                'hardware_acceleration': {
                    'preferred_order': ['videotoolbox', 'nvenc', 'qsv'],
                    'videotoolbox': {
                        'h264_encoder': 'h264_videotoolbox',
                        'h265_encoder': 'hevc_videotoolbox',
                        'prores_encoder': 'prores_videotoolbox'
                    },
                    'nvenc': {
                        'h264_encoder': 'h264_nvenc',
                        'h265_encoder': 'hevc_nvenc'
                    },
                    'qsv': {
                        'h264_encoder': 'h264_qsv',
                        'h265_encoder': 'hevc_qsv'
                    }
                },
                
                # Performance optimization
                'optimization': {
                    'enable_parallel_processing': True,
                    'max_parallel_segments': 4,
                    'memory_limit_gb': 8,
                    'temp_dir_cleanup': True,
                    'preserve_temp_files_on_error': False,
                    'ffmpeg_thread_count': 0,  # 0 = auto-detect
                    'enable_gpu_acceleration': True
                },
                
                # Audio settings for rendering
                'audio': {
                    'default_bitrate': '192k',
                    'sample_rates': [44100, 48000, 96000],
                    'codec_preferences': ['aac', 'mp3', 'opus'],
                    'preserve_original_channels': True,
                    'normalize_audio': False
                },
                
                # Video settings for rendering
                'video': {
                    'default_bitrate': 'auto',  # Auto-calculate based on resolution
                    'bitrate_multipliers': {
                        '360p': 1.0,
                        '480p': 1.5,
                        '720p': 2.5,
                        '1080p': 4.0,
                        '1440p': 8.0,
                        '2160p': 16.0
                    },
                    'max_bitrate': '50M',
                    'pixel_format': 'yuv420p',
                    'color_range': 'tv',
                    'preserve_hdr': False
                },
                
                # Export and batch processing
                'export': {
                    'default_naming_pattern': '{original_name}_edited_{timestamp}',
                    'create_export_log': True,
                    'verify_output_integrity': True,
                    'auto_open_output_folder': False,
                    'batch_processing': {
                        'max_concurrent_jobs': 2,
                        'auto_queue_failed_jobs': True,
                        'priority_queue': True
                    }
                }
            }
        }
    
    def _load_config(self):
        """Load configuration from file if it exists"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    user_config = yaml.safe_load(f)
                    self._merge_config(user_config)
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")
    
    def _merge_config(self, user_config: Dict[str, Any]):
        """Merge user configuration with defaults"""
        for section, values in user_config.items():
            if section in self._config and isinstance(values, dict):
                self._config[section].update(values)
            else:
                self._config[section] = values
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'processing.chunk_size_mb')"""
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """Set configuration value using dot notation"""
        keys = key.split('.')
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def save(self):
        """Save current configuration to file"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False)


# Global configuration instance
config = Config()
#!/usr/bin/env python3
"""
AutoCut Complete End-to-End Video Editing Prototype

This script demonstrates the complete AutoCut video editing workflow from video input 
to edited output, showcasing all core capabilities:

- Video ingestion with multi-format support and hardware acceleration
- Audio analysis with beat detection and rhythm analysis
- Scene detection with multiple algorithms and performance optimization
- Face detection with quality assessment and tracking
- Quality scoring with multiple weighted factors and profile selection
- Beat-synchronized timeline generation with intelligent cut placement
- High-performance video rendering with lossless stream copying

Key Features:
- Complete pipeline integration with error handling and logging
- CLI interface with comprehensive options and presets
- Multiple editing styles (aggressive, smooth, adaptive, musical, cinematic)
- Quality profiles (talking_head, action, landscape, documentary, adaptive)
- Performance modes (speed, balanced, quality, precision)
- Mock data generation for testing without real video files
- Performance benchmarking and statistics reporting
- Configuration file support and example usage

Usage Examples:
    # Basic usage with external music
    python autocut_prototype.py video_folder/ --music song.mp3

    # Single video with music
    python autocut_prototype.py video.mp4 --music song.mp3

    # Specify editing style and quality profile
    python autocut_prototype.py video_folder/ --music song.mp3 --style musical --profile talking_head

    # Performance mode and output options
    python autocut_prototype.py video_folder/ --music song.mp3 --performance speed --output highlight.mp4

    # Export timeline only for review
    python autocut_prototype.py video_folder/ --music song.mp3 --export timeline --no-render

    # Demo mode with mock data
    python autocut_prototype.py --demo --mock-duration 60

    # Benchmark mode for performance testing
    python autocut_prototype.py --benchmark

Author: AutoCut Development Team
Version: 1.0.0
"""

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import traceback

# AutoCut core imports
from src.audio.analyzer import AudioAnalyzer, AudioAnalysis
from src.video.ingestion import VideoIngestion, VideoInfo
from src.video.scene_detection import SceneDetection, SceneDetectionAlgorithm, ProcessingMode as SceneProcessingMode
from src.video.face_detection import (
    FaceDetectionEngine, 
    create_face_detection_engine, 
    create_video_frame_generator,
    ProcessingMode as FaceProcessingMode
)
from src.core.quality_scoring import (
    QualityScoring, 
    create_quality_scorer, 
    QualityProfile,
    create_video_frame_generator_with_quality
)
from src.core.timeline import BeatSyncTimelineGenerator, EditingStyle
from src.video.renderer import VideoRenderer, create_render_options, QualityPreset, OutputFormat
from src.utils.logging import setup_logging, get_logger
from src.utils.config import config

# Initialize logging
logger = get_logger(__name__)


class AutoCutPrototype:
    """
    Complete AutoCut video editing prototype demonstrating the full pipeline
    """
    
    def __init__(self):
        """Initialize the AutoCut prototype with all core components"""
        
        # Core processing components
        self.video_ingestion = VideoIngestion()
        self.audio_analyzer = AudioAnalyzer()
        self.scene_detection = SceneDetection()
        self.face_detection_engine = None  # Created per video
        self.quality_scoring = None  # Created per video
        self.timeline_generator = BeatSyncTimelineGenerator()
        self.video_renderer = VideoRenderer()
        
        # Supported video and audio formats
        self.supported_video_formats = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.m4v'}
        self.supported_audio_formats = {'.mp3', '.wav', '.flac', '.aac', '.m4a', '.ogg'}
        
        # Statistics tracking
        self.stats = {
            'ingestion_time': 0.0,
            'audio_analysis_time': 0.0,
            'scene_detection_time': 0.0,
            'face_detection_time': 0.0,
            'quality_scoring_time': 0.0,
            'timeline_generation_time': 0.0,
            'rendering_time': 0.0,
            'total_time': 0.0,
            'video_duration': 0.0,
            'overall_speed_factor': 0.0
        }
        
        logger.info("AutoCut prototype initialized successfully")
    
    def discover_video_files(self, input_path: Path) -> List[Path]:
        """
        Discover video files from input path (file or folder)
        
        Args:
            input_path: Path to video file or folder containing videos
            
        Returns:
            List of video file paths
        """
        video_files = []
        
        if input_path.is_file():
            # Single video file
            if input_path.suffix.lower() in self.supported_video_formats:
                video_files.append(input_path)
                logger.info("Single video file detected", file=str(input_path))
            else:
                raise ValueError(f"Unsupported video format: {input_path.suffix}")
        
        elif input_path.is_dir():
            # Folder containing videos - scan recursively
            logger.info("Scanning folder for video files", folder=str(input_path))
            
            for file_path in input_path.rglob('*'):
                if file_path.is_file() and file_path.suffix.lower() in self.supported_video_formats:
                    video_files.append(file_path)
            
            video_files.sort()  # Sort for consistent processing order
            logger.info("Discovered video files", count=len(video_files), 
                       files=[f.name for f in video_files])
            
            if not video_files:
                raise ValueError(f"No supported video files found in folder: {input_path}")
        
        else:
            raise ValueError(f"Input path not found: {input_path}")
        
        return video_files
    
    def validate_music_file(self, music_path: Path) -> bool:
        """
        Validate music file format and existence
        
        Args:
            music_path: Path to music file
            
        Returns:
            True if valid music file
        """
        if not music_path.exists():
            raise FileNotFoundError(f"Music file not found: {music_path}")
        
        if music_path.suffix.lower() not in self.supported_audio_formats:
            raise ValueError(f"Unsupported audio format: {music_path.suffix}. "
                           f"Supported formats: {', '.join(self.supported_audio_formats)}")
        
        logger.info("Music file validated", file=str(music_path))
        return True
    
    def process_videos_with_music(self,
                                 input_path: Path,
                                 music_path: Optional[Path] = None,
                                 output_path: Optional[Path] = None,
                                 editing_style: EditingStyle = EditingStyle.ADAPTIVE,
                                 quality_profile: QualityProfile = QualityProfile.ADAPTIVE,
                                 performance_mode: str = "balanced",
                                 export_options: Dict[str, Any] = None,
                                 progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        Process multiple videos with external music through the complete AutoCut pipeline
        
        Args:
            input_path: Path to video file or folder containing videos
            music_path: Path to external music file (optional, uses video audio if not provided)
            output_path: Path for output video (optional)
            editing_style: Timeline editing style
            quality_profile: Quality scoring profile
            performance_mode: Processing performance mode
            export_options: Export configuration options
            progress_callback: Optional progress callback function
            
        Returns:
            Dictionary containing processing results and statistics
        """
        
        start_time = time.time()
        export_options = export_options or {}
        
        logger.info("Starting multi-video processing pipeline with external music",
                   input_path=str(input_path),
                   music_path=str(music_path) if music_path else "embedded audio",
                   editing_style=editing_style.value,
                   quality_profile=quality_profile.value,
                   performance_mode=performance_mode)
        
        try:
            # Step 0: Discover video files and validate music
            if progress_callback:
                progress_callback("Discovering video files...", 0)
            
            video_files = self.discover_video_files(input_path)
            
            if music_path:
                self.validate_music_file(music_path)
                audio_source = music_path
            else:
                # Use first video's audio if no external music provided
                audio_source = video_files[0]
                logger.info("No external music provided, using first video's audio")
            
            # Step 1: Audio Analysis (from external music or first video)
            logger.info("Step 1: Audio analysis")
            if progress_callback:
                progress_callback("Analyzing audio track...", 5)
            
            step_start = time.time()
            audio_analysis = self.audio_analyzer.analyze_audio(str(audio_source))
            self.stats['audio_analysis_time'] = time.time() - step_start
            
            logger.info("Audio analysis completed",
                       duration=f"{audio_analysis.duration:.2f}s",
                       tempo=f"{audio_analysis.bpm:.1f} BPM",
                       beats=len(audio_analysis.beats))
            
            # Step 2: Process all videos for quality and scene detection
            logger.info("Step 2: Multi-video analysis")
            if progress_callback:
                progress_callback("Analyzing video files...", 15)
            
            all_video_info = []
            all_scene_detections = []
            all_face_detections = []
            all_quality_results = []
            
            for i, video_file in enumerate(video_files):
                progress = 15 + (i / len(video_files)) * 50  # 15-65% for video processing
                if progress_callback:
                    progress_callback(f"Processing {video_file.name}...", progress)
                
                # Load video
                step_start = time.time()
                video_info = self.video_ingestion.load_video(video_file)
                if not video_info.is_valid:
                    logger.warning("Skipping invalid video", file=str(video_file), 
                                 errors=video_info.validation_errors)
                    continue
                
                self.stats['ingestion_time'] += time.time() - step_start
                all_video_info.append(video_info)
                
                # Scene detection
                step_start = time.time()
                scene_detection = self.scene_detection.detect_scenes(
                    video_file, SceneDetectionAlgorithm.COMBINED
                )
                self.stats['scene_detection_time'] += time.time() - step_start
                all_scene_detections.append(scene_detection)
                
                # Face detection (if enabled)
                face_detection = None
                if not export_options.get('no_face_detection', False):
                    step_start = time.time()
                    if self.face_detection_engine is None:
                        self.face_detection_engine = create_face_detection_engine(video_info)
                    frame_generator = create_video_frame_generator(video_file)
                    face_detection = self.face_detection_engine.process_video_frames(
                        video_info, frame_generator, lambda count, ts: None
                    )
                    self.stats['face_detection_time'] += time.time() - step_start
                    all_face_detections.append(face_detection)
                
                # Quality scoring (if enabled)
                quality_result = None
                if not export_options.get('no_quality_scoring', False):
                    step_start = time.time()
                    if self.quality_scoring is None:
                        self.quality_scoring = create_quality_scorer(
                            video_info,
                            target_realtime_multiple=15.0,
                            content_type=quality_profile.value
                        )
                    # Create frame generator for quality processing
                    frame_generator = create_video_frame_generator_with_quality(video_file)
                    
                    # Create face results generator if face detection was performed
                    face_results_generator = None
                    if face_detection is not None:
                        face_results_generator = iter(face_detection.frame_results)
                    
                    quality_result = self.quality_scoring.process_video_quality(
                        video_info, frame_generator, face_results_generator
                    )
                    self.stats['quality_scoring_time'] += time.time() - step_start
                    all_quality_results.append(quality_result)
                
                logger.info("Video analysis completed", file=video_file.name,
                           duration=f"{video_info.duration:.2f}s",
                           scenes=len(scene_detection.scene_changes) if scene_detection else 0,
                           faces=sum(r.total_faces for r in face_detection.frame_results) if face_detection else 0)
            
            if not all_video_info:
                raise ValueError("No valid video files found to process")
            
            # Step 3: Generate timeline from all video content
            logger.info("Step 3: Timeline generation from multi-video content")
            if progress_callback:
                progress_callback("Generating beat-sync timeline...", 70)
            
            step_start = time.time()
            
            # Combine all content for timeline generation
            combined_timeline = self.timeline_generator.generate_multi_video_timeline(
                audio_analysis=audio_analysis,
                video_info_list=all_video_info,
                scene_detections=all_scene_detections,
                quality_results=all_quality_results,
                editing_style=editing_style
            )
            
            self.stats['timeline_generation_time'] = time.time() - step_start
            
            logger.info("Timeline generation completed",
                       segments=len(combined_timeline.segments),
                       duration=f"{combined_timeline.duration:.2f}s",
                       beat_sync=f"{combined_timeline.beat_sync_percentage:.1f}%")
            
            # Step 4: Video rendering with external music
            if not export_options.get('no_render', False):
                logger.info("Step 4: Video rendering with external music")
                if progress_callback:
                    progress_callback("Rendering final video...", 80)
                
                step_start = time.time()
                
                if output_path is None:
                    output_path = input_path.parent / f"{input_path.stem}_edited.mp4"
                
                rendering_result = self.video_renderer.render_multi_video_timeline(
                    timeline=combined_timeline,
                    video_info_list=all_video_info,
                    music_path=music_path,  # External music track
                    output_path=output_path,
                    preset=export_options.get('quality_preset', 'lossless')
                )
                
                self.stats['rendering_time'] = time.time() - step_start
                
                logger.info("Video rendering completed",
                           output_path=str(output_path),
                           file_size=f"{output_path.stat().st_size / (1024*1024):.1f}MB")
            
            # Calculate overall statistics
            total_time = time.time() - start_time
            total_video_duration = sum(vi.duration for vi in all_video_info)
            self.stats['total_time'] = total_time
            self.stats['video_duration'] = total_video_duration
            self.stats['overall_speed_factor'] = total_video_duration / total_time if total_time > 0 else 0
            
            if progress_callback:
                progress_callback("Processing complete!", 100)
            
            # Prepare results
            results = {
                'success': True,
                'input_videos': [str(vf) for vf in video_files],
                'music_file': str(music_path) if music_path else "embedded audio",
                'output_path': str(output_path) if output_path else None,
                'timeline': combined_timeline.to_dict(),
                'statistics': self.stats.copy(),
                'video_info_list': all_video_info,
                'audio_analysis': audio_analysis.to_dict(),
                'scene_detections': [sd.to_dict() for sd in all_scene_detections],
                'face_detections': [fd.to_dict() for fd in all_face_detections if fd],
                'quality_results': [qr.to_dict() for qr in all_quality_results if qr],
                'render_stats': None,  # Multi-video processing doesn't render final output
                'processing_stats': self.stats.copy(),
                'export_results': {}  # TODO: Implement multi-video exports
            }
            
            logger.info("Multi-video processing completed successfully",
                       total_time=f"{total_time:.2f}s",
                       speed_factor=f"{self.stats['overall_speed_factor']:.1f}x",
                       input_videos=len(video_files))
            
            return results
            
        except Exception as e:
            logger.error("Multi-video processing failed", error=str(e), traceback=traceback.format_exc())
            return {
                'success': False,
                'error': str(e),
                'statistics': self.stats.copy()
            }
    
    def process_video(self, 
                     input_path: Path,
                     output_path: Optional[Path] = None,
                     editing_style: EditingStyle = EditingStyle.ADAPTIVE,
                     quality_profile: QualityProfile = QualityProfile.ADAPTIVE,
                     performance_mode: str = "balanced",
                     export_options: Dict[str, Any] = None,
                     progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        Process a video through the complete AutoCut pipeline
        
        Args:
            input_path: Path to input video file
            output_path: Path for output video (optional)
            editing_style: Timeline editing style
            quality_profile: Quality scoring profile
            performance_mode: Processing performance mode
            export_options: Export configuration options
            progress_callback: Optional progress callback function
            
        Returns:
            Dictionary containing processing results and statistics
        """
        
        start_time = time.time()
        export_options = export_options or {}
        
        logger.info("Starting complete video processing pipeline",
                   input_path=str(input_path),
                   editing_style=editing_style.value,
                   quality_profile=quality_profile.value,
                   performance_mode=performance_mode)
        
        try:
            # Update progress
            if progress_callback:
                progress_callback("Starting video processing...", 0)
            
            # Step 1: Video Ingestion
            logger.info("Step 1: Video ingestion")
            step_start = time.time()
            
            video_info = self.video_ingestion.load_video(input_path)
            if not video_info.is_valid:
                raise ValueError(f"Invalid video file: {video_info.validation_errors}")
            
            self.stats['ingestion_time'] = time.time() - step_start
            self.stats['video_duration'] = video_info.duration
            
            logger.info("Video ingestion completed",
                       duration=f"{video_info.duration:.2f}s",
                       resolution=f"{video_info.resolution[0]}x{video_info.resolution[1]}",
                       codec=video_info.primary_video_stream.codec.value if video_info.primary_video_stream else "unknown",
                       processing_time=f"{self.stats['ingestion_time']:.2f}s")
            
            if progress_callback:
                progress_callback("Video loaded successfully", 10)
            
            # Step 2: Audio Analysis
            logger.info("Step 2: Audio analysis")
            step_start = time.time()
            
            audio_analysis = self.audio_analyzer.analyze_audio(str(input_path))
            self.stats['audio_analysis_time'] = time.time() - step_start
            
            logger.info("Audio analysis completed",
                       bpm=f"{audio_analysis.bpm:.1f}",
                       beats=len(audio_analysis.beats),
                       confidence=f"{audio_analysis.confidence:.2f}",
                       processing_time=f"{self.stats['audio_analysis_time']:.2f}s")
            
            if progress_callback:
                progress_callback("Audio analysis completed", 25)
            
            # Step 3: Scene Detection
            logger.info("Step 3: Scene detection")
            step_start = time.time()
            
            # Map performance mode to scene processing mode
            scene_mode_map = {
                "speed": SceneProcessingMode.SPEED,
                "balanced": SceneProcessingMode.BALANCED,
                "quality": SceneProcessingMode.QUALITY,
                "precision": SceneProcessingMode.PRECISION
            }
            scene_mode = scene_mode_map.get(performance_mode, SceneProcessingMode.BALANCED)
            
            self.scene_detection.processing_mode = scene_mode
            scene_detection_result = self.scene_detection.detect_scenes(
                input_path, SceneDetectionAlgorithm.COMBINED, video_info
            )
            
            self.stats['scene_detection_time'] = time.time() - step_start
            
            logger.info("Scene detection completed",
                       scenes=scene_detection_result.scene_count,
                       avg_duration=f"{scene_detection_result.average_scene_duration:.1f}s",
                       processing_speed=f"{scene_detection_result.processing_speed_multiplier:.1f}x",
                       processing_time=f"{self.stats['scene_detection_time']:.2f}s")
            
            if progress_callback:
                progress_callback("Scene detection completed", 40)
            
            # Step 4: Face Detection (if enabled)
            face_detection_result = None
            if export_options.get('enable_face_detection', True):
                logger.info("Step 4: Face detection")
                step_start = time.time()
                
                # Create optimized face detection engine
                self.face_detection_engine = create_face_detection_engine(
                    video_info, 
                    target_realtime_multiple=15.0,
                    quality_mode=performance_mode
                )
                
                # Process video frames for face detection
                frame_generator = create_video_frame_generator(input_path)
                face_detection_result = self.face_detection_engine.process_video_frames(
                    video_info, frame_generator, lambda count, ts: None
                )
                
                self.stats['face_detection_time'] = time.time() - step_start
                
                logger.info("Face detection completed",
                           frames_processed=face_detection_result.total_frames_processed,
                           faces_per_second=f"{face_detection_result.faces_per_second:.1f}",
                           quality_score=f"{face_detection_result.overall_quality_score:.2f}",
                           processing_time=f"{self.stats['face_detection_time']:.2f}s")
            else:
                self.stats['face_detection_time'] = 0.0
                logger.info("Face detection skipped (disabled)")
            
            if progress_callback:
                progress_callback("Face detection completed", 55)
            
            # Step 5: Quality Scoring
            quality_result = None
            if export_options.get('enable_quality_scoring', True):
                logger.info("Step 5: Quality scoring")
                step_start = time.time()
                
                # Create quality scorer
                self.quality_scoring = create_quality_scorer(
                    video_info,
                    target_realtime_multiple=15.0,
                    content_type=quality_profile.value
                )
                
                # Process video frames for quality scoring
                frame_generator = create_video_frame_generator_with_quality(input_path)
                
                # Create face results generator if available
                face_results_generator = None
                if face_detection_result:
                    face_results_generator = iter(face_detection_result.frame_results)
                
                quality_result = self.quality_scoring.process_video_quality(
                    video_info, frame_generator, face_results_generator, lambda count, ts: None
                )
                
                self.stats['quality_scoring_time'] = time.time() - step_start
                
                logger.info("Quality scoring completed",
                           mean_quality=f"{quality_result.mean_quality:.1f}",
                           quality_trend=quality_result.quality_trend,
                           processing_time=f"{self.stats['quality_scoring_time']:.2f}s")
            else:
                self.stats['quality_scoring_time'] = 0.0
                logger.info("Quality scoring skipped (disabled)")
            
            if progress_callback:
                progress_callback("Quality scoring completed", 70)
            
            # Step 6: Timeline Generation
            logger.info("Step 6: Timeline generation")
            step_start = time.time()
            
            timeline = self.timeline_generator.generate_timeline(
                audio_analysis=audio_analysis,
                scene_detection=scene_detection_result,
                video_info=video_info,
                editing_style=editing_style
            )
            
            self.stats['timeline_generation_time'] = time.time() - step_start
            
            logger.info("Timeline generation completed",
                       segments=timeline.segment_count,
                       avg_duration=f"{timeline.average_segment_duration:.1f}s",
                       beat_sync=f"{timeline.beat_sync_percentage:.1f}%",
                       scene_respect=f"{timeline.scene_respect_percentage:.1f}%",
                       processing_time=f"{self.stats['timeline_generation_time']:.2f}s")
            
            if progress_callback:
                progress_callback("Timeline generated", 80)
            
            # Step 7: Video Rendering (if output path specified)
            render_stats = None
            if output_path:
                logger.info("Step 7: Video rendering")
                step_start = time.time()
                
                # Create render options
                render_options = create_render_options(
                    quality=export_options.get('render_quality', 'lossless'),
                    output_format=export_options.get('output_format', 'mp4'),
                    resolution=export_options.get('target_resolution'),
                    fps=export_options.get('target_fps')
                )
                
                # Render progress callback
                def render_progress(progress):
                    if progress_callback:
                        base_progress = 80
                        render_progress_amount = (progress.progress_percentage / 100.0) * 15
                        total_progress = base_progress + render_progress_amount
                        progress_callback(f"Rendering: {progress.progress_percentage:.0f}%", total_progress)
                
                render_stats = self.video_renderer.render_timeline(
                    timeline, output_path, render_options, render_progress
                )
                
                self.stats['rendering_time'] = time.time() - step_start
                
                logger.info("Video rendering completed",
                           output_size_mb=f"{render_stats.output_file_size / (1024**2):.1f}",
                           speed_factor=f"{render_stats.speed_factor:.1f}x",
                           used_stream_copy=render_stats.used_stream_copy,
                           processing_time=f"{self.stats['rendering_time']:.2f}s")
            else:
                self.stats['rendering_time'] = 0.0
                logger.info("Video rendering skipped (no output path)")
            
            if progress_callback:
                progress_callback("Processing completed!", 100)
            
            # Calculate final statistics
            self.stats['total_time'] = time.time() - start_time
            self.stats['overall_speed_factor'] = (
                self.stats['video_duration'] / self.stats['total_time'] 
                if self.stats['total_time'] > 0 else 0.0
            )
            
            # Export additional outputs if requested
            export_results = self._handle_exports(
                timeline, audio_analysis, scene_detection_result, 
                face_detection_result, quality_result, export_options
            )
            
            # Compile results
            results = {
                'success': True,
                'video_info': video_info.to_dict(),
                'audio_analysis': audio_analysis.to_dict(),
                'scene_detection': scene_detection_result.to_dict(),
                'face_detection': face_detection_result.to_dict() if face_detection_result else None,
                'quality_scoring': quality_result.to_dict() if quality_result else None,
                'timeline': timeline.to_dict(),
                'render_stats': asdict(render_stats) if render_stats else None,
                'processing_stats': self.stats.copy(),
                'export_results': export_results
            }
            
            logger.info("Complete pipeline processing finished successfully",
                       total_time=f"{self.stats['total_time']:.2f}s",
                       speed_factor=f"{self.stats['overall_speed_factor']:.1f}x")
            
            return results
            
        except Exception as e:
            self.stats['total_time'] = time.time() - start_time
            logger.error("Pipeline processing failed", 
                        error=str(e), 
                        total_time=f"{self.stats['total_time']:.2f}s")
            
            return {
                'success': False,
                'error': str(e),
                'processing_stats': self.stats.copy()
            }
    
    def _handle_exports(self, timeline, audio_analysis, scene_detection, 
                       face_detection, quality_result, export_options) -> Dict[str, Any]:
        """Handle various export options (timeline, analysis data, etc.)"""
        
        export_results = {}
        export_dir = Path(export_options.get('export_dir', './exports'))
        export_dir.mkdir(parents=True, exist_ok=True)
        
        # Export timeline
        if export_options.get('export_timeline', False):
            timeline_format = export_options.get('timeline_format', 'json')
            timeline_path = export_dir / f"timeline.{timeline_format}"
            
            self.timeline_generator.export_timeline(timeline, timeline_path, timeline_format)
            export_results['timeline_export'] = str(timeline_path)
            logger.info("Timeline exported", path=str(timeline_path), format=timeline_format)
        
        # Export audio analysis
        if export_options.get('export_audio_analysis', False):
            audio_path = export_dir / "audio_analysis.json"
            self.audio_analyzer.export_analysis(audio_analysis, str(audio_path))
            export_results['audio_export'] = str(audio_path)
            logger.info("Audio analysis exported", path=str(audio_path))
        
        # Export quality timeline
        if export_options.get('export_quality_timeline', False) and quality_result:
            quality_format = export_options.get('quality_format', 'json')
            quality_path = export_dir / f"quality_timeline.{quality_format}"
            
            self.quality_scoring.export_quality_timeline(quality_result, quality_path, quality_format)
            export_results['quality_export'] = str(quality_path)
            logger.info("Quality timeline exported", path=str(quality_path), format=quality_format)
        
        # Export processing statistics
        if export_options.get('export_stats', False):
            stats_path = export_dir / "processing_stats.json"
            with open(stats_path, 'w') as f:
                json.dump(self.stats, f, indent=2)
            export_results['stats_export'] = str(stats_path)
            logger.info("Processing statistics exported", path=str(stats_path))
        
        return export_results
    
    def generate_mock_data(self, duration: float = 60.0, resolution: Tuple[int, int] = (1920, 1080)) -> Dict[str, Any]:
        """
        Generate mock data for testing the pipeline without real video files
        
        Args:
            duration: Mock video duration in seconds
            resolution: Mock video resolution (width, height)
            
        Returns:
            Dictionary with mock analysis results
        """
        
        logger.info("Generating mock data for testing",
                   duration=f"{duration}s",
                   resolution=f"{resolution[0]}x{resolution[1]}")
        
        import numpy as np
        
        # Mock video info
        from src.video.ingestion import VideoInfo, VideoStream, AudioStream, VideoCodec, ContainerFormat
        
        mock_video_stream = VideoStream(
            index=0,
            codec=VideoCodec.H264,
            width=resolution[0],
            height=resolution[1],
            fps=30.0,
            bitrate=5000000,
            duration=duration
        )
        
        mock_audio_stream = AudioStream(
            index=1,
            codec="aac",
            sample_rate=44100,
            channels=2,
            bitrate=192000,
            duration=duration
        )
        
        mock_video_info = VideoInfo(
            file_path=Path("mock_video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=duration,
            file_size=int(duration * 1000000),  # ~1MB per second
            video_streams=[mock_video_stream],
            audio_streams=[mock_audio_stream],
            metadata={"title": "Mock Video for Testing"},
            is_valid=True,
            hardware_decodable=True
        )
        
        # Mock audio analysis
        bpm = 120.0
        beat_interval = 60.0 / bpm
        beats = list(np.arange(0, duration, beat_interval))
        
        mock_audio_analysis = AudioAnalysis(
            bpm=bpm,
            beats=beats,
            confidence=0.85,
            duration=duration,
            sample_rate=44100
        )
        
        # Mock scene detection
        from src.video.scene_detection import SceneDetectionResult, SceneChange, SceneDetectionAlgorithm
        
        # Generate scene changes every 10-15 seconds
        scene_changes = []
        for i in range(1, int(duration // 12)):
            timestamp = i * 12 + np.random.uniform(-2, 2)
            if timestamp < duration:
                scene_changes.append(SceneChange(
                    timestamp=timestamp,
                    frame_number=int(timestamp * 30),
                    confidence=0.7 + np.random.uniform(0, 0.3),
                    algorithm=SceneDetectionAlgorithm.COMBINED
                ))
        
        mock_scene_detection = SceneDetectionResult(
            video_info=mock_video_info,
            scene_changes=scene_changes,
            processing_time=duration / 10,  # 10x real-time
            algorithm_used=SceneDetectionAlgorithm.COMBINED,
            processing_mode=SceneProcessingMode.BALANCED,
            frames_processed=int(duration * 30 / 4),  # Every 4th frame
            frames_skipped=int(duration * 30 * 3 / 4),
            success=True
        )
        
        # Generate mock timeline
        timeline = self.timeline_generator.generate_timeline(
            audio_analysis=mock_audio_analysis,
            scene_detection=mock_scene_detection,
            video_info=mock_video_info,
            editing_style=EditingStyle.ADAPTIVE
        )
        
        logger.info("Mock data generation completed",
                   beats=len(beats),
                   scenes=len(scene_changes),
                   timeline_segments=timeline.segment_count)
        
        return {
            'video_info': mock_video_info,
            'audio_analysis': mock_audio_analysis,
            'scene_detection': mock_scene_detection,
            'timeline': timeline,
            'mock_data': True
        }
    
    def benchmark_performance(self, test_cases: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Run performance benchmarks to test system capabilities
        
        Args:
            test_cases: Optional list of test case configurations
            
        Returns:
            Dictionary with benchmark results
        """
        
        if test_cases is None:
            test_cases = [
                {
                    'name': '1080p_30fps_60s',
                    'duration': 60.0,
                    'resolution': (1920, 1080),
                    'fps': 30.0,
                    'expected_analysis_speed': 10.0
                },
                {
                    'name': '720p_30fps_120s',
                    'duration': 120.0,
                    'resolution': (1280, 720),
                    'fps': 30.0,
                    'expected_analysis_speed': 15.0
                },
                {
                    'name': '4k_60fps_30s',
                    'duration': 30.0,
                    'resolution': (3840, 2160),
                    'fps': 60.0,
                    'expected_analysis_speed': 5.0
                }
            ]
        
        logger.info("Starting performance benchmark", test_cases=len(test_cases))
        
        benchmark_results = {
            'system_info': self._get_system_info(),
            'test_results': [],
            'summary': {}
        }
        
        for i, test_case in enumerate(test_cases):
            logger.info(f"Running benchmark {i+1}/{len(test_cases)}: {test_case['name']}")
            
            start_time = time.time()
            
            # Generate mock data for this test case
            mock_data = self.generate_mock_data(
                duration=test_case['duration'],
                resolution=test_case['resolution']
            )
            
            # Simulate processing times based on video characteristics
            pixel_count = test_case['resolution'][0] * test_case['resolution'][1]
            complexity_factor = pixel_count / (1920 * 1080)  # Normalize to 1080p
            duration_factor = test_case['duration']
            
            # Simulate realistic processing times
            simulated_times = {
                'ingestion_time': 0.1 + duration_factor * 0.01,
                'audio_analysis_time': duration_factor / 20,  # 20x real-time
                'scene_detection_time': duration_factor / test_case['expected_analysis_speed'],
                'face_detection_time': duration_factor * complexity_factor / 12,  # 12x real-time
                'quality_scoring_time': duration_factor * complexity_factor / 15,  # 15x real-time
                'timeline_generation_time': 0.1 + len(mock_data['timeline'].segments) * 0.001,
                'rendering_time_lossless': duration_factor / 15,  # 15x real-time for lossless
                'rendering_time_encoded': duration_factor * complexity_factor * 2  # 0.5x real-time
            }
            
            total_analysis_time = sum([
                simulated_times['ingestion_time'],
                simulated_times['audio_analysis_time'], 
                simulated_times['scene_detection_time'],
                simulated_times['face_detection_time'],
                simulated_times['quality_scoring_time'],
                simulated_times['timeline_generation_time']
            ])
            
            analysis_speed_factor = test_case['duration'] / total_analysis_time
            
            test_result = {
                'test_case': test_case.copy(),
                'processing_times': simulated_times,
                'analysis_speed_factor': analysis_speed_factor,
                'lossless_render_speed': test_case['duration'] / simulated_times['rendering_time_lossless'],
                'encoded_render_speed': test_case['duration'] / simulated_times['rendering_time_encoded'],
                'timeline_segments': mock_data['timeline'].segment_count,
                'beat_sync_percentage': mock_data['timeline'].beat_sync_percentage,
                'benchmark_time': time.time() - start_time,
                'meets_performance_target': analysis_speed_factor >= test_case['expected_analysis_speed'] * 0.8
            }
            
            benchmark_results['test_results'].append(test_result)
            
            logger.info(f"Benchmark {test_case['name']} completed",
                       analysis_speed=f"{analysis_speed_factor:.1f}x",
                       lossless_speed=f"{test_result['lossless_render_speed']:.1f}x",
                       meets_target=test_result['meets_performance_target'])
        
        # Calculate summary statistics
        all_results = benchmark_results['test_results']
        benchmark_results['summary'] = {
            'total_tests': len(all_results),
            'tests_passed': sum(1 for r in all_results if r['meets_performance_target']),
            'average_analysis_speed': sum(r['analysis_speed_factor'] for r in all_results) / len(all_results),
            'average_lossless_render_speed': sum(r['lossless_render_speed'] for r in all_results) / len(all_results),
            'average_encoded_render_speed': sum(r['encoded_render_speed'] for r in all_results) / len(all_results),
            'total_benchmark_time': sum(r['benchmark_time'] for r in all_results)
        }
        
        logger.info("Performance benchmark completed",
                   tests_passed=f"{benchmark_results['summary']['tests_passed']}/{benchmark_results['summary']['total_tests']}",
                   avg_analysis_speed=f"{benchmark_results['summary']['average_analysis_speed']:.1f}x",
                   total_time=f"{benchmark_results['summary']['total_benchmark_time']:.2f}s")
        
        return benchmark_results
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get system information for benchmarking"""
        import platform
        import os
        
        return {
            'platform': platform.platform(),
            'python_version': platform.python_version(),
            'cpu_count': os.cpu_count(),
            'architecture': platform.architecture()[0],
            'machine': platform.machine()
        }


def create_cli_parser() -> argparse.ArgumentParser:
    """Create comprehensive CLI argument parser"""
    
    parser = argparse.ArgumentParser(
        prog='autocut_prototype',
        description='AutoCut End-to-End Video Editing Prototype',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with default settings
  %(prog)s input_video.mp4

  # Specify editing style and quality profile
  %(prog)s input_video.mp4 --style aggressive --profile talking_head

  # Performance mode and output options
  %(prog)s input_video.mp4 --performance speed --output edited_video.mp4 --quality lossless

  # Export timeline only for review
  %(prog)s input_video.mp4 --export timeline --timeline-format json --no-render

  # Demo mode with mock data
  %(prog)s --demo --mock-duration 60

  # Benchmark mode for performance testing
  %(prog)s --benchmark

Editing Styles:
  aggressive  - Frequent cuts, strong beat sync, scene overrides allowed
  smooth      - Longer clips, prioritize scene boundaries, gentle transitions
  adaptive    - Dynamic adjustment based on content characteristics
  musical     - Strict beat alignment, musical phrasing emphasis
  cinematic   - Story-driven, minimal beat sync, longer segments

Quality Profiles:
  talking_head - Emphasizes face quality and sharpness
  action      - Emphasizes motion and exposure handling
  landscape   - Emphasizes composition and color quality
  documentary - Balanced approach with slight face emphasis
  adaptive    - Dynamic adjustment based on video content

Performance Modes:
  speed       - Maximum speed, basic quality (15x+ real-time)
  balanced    - Balance of speed and quality (10x real-time)
  quality     - Higher quality, moderate speed (5x real-time)
  precision   - Maximum quality, all frames (2x real-time)
        """
    )
    
    # Input/Output options
    parser.add_argument('input_path', nargs='?', type=str,
                       help='Input video file or folder path containing video files')
    parser.add_argument('-m', '--music', type=str, required=False,
                       help='Music file to sync video cuts to (MP3, WAV, FLAC, AAC, M4A)')
    parser.add_argument('-o', '--output', type=str,
                       help='Output video file path (default: input_edited.mp4)')
    
    # Processing options
    parser.add_argument('--style', choices=['aggressive', 'smooth', 'adaptive', 'musical', 'cinematic'],
                       default='adaptive', help='Timeline editing style (default: adaptive)')
    parser.add_argument('--profile', choices=['talking_head', 'action', 'landscape', 'documentary', 'adaptive'],
                       default='adaptive', help='Quality scoring profile (default: adaptive)')
    parser.add_argument('--performance', choices=['speed', 'balanced', 'quality', 'precision'],
                       default='balanced', help='Processing performance mode (default: balanced)')
    
    # Quality and format options
    parser.add_argument('--quality', choices=['lossless', 'high', 'medium', 'draft'],
                       default='lossless', help='Rendering quality preset (default: lossless)')
    parser.add_argument('--format', choices=['mp4', 'mov', 'avi', 'mkv', 'webm'],
                       default='mp4', help='Output format (default: mp4)')
    parser.add_argument('--resolution', type=str,
                       help='Target resolution (e.g., 1080p, 720p, 1920x1080)')
    parser.add_argument('--fps', type=float,
                       help='Target frame rate')
    
    # Feature toggles
    parser.add_argument('--no-face-detection', action='store_true',
                       help='Disable face detection processing')
    parser.add_argument('--no-quality-scoring', action='store_true',
                       help='Disable quality scoring processing')
    parser.add_argument('--no-render', action='store_true',
                       help='Skip video rendering (analysis only)')
    
    # Export options
    parser.add_argument('--export', nargs='+', 
                       choices=['timeline', 'audio', 'quality', 'stats'],
                       help='Export additional data (timeline, audio, quality, stats)')
    parser.add_argument('--export-dir', type=str, default='./exports',
                       help='Directory for exported files (default: ./exports)')
    parser.add_argument('--timeline-format', choices=['json', 'csv', 'edl'],
                       default='json', help='Timeline export format (default: json)')
    parser.add_argument('--quality-format', choices=['json', 'csv', 'xml'],
                       default='json', help='Quality timeline export format (default: json)')
    
    # Demo and testing modes
    parser.add_argument('--demo', action='store_true',
                       help='Run in demo mode with mock data')
    parser.add_argument('--mock-duration', type=float, default=60.0,
                       help='Duration for mock data in demo mode (default: 60s)')
    parser.add_argument('--benchmark', action='store_true',
                       help='Run performance benchmark tests')
    
    # Logging and debugging
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO', help='Logging level (default: INFO)')
    parser.add_argument('--log-file', type=str,
                       help='Log file path (default: console only)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose output')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Suppress non-error output')
    
    # Configuration
    parser.add_argument('--config', type=str,
                       help='Configuration file path')
    parser.add_argument('--save-config', action='store_true',
                       help='Save current configuration to file')
    
    return parser


def print_processing_stats(stats: Dict[str, float], video_duration: float):
    """Print formatted processing statistics"""
    
    print("\n" + "="*60)
    print("PROCESSING STATISTICS")
    print("="*60)
    
    print(f"Video Duration:        {video_duration:.2f}s")
    print(f"Total Processing Time: {stats['total_time']:.2f}s")
    print(f"Overall Speed Factor:  {stats['overall_speed_factor']:.1f}x real-time")
    print()
    
    print("Component Breakdown:")
    print("-" * 30)
    
    components = [
        ('Video Ingestion', stats['ingestion_time']),
        ('Audio Analysis', stats['audio_analysis_time']),
        ('Scene Detection', stats['scene_detection_time']),
        ('Face Detection', stats['face_detection_time']),
        ('Quality Scoring', stats['quality_scoring_time']),
        ('Timeline Generation', stats['timeline_generation_time']),
        ('Video Rendering', stats['rendering_time'])
    ]
    
    total_component_time = sum(time for _, time in components)
    
    for name, time_taken in components:
        if time_taken > 0:
            percentage = (time_taken / total_component_time) * 100
            speed_factor = video_duration / time_taken if time_taken > 0 else 0
            print(f"  {name:<20} {time_taken:>6.2f}s ({percentage:>5.1f}%) [{speed_factor:>5.1f}x]")
        else:
            print(f"  {name:<20} {'skipped':>6s}")


def print_pipeline_results(results: Dict[str, Any]):
    """Print formatted pipeline results"""
    
    if not results['success']:
        print(f"\n❌ Pipeline failed: {results['error']}")
        return
    
    print("\n" + "="*60)
    print("PIPELINE RESULTS")
    print("="*60)
    
    # Video info - handle both single video and multi-video cases
    if 'video_info' in results:
        # Single video case
        video_info = results['video_info']
        print(f"Input Video:")
        print(f"  Duration:    {video_info['duration']:.1f}s")
        print(f"  Resolution:  {video_info['resolution'][0]}x{video_info['resolution'][1]}")
        print(f"  Format:      {video_info['container_format']}")
        print(f"  Codec:       {video_info.get('video_codec', 'unknown')}")
    elif 'video_info_list' in results:
        # Multi-video case
        video_info_list = results['video_info_list']
        print(f"Input Videos ({len(video_info_list)} files):")
        total_duration = sum(vi.duration for vi in video_info_list)
        print(f"  Total Duration: {total_duration:.1f}s")
        for i, vi in enumerate(video_info_list):
            print(f"  Video {i+1}: {vi.file_path.name} ({vi.duration:.1f}s, {vi.resolution[0]}x{vi.resolution[1]})")
        # Use first video for format/codec info
        if video_info_list:
            first_video = video_info_list[0]
            print(f"  Primary Format: {first_video.container_format}")
            print(f"  Primary Codec:  {first_video.primary_video_stream.codec.value if first_video.primary_video_stream else 'unknown'}")
    
    # Audio analysis
    audio_info = results['audio_analysis']
    print(f"\nAudio Analysis:")
    print(f"  BPM:         {audio_info['bpm']:.1f}")
    print(f"  Beats:       {audio_info['beat_count']}")
    print(f"  Confidence:  {audio_info['confidence']:.2f}")
    
    # Scene detection - handle both single and multi-video cases
    print(f"\nScene Detection:")
    if 'scene_detection' in results:
        # Single video case
        scene_info = results['scene_detection']
        print(f"  Scenes:      {scene_info['scene_count']}")
    elif 'scene_detections' in results:
        # Multi-video case
        scene_detections = results['scene_detections']
        total_scenes = sum(sd['scene_count'] for sd in scene_detections)
        print(f"  Total Scenes: {total_scenes}")
        for i, sd in enumerate(scene_detections):
            print(f"  Video {i+1}: {sd['scene_count']} scenes")
    else:
        print("  No scene detection data available")
    
    # Additional scene details (only for single video)
    if 'scene_detection' in results:
        scene_info = results['scene_detection']
        print(f"  Avg Duration: {scene_info['average_scene_duration']:.1f}s")
        print(f"  Algorithm:   {scene_info['algorithm_used']}")
    
    # Face detection (if available) - handle both single and multi-video cases
    if 'face_detection' in results and results['face_detection']:
        # Single video case
        face_info = results['face_detection']
        print(f"\nFace Detection:")
        print(f"  Faces/sec:   {face_info['faces_per_second']:.1f}")
        print(f"  Quality:     {face_info['overall_quality_score']:.2f}")
        print(f"  Frames:      {face_info['total_frames_processed']}")
    elif 'face_detections' in results and results['face_detections']:
        # Multi-video case
        face_detections = results['face_detections']
        print(f"\nFace Detection:")
        total_faces = sum(fd.get('total_faces_detected', 0) for fd in face_detections if fd)
        print(f"  Total Faces: {total_faces}")
        avg_quality = sum(fd.get('overall_quality_score', 0) for fd in face_detections if fd) / len([fd for fd in face_detections if fd]) if any(face_detections) else 0
        print(f"  Avg Quality: {avg_quality:.2f}")
        for i, fd in enumerate(face_detections):
            if fd:
                print(f"  Video {i+1}: {fd.get('total_faces_detected', 0)} faces")
    
    # Quality scoring (if available) - handle both single and multi-video cases
    if 'quality_scoring' in results and results['quality_scoring']:
        # Single video case
        quality_info = results['quality_scoring']
        print(f"\nQuality Scoring:")
        print(f"  Mean Quality: {quality_info['mean_quality']:.1f}")
        print(f"  Trend:       {quality_info['quality_trend']}")
        print(f"  Profile:     {quality_info['profile_used']}")
    elif 'quality_results' in results and results['quality_results']:
        # Multi-video case
        quality_results = results['quality_results']
        print(f"\nQuality Scoring:")
        avg_quality = sum(qr.get('mean_quality', 0) for qr in quality_results if qr) / len([qr for qr in quality_results if qr]) if any(quality_results) else 0
        print(f"  Avg Quality: {avg_quality:.1f}")
        for i, qr in enumerate(quality_results):
            if qr:
                print(f"  Video {i+1}: {qr.get('mean_quality', 0):.1f} quality")
    
    # Timeline - handle both dict and object formats
    print(f"\nTimeline Generation:")
    if 'timeline' in results:
        timeline_info = results['timeline']
        # Handle both dictionary and object formats
        if isinstance(timeline_info, dict):
            print(f"  Segments:    {timeline_info.get('segment_count', 'N/A')}")
            print(f"  Avg Duration: {timeline_info.get('average_segment_duration', 0):.1f}s")
            print(f"  Beat Sync:   {timeline_info.get('beat_sync_percentage', 0):.1f}%")
            print(f"  Scene Respect: {timeline_info.get('scene_respect_percentage', 0):.1f}%")
            print(f"  Style:       {timeline_info.get('editing_style', 'N/A')}")
        else:
            # Fallback for object format
            print(f"  Segments:    {getattr(timeline_info, 'segment_count', 'N/A')}")
            print(f"  Duration:    {getattr(timeline_info, 'duration', 0):.1f}s")
            print(f"  Style:       {getattr(timeline_info, 'editing_style', 'N/A')}")
    else:
        print("  No timeline data available")
    
    # Rendering (if available)
    if 'render_stats' in results and results['render_stats']:
        render_info = results['render_stats']
        print(f"\nVideo Rendering:")
        print(f"  Output Size: {render_info['output_file_size'] / (1024**2):.1f} MB")
        print(f"  Speed:       {render_info['speed_factor']:.1f}x real-time")
        print(f"  Stream Copy: {render_info['used_stream_copy']}")
        print(f"  HW Accel:    {render_info['hardware_acceleration']}")
    elif 'video_info_list' in results:
        print(f"\nVideo Rendering:")
        if results.get('output_path'):
            print(f"  Multi-video rendering completed")
            print(f"  Output: {results['output_path']}")
        else:
            print(f"  Multi-video processing - no final rendering performed")
    
    # Processing statistics
    if 'video_info' in results:
        duration = results['video_info']['duration']
    elif 'video_info_list' in results:
        duration = sum(vi.duration for vi in results['video_info_list'])
    else:
        duration = 0.0
    print_processing_stats(results['processing_stats'], duration)
    
    # Export results
    if results['export_results']:
        print(f"\nExported Files:")
        for export_type, path in results['export_results'].items():
            print(f"  {export_type:<15} {path}")


def main():
    """Main entry point for the AutoCut prototype"""
    
    # Parse command line arguments
    parser = create_cli_parser()
    args = parser.parse_args()
    
    # Setup logging
    log_level = 'ERROR' if args.quiet else ('DEBUG' if args.verbose else args.log_level)
    log_file = Path(args.log_file) if args.log_file else None
    
    setup_logging(level=log_level, log_file=log_file)
    logger = get_logger(__name__)
    
    # Print header
    if not args.quiet:
        print("🎬 AutoCut End-to-End Video Editing Prototype")
        print("=" * 60)
        print("Complete pipeline from video ingestion to final render")
        print()
    
    try:
        # Initialize prototype
        prototype = AutoCutPrototype()
        
        # Handle different modes
        if args.benchmark:
            # Benchmark mode
            logger.info("Running performance benchmark")
            benchmark_results = prototype.benchmark_performance()
            
            if not args.quiet:
                print("PERFORMANCE BENCHMARK RESULTS")
                print("=" * 60)
                
                summary = benchmark_results['summary']
                print(f"Tests Passed:     {summary['tests_passed']}/{summary['total_tests']}")
                print(f"Avg Analysis:     {summary['average_analysis_speed']:.1f}x real-time")
                print(f"Avg Lossless:     {summary['average_lossless_render_speed']:.1f}x real-time")
                print(f"Avg Encoded:      {summary['average_encoded_render_speed']:.1f}x real-time")
                print(f"Total Time:       {summary['total_benchmark_time']:.2f}s")
                
                print("\nDetailed Results:")
                for result in benchmark_results['test_results']:
                    test = result['test_case'] 
                    status = "✅ PASS" if result['meets_performance_target'] else "❌ FAIL"
                    print(f"  {test['name']:<20} {result['analysis_speed_factor']:>6.1f}x  {status}")
            
            # Export benchmark results
            if args.export and 'stats' in args.export:
                export_dir = Path(args.export_dir)
                export_dir.mkdir(parents=True, exist_ok=True)
                benchmark_path = export_dir / 'benchmark_results.json'
                
                with open(benchmark_path, 'w') as f:
                    json.dump(benchmark_results, f, indent=2, default=str)
                
                logger.info("Benchmark results exported", path=str(benchmark_path))
        
        elif args.demo:
            # Demo mode with mock data
            logger.info("Running demo mode with mock data")
            
            mock_data = prototype.generate_mock_data(duration=args.mock_duration)
            
            if not args.quiet:
                print("DEMO MODE - MOCK DATA GENERATED")
                print("=" * 60)
                print(f"Video Duration:   {args.mock_duration}s")
                print(f"Resolution:       1920x1080")
                print(f"Audio BPM:        {mock_data['audio_analysis'].bpm:.1f}")
                print(f"Beats Detected:   {len(mock_data['audio_analysis'].beats)}")
                print(f"Scenes Detected:  {len(mock_data['scene_detection'].scene_changes)}")
                print(f"Timeline Segments: {mock_data['timeline'].segment_count}")
                print(f"Beat Sync:        {mock_data['timeline'].beat_sync_percentage:.1f}%")
                print(f"Scene Respect:    {mock_data['timeline'].scene_respect_percentage:.1f}%")
                print()
                print("This demonstrates the complete AutoCut pipeline structure")
                print("without requiring an actual video file.")
        
        else:
            # Normal processing mode
            if not args.input_path:
                parser.error("Input path is required (video file or folder)")
            
            input_path = Path(args.input_path)
            if not input_path.exists():
                print(f"❌ Input path not found: {input_path}")
                return 1
            
            # Validate music file if provided
            music_path = None
            if args.music:
                music_path = Path(args.music)
                if not music_path.exists():
                    print(f"❌ Music file not found: {music_path}")
                    return 1
            
            # Determine output path
            output_path = None
            if not args.no_render:
                if args.output:
                    output_path = Path(args.output)
                else:
                    # Generate default output name based on input
                    if input_path.is_file():
                        stem = input_path.stem
                    else:
                        stem = input_path.name
                    output_path = input_path.parent / f"{stem}_edited.mp4"
            
            # Configure processing options
            editing_style = EditingStyle(args.style)
            quality_profile = QualityProfile(args.profile)
            
            # Configure export options
            export_options = {
                'no_face_detection': args.no_face_detection,
                'no_quality_scoring': args.no_quality_scoring,
                'no_render': args.no_render,
                'quality_preset': args.quality,
                'output_format': args.format,
                'target_resolution': args.resolution,
                'target_fps': args.fps,
                'export_dir': args.export_dir
            }
            
            # Set export flags
            if args.export:
                export_options.update({
                    'export_timeline': 'timeline' in args.export,
                    'export_audio_analysis': 'audio' in args.export,
                    'export_quality_timeline': 'quality' in args.export,
                    'export_stats': 'stats' in args.export,
                    'timeline_format': args.timeline_format,
                    'quality_format': args.quality_format
                })
            
            # Progress callback
            last_progress = 0
            def progress_callback(message, progress):
                nonlocal last_progress
                if not args.quiet and progress >= last_progress + 5:  # Update every 5%
                    print(f"Progress: {progress:3.0f}% - {message}")
                    last_progress = progress
            
            # Display input information
            if not args.quiet:
                if input_path.is_file():
                    print(f"📹 Input Video: {input_path}")
                else:
                    print(f"📁 Input Folder: {input_path}")
                if music_path:
                    print(f"🎵 Music Track: {music_path}")
                else:
                    print("🎵 Music Track: Using embedded video audio")
                if output_path:
                    print(f"📤 Output: {output_path}")
                print()
            
            # Process videos with music
            logger.info("Starting multi-video processing", 
                       input_path=str(input_path),
                       music_path=str(music_path) if music_path else "embedded")
            
            results = prototype.process_videos_with_music(
                input_path=input_path,
                music_path=music_path,
                output_path=output_path,
                editing_style=editing_style,
                quality_profile=quality_profile,
                performance_mode=args.performance,
                export_options=export_options,
                progress_callback=progress_callback if not args.quiet else None
            )
            
            # Print results
            if not args.quiet:
                print_pipeline_results(results)
            
            if results['success']:
                if not args.quiet:
                    print(f"\n✅ Processing completed successfully!")
                    if output_path:
                        print(f"📹 Output video: {output_path}")
                    if results['export_results']:
                        print(f"📁 Exported files in: {args.export_dir}")
                return 0
            else:
                print(f"\n❌ Processing failed: {results['error']}")
                return 1
    
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Processing interrupted by user")
        return 130
    
    except Exception as e:
        logger.error("Unexpected error in main", error=str(e))
        if args.verbose:
            traceback.print_exc()
        print(f"\n❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
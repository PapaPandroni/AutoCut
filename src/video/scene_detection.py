"""Scene detection module for AutoCut with multiple algorithms and hardware acceleration"""
import cv2
import numpy as np
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..utils.logging import get_logger
from ..utils.config import config
from .ingestion import VideoInfo, VideoIngestion

logger = get_logger(__name__)


class SceneDetectionAlgorithm(Enum):
    """Available scene detection algorithms"""
    HISTOGRAM = "histogram"
    EDGE_DETECTION = "edge_detection"
    OPTICAL_FLOW = "optical_flow"
    COMBINED = "combined"


class ProcessingMode(Enum):
    """Processing modes for speed vs quality trade-offs"""
    SPEED = "speed"          # 15x+ real-time, skip many frames
    BALANCED = "balanced"    # 10x real-time, moderate frame skipping
    QUALITY = "quality"      # 5x real-time, minimal frame skipping
    PRECISION = "precision"  # 2x real-time, all frames


@dataclass
class SceneChange:
    """Individual scene change detection result"""
    timestamp: float
    frame_number: int
    confidence: float
    algorithm: SceneDetectionAlgorithm
    metrics: Dict[str, float] = field(default_factory=dict)
    
    def __post_init__(self):
        # Ensure confidence is within valid range
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class SceneDetectionResult:
    """Complete scene detection results for a video"""
    video_info: VideoInfo
    scene_changes: List[SceneChange]
    processing_time: float
    algorithm_used: SceneDetectionAlgorithm
    processing_mode: ProcessingMode
    frames_processed: int
    frames_skipped: int
    success: bool = True
    errors: List[str] = field(default_factory=list)
    
    @property
    def scene_count(self) -> int:
        """Number of detected scenes (including first scene)"""
        return len(self.scene_changes) + 1
    
    @property
    def average_scene_duration(self) -> float:
        """Average duration of scenes in seconds"""
        if not self.scene_changes:
            return self.video_info.duration
        
        durations = []
        prev_time = 0.0
        
        for change in self.scene_changes:
            durations.append(change.timestamp - prev_time)
            prev_time = change.timestamp
        
        # Add final scene duration
        durations.append(self.video_info.duration - prev_time)
        
        return sum(durations) / len(durations) if durations else 0.0
    
    @property
    def processing_speed_multiplier(self) -> float:
        """How many times faster than real-time the processing was"""
        if self.processing_time <= 0:
            return 0.0
        return self.video_info.duration / self.processing_time
    
    def get_scene_segments(self) -> List[Tuple[float, float]]:
        """Get list of (start_time, end_time) tuples for each scene"""
        if not self.scene_changes:
            return [(0.0, self.video_info.duration)]
        
        segments = []
        prev_time = 0.0
        
        for change in self.scene_changes:
            segments.append((prev_time, change.timestamp))
            prev_time = change.timestamp
        
        # Add final scene
        segments.append((prev_time, self.video_info.duration))
        
        return segments
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'video_path': str(self.video_info.file_path),
            'scene_count': self.scene_count,
            'scene_changes': [
                {
                    'timestamp': sc.timestamp,
                    'frame_number': sc.frame_number,
                    'confidence': sc.confidence,
                    'algorithm': sc.algorithm.value,
                    'metrics': sc.metrics
                }
                for sc in self.scene_changes
            ],
            'processing_time': self.processing_time,
            'algorithm_used': self.algorithm_used.value,
            'processing_mode': self.processing_mode.value,
            'frames_processed': self.frames_processed,
            'frames_skipped': self.frames_skipped,
            'processing_speed_multiplier': self.processing_speed_multiplier,
            'average_scene_duration': self.average_scene_duration,
            'success': self.success,
            'errors': self.errors
        }


class SceneDetection:
    """Scene detection engine with multiple algorithms and hardware acceleration"""
    
    def __init__(self, processing_mode: ProcessingMode = ProcessingMode.BALANCED):
        """
        Initialize scene detection engine
        
        Args:
            processing_mode: Speed vs quality trade-off mode
        """
        self.processing_mode = processing_mode
        self.video_ingestion = VideoIngestion()
        
        # Load configuration
        self.min_scene_duration = config.get('scene_detection.min_scene_duration_sec', 1.0)
        self.confidence_threshold = config.get('scene_detection.confidence_threshold', 0.3)
        self.enable_hardware_acceleration = config.get('video.enable_hardware_acceleration', True)
        self.max_workers = config.get('processing.max_workers', 4)
        
        # Processing mode configurations
        self.mode_configs = {
            ProcessingMode.SPEED: {
                'frame_skip': 8,      # Process every 8th frame
                'resize_factor': 0.25,  # Quarter resolution
                'algorithms': [SceneDetectionAlgorithm.HISTOGRAM],
                'histogram_bins': 16
            },
            ProcessingMode.BALANCED: {
                'frame_skip': 4,      # Process every 4th frame
                'resize_factor': 0.5,   # Half resolution
                'algorithms': [SceneDetectionAlgorithm.HISTOGRAM, SceneDetectionAlgorithm.EDGE_DETECTION],
                'histogram_bins': 32
            },
            ProcessingMode.QUALITY: {
                'frame_skip': 2,      # Process every 2nd frame
                'resize_factor': 0.75,  # 3/4 resolution
                'algorithms': [SceneDetectionAlgorithm.HISTOGRAM, SceneDetectionAlgorithm.EDGE_DETECTION, SceneDetectionAlgorithm.OPTICAL_FLOW],
                'histogram_bins': 64
            },
            ProcessingMode.PRECISION: {
                'frame_skip': 1,      # Process all frames
                'resize_factor': 1.0,   # Full resolution
                'algorithms': [SceneDetectionAlgorithm.COMBINED],
                'histogram_bins': 128
            }
        }
        
        # Algorithm-specific thresholds
        self.algorithm_thresholds = {
            SceneDetectionAlgorithm.HISTOGRAM: config.get('scene_detection.histogram_threshold', 0.3),
            SceneDetectionAlgorithm.EDGE_DETECTION: config.get('scene_detection.edge_threshold', 0.4),
            SceneDetectionAlgorithm.OPTICAL_FLOW: config.get('scene_detection.optical_flow_threshold', 0.5),
            SceneDetectionAlgorithm.COMBINED: config.get('scene_detection.combined_threshold', 0.35)
        }
        
        # Frame buffers for optical flow
        self.prev_frame = None
        self.optical_flow_initialized = False
        
        logger.info("SceneDetection initialized", 
                   processing_mode=processing_mode.value,
                   min_scene_duration=self.min_scene_duration,
                   confidence_threshold=self.confidence_threshold,
                   hardware_acceleration=self.enable_hardware_acceleration)
    
    def detect_scenes(self, 
                     video_path: Union[str, Path], 
                     algorithm: SceneDetectionAlgorithm = SceneDetectionAlgorithm.HISTOGRAM,
                     video_info: Optional[VideoInfo] = None) -> SceneDetectionResult:
        """
        Detect scene changes in video
        
        Args:
            video_path: Path to video file
            algorithm: Scene detection algorithm to use
            video_info: Pre-loaded video info (optional, will load if not provided)
            
        Returns:
            SceneDetectionResult with detected scene changes
        """
        video_path = Path(video_path)
        start_time = time.time()
        
        logger.info("Starting scene detection", 
                   video_path=str(video_path),
                   algorithm=algorithm.value,
                   processing_mode=self.processing_mode.value)
        
        try:
            # Load video info if not provided
            if video_info is None:
                video_info = self.video_ingestion.load_video(video_path)
            
            if not video_info.is_valid:
                return SceneDetectionResult(
                    video_info=video_info,
                    scene_changes=[],
                    processing_time=time.time() - start_time,
                    algorithm_used=algorithm,
                    processing_mode=self.processing_mode,
                    frames_processed=0,
                    frames_skipped=0,
                    success=False,
                    errors=["Invalid video file"] + video_info.validation_errors
                )
            
            # Select appropriate algorithms for processing mode
            if algorithm == SceneDetectionAlgorithm.COMBINED:
                algorithms = self.mode_configs[self.processing_mode]['algorithms']
            else:
                algorithms = [algorithm]
            
            # Detect scenes using selected algorithms
            scene_changes = self._detect_with_algorithms(video_info, algorithms)
            
            # Post-process results
            scene_changes = self._post_process_scene_changes(scene_changes, video_info)
            
            processing_time = time.time() - start_time
            
            result = SceneDetectionResult(
                video_info=video_info,
                scene_changes=scene_changes,
                processing_time=processing_time,
                algorithm_used=algorithm,
                processing_mode=self.processing_mode,
                frames_processed=self._frames_processed,
                frames_skipped=self._frames_skipped,
                success=True
            )
            
            logger.info("Scene detection completed",
                       video_path=str(video_path),
                       scene_count=result.scene_count,
                       processing_time=f"{processing_time:.2f}s",
                       processing_speed=f"{result.processing_speed_multiplier:.1f}x",
                       frames_processed=result.frames_processed)
            
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Scene detection failed: {str(e)}"
            logger.error("Scene detection failed", 
                        video_path=str(video_path),
                        error=str(e),
                        processing_time=processing_time)
            
            return SceneDetectionResult(
                video_info=video_info or VideoInfo(
                    file_path=video_path,
                    container_format=None,
                    duration=0,
                    file_size=0,
                    video_streams=[],
                    audio_streams=[],
                    metadata={},
                    is_valid=False
                ),
                scene_changes=[],
                processing_time=processing_time,
                algorithm_used=algorithm,
                processing_mode=self.processing_mode,
                frames_processed=0,
                frames_skipped=0,
                success=False,
                errors=[error_msg]
            )
    
    def _detect_with_algorithms(self, video_info: VideoInfo, algorithms: List[SceneDetectionAlgorithm]) -> List[SceneChange]:
        """Detect scenes using multiple algorithms"""
        config = self.mode_configs[self.processing_mode]
        
        # Open video capture
        cap = cv2.VideoCapture(str(video_info.file_path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file: {video_info.file_path}")
        
        # Configure video capture for hardware acceleration if available
        if self.enable_hardware_acceleration and video_info.hardware_decodable:
            # Try to enable hardware acceleration for M1/M2 Macs
            try:
                # Set VideoToolbox backend for macOS hardware acceleration
                cap.set(cv2.CAP_PROP_BACKEND, cv2.CAP_AVFOUNDATION)
                
                # Configure hardware decoder based on codec
                if video_info.primary_video_stream:
                    codec = video_info.primary_video_stream.codec
                    if hasattr(cv2, 'CAP_PROP_CODEC_PIXEL_FORMAT'):
                        # Set pixel format for hardware decoding
                        cap.set(cv2.CAP_PROP_CODEC_PIXEL_FORMAT, cv2.CAP_PROP_FORMAT)
                    
                    # Enable hardware decoding flags
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimal buffer for faster processing
                    
                logger.debug("Hardware acceleration configured", 
                           codec=video_info.primary_video_stream.codec.value if video_info.primary_video_stream else "unknown")
            except Exception as e:
                logger.debug("Hardware acceleration setup failed, falling back to software", error=str(e))
        
        fps = video_info.primary_video_stream.fps if video_info.primary_video_stream else 30.0
        total_frames = int(video_info.duration * fps)
        frame_skip = config['frame_skip']
        resize_factor = config['resize_factor']
        
        # Initialize counters
        self._frames_processed = 0
        self._frames_skipped = 0
        
        # Algorithm-specific data
        prev_histogram = None
        prev_edges = None
        self.prev_frame = None
        self.optical_flow_initialized = False
        
        scene_changes = []
        frame_number = 0
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Skip frames based on processing mode
                if frame_number % frame_skip != 0:
                    self._frames_skipped += 1
                    frame_number += 1
                    continue
                
                timestamp = frame_number / fps
                
                # Resize frame for processing efficiency
                if resize_factor != 1.0:
                    new_height = int(frame.shape[0] * resize_factor)
                    new_width = int(frame.shape[1] * resize_factor)
                    frame = cv2.resize(frame, (new_width, new_height))
                
                # Update previous frame data for algorithms that need it
                if SceneDetectionAlgorithm.HISTOGRAM in algorithms:
                    if prev_histogram is None:
                        prev_histogram = self._calculate_histogram(frame, config['histogram_bins'])
                    else:
                        # Detect histogram change
                        change = self._detect_histogram_change(frame, prev_histogram, timestamp, frame_number, config)
                        if change and change.confidence >= self.algorithm_thresholds[SceneDetectionAlgorithm.HISTOGRAM]:
                            scene_changes.append(change)
                        # Always update histogram for next comparison
                        prev_histogram = self._calculate_histogram(frame, config['histogram_bins'])
                
                if SceneDetectionAlgorithm.EDGE_DETECTION in algorithms:
                    if prev_edges is None:
                        prev_edges = self._calculate_edges(frame)
                    else:
                        # Detect edge change
                        change = self._detect_edge_change(frame, prev_edges, timestamp, frame_number)
                        if change and change.confidence >= self.algorithm_thresholds[SceneDetectionAlgorithm.EDGE_DETECTION]:
                            scene_changes.append(change)
                        # Always update edges for next comparison
                        prev_edges = self._calculate_edges(frame)
                
                if SceneDetectionAlgorithm.OPTICAL_FLOW in algorithms:
                    if self.optical_flow_initialized and self.prev_frame is not None:
                        # Detect optical flow change
                        change = self._detect_optical_flow_change(frame, timestamp, frame_number)
                        if change and change.confidence >= self.algorithm_thresholds[SceneDetectionAlgorithm.OPTICAL_FLOW]:
                            scene_changes.append(change)
                    
                    # Always update previous frame for optical flow
                    self.prev_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    self.optical_flow_initialized = True
                
                self._frames_processed += 1
                frame_number += 1
                
        finally:
            cap.release()
        
        return scene_changes
    
    def _detect_histogram_change(self, frame: np.ndarray, prev_histogram: Optional[np.ndarray], 
                                timestamp: float, frame_number: int, config: Dict) -> Optional[SceneChange]:
        """Detect scene change using histogram comparison"""
        current_histogram = self._calculate_histogram(frame, config['histogram_bins'])
        
        if prev_histogram is None:
            return None
        
        # Calculate histogram correlation
        correlation = cv2.compareHist(prev_histogram, current_histogram, cv2.HISTCMP_CORREL)
        
        # Convert correlation to difference (lower correlation = higher difference)
        difference = 1.0 - correlation
        
        if difference >= self.algorithm_thresholds[SceneDetectionAlgorithm.HISTOGRAM]:
            return SceneChange(
                timestamp=timestamp,
                frame_number=frame_number,
                confidence=min(difference, 1.0),
                algorithm=SceneDetectionAlgorithm.HISTOGRAM,
                metrics={
                    'histogram_correlation': correlation,
                    'histogram_difference': difference,
                    'histogram_bins': config['histogram_bins']
                }
            )
        
        return None
    
    def _detect_edge_change(self, frame: np.ndarray, prev_edges: Optional[np.ndarray], 
                           timestamp: float, frame_number: int) -> Optional[SceneChange]:
        """Detect scene change using edge detection"""
        current_edges = self._calculate_edges(frame)
        
        if prev_edges is None:
            return None
        
        # Calculate edge difference using Hamming distance
        edge_diff = np.sum(np.abs(current_edges.astype(float) - prev_edges.astype(float)))
        edge_diff_normalized = edge_diff / (current_edges.shape[0] * current_edges.shape[1] * 255.0)
        
        if edge_diff_normalized >= self.algorithm_thresholds[SceneDetectionAlgorithm.EDGE_DETECTION]:
            return SceneChange(
                timestamp=timestamp,
                frame_number=frame_number,
                confidence=min(edge_diff_normalized, 1.0),
                algorithm=SceneDetectionAlgorithm.EDGE_DETECTION,
                metrics={
                    'edge_difference': edge_diff_normalized,
                    'total_edge_pixels': np.sum(current_edges > 0)
                }
            )
        
        return None
    
    def _detect_optical_flow_change(self, frame: np.ndarray, timestamp: float, 
                                   frame_number: int) -> Optional[SceneChange]:
        """Detect scene change using optical flow"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        if not self.optical_flow_initialized or self.prev_frame is None:
            return None
        
        # Calculate optical flow
        flow = cv2.calcOpticalFlowPyrLK(
            self.prev_frame, gray, None, None,
            winSize=(15, 15),
            maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )
        
        # Calculate flow magnitude
        if flow[0] is not None:
            flow_magnitude = np.sqrt(flow[0][:, :, 0]**2 + flow[0][:, :, 1]**2)
            avg_flow = np.mean(flow_magnitude)
            
            # Normalize flow magnitude
            normalized_flow = avg_flow / (frame.shape[0] + frame.shape[1])
            
            if normalized_flow >= self.algorithm_thresholds[SceneDetectionAlgorithm.OPTICAL_FLOW]:
                return SceneChange(
                    timestamp=timestamp,
                    frame_number=frame_number,
                    confidence=min(normalized_flow, 1.0),
                    algorithm=SceneDetectionAlgorithm.OPTICAL_FLOW,
                    metrics={
                        'optical_flow_magnitude': avg_flow,
                        'normalized_flow': normalized_flow,
                        'flow_points': len(flow[0]) if flow[0] is not None else 0
                    }
                )
        
        return None
    
    def _calculate_histogram(self, frame: np.ndarray, bins: int) -> np.ndarray:
        """Calculate color histogram for frame"""
        # Convert to HSV for better color representation
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # Calculate histogram for each channel
        hist_h = cv2.calcHist([hsv], [0], None, [bins], [0, 180])
        hist_s = cv2.calcHist([hsv], [1], None, [bins], [0, 256])
        hist_v = cv2.calcHist([hsv], [2], None, [bins], [0, 256])
        
        # Combine histograms
        histogram = np.concatenate([hist_h.flatten(), hist_s.flatten(), hist_v.flatten()])
        
        # Normalize histogram
        histogram = histogram / (np.sum(histogram) + 1e-7)
        
        return histogram
    
    def _calculate_edges(self, frame: np.ndarray) -> np.ndarray:
        """Calculate edge map for frame"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Canny edge detection
        edges = cv2.Canny(blurred, 50, 150)
        
        return edges
    
    def _post_process_scene_changes(self, scene_changes: List[SceneChange], 
                                   video_info: VideoInfo) -> List[SceneChange]:
        """Post-process scene changes to remove false positives and merge nearby changes"""
        if not scene_changes:
            return scene_changes
        
        # Sort by timestamp
        scene_changes.sort(key=lambda x: x.timestamp)
        
        # Remove changes that are too close together (merge nearby changes)
        filtered_changes = []
        last_timestamp = -float('inf')
        
        for change in scene_changes:
            if change.timestamp - last_timestamp >= self.min_scene_duration:
                filtered_changes.append(change)
                last_timestamp = change.timestamp
            else:
                # Merge with previous change if it has lower confidence
                if filtered_changes and change.confidence > filtered_changes[-1].confidence:
                    filtered_changes[-1] = change
        
        # Filter by confidence threshold
        final_changes = [
            change for change in filtered_changes 
            if change.confidence >= self.confidence_threshold
        ]
        
        logger.debug("Post-processed scene changes",
                    original_count=len(scene_changes),
                    after_merge=len(filtered_changes),
                    final_count=len(final_changes))
        
        return final_changes
    
    def batch_detect_scenes(self, video_paths: List[Union[str, Path]], 
                           algorithm: SceneDetectionAlgorithm = SceneDetectionAlgorithm.HISTOGRAM,
                           max_workers: Optional[int] = None) -> List[SceneDetectionResult]:
        """
        Detect scenes in multiple videos using parallel processing
        
        Args:
            video_paths: List of video file paths
            algorithm: Scene detection algorithm to use
            max_workers: Maximum number of worker threads (default: use config)
            
        Returns:
            List of SceneDetectionResult objects
        """
        max_workers = max_workers or min(self.max_workers, len(video_paths))
        
        logger.info("Starting batch scene detection",
                   video_count=len(video_paths),
                   algorithm=algorithm.value,
                   max_workers=max_workers)
        
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_path = {
                executor.submit(self.detect_scenes, path, algorithm): path 
                for path in video_paths
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error("Batch processing failed for video",
                               video_path=str(path),
                               error=str(e))
                    
                    # Create error result
                    error_result = SceneDetectionResult(
                        video_info=VideoInfo(
                            file_path=Path(path),
                            container_format=None,
                            duration=0,
                            file_size=0,
                            video_streams=[],
                            audio_streams=[],
                            metadata={},
                            is_valid=False
                        ),
                        scene_changes=[],
                        processing_time=0,
                        algorithm_used=algorithm,
                        processing_mode=self.processing_mode,
                        frames_processed=0,
                        frames_skipped=0,
                        success=False,
                        errors=[f"Batch processing failed: {str(e)}"]
                    )
                    results.append(error_result)
        
        # Sort results by original order
        path_to_index = {str(path): i for i, path in enumerate(video_paths)}
        results.sort(key=lambda r: path_to_index.get(str(r.video_info.file_path), float('inf')))
        
        successful_count = sum(1 for r in results if r.success)
        
        logger.info("Batch scene detection completed",
                   total_videos=len(video_paths),
                   successful=successful_count,
                   failed=len(video_paths) - successful_count)
        
        return results
    
    def get_processing_speed_estimate(self, video_info: VideoInfo) -> float:
        """
        Estimate processing speed multiplier for given video
        
        Args:
            video_info: Video information
            
        Returns:
            Estimated speed multiplier (e.g., 15.0 for 15x real-time)
        """
        base_speeds = {
            ProcessingMode.SPEED: 15.0,
            ProcessingMode.BALANCED: 10.0,
            ProcessingMode.QUALITY: 5.0,
            ProcessingMode.PRECISION: 2.0
        }
        
        base_speed = base_speeds[self.processing_mode]
        
        # Adjust for resolution
        if video_info.primary_video_stream:
            width, height = video_info.resolution
            pixels = width * height
            
            # Normalize to 1080p (1920x1080 = 2,073,600 pixels)
            resolution_factor = pixels / 2073600.0
            
            # Higher resolution = slower processing
            speed_adjustment = 1.0 / (resolution_factor ** 0.5)
            
            # Hardware acceleration bonus
            if self.enable_hardware_acceleration and video_info.hardware_decodable:
                speed_adjustment *= 1.5
            
            return base_speed * speed_adjustment
        
        return base_speed
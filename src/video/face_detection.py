"""
High-performance face detection module for AutoCut using MediaPipe.
Optimized for M1/M2 Mac hardware acceleration and 15x real-time video processing.
"""

import cv2
import numpy as np
import mediapipe as mp
import time
from typing import Dict, List, Optional, Tuple, Union, Iterator, NamedTuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
import gc
from contextlib import contextmanager

from .ingestion import VideoInfo, VideoStream
from ..utils.logging import get_logger
from ..utils.config import config

logger = get_logger(__name__)


class FaceDetectionModel(Enum):
    """Face detection model selection"""
    SHORT_RANGE = 0  # Optimized for faces within 2 meters
    FULL_RANGE = 1   # Optimized for faces within 5 meters


class ProcessingMode(Enum):
    """Processing mode selection"""
    REALTIME = "realtime"     # Maximum speed, basic quality
    BALANCED = "balanced"     # Balance of speed and quality  
    QUALITY = "quality"       # Maximum quality, slower processing


class FaceQuality(Enum):
    """Face quality assessment levels"""
    POOR = 0
    FAIR = 1
    GOOD = 2
    EXCELLENT = 3


@dataclass
class FaceBoundingBox:
    """Face bounding box with normalized coordinates"""
    x_min: float  # Normalized by image width [0.0, 1.0]
    y_min: float  # Normalized by image height [0.0, 1.0]
    width: float  # Normalized width [0.0, 1.0]
    height: float # Normalized height [0.0, 1.0]
    
    def to_pixel_coords(self, image_width: int, image_height: int) -> Tuple[int, int, int, int]:
        """Convert to pixel coordinates (x, y, w, h)"""
        x = int(self.x_min * image_width)
        y = int(self.y_min * image_height)
        w = int(self.width * image_width)
        h = int(self.height * image_height)
        return (x, y, w, h)
    
    def area(self) -> float:
        """Calculate normalized area"""
        return self.width * self.height
    
    def center(self) -> Tuple[float, float]:
        """Get center point (normalized)"""
        return (self.x_min + self.width / 2, self.y_min + self.height / 2)


@dataclass 
class FaceLandmark:
    """Individual face landmark with normalized coordinates"""
    x: float  # Normalized by image width [0.0, 1.0]
    y: float  # Normalized by image height [0.0, 1.0]
    
    def to_pixel_coords(self, image_width: int, image_height: int) -> Tuple[int, int]:
        """Convert to pixel coordinates"""
        return (int(self.x * image_width), int(self.y * image_height))


@dataclass
class FaceKeyPoints:
    """Key facial landmarks for quality assessment"""
    right_eye: FaceLandmark
    left_eye: FaceLandmark
    nose_tip: FaceLandmark
    mouth_center: FaceLandmark
    right_ear: Optional[FaceLandmark] = None
    left_ear: Optional[FaceLandmark] = None
    
    def eye_distance(self) -> float:
        """Calculate distance between eyes (normalized)"""
        return np.sqrt((self.left_eye.x - self.right_eye.x)**2 + 
                      (self.left_eye.y - self.right_eye.y)**2)
    
    def face_angle(self) -> float:
        """Estimate face angle in degrees (0 = straight, positive = left turn)"""
        eye_vector = np.array([self.left_eye.x - self.right_eye.x,
                              self.left_eye.y - self.right_eye.y])
        angle = np.arctan2(eye_vector[1], eye_vector[0]) * 180 / np.pi
        return angle


@dataclass
class FaceDetectionResult:
    """Complete face detection result for a single face"""
    bounding_box: FaceBoundingBox
    keypoints: FaceKeyPoints
    confidence: float  # Detection confidence [0.0, 1.0]
    face_id: Optional[int] = None  # For tracking across frames
    
    # Quality metrics
    relative_size: float = 0.0     # Face size relative to frame [0.0, 1.0]
    visibility: float = 1.0        # Visibility score [0.0, 1.0]
    pose_angle: float = 0.0        # Face pose angle in degrees
    quality_score: float = 0.0     # Overall quality score [0.0, 1.0]
    quality_level: FaceQuality = FaceQuality.FAIR
    
    # Occlusion detection
    is_occluded: bool = False
    occlusion_score: float = 0.0   # Occlusion level [0.0, 1.0]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'bounding_box': {
                'x_min': self.bounding_box.x_min,
                'y_min': self.bounding_box.y_min,
                'width': self.bounding_box.width,
                'height': self.bounding_box.height
            },
            'keypoints': {
                'right_eye': {'x': self.keypoints.right_eye.x, 'y': self.keypoints.right_eye.y},
                'left_eye': {'x': self.keypoints.left_eye.x, 'y': self.keypoints.left_eye.y},
                'nose_tip': {'x': self.keypoints.nose_tip.x, 'y': self.keypoints.nose_tip.y},
                'mouth_center': {'x': self.keypoints.mouth_center.x, 'y': self.keypoints.mouth_center.y}
            },
            'confidence': self.confidence,
            'face_id': self.face_id,
            'relative_size': self.relative_size,
            'visibility': self.visibility,
            'pose_angle': self.pose_angle,
            'quality_score': self.quality_score,
            'quality_level': self.quality_level.name,
            'is_occluded': self.is_occluded,
            'occlusion_score': self.occlusion_score
        }


@dataclass
class FrameFaceDetectionResult:
    """Face detection results for a single frame"""
    timestamp: float                           # Frame timestamp in seconds
    frame_index: int                          # Frame number
    faces: List[FaceDetectionResult]          # All detected faces
    processing_time: float                    # Processing time in seconds
    frame_width: int                          # Frame dimensions
    frame_height: int
    
    # Frame-level statistics
    total_faces: int = field(init=False)
    best_face: Optional[FaceDetectionResult] = field(init=False)
    average_quality: float = field(init=False)
    
    def __post_init__(self):
        self.total_faces = len(self.faces)
        self.best_face = max(self.faces, key=lambda f: f.quality_score) if self.faces else None
        self.average_quality = sum(f.quality_score for f in self.faces) / len(self.faces) if self.faces else 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'timestamp': self.timestamp,
            'frame_index': self.frame_index,
            'total_faces': self.total_faces,
            'processing_time': self.processing_time,
            'frame_dimensions': {'width': self.frame_width, 'height': self.frame_height},
            'faces': [face.to_dict() for face in self.faces],
            'best_face': self.best_face.to_dict() if self.best_face else None,
            'average_quality': self.average_quality
        }


@dataclass
class VideoFaceDetectionResult:
    """Complete face detection results for an entire video"""
    video_info: VideoInfo
    frame_results: List[FrameFaceDetectionResult]
    processing_settings: Dict
    
    # Video-level statistics
    total_frames_processed: int = field(init=False)
    total_processing_time: float = field(init=False)
    average_fps: float = field(init=False)
    faces_per_second: float = field(init=False)
    
    # Quality statistics
    best_frame: Optional[FrameFaceDetectionResult] = field(init=False)
    worst_frame: Optional[FrameFaceDetectionResult] = field(init=False)
    overall_quality_score: float = field(init=False)
    
    def __post_init__(self):
        self.total_frames_processed = len(self.frame_results)
        self.total_processing_time = sum(r.processing_time for r in self.frame_results)
        
        if self.total_processing_time > 0:
            self.average_fps = self.total_frames_processed / self.total_processing_time
        else:
            self.average_fps = 0.0
            
        total_faces = sum(r.total_faces for r in self.frame_results)
        video_duration = self.video_info.duration
        self.faces_per_second = total_faces / video_duration if video_duration > 0 else 0.0
        
        # Find best and worst frames by quality
        frames_with_faces = [r for r in self.frame_results if r.faces]
        if frames_with_faces:
            self.best_frame = max(frames_with_faces, key=lambda r: r.average_quality)
            self.worst_frame = min(frames_with_faces, key=lambda r: r.average_quality)
            self.overall_quality_score = sum(r.average_quality for r in frames_with_faces) / len(frames_with_faces)
        else:
            self.best_frame = None
            self.worst_frame = None
            self.overall_quality_score = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'video_path': str(self.video_info.file_path),
            'video_duration': self.video_info.duration,
            'processing_settings': self.processing_settings,
            'statistics': {
                'total_frames_processed': self.total_frames_processed,
                'total_processing_time': self.total_processing_time,
                'average_fps': self.average_fps,
                'faces_per_second': self.faces_per_second,
                'overall_quality_score': self.overall_quality_score
            },
            'frame_results': [r.to_dict() for r in self.frame_results],
            'best_frame': self.best_frame.to_dict() if self.best_frame else None,
            'worst_frame': self.worst_frame.to_dict() if self.worst_frame else None
        }


class FrameSampler:
    """Intelligent frame sampling for performance optimization"""
    
    def __init__(self, target_fps: float, video_fps: float, mode: ProcessingMode):
        self.target_fps = target_fps
        self.video_fps = video_fps
        self.mode = mode
        
        # Calculate frame skip interval
        if target_fps >= video_fps:
            self.skip_interval = 1
        else:
            self.skip_interval = max(1, int(video_fps / target_fps))
        
        logger.debug("Frame sampler initialized",
                    target_fps=target_fps,
                    video_fps=video_fps,
                    skip_interval=self.skip_interval,
                    mode=mode.value)
    
    def should_process_frame(self, frame_index: int) -> bool:
        """Determine if frame should be processed"""
        return frame_index % self.skip_interval == 0
    
    def get_processing_interval(self) -> int:
        """Get frame processing interval"""
        return self.skip_interval


class FaceDetectionEngine:
    """High-performance face detection engine using MediaPipe"""
    
    def __init__(self, 
                 model: FaceDetectionModel = FaceDetectionModel.SHORT_RANGE,
                 mode: ProcessingMode = ProcessingMode.BALANCED,
                 min_detection_confidence: float = 0.5,
                 target_fps: float = 15.0,
                 max_workers: Optional[int] = None):
        """
        Initialize face detection engine
        
        Args:
            model: Face detection model (SHORT_RANGE or FULL_RANGE)
            mode: Processing mode (REALTIME, BALANCED, QUALITY)
            min_detection_confidence: Minimum detection confidence threshold
            target_fps: Target processing FPS for frame sampling
            max_workers: Maximum number of worker threads (None for auto)
        """
        self.model = model
        self.mode = mode
        self.min_detection_confidence = min_detection_confidence
        self.target_fps = target_fps
        
        # Threading configuration
        if max_workers is None:
            # Optimize for M1/M2 Macs - use performance cores efficiently
            import os
            cpu_count = os.cpu_count() or 4
            self.max_workers = min(cpu_count // 2, 4)  # Conservative for memory usage
        else:
            self.max_workers = max_workers
        
        # Performance tracking
        self._total_frames_processed = 0
        self._total_processing_time = 0.0
        self._performance_lock = threading.Lock()
        
        # Early exit optimization for videos without faces
        self._consecutive_empty_frames = 0
        self._early_exit_threshold = 10  # Skip processing after 10 consecutive frames without faces
        self._early_exit_mode = False
        
        # Initialize MediaPipe components
        self.mp_face_detection = mp.solutions.face_detection
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Model configuration based on mode
        self._configure_for_mode()
        
        logger.info("FaceDetectionEngine initialized",
                   model=model.name,
                   mode=mode.value,
                   min_confidence=min_detection_confidence,
                   target_fps=target_fps,
                   max_workers=self.max_workers)
    
    def _configure_for_mode(self):
        """Configure detection parameters based on processing mode"""
        mode_configs = {
            ProcessingMode.REALTIME: {
                'min_detection_confidence': max(0.3, self.min_detection_confidence - 0.2),
                'batch_size': 8,
                'quality_assessment': False
            },
            ProcessingMode.BALANCED: {
                'min_detection_confidence': self.min_detection_confidence,
                'batch_size': 4,
                'quality_assessment': True
            },
            ProcessingMode.QUALITY: {
                'min_detection_confidence': min(0.8, self.min_detection_confidence + 0.2),
                'batch_size': 2,
                'quality_assessment': True
            }
        }
        
        self.config = mode_configs[self.mode]
        logger.debug("Engine configured for mode", mode=self.mode.value, config=self.config)
    
    @contextmanager
    def _get_detector(self):
        """Context manager for MediaPipe face detector"""
        detector = None
        try:
            detector = self.mp_face_detection.FaceDetection(
                model_selection=self.model.value,
                min_detection_confidence=self.config['min_detection_confidence']
            )
            yield detector
        finally:
            if detector:
                detector.close()
            # Force garbage collection to free memory
            gc.collect()
    
    def _extract_face_keypoints(self, detection) -> FaceKeyPoints:
        """Extract key facial landmarks from MediaPipe detection"""
        # MediaPipe provides 6 key points
        keypoints = detection.location_data.relative_keypoints
        
        # Map MediaPipe keypoints to our structure
        right_eye = FaceLandmark(keypoints[0].x, keypoints[0].y)
        left_eye = FaceLandmark(keypoints[1].x, keypoints[1].y)
        nose_tip = FaceLandmark(keypoints[2].x, keypoints[2].y)
        mouth_center = FaceLandmark(keypoints[3].x, keypoints[3].y)
        
        # Ear points (if reliable)
        right_ear = None
        left_ear = None
        if len(keypoints) > 4:
            right_ear = FaceLandmark(keypoints[4].x, keypoints[4].y)
        if len(keypoints) > 5:
            left_ear = FaceLandmark(keypoints[5].x, keypoints[5].y)
        
        return FaceKeyPoints(
            right_eye=right_eye,
            left_eye=left_eye,
            nose_tip=nose_tip,
            mouth_center=mouth_center,
            right_ear=right_ear,
            left_ear=left_ear
        )
    
    def _assess_face_quality(self, face_result: FaceDetectionResult, 
                           frame_width: int, frame_height: int) -> FaceDetectionResult:
        """Assess face quality metrics"""
        if not self.config['quality_assessment']:
            return face_result
        
        # Calculate relative face size
        face_result.relative_size = face_result.bounding_box.area()
        
        # Estimate pose angle
        face_result.pose_angle = face_result.keypoints.face_angle()
        
        # Quality scoring based on multiple factors
        size_score = min(1.0, face_result.relative_size * 10)  # Larger faces get higher scores
        confidence_score = face_result.confidence
        angle_score = max(0.0, 1.0 - abs(face_result.pose_angle) / 45.0)  # Prefer straight-on faces
        
        # Occlusion detection based on keypoint positions
        eye_distance = face_result.keypoints.eye_distance()
        expected_mouth_y = (face_result.keypoints.right_eye.y + face_result.keypoints.left_eye.y) / 2 + eye_distance * 0.8
        mouth_deviation = abs(face_result.keypoints.mouth_center.y - expected_mouth_y)
        occlusion_score = min(1.0, mouth_deviation * 5)  # Higher deviation suggests occlusion
        
        face_result.occlusion_score = occlusion_score
        face_result.is_occluded = occlusion_score > 0.3
        
        # Overall quality score (weighted combination)
        face_result.quality_score = (
            size_score * 0.3 +
            confidence_score * 0.4 +
            angle_score * 0.2 +
            (1.0 - occlusion_score) * 0.1
        )
        
        # Determine quality level
        if face_result.quality_score >= 0.8:
            face_result.quality_level = FaceQuality.EXCELLENT
        elif face_result.quality_score >= 0.6:
            face_result.quality_level = FaceQuality.GOOD
        elif face_result.quality_score >= 0.4:
            face_result.quality_level = FaceQuality.FAIR
        else:
            face_result.quality_level = FaceQuality.POOR
        
        return face_result
    
    def _process_frame(self, frame: np.ndarray, timestamp: float, 
                      frame_index: int) -> FrameFaceDetectionResult:
        """Process a single frame for face detection"""
        start_time = time.time()
        frame_height, frame_width = frame.shape[:2]
        faces = []
        
        # Early exit optimization: skip heavy processing if video likely has no faces
        if self._early_exit_mode:
            # Skip expensive MediaPipe processing
            processing_time = time.time() - start_time
            
            # Update performance metrics
            with self._performance_lock:
                self._total_frames_processed += 1
                self._total_processing_time += processing_time
            
            return FrameFaceDetectionResult(
                timestamp=timestamp,
                frame_index=frame_index,
                faces=[],  # No faces in early exit mode
                processing_time=processing_time,
                frame_width=frame_width,
                frame_height=frame_height
            )
        
        # Convert BGR to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        with self._get_detector() as face_detection:
            # Set frame as not writeable for performance
            rgb_frame.flags.writeable = False
            results = face_detection.process(rgb_frame)
            
            if results.detections:
                for detection in results.detections:
                    # Extract bounding box
                    bbox = detection.location_data.relative_bounding_box
                    bounding_box = FaceBoundingBox(
                        x_min=bbox.xmin,
                        y_min=bbox.ymin,
                        width=bbox.width,
                        height=bbox.height
                    )
                    
                    # Extract keypoints
                    keypoints = self._extract_face_keypoints(detection)
                    
                    # Create face result
                    face_result = FaceDetectionResult(
                        bounding_box=bounding_box,
                        keypoints=keypoints,
                        confidence=detection.score[0]  # MediaPipe provides confidence as list
                    )
                    
                    # Assess quality if enabled
                    face_result = self._assess_face_quality(face_result, frame_width, frame_height)
                    
                    faces.append(face_result)
        
        processing_time = time.time() - start_time
        
        # Track consecutive empty frames for early exit optimization
        if len(faces) == 0:
            self._consecutive_empty_frames += 1
            if self._consecutive_empty_frames >= self._early_exit_threshold:
                if not self._early_exit_mode:
                    logger.info("Activating early exit optimization for face detection",
                              consecutive_empty_frames=self._consecutive_empty_frames,
                              threshold=self._early_exit_threshold)
                    self._early_exit_mode = True
        else:
            # Reset counter if faces are found
            self._consecutive_empty_frames = 0
            if self._early_exit_mode:
                logger.info("Deactivating early exit optimization - faces detected again")
                self._early_exit_mode = False
        
        # Update performance metrics
        with self._performance_lock:
            self._total_frames_processed += 1
            self._total_processing_time += processing_time
        
        return FrameFaceDetectionResult(
            timestamp=timestamp,
            frame_index=frame_index,
            faces=faces,
            processing_time=processing_time,
            frame_width=frame_width,
            frame_height=frame_height
        )
    
    def process_video_frames(self, video_info: VideoInfo, 
                           frame_generator: Iterator[Tuple[np.ndarray, float, int]],
                           progress_callback: Optional[callable] = None) -> VideoFaceDetectionResult:
        """
        Process video frames for face detection
        
        Args:
            video_info: Video information
            frame_generator: Iterator yielding (frame, timestamp, frame_index) tuples
            progress_callback: Optional callback for progress updates
            
        Returns:
            Complete video face detection results
        """
        logger.info("Starting face detection processing",
                   video_path=str(video_info.file_path),
                   target_fps=self.target_fps,
                   mode=self.mode.value)
        
        # Initialize frame sampler
        video_fps = video_info.primary_video_stream.fps if video_info.primary_video_stream else 30.0
        sampler = FrameSampler(self.target_fps, video_fps, self.mode)
        
        frame_results = []
        processed_count = 0
        
        # Batch processing for efficiency
        batch_size = self.config['batch_size']
        frame_batch = []
        
        try:
            for frame, timestamp, frame_index in frame_generator:
                # Apply frame sampling
                if not sampler.should_process_frame(frame_index):
                    continue
                
                frame_batch.append((frame, timestamp, frame_index))
                
                # Process batch when full or at end
                if len(frame_batch) >= batch_size:
                    batch_results = self._process_frame_batch(frame_batch)
                    frame_results.extend(batch_results)
                    frame_batch = []
                    
                    processed_count += len(batch_results)
                    
                    # Progress callback
                    if progress_callback:
                        progress_callback(processed_count, timestamp)
            
            # Process remaining frames
            if frame_batch:
                batch_results = self._process_frame_batch(frame_batch)
                frame_results.extend(batch_results)
        
        except Exception as e:
            logger.error("Error during face detection processing", error=str(e))
            raise
        
        # Create final result
        processing_settings = {
            'model': self.model.name,
            'mode': self.mode.value,
            'min_detection_confidence': self.config['min_detection_confidence'],
            'target_fps': self.target_fps,
            'frame_skip_interval': sampler.get_processing_interval(),
            'quality_assessment_enabled': self.config['quality_assessment']
        }
        
        result = VideoFaceDetectionResult(
            video_info=video_info,
            frame_results=frame_results,
            processing_settings=processing_settings
        )
        
        logger.info("Face detection processing completed",
                   total_frames=len(frame_results),
                   total_faces=sum(r.total_faces for r in frame_results),
                   average_fps=result.average_fps,
                   overall_quality=result.overall_quality_score)
        
        return result
    
    def _process_frame_batch(self, frame_batch: List[Tuple[np.ndarray, float, int]]) -> List[FrameFaceDetectionResult]:
        """Process a batch of frames using threading"""
        if len(frame_batch) == 1:
            # Single frame - process directly
            frame, timestamp, frame_index = frame_batch[0]
            return [self._process_frame(frame, timestamp, frame_index)]
        
        # Multi-threaded batch processing
        results = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(frame_batch))) as executor:
            # Submit all frames for processing
            future_to_frame = {
                executor.submit(self._process_frame, frame, timestamp, frame_index): (timestamp, frame_index)
                for frame, timestamp, frame_index in frame_batch
            }
            
            # Collect results
            for future in as_completed(future_to_frame):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    timestamp, frame_index = future_to_frame[future]
                    logger.error("Error processing frame",
                               frame_index=frame_index,
                               timestamp=timestamp,
                               error=str(e))
        
        # Sort results by frame index to maintain order
        results.sort(key=lambda r: r.frame_index)
        return results
    
    def get_performance_stats(self) -> Dict:
        """Get current performance statistics"""
        with self._performance_lock:
            if self._total_frames_processed > 0:
                avg_time_per_frame = self._total_processing_time / self._total_frames_processed
                estimated_fps = 1.0 / avg_time_per_frame if avg_time_per_frame > 0 else 0.0
            else:
                avg_time_per_frame = 0.0
                estimated_fps = 0.0
            
            return {
                'total_frames_processed': self._total_frames_processed,
                'total_processing_time': self._total_processing_time,
                'average_time_per_frame': avg_time_per_frame,
                'estimated_fps': estimated_fps,
                'target_fps': self.target_fps,
                'mode': self.mode.value
            }


def create_video_frame_generator(video_path: Union[str, Path]) -> Iterator[Tuple[np.ndarray, float, int]]:
    """
    Create a generator for video frames with timestamps
    
    Args:
        video_path: Path to video file
        
    Yields:
        Tuple of (frame, timestamp, frame_index)
    """
    cap = cv2.VideoCapture(str(video_path))
    
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0  # Default fallback
        logger.warning("Could not determine video FPS, using default", fps=fps)
    
    frame_index = 0
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # CRITICAL FIX: Validate frame data before yielding
            if frame is None:
                logger.warning("Null frame detected", frame_index=frame_index)
                frame_index += 1
                continue
                
            if not isinstance(frame, np.ndarray):
                logger.warning("Invalid frame type detected", frame_index=frame_index, frame_type=type(frame))
                frame_index += 1
                continue
                
            if frame.size == 0:
                logger.warning("Empty frame detected", frame_index=frame_index)
                frame_index += 1
                continue
                
            # Additional validation for corrupted frames
            if len(frame.shape) != 3 or frame.shape[2] != 3:
                logger.warning("Invalid frame dimensions", frame_index=frame_index, shape=frame.shape)
                frame_index += 1
                continue
            
            timestamp = frame_index / fps
            yield frame, timestamp, frame_index
            frame_index += 1
    
    finally:
        cap.release()


# Factory function for easy engine creation
def create_face_detection_engine(video_info: VideoInfo, 
                                target_realtime_multiple: float = 15.0,
                                quality_mode: str = "balanced") -> FaceDetectionEngine:
    """
    Create optimized face detection engine for given video
    
    Args:
        video_info: Video information for optimization
        target_realtime_multiple: Target processing speed multiplier (15x = 15x real-time)
        quality_mode: Processing quality mode ("realtime", "balanced", "quality")
        
    Returns:
        Configured FaceDetectionEngine
    """
    # Determine optimal settings based on video properties
    video_fps = video_info.primary_video_stream.fps if video_info.primary_video_stream else 30.0
    target_fps = min(video_fps, video_fps / target_realtime_multiple)
    
    # Choose model based on video resolution
    width, height = video_info.resolution
    if max(width, height) <= 720:
        model = FaceDetectionModel.SHORT_RANGE  # Lower resolution, assume closer subjects
    else:
        model = FaceDetectionModel.FULL_RANGE   # Higher resolution, may have distant subjects
    
    # Map quality mode string to enum
    mode_mapping = {
        "realtime": ProcessingMode.REALTIME,
        "balanced": ProcessingMode.BALANCED,
        "quality": ProcessingMode.QUALITY
    }
    mode = mode_mapping.get(quality_mode.lower(), ProcessingMode.BALANCED)
    
    # Adjust confidence based on video quality
    base_confidence = 0.5
    if video_info.primary_video_stream and video_info.primary_video_stream.bitrate:
        # Higher bitrate videos can use higher confidence
        bitrate_mbps = video_info.primary_video_stream.bitrate / 1_000_000
        if bitrate_mbps > 10:
            base_confidence = 0.6
        elif bitrate_mbps < 2:
            base_confidence = 0.4
    
    logger.info("Creating optimized face detection engine",
               video_resolution=f"{width}x{height}",
               video_fps=video_fps,
               target_fps=target_fps,
               model=model.name,
               mode=mode.value,
               confidence=base_confidence)
    
    return FaceDetectionEngine(
        model=model,
        mode=mode,
        min_detection_confidence=base_confidence,
        target_fps=target_fps
    )
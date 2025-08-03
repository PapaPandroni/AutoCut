"""
Comprehensive quality scoring algorithm for AutoCut video editing.

This module implements sophisticated algorithms for evaluating video frame quality
based on multiple weighted factors including face quality, blur detection, exposure
analysis, motion blur, composition, and color quality assessment.

Algorithm Architecture:
1. Multi-factor analysis with configurable weight profiles
2. Real-time performance optimization for 15x processing target
3. Integration with existing face detection and scene analysis
4. Parallel processing with memory-efficient frame sampling
5. Quality timeline generation for cut optimization

Mathematical Foundation:
- Face Quality: F = Σ(face_quality_score * face_area_weight) / total_faces
- Blur Detection: B = α * Laplacian_Variance + (1-α) * FFT_HighFreq
- Exposure Analysis: E = w1*Histogram + w2*DynamicRange + w3*ClippingDetection
- Motion Blur: M = w1*OpticalFlow + w2*FrameDifference
- Composition: C = max(RuleOfThirds, CenterFraming) * strength
- Color Quality: K = (Saturation + Contrast + ColorBalance) / 3
- Total: Q = Σ(w_i * Factor_i) where Σw_i = 1.0
"""

import cv2
import numpy as np
import time
from typing import Dict, List, Optional, Tuple, Any, Union, Iterator, NamedTuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
import gc
from contextlib import contextmanager
import math

from ..video.ingestion import VideoInfo, VideoStream
from ..video.face_detection import FrameFaceDetectionResult, FaceDetectionResult
from ..utils.logging import get_logger
from ..utils.config import config

logger = get_logger(__name__)


class QualityProfile(Enum):
    """Quality scoring profiles for different video content types"""
    TALKING_HEAD = "talking_head"     # Emphasizes face quality and sharpness
    ACTION = "action"                 # Emphasizes motion and exposure
    LANDSCAPE = "landscape"           # Emphasizes composition and color
    DOCUMENTARY = "documentary"       # Balanced with slight face emphasis
    ADAPTIVE = "adaptive"             # Dynamic adjustment based on content
    
    
class BlurMethod(Enum):
    """Blur detection algorithm methods"""
    LAPLACIAN_VARIANCE = "laplacian_variance"
    FFT_HIGH_FREQUENCY = "fft_high_frequency"
    COMBINED = "combined"


@dataclass
class QualityMetrics:
    """Individual quality metrics for a frame"""
    # FIXED: Core quality factors (0.0 - 1.0) - Use 0.5 neutral scores to distinguish unprocessed from poor quality
    face_quality: float = 0.5
    blur_score: float = 0.5
    exposure_score: float = 0.5
    motion_blur_score: float = 0.5
    composition_score: float = 0.5
    color_quality_score: float = 0.5
    
    # FIXED: Detailed sub-metrics - Use 0.5 neutral scores for consistent baseline
    blur_laplacian: float = 0.5
    blur_fft: float = 0.5
    exposure_histogram: float = 0.5
    exposure_dynamic_range: float = 0.5  
    exposure_clipping: float = 0.5
    motion_optical_flow: float = 0.5
    motion_frame_diff: float = 0.5
    composition_rule_thirds: float = 0.5
    composition_center: float = 0.5
    color_saturation: float = 0.5
    color_contrast: float = 0.5
    color_balance: float = 0.5
    
    # Processing metadata (keep 0.0 for timing and string defaults)
    processing_time: float = 0.0
    method_used: str = ""
    
    def to_dict(self) -> Dict[str, float]:
        """Convert metrics to dictionary"""
        return {
            'face_quality': self.face_quality,
            'blur_score': self.blur_score,
            'exposure_score': self.exposure_score, 
            'motion_blur_score': self.motion_blur_score,
            'composition_score': self.composition_score,
            'color_quality_score': self.color_quality_score,
            'blur_laplacian': self.blur_laplacian,
            'blur_fft': self.blur_fft,
            'exposure_histogram': self.exposure_histogram,
            'exposure_dynamic_range': self.exposure_dynamic_range,
            'exposure_clipping': self.exposure_clipping,
            'motion_optical_flow': self.motion_optical_flow,
            'motion_frame_diff': self.motion_frame_diff,
            'composition_rule_thirds': self.composition_rule_thirds,
            'composition_center': self.composition_center,
            'color_saturation': self.color_saturation,
            'color_contrast': self.color_contrast,
            'color_balance': self.color_balance,
            'processing_time': self.processing_time,
            'method_used': self.method_used
        }


@dataclass
class FrameQualityResult:
    """Quality assessment result for a single frame"""
    timestamp: float
    frame_index: int
    overall_quality: float              # Final weighted quality score (0-100)
    metrics: QualityMetrics
    profile_used: QualityProfile
    face_count: int = 0
    
    # Processing metadata
    frame_width: int = 0
    frame_height: int = 0
    processing_time: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'timestamp': self.timestamp,
            'frame_index': self.frame_index,
            'overall_quality': self.overall_quality,
            'metrics': self.metrics.to_dict(),
            'profile_used': self.profile_used.value,
            'face_count': self.face_count,
            'frame_dimensions': {'width': self.frame_width, 'height': self.frame_height},
            'processing_time': self.processing_time
        }


@dataclass  
class VideoQualityResult:
    """Complete quality assessment results for an entire video"""
    video_info: VideoInfo
    frame_results: List[FrameQualityResult]
    profile_used: QualityProfile
    processing_settings: Dict[str, Any]
    
    # Video-level statistics
    total_frames_processed: int = field(init=False)
    total_processing_time: float = field(init=False)
    average_fps: float = field(init=False)
    
    # Quality statistics
    mean_quality: float = field(init=False)
    median_quality: float = field(init=False)
    quality_std: float = field(init=False)
    best_frame: Optional[FrameQualityResult] = field(init=False)
    worst_frame: Optional[FrameQualityResult] = field(init=False)
    
    # Quality timeline data
    quality_timeline: List[Tuple[float, float]] = field(init=False)  # (timestamp, quality)
    quality_trend: str = field(init=False)  # "improving", "declining", "stable"
    
    def __post_init__(self):
        self.total_frames_processed = len(self.frame_results)
        self.total_processing_time = sum(r.processing_time for r in self.frame_results)
        
        if self.total_processing_time > 0:
            self.average_fps = self.total_frames_processed / self.total_processing_time
        else:
            self.average_fps = 0.0
            
        if self.frame_results:
            qualities = [r.overall_quality for r in self.frame_results]
            # CRITICAL FIX: Convert from 0-100 scale to 0-1 scale for consistency
            mean_quality_100_scale = np.mean(qualities)
            self.mean_quality = mean_quality_100_scale / 100.0
            # CRITICAL FIX: Convert all quality metrics to 0-1 scale for consistency
            self.median_quality = np.median(qualities) / 100.0
            self.quality_std = np.std(qualities) / 100.0
            
            self.best_frame = max(self.frame_results, key=lambda r: r.overall_quality)
            self.worst_frame = min(self.frame_results, key=lambda r: r.overall_quality)
            
            # Generate quality timeline
            self.quality_timeline = [(r.timestamp, r.overall_quality) for r in self.frame_results]
            
            # Analyze quality trend
            self.quality_trend = self._analyze_quality_trend(qualities)
        else:
            self.mean_quality = 0.0
            self.median_quality = 0.0
            self.quality_std = 0.0
            self.best_frame = None
            self.worst_frame = None
            self.quality_timeline = []
            self.quality_trend = "unknown"
            
    def _analyze_quality_trend(self, qualities: List[float]) -> str:
        """Analyze overall quality trend across the video"""
        if len(qualities) < 10:
            return "insufficient_data"
            
        # Split into segments and compare
        segment_size = len(qualities) // 3
        first_third = np.mean(qualities[:segment_size])
        last_third = np.mean(qualities[-segment_size:])
        
        diff = last_third - first_third
        threshold = self.quality_std * 0.5  # Use half standard deviation as threshold
        
        if diff > threshold:
            return "improving"
        elif diff < -threshold:
            return "declining"
        else:
            return "stable"
    
    def get_quality_segments(self, min_quality: float = 60.0) -> List[Tuple[float, float]]:
        """Get time segments with quality above threshold"""
        segments = []
        start_time = None
        
        for result in self.frame_results:
            if result.overall_quality >= min_quality:
                if start_time is None:
                    start_time = result.timestamp
            else:
                if start_time is not None:
                    segments.append((start_time, result.timestamp))
                    start_time = None
        
        # Close final segment if needed
        if start_time is not None:
            segments.append((start_time, self.frame_results[-1].timestamp))
            
        return segments
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'video_path': str(self.video_info.file_path),
            'video_duration': self.video_info.duration,
            'profile_used': self.profile_used.value,
            'processing_settings': self.processing_settings,
            'statistics': {
                'total_frames_processed': self.total_frames_processed,
                'total_processing_time': self.total_processing_time,
                'average_fps': self.average_fps,
                'mean_quality': self.mean_quality,
                'median_quality': self.median_quality,
                'quality_std': self.quality_std,
                'quality_trend': self.quality_trend
            },
            'frame_results': [r.to_dict() for r in self.frame_results],
            'best_frame': self.best_frame.to_dict() if self.best_frame else None,
            'worst_frame': self.worst_frame.to_dict() if self.worst_frame else None,
            'quality_timeline': self.quality_timeline
        }


class QualityScoring:
    """
    High-performance quality scoring engine for video frames.
    
    Implements sophisticated multi-factor quality assessment with configurable
    profiles and real-time performance optimization.
    """
    
    def __init__(self, 
                 profile: QualityProfile = QualityProfile.ADAPTIVE,
                 target_fps: float = 15.0,
                 max_workers: Optional[int] = None,
                 enable_face_integration: bool = True):
        """
        Initialize quality scoring engine
        
        Args:
            profile: Quality scoring profile for weight configuration
            target_fps: Target processing FPS for frame sampling
            max_workers: Maximum number of worker threads (None for auto)
            enable_face_integration: Whether to integrate with face detection results
        """
        self.profile = profile
        self.target_fps = target_fps
        self.enable_face_integration = enable_face_integration
        
        # Threading configuration
        if max_workers is None:
            import os
            cpu_count = os.cpu_count() or 4
            self.max_workers = min(cpu_count // 2, 4)  # Conservative for memory usage
        else:
            self.max_workers = max_workers
            
        # Load configuration
        self.blur_threshold = config.get('quality.blur_threshold', 100.0)
        self.exposure_optimal_mean = config.get('quality.exposure_optimal_mean', 127.0)
        self.motion_threshold = config.get('quality.motion_threshold', 10.0)
        self.composition_strength = config.get('quality.composition_strength', 0.3)
        
        # Quality profile configurations
        self.profile_weights = {
            QualityProfile.TALKING_HEAD: {
                'face_weight': 0.25,
                'blur_weight': 0.25, 
                'exposure_weight': 0.20,
                'motion_weight': 0.15,
                'composition_weight': 0.10,
                'color_weight': 0.05
            },
            QualityProfile.ACTION: {
                'face_weight': 0.10,
                'blur_weight': 0.20,
                'exposure_weight': 0.25,
                'motion_weight': 0.25,
                'composition_weight': 0.15,
                'color_weight': 0.05
            },
            QualityProfile.LANDSCAPE: {
                'face_weight': 0.05,
                'blur_weight': 0.15,
                'exposure_weight': 0.20,
                'motion_weight': 0.10,
                'composition_weight': 0.30,
                'color_weight': 0.20
            },
            QualityProfile.DOCUMENTARY: {
                'face_weight': 0.20,
                'blur_weight': 0.20,
                'exposure_weight': 0.20,
                'motion_weight': 0.15,
                'composition_weight': 0.15,
                'color_weight': 0.10
            },
            QualityProfile.ADAPTIVE: {
                'face_weight': 0.15,
                'blur_weight': 0.20,
                'exposure_weight': 0.20,
                'motion_weight': 0.20,
                'composition_weight': 0.15,
                'color_weight': 0.10
            }
        }
        
        # Performance tracking
        self._total_frames_processed = 0
        self._total_processing_time = 0.0
        self._performance_lock = threading.Lock()
        
        # Motion detection state
        self._prev_frame = None
        self._optical_flow_initialized = False
        
        logger.info("QualityScoring initialized",
                   profile=profile.value,
                   target_fps=target_fps,
                   max_workers=self.max_workers,
                   face_integration=enable_face_integration)
    
    def assess_frame_quality(self, 
                           frame: np.ndarray,
                           timestamp: float,
                           frame_index: int,
                           face_results: Optional[FrameFaceDetectionResult] = None) -> FrameQualityResult:
        """
        Assess quality of a single frame
        
        Args:
            frame: Input frame as numpy array (BGR format)
            timestamp: Frame timestamp in seconds
            frame_index: Frame number in sequence
            face_results: Optional face detection results for integration
            
        Returns:
            FrameQualityResult with comprehensive quality assessment
        """
        start_time = time.time()
        
        # Initialize metrics
        metrics = QualityMetrics()
        frame_height, frame_width = frame.shape[:2]
        
        # ENHANCED FIX: Calculate individual quality factors with mandatory validation
        # Each method call is protected to prevent silent failures
        try:
            metrics.face_quality = self._assess_face_quality(frame, face_results)
        except Exception as e:
            logger.warning("Face quality assessment failed", error=str(e), frame_index=frame_index)
            metrics.face_quality = 0.5  # Neutral fallback
            
        try:
            metrics.blur_score = self._assess_blur_quality(frame, metrics)
        except Exception as e:
            logger.warning("Blur quality assessment failed", error=str(e), frame_index=frame_index)
            metrics.blur_score = 0.5  # Neutral fallback
            
        try:
            metrics.exposure_score = self._assess_exposure_quality(frame, metrics)
        except Exception as e:
            logger.warning("Exposure quality assessment failed", error=str(e), frame_index=frame_index)
            metrics.exposure_score = 0.5  # Neutral fallback
            
        try:
            metrics.motion_blur_score = self._assess_motion_quality(frame, metrics)
        except Exception as e:
            logger.warning("Motion quality assessment failed", error=str(e), frame_index=frame_index)
            metrics.motion_blur_score = 0.5  # Neutral fallback
            
        try:
            metrics.composition_score = self._assess_composition_quality(frame, metrics)
        except Exception as e:
            logger.warning("Composition quality assessment failed", error=str(e), frame_index=frame_index)
            metrics.composition_score = 0.5  # Neutral fallback
            
        try:
            metrics.color_quality_score = self._assess_color_quality(frame, metrics)
        except Exception as e:
            logger.warning("Color quality assessment failed", error=str(e), frame_index=frame_index)
            metrics.color_quality_score = 0.5  # Neutral fallback
        
        # Calculate overall quality using profile weights
        overall_quality = self._calculate_weighted_quality(metrics)
        
        # Record processing time
        processing_time = time.time() - start_time
        metrics.processing_time = processing_time
        
        # Update performance tracking
        with self._performance_lock:
            self._total_frames_processed += 1
            self._total_processing_time += processing_time
        
        return FrameQualityResult(
            timestamp=timestamp,
            frame_index=frame_index,
            overall_quality=overall_quality,
            metrics=metrics,
            profile_used=self.profile,
            face_count=len(face_results.faces) if face_results else 0,
            frame_width=frame_width,
            frame_height=frame_height,
            processing_time=processing_time
        )
    
    def _assess_face_quality(self, 
                           frame: np.ndarray,
                           face_results: Optional[FrameFaceDetectionResult]) -> float:
        """
        Assess face quality factor using existing face detection results
        
        Args:
            frame: Input frame
            face_results: Face detection results from existing pipeline
            
        Returns:
            Face quality score (0.0 - 1.0)
        """
        if not self.enable_face_integration or not face_results or not face_results.faces:
            return 0.5  # Neutral score when no faces or face integration disabled
        
        # Calculate weighted face quality based on face size and quality
        total_weight = 0.0
        weighted_quality = 0.0
        
        frame_area = frame.shape[0] * frame.shape[1]
        
        for face in face_results.faces:
            # Use face quality score from existing detection
            face_quality = face.quality_score
            
            # Weight by relative face size (larger faces contribute more)
            face_area = face.bounding_box.area()
            area_weight = min(1.0, face_area * 10)  # Scale factor for weighting
            
            # Bonus for faces with high visibility and good pose
            visibility_bonus = face.visibility * 0.2
            pose_bonus = max(0.0, 1.0 - abs(face.pose_angle) / 45.0) * 0.1
            
            adjusted_quality = face_quality + visibility_bonus + pose_bonus
            adjusted_quality = min(1.0, adjusted_quality)
            
            weighted_quality += adjusted_quality * area_weight
            total_weight += area_weight
        
        if total_weight > 0:
            return weighted_quality / total_weight
        else:
            return 0.5
    
    def _assess_blur_quality(self, frame: np.ndarray, metrics: QualityMetrics) -> float:
        """
        Assess blur quality using Laplacian variance and FFT high-frequency analysis
        
        Mathematical Foundation:
        - Laplacian Variance: Var(∇²I) measures edge sharpness
        - FFT High-Frequency: Ratio of high-frequency to total energy
        - Combined Score: B = α * B_lap + (1-α) * B_fft, where α = 0.7
        
        Args:
            frame: Input frame
            metrics: QualityMetrics object to store detailed results
            
        Returns:
            Blur quality score (0.0 - 1.0, higher = sharper)
        """
        # Convert to grayscale for analysis
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()
        
        # Method 1: Laplacian Variance
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        laplacian_var = laplacian.var()
        
        # Normalize Laplacian variance (typical range: 0-2000+)
        blur_laplacian = min(1.0, laplacian_var / self.blur_threshold)
        metrics.blur_laplacian = blur_laplacian
        
        # Method 2: FFT High-Frequency Content
        # Apply FFT to analyze frequency content
        f_transform = np.fft.fft2(gray)
        f_shift = np.fft.fftshift(f_transform)
        magnitude_spectrum = np.abs(f_shift)
        
        # Define high-frequency region (outer 30% of spectrum)
        h, w = magnitude_spectrum.shape
        center_h, center_w = h // 2, w // 2
        
        # Create masks for high and total frequency regions
        y, x = np.ogrid[:h, :w]
        center_distance = np.sqrt((x - center_w)**2 + (y - center_h)**2)
        max_distance = np.sqrt(center_h**2 + center_w**2)
        
        # High-frequency mask (outer 30%)
        high_freq_mask = center_distance > (max_distance * 0.7)
        
        # Calculate frequency energy ratios
        total_energy = np.sum(magnitude_spectrum**2)
        high_freq_energy = np.sum(magnitude_spectrum[high_freq_mask]**2)
        
        # ENHANCED FIX: Robust division-by-zero protection with edge case handling
        if total_energy > 1e-10:  # Use small epsilon to avoid near-zero division
            blur_fft = high_freq_energy / total_energy
        else:
            # Handle completely black frames or frames with no frequency content
            logger.debug("Zero or near-zero total energy in FFT analysis", 
                        total_energy=total_energy, 
                        high_freq_energy=high_freq_energy)
            blur_fft = 0.5  # Neutral score for edge cases instead of 0.0
            
        # Validate FFT result before normalization
        if not isinstance(blur_fft, (int, float)) or not np.isfinite(blur_fft):
            logger.warning("Invalid FFT blur result", blur_fft=blur_fft)
            blur_fft = 0.5
            
        # Normalize FFT score (typical range: 0-0.3)
        blur_fft = min(1.0, max(0.0, blur_fft * 10))  # Ensure valid range
        metrics.blur_fft = blur_fft
        
        # Combine methods with weighted average
        alpha = 0.7  # Weight factor favoring Laplacian method
        combined_blur_score = alpha * blur_laplacian + (1 - alpha) * blur_fft
        
        return combined_blur_score
    
    def _assess_exposure_quality(self, frame: np.ndarray, metrics: QualityMetrics) -> float:
        """
        Assess exposure quality using histogram analysis, dynamic range, and clipping detection
        
        Mathematical Foundation:
        - Histogram Score: E_hist = 1 - |peak_position - 0.5|
        - Dynamic Range: E_range = (max_luminance - min_luminance) / 255
        - Clipping Detection: E_clip = 1 - (clipped_pixels / total_pixels)
        - Combined: E = 0.4 * E_hist + 0.3 * E_range + 0.3 * E_clip
        
        Args:
            frame: Input frame
            metrics: QualityMetrics object to store detailed results
            
        Returns:
            Exposure quality score (0.0 - 1.0)
        """
        # Convert to grayscale for luminance analysis
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()
        
        # Calculate histogram
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        hist = hist.flatten()
        
        # Method 1: Histogram Analysis
        # Find peak position and evaluate distribution
        peak_bin = np.argmax(hist)
        peak_position = peak_bin / 255.0
        
        # Optimal peak should be around middle (0.4-0.6 range)
        optimal_center = 0.5
        histogram_score = 1.0 - abs(peak_position - optimal_center) * 2
        histogram_score = max(0.0, histogram_score)
        metrics.exposure_histogram = histogram_score
        
        # Method 2: Dynamic Range Analysis
        # Calculate the range of brightness values
        min_val = np.min(gray)
        max_val = np.max(gray)
        dynamic_range = (max_val - min_val) / 255.0
        
        # Good exposure should use most of the available range
        # But penalize if range is too narrow (< 0.3) or too wide with extreme values
        if dynamic_range < 0.3:
            range_score = dynamic_range / 0.3  # Linear scaling for narrow range
        else:
            range_score = 1.0
            
        metrics.exposure_dynamic_range = range_score
        
        # Method 3: Clipping Detection
        # Detect overexposed (>240) and underexposed (<15) pixels
        total_pixels = gray.size
        overexposed = np.sum(gray > 240)
        underexposed = np.sum(gray < 15)
        clipped_pixels = overexposed + underexposed
        
        clipping_ratio = clipped_pixels / total_pixels
        clipping_score = 1.0 - clipping_ratio
        clipping_score = max(0.0, clipping_score)
        metrics.exposure_clipping = clipping_score
        
        # Combine exposure factors
        exposure_score = (
            0.4 * histogram_score +
            0.3 * range_score +
            0.3 * clipping_score
        )
        
        return exposure_score
    
    def _assess_motion_quality(self, frame: np.ndarray, metrics: QualityMetrics) -> float:
        """
        Assess motion blur quality using optical flow and frame difference analysis
        
        Mathematical Foundation:
        - Optical Flow: M_flow = 1 / (1 + mean_optical_flow_magnitude)
        - Frame Difference: M_diff = 1 - normalized_frame_difference
        - Combined: M = 0.6 * M_flow + 0.4 * M_diff
        
        Args:
            frame: Input frame  
            metrics: QualityMetrics object to store detailed results
            
        Returns:
            Motion quality score (0.0 - 1.0, higher = less motion blur)
        """
        # Convert to grayscale
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()
        
        motion_flow_score = 0.5  # Default when no previous frame
        motion_diff_score = 0.5
        
        if self._prev_frame is not None:
            try:
                # Method 1: FIXED - Dense Optical Flow Analysis (replaces incorrect sparse flow)
                # ENHANCED FIX: Check frame size compatibility for multi-video processing
                if (self._optical_flow_initialized and 
                    self._prev_frame.shape == gray.shape):
                    # Use Farneback dense optical flow for accurate motion analysis
                    flow = cv2.calcOpticalFlowFarneback(
                        self._prev_frame, gray, None, 
                        pyr_scale=0.5, levels=3, winsize=15, 
                        iterations=3, poly_n=5, poly_sigma=1.2, flags=0
                    )
                    
                    if flow is not None:
                        # Calculate flow magnitude across the entire frame
                        flow_magnitude = np.sqrt(flow[:, :, 0]**2 + flow[:, :, 1]**2)
                        mean_flow = np.mean(flow_magnitude)
                        
                        # Convert to quality score (less motion = higher quality)
                        # Normalize by typical motion range (0-10 pixels per frame)
                        normalized_motion = min(mean_flow / 10.0, 1.0)
                        motion_flow_score = 1.0 - normalized_motion
                        metrics.motion_optical_flow = motion_flow_score
                    else:
                        # Fallback if flow calculation fails
                        metrics.motion_optical_flow = 0.5
                elif self._prev_frame.shape != gray.shape:
                    # ENHANCED FIX: Reset optical flow state when frame size changes
                    logger.debug("Frame size changed - resetting optical flow", 
                               prev_shape=self._prev_frame.shape, 
                               current_shape=gray.shape)
                    self._optical_flow_initialized = False
                    metrics.motion_optical_flow = 0.5  # Neutral score for size transition
                else:
                    # First frame or optical flow not initialized
                    metrics.motion_optical_flow = 0.5
                
                # Method 2: Frame Difference Analysis (with size compatibility check)
                if self._prev_frame.shape == gray.shape:
                    frame_diff = cv2.absdiff(self._prev_frame, gray)
                    mean_diff = np.mean(frame_diff)
                    
                    # Normalize difference (typical range: 0-50)
                    normalized_diff = mean_diff / 50.0
                    motion_diff_score = 1.0 - min(1.0, normalized_diff)
                    metrics.motion_frame_diff = motion_diff_score
                else:
                    # Different frame sizes - use neutral score
                    metrics.motion_frame_diff = 0.5
                
            except Exception as e:
                # ENHANCED FIX: Provide detailed error handling with fallback scoring
                logger.warning("Motion analysis failed", 
                             error=str(e), 
                             error_type=type(e).__name__,
                             frame_shape=gray.shape if 'gray' in locals() else "unknown",
                             prev_frame_shape=self._prev_frame.shape if self._prev_frame is not None else "unknown")
                
                # Provide reasonable fallback scores instead of leaving them undefined
                if not hasattr(metrics, 'motion_optical_flow') or metrics.motion_optical_flow is None:
                    metrics.motion_optical_flow = 0.5  # Neutral score for optical flow
                    
                if not hasattr(metrics, 'motion_frame_diff') or metrics.motion_frame_diff is None:
                    metrics.motion_frame_diff = 0.5  # Neutral score for frame difference
                    
                logger.info("Applied fallback motion scores", 
                          optical_flow=metrics.motion_optical_flow,
                          frame_diff=metrics.motion_frame_diff)
        
        # Update previous frame for next iteration
        self._prev_frame = gray.copy()
        self._optical_flow_initialized = True
        
        # FIXED: Combine motion assessment methods using metrics values
        # Ensure we use the actual calculated/fallback values from metrics
        combined_motion_score = 0.6 * metrics.motion_optical_flow + 0.4 * metrics.motion_frame_diff
        
        return combined_motion_score
    
    def _assess_composition_quality(self, frame: np.ndarray, metrics: QualityMetrics) -> float:
        """
        Assess composition quality using rule of thirds and center framing analysis
        
        Mathematical Foundation:
        - Rule of Thirds: C_rot = 1 - min_distance_to_thirds_lines
        - Center Framing: C_center = gaussian_weight_from_center  
        - Combined: C = max(C_rot, C_center) * composition_strength
        
        Args:
            frame: Input frame
            metrics: QualityMetrics object to store detailed results
            
        Returns:
            Composition quality score (0.0 - 1.0)
        """
        height, width = frame.shape[:2]
        
        # Convert to grayscale for edge detection
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()
        
        # Find prominent features using edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Find contours to identify main subjects
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            # No prominent features found, return neutral score
            metrics.composition_rule_thirds = 0.5
            metrics.composition_center = 0.5
            return 0.5
        
        # Find the largest contour (assumed to be main subject)
        largest_contour = max(contours, key=cv2.contourArea)
        
        # Get centroid of main subject
        M = cv2.moments(largest_contour)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            # Fallback to frame center
            cx, cy = width // 2, height // 2
        
        # Normalize coordinates (0.0 - 1.0)
        norm_x = cx / width
        norm_y = cy / height
        
        # Method 1: Rule of Thirds Analysis
        # Rule of thirds lines at 1/3 and 2/3 positions
        third_lines_x = [1/3, 2/3]
        third_lines_y = [1/3, 2/3]
        
        # Calculate minimum distance to any rule of thirds line
        min_dist_x = min(abs(norm_x - line) for line in third_lines_x)
        min_dist_y = min(abs(norm_y - line) for line in third_lines_y)
        
        # Combined distance (closer to thirds lines = better composition)
        thirds_distance = math.sqrt(min_dist_x**2 + min_dist_y**2)
        
        # Convert to quality score (closer = higher score)
        # Maximum possible distance is ~0.47, so normalize
        rule_thirds_score = 1.0 - min(1.0, thirds_distance / 0.47)
        metrics.composition_rule_thirds = rule_thirds_score
        
        # Method 2: Center Framing Analysis
        # Calculate distance from center
        center_dist_x = abs(norm_x - 0.5)
        center_dist_y = abs(norm_y - 0.5)
        center_distance = math.sqrt(center_dist_x**2 + center_dist_y**2)
        
        # Apply Gaussian weighting (center gets high score, falls off with distance)
        sigma = 0.3  # Controls falloff rate
        center_score = math.exp(-(center_distance**2) / (2 * sigma**2))
        metrics.composition_center = center_score
        
        # Method 3: Subject Size Analysis
        # Larger subjects can indicate better composition
        contour_area = cv2.contourArea(largest_contour)
        frame_area = width * height
        subject_ratio = contour_area / frame_area
        
        # Optimal subject size is around 10-40% of frame
        if 0.1 <= subject_ratio <= 0.4:
            size_bonus = 1.0
        elif subject_ratio < 0.1:
            size_bonus = subject_ratio / 0.1  # Linear scaling for small subjects
        else:
            size_bonus = max(0.2, 1.0 - (subject_ratio - 0.4) / 0.6)  # Penalize oversized subjects
        
        # Combine composition methods
        # Take the maximum of rule of thirds and center framing (different styles)
        base_composition = max(rule_thirds_score, center_score)
        
        # Apply size bonus and composition strength factor
        final_composition = base_composition * size_bonus * self.composition_strength
        
        # Ensure score doesn't exceed 1.0
        final_composition = min(1.0, final_composition)
        
        return final_composition
    
    def _assess_color_quality(self, frame: np.ndarray, metrics: QualityMetrics) -> float:
        """
        Assess color quality including saturation, contrast, and color balance
        
        Mathematical Foundation:
        - Saturation: K_sat = mean_saturation / optimal_saturation
        - Contrast: K_con = std_deviation_luminance / max_contrast
        - Color Balance: K_bal = 1 - |mean_color_cast|
        - Combined: K = (K_sat + K_con + K_bal) / 3
        
        Args:
            frame: Input frame (BGR format)
            metrics: QualityMetrics object to store detailed results
            
        Returns:
            Color quality score (0.0 - 1.0)
        """
        # Ensure we have a color image
        if len(frame.shape) != 3:
            # Grayscale image - limited color analysis
            metrics.color_saturation = 0.0
            metrics.color_contrast = 0.5
            metrics.color_balance = 0.5
            return 0.3
        
        # Convert to different color spaces for analysis
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        
        # Method 1: Saturation Analysis
        saturation = hsv[:, :, 1]  # S channel in HSV
        mean_saturation = np.mean(saturation) / 255.0
        
        # Optimal saturation is around 0.3-0.7 (not too dull, not oversaturated)
        if 0.3 <= mean_saturation <= 0.7:
            saturation_score = 1.0
        elif mean_saturation < 0.3:
            saturation_score = mean_saturation / 0.3
        else:
            saturation_score = max(0.2, 1.0 - (mean_saturation - 0.7) / 0.3)
        
        metrics.color_saturation = saturation_score
        
        # Method 2: Contrast Analysis
        # Use luminance channel (L in LAB color space)
        luminance = lab[:, :, 0]
        contrast_std = np.std(luminance)
        
        # Normalize contrast (typical range: 0-50)
        normalized_contrast = contrast_std / 50.0
        contrast_score = min(1.0, normalized_contrast)
        metrics.color_contrast = contrast_score
        
        # Method 3: Color Balance Analysis
        # Analyze color cast by examining mean values in LAB space
        a_channel = lab[:, :, 1].astype(np.float32) - 128  # Center around 0
        b_channel = lab[:, :, 2].astype(np.float32) - 128
        
        mean_a = np.mean(a_channel)
        mean_b = np.mean(b_channel) 
        
        # Calculate color cast magnitude
        color_cast_magnitude = math.sqrt(mean_a**2 + mean_b**2)
        
        # Normalize (typical range: 0-50)
        normalized_cast = color_cast_magnitude / 50.0
        color_balance_score = 1.0 - min(1.0, normalized_cast)
        metrics.color_balance = color_balance_score
        
        # Method 4: Color Harmony Analysis (bonus factor)
        # Analyze color distribution for pleasing color combinations
        hue = hsv[:, :, 0]
        hue_hist = cv2.calcHist([hue], [0], None, [36], [0, 180])  # 36 bins for 5-degree intervals
        hue_hist = hue_hist.flatten() / np.sum(hue_hist)  # Normalize
        
        # Calculate entropy (diversity of colors)
        # Higher entropy can indicate more interesting color composition
        hue_entropy = -np.sum(hue_hist * np.log(hue_hist + 1e-10))
        max_entropy = np.log(36)  # Maximum possible entropy
        entropy_score = hue_entropy / max_entropy
        
        # Combine color quality factors
        base_color_score = (saturation_score + contrast_score + color_balance_score) / 3
        
        # Apply entropy bonus (up to 10% improvement)
        color_quality = base_color_score * (1.0 + entropy_score * 0.1)
        color_quality = min(1.0, color_quality)
        
        return color_quality
    
    def _calculate_weighted_quality(self, metrics: QualityMetrics) -> float:
        """
        Calculate final weighted quality score using profile-specific weights
        
        Args:
            metrics: QualityMetrics with individual factor scores
            
        Returns:
            Weighted overall quality score (0-100)
        """
        weights = self.profile_weights[self.profile]
        
        # CRITICAL FIX: Validate individual metric scores before calculation
        def validate_score(score: float, metric_name: str) -> float:
            """Validate and sanitize individual metric scores"""
            if score is None or not isinstance(score, (int, float, np.number)):
                logger.warning(f"Invalid {metric_name} score type", score=score, score_type=type(score))
                return 0.5  # Neutral score for invalid data
                
            if not (0.0 <= score <= 1.0):
                logger.warning(f"Out-of-range {metric_name} score", score=score)
                return max(0.0, min(1.0, score))  # Clamp to valid range
                
            if score == 0.0:
                logger.debug(f"Zero {metric_name} score detected", score=score)
                
            return score
        
        # Validate and sanitize all metric scores
        face_quality = validate_score(metrics.face_quality, "face_quality")
        blur_score = validate_score(metrics.blur_score, "blur_score")
        exposure_score = validate_score(metrics.exposure_score, "exposure_score")
        motion_blur_score = validate_score(metrics.motion_blur_score, "motion_blur_score")
        composition_score = validate_score(metrics.composition_score, "composition_score")
        color_quality_score = validate_score(metrics.color_quality_score, "color_quality_score")
        
        # Calculate weighted sum with validated scores
        weighted_score = (
            face_quality * weights['face_weight'] +
            blur_score * weights['blur_weight'] +
            exposure_score * weights['exposure_weight'] +
            motion_blur_score * weights['motion_weight'] +
            composition_score * weights['composition_weight'] +
            color_quality_score * weights['color_weight']
        )
        
        # Additional validation: ensure weighted score is reasonable
        if weighted_score < 0.0 or weighted_score > 1.0:
            logger.warning("Invalid weighted score calculated", 
                         weighted_score=weighted_score,
                         face_quality=face_quality,
                         blur_score=blur_score,
                         exposure_score=exposure_score,
                         motion_blur_score=motion_blur_score,
                         composition_score=composition_score,
                         color_quality_score=color_quality_score)
            weighted_score = max(0.0, min(1.0, weighted_score))
        
        # Convert to 0-100 scale
        final_score = weighted_score * 100.0
        
        # Final sanity check
        if final_score == 0.0:
            logger.warning("Zero final quality score calculated", 
                         individual_scores={
                             'face': face_quality,
                             'blur': blur_score, 
                             'exposure': exposure_score,
                             'motion': motion_blur_score,
                             'composition': composition_score,
                             'color': color_quality_score
                         })
        
        return final_score
    
    def process_video_quality(self, 
                            video_info: VideoInfo,
                            frame_generator: Iterator[Tuple[np.ndarray, float, int]],
                            face_results_generator: Optional[Iterator[Optional[FrameFaceDetectionResult]]] = None,
                            progress_callback: Optional[callable] = None) -> VideoQualityResult:
        """
        Process entire video for quality assessment with parallel processing optimization
        
        Args:
            video_info: Video information
            frame_generator: Iterator yielding (frame, timestamp, frame_index) tuples
            face_results_generator: Optional iterator for face detection results
            progress_callback: Optional callback for progress updates
            
        Returns:
            VideoQualityResult with comprehensive quality analysis
        """
        logger.info("Starting video quality processing",
                   video_path=str(video_info.file_path),
                   profile=self.profile.value,
                   target_fps=self.target_fps)
        
        # Initialize frame sampler for performance optimization
        video_fps = video_info.primary_video_stream.fps if video_info.primary_video_stream else 30.0
        sampler = self._create_frame_sampler(video_fps)
        
        frame_results = []
        processed_count = 0
        total_frames_seen = 0
        frames_skipped_by_sampler = 0
        
        # Batch processing for efficiency
        batch_size = 4  # Process frames in small batches
        frame_batch = []
        face_batch = []
        
        try:
            # Zip frame and face result generators
            if face_results_generator is not None:
                combined_generator = zip(frame_generator, face_results_generator)
            else:
                combined_generator = zip(frame_generator, [None] * 10000)  # Large number for fallback
            
            logger.debug("Starting frame processing loop", batch_size=batch_size)
            
            for (frame, timestamp, frame_index), face_results in combined_generator:
                total_frames_seen += 1
                
                # Debug: Log first few frames
                if total_frames_seen <= 5:
                    logger.debug("Processing frame", 
                               frame_index=frame_index, 
                               timestamp=f"{timestamp:.2f}s",
                               frame_shape=frame.shape if frame is not None else "None")
                
                # Apply frame sampling for performance
                if not sampler.should_process_frame(frame_index):
                    frames_skipped_by_sampler += 1
                    continue
                
                frame_batch.append((frame, timestamp, frame_index))
                face_batch.append(face_results)
                
                # Process batch when full
                if len(frame_batch) >= batch_size:
                    batch_results = self._process_frame_batch(frame_batch, face_batch)
                    frame_results.extend(batch_results)
                    frame_batch = []
                    face_batch = []
                    
                    processed_count += len(batch_results)
                    
                    # Progress callback
                    if progress_callback:
                        progress_callback(processed_count, timestamp)
            
            # Process remaining frames
            if frame_batch:
                batch_results = self._process_frame_batch(frame_batch, face_batch)
                frame_results.extend(batch_results)
        
        except Exception as e:
            logger.error("Error during video quality processing", error=str(e))
            raise
        
        # CRITICAL FIX: Validate that we processed some frames
        if not frame_results:
            logger.error("No frames were processed by quality scoring", 
                        total_frames_seen=total_frames_seen,
                        frames_skipped_by_sampler=frames_skipped_by_sampler,
                        sampling_interval=sampler.get_processing_interval())
            
            # Create minimal fallback result to prevent 0.0 scores
            fallback_metrics = QualityMetrics()
            fallback_metrics.face_quality = 0.5
            fallback_metrics.blur_score = 0.5  
            fallback_metrics.exposure_score = 0.5
            fallback_metrics.motion_blur_score = 0.5
            fallback_metrics.composition_score = 0.5
            fallback_metrics.color_quality_score = 0.5
            
            frame_results = [(0.0, fallback_metrics)]
            logger.warning("Applied fallback quality metrics due to no frame processing")
        
        # Create processing settings record
        processing_settings = {
            'profile': self.profile.value,
            'target_fps': self.target_fps,
            'frame_skip_interval': sampler.get_processing_interval(),
            'face_integration_enabled': self.enable_face_integration,
            'max_workers': self.max_workers,
            'blur_threshold': self.blur_threshold,
            'motion_threshold': self.motion_threshold,
            'composition_strength': self.composition_strength
        }
        
        result = VideoQualityResult(
            video_info=video_info,
            frame_results=frame_results,
            profile_used=self.profile,
            processing_settings=processing_settings
        )
        
        logger.info("Video quality processing completed",
                   total_frames=len(frame_results),
                   total_frames_seen=total_frames_seen,
                   frames_skipped_by_sampler=frames_skipped_by_sampler,
                   processing_efficiency=f"{len(frame_results)}/{total_frames_seen}" if total_frames_seen > 0 else "0/0",
                   mean_quality=f"{result.mean_quality:.1f}",
                   processing_fps=f"{result.average_fps:.1f}x")
        
        return result
    
    def _create_frame_sampler(self, video_fps: float):
        """Create frame sampler for performance optimization"""
        from ..video.face_detection import FrameSampler, ProcessingMode
        
        # Map quality profile to processing mode
        profile_to_mode = {
            QualityProfile.TALKING_HEAD: ProcessingMode.BALANCED,
            QualityProfile.ACTION: ProcessingMode.QUALITY,
            QualityProfile.LANDSCAPE: ProcessingMode.BALANCED,
            QualityProfile.DOCUMENTARY: ProcessingMode.BALANCED,
            QualityProfile.ADAPTIVE: ProcessingMode.BALANCED
        }
        
        mode = profile_to_mode.get(self.profile, ProcessingMode.BALANCED)
        return FrameSampler(self.target_fps, video_fps, mode)
    
    def _process_frame_batch(self, 
                           frame_batch: List[Tuple[np.ndarray, float, int]],
                           face_batch: List[Optional[FrameFaceDetectionResult]]) -> List[FrameQualityResult]:
        """Process a batch of frames using parallel processing"""
        if len(frame_batch) == 1:
            # Single frame - process directly
            frame, timestamp, frame_index = frame_batch[0]
            face_results = face_batch[0] if face_batch else None
            return [self.assess_frame_quality(frame, timestamp, frame_index, face_results)]
        
        # Multi-threaded batch processing
        results = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(frame_batch))) as executor:
            # Submit all frames for processing
            future_to_frame = {
                executor.submit(
                    self.assess_frame_quality, 
                    frame, timestamp, frame_index, 
                    face_batch[i] if i < len(face_batch) else None
                ): (timestamp, frame_index)
                for i, (frame, timestamp, frame_index) in enumerate(frame_batch)
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
    
    def adaptive_profile_selection(self, 
                                 video_info: VideoInfo,
                                 sample_frames: List[np.ndarray],
                                 face_detection_available: bool = False) -> QualityProfile:
        """
        Automatically select optimal quality profile based on video content analysis
        
        Args:
            video_info: Video information
            sample_frames: Small sample of frames for analysis
            face_detection_available: Whether face detection results are available
            
        Returns:
            Recommended QualityProfile
        """
        if not sample_frames:
            return QualityProfile.ADAPTIVE
        
        # Analyze sample frames to determine content type
        face_presence_score = 0.0
        motion_level_score = 0.0
        composition_complexity = 0.0
        
        for i, frame in enumerate(sample_frames[:10]):  # Analyze up to 10 sample frames
            # Quick face detection if not available from pipeline
            if not face_detection_available:
                face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                face_presence_score += len(faces) / len(sample_frames)
            
            # Analyze motion (using frame differences)
            if i > 0:
                prev_gray = cv2.cvtColor(sample_frames[i-1], cv2.COLOR_BGR2GRAY)
                curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frame_diff = cv2.absdiff(prev_gray, curr_gray)
                motion_level_score += np.mean(frame_diff) / 255.0
            
            # Analyze composition complexity
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            composition_complexity += edge_density
        
        # Normalize scores
        motion_level_score /= max(1, len(sample_frames) - 1)
        composition_complexity /= len(sample_frames)
        
        # Select profile based on content characteristics
        if face_presence_score > 0.5:  # Strong face presence
            if motion_level_score < 0.1:  # Low motion
                return QualityProfile.TALKING_HEAD
            else:
                return QualityProfile.DOCUMENTARY
        elif motion_level_score > 0.3:  # High motion content
            return QualityProfile.ACTION
        elif composition_complexity > 0.2:  # Complex composition
            return QualityProfile.LANDSCAPE
        else:
            return QualityProfile.ADAPTIVE
    
    def export_quality_timeline(self, 
                              result: VideoQualityResult,
                              output_path: Union[str, Path],
                              format: str = 'json') -> None:
        """
        Export quality timeline to various formats
        
        Args:
            result: VideoQualityResult to export
            output_path: Path to save the exported timeline
            format: Export format ('json', 'csv', 'xml')
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format.lower() == 'json':
            import json
            with open(output_path, 'w') as f:
                json.dump(result.to_dict(), f, indent=2)
        
        elif format.lower() == 'csv':
            import csv
            with open(output_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'frame_index', 'overall_quality',
                    'face_quality', 'blur_score', 'exposure_score', 
                    'motion_score', 'composition_score', 'color_score'
                ])
                for frame_result in result.frame_results:
                    m = frame_result.metrics
                    writer.writerow([
                        frame_result.timestamp, frame_result.frame_index, frame_result.overall_quality,
                        m.face_quality, m.blur_score, m.exposure_score,
                        m.motion_blur_score, m.composition_score, m.color_quality_score
                    ])
        
        elif format.lower() == 'xml':
            import xml.etree.ElementTree as ET
            root = ET.Element('VideoQualityAnalysis')
            
            # Add metadata
            metadata = ET.SubElement(root, 'Metadata')
            ET.SubElement(metadata, 'VideoPath').text = str(result.video_info.file_path)
            ET.SubElement(metadata, 'Profile').text = result.profile_used.value
            ET.SubElement(metadata, 'MeanQuality').text = str(result.mean_quality)
            
            # Add frame results
            frames = ET.SubElement(root, 'Frames')
            for frame_result in result.frame_results:
                frame_elem = ET.SubElement(frames, 'Frame')
                frame_elem.set('timestamp', str(frame_result.timestamp))
                frame_elem.set('index', str(frame_result.frame_index))
                frame_elem.set('quality', str(frame_result.overall_quality))
                
                # Add detailed metrics
                metrics_elem = ET.SubElement(frame_elem, 'Metrics')
                m = frame_result.metrics
                for metric_name, value in m.to_dict().items():
                    if isinstance(value, (int, float)):
                        ET.SubElement(metrics_elem, metric_name).text = str(value)
            
            tree = ET.ElementTree(root)
            tree.write(output_path, encoding='utf-8', xml_declaration=True)
        
        logger.info("Quality timeline exported", 
                   output_path=str(output_path), 
                   format=format,
                   frame_count=len(result.frame_results))
    
    def get_quality_hotspots(self, 
                           result: VideoQualityResult,
                           top_percent: float = 10.0) -> List[Tuple[float, float, float]]:
        """
        Identify quality hotspots (highest quality segments) in the video
        
        Args:
            result: VideoQualityResult to analyze
            top_percent: Percentage of top quality frames to include
            
        Returns:
            List of (start_time, end_time, avg_quality) tuples for hotspots
        """
        if not result.frame_results:
            return []
        
        # Sort frames by quality
        sorted_frames = sorted(result.frame_results, key=lambda r: r.overall_quality, reverse=True)
        
        # Take top percentage
        top_count = max(1, int(len(sorted_frames) * top_percent / 100.0))
        top_frames = sorted_frames[:top_count]
        
        # Sort top frames by timestamp
        top_frames.sort(key=lambda r: r.timestamp)
        
        # Group consecutive high-quality frames into segments
        segments = []
        current_start = None
        current_end = None
        current_qualities = []
        gap_threshold = 2.0  # Maximum gap between frames in seconds
        
        for frame in top_frames:
            if current_start is None:
                current_start = frame.timestamp
                current_end = frame.timestamp
                current_qualities = [frame.overall_quality]
            elif frame.timestamp - current_end <= gap_threshold:
                current_end = frame.timestamp
                current_qualities.append(frame.overall_quality)
            else:
                # Gap too large, finish current segment and start new one
                avg_quality = np.mean(current_qualities)
                segments.append((current_start, current_end, avg_quality))
                
                current_start = frame.timestamp
                current_end = frame.timestamp
                current_qualities = [frame.overall_quality]
        
        # Add final segment
        if current_start is not None:
            avg_quality = np.mean(current_qualities)
            segments.append((current_start, current_end, avg_quality))
        
        logger.info("Quality hotspots identified",
                   segment_count=len(segments),
                   top_percent=top_percent)
        
        return segments
    
    def get_performance_stats(self) -> Dict[str, Any]:
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
                'profile': self.profile.value,
                'face_integration_enabled': self.enable_face_integration,
                'max_workers': self.max_workers
            }


# Factory functions for easy creation

def create_quality_scorer(video_info: VideoInfo,
                        target_realtime_multiple: float = 15.0,
                        content_type: Optional[str] = None) -> QualityScoring:
    """
    Create optimized quality scorer for given video
    
    Args:
        video_info: Video information for optimization
        target_realtime_multiple: Target processing speed multiplier (15x = 15x real-time)
        content_type: Content type hint ('talking_head', 'action', 'landscape', 'documentary')
        
    Returns:
        Configured QualityScoring instance
    """
    # Determine optimal profile
    if content_type:
        profile_mapping = {
            'talking_head': QualityProfile.TALKING_HEAD,
            'action': QualityProfile.ACTION,
            'landscape': QualityProfile.LANDSCAPE,
            'documentary': QualityProfile.DOCUMENTARY
        }
        profile = profile_mapping.get(content_type.lower(), QualityProfile.ADAPTIVE)
    else:
        profile = QualityProfile.ADAPTIVE
    
    # Calculate target FPS based on video properties
    video_fps = video_info.primary_video_stream.fps if video_info.primary_video_stream else 30.0
    target_fps = min(video_fps, video_fps / target_realtime_multiple)
    
    logger.info("Creating optimized quality scorer",
               video_resolution=f"{video_info.resolution[0]}x{video_info.resolution[1]}",
               video_fps=video_fps,
               target_fps=target_fps,
               profile=profile.value,
               content_type=content_type)
    
    return QualityScoring(
        profile=profile,
        target_fps=target_fps,
        enable_face_integration=True
    )


def create_video_frame_generator_with_quality(video_path: Union[str, Path]) -> Iterator[Tuple[np.ndarray, float, int]]:
    """
    Create a generator for video frames optimized for quality analysis
    
    Args:
        video_path: Path to video file
        
    Yields:
        Tuple of (frame, timestamp, frame_index)
    """
    # This reuses the existing frame generator from face detection
    from ..video.face_detection import create_video_frame_generator
    return create_video_frame_generator(video_path)
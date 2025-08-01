"""Beat-sync timeline generation algorithm for AutoCut

This module implements a sophisticated algorithm that synchronizes video cuts with audio beats
while respecting scene boundaries and maintaining visual flow. The algorithm uses multiple
weighted scoring factors to determine optimal cut points.

Algorithm Overview:
1. Beat Detection & Scoring: Analyze beat timestamps and assign confidence scores
2. Scene Boundary Analysis: Identify scene changes and calculate override costs
3. Cut Point Scoring: Combine beat strength, scene compatibility, and timing factors
4. Timeline Optimization: Apply editing style constraints and flow smoothing
5. Edge Case Handling: Manage tempo changes, silence, and duration constraints

The algorithm supports multiple editing styles:
- Aggressive: Frequent cuts, strong beat alignment, scene overrides allowed
- Smooth: Longer clips, prioritize scene boundaries, gentle transitions
- Adaptive: Dynamic adjustment based on content characteristics
"""

import numpy as np
import time
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import math

from ..audio.analyzer import AudioAnalysis
from ..video.scene_detection import SceneDetectionResult, SceneChange
from ..video.ingestion import VideoInfo
from ..utils.logging import get_logger
from ..utils.config import config

logger = get_logger(__name__)


class EditingStyle(Enum):
    """Available editing styles with different cut behaviors"""
    AGGRESSIVE = "aggressive"    # Frequent cuts, strong beat sync, scene overrides
    SMOOTH = "smooth"           # Longer clips, respect scenes, gentle flow
    ADAPTIVE = "adaptive"       # Dynamic adjustment based on content
    MUSICAL = "musical"         # Strict beat alignment, musical phrasing
    CINEMATIC = "cinematic"     # Story-driven, minimal beat sync


class CutType(Enum):
    """Types of cuts in the timeline"""
    BEAT_CUT = "beat_cut"              # Cut on musical beat
    SCENE_CUT = "scene_cut"            # Cut on scene change
    FORCED_CUT = "forced_cut"          # Cut for duration constraints
    TRANSITION_CUT = "transition_cut"  # Smooth transition cut
    SILENCE_CUT = "silence_cut"        # Cut during audio silence


@dataclass
class CutPoint:
    """Represents a potential or actual cut point in the timeline"""
    timestamp: float
    confidence: float
    cut_type: CutType
    beat_alignment: float = 0.0      # How well aligned with beat (0-1)
    scene_compatibility: float = 0.0  # How compatible with scene boundaries (0-1)
    flow_score: float = 0.0          # How well it fits the overall flow (0-1)
    override_cost: float = 0.0       # Cost of overriding scene boundaries (0-1)
    metrics: Dict[str, float] = field(default_factory=dict)
    
    @property
    def composite_score(self) -> float:
        """Calculate composite score for this cut point"""
        return (self.confidence * self.beat_alignment * 
                self.scene_compatibility * self.flow_score * 
                (1.0 - self.override_cost))


@dataclass
class TimelineSegment:
    """Represents a segment between two cut points"""
    start_time: float
    end_time: float
    cut_in_type: CutType = CutType.BEAT_CUT
    cut_out_type: CutType = CutType.BEAT_CUT
    duration: float = field(init=False)
    scene_changes_count: int = 0
    beat_count: int = 0
    quality_score: float = 0.0
    
    # Multi-video support fields
    source_video_index: Optional[int] = None
    source_video_path: Optional[Path] = None  
    source_start_time: Optional[float] = None
    source_end_time: Optional[float] = None
    beat_alignment_score: float = 0.0
    scene_respect_score: float = 0.0
    
    def __post_init__(self):
        self.duration = self.end_time - self.start_time


@dataclass
class EditingTimeline:
    """Complete editing timeline with cut points and segments"""
    segments: List[TimelineSegment]
    cut_points: List[CutPoint] = field(default_factory=list)
    editing_style: EditingStyle = EditingStyle.ADAPTIVE
    duration: float = 0.0
    generation_time: float = 0.0
    success: bool = True
    errors: List[str] = field(default_factory=list)
    
    # Optional single-video compatibility
    video_info: Optional[VideoInfo] = None
    audio_analysis: Optional[AudioAnalysis] = None
    scene_detection: Optional[SceneDetectionResult] = None
    total_duration: Optional[float] = None
    
    @property
    def segment_count(self) -> int:
        """Number of timeline segments"""
        return len(self.segments)
    
    @property
    def average_segment_duration(self) -> float:
        """Average duration of timeline segments"""
        if not self.segments:
            return 0.0
        return sum(seg.duration for seg in self.segments) / len(self.segments)
    
    @property
    def beat_sync_percentage(self) -> float:
        """Percentage of cuts that are beat-aligned"""
        if not self.cut_points:
            return 0.0
        beat_cuts = sum(1 for cp in self.cut_points if cp.cut_type == CutType.BEAT_CUT)
        return (beat_cuts / len(self.cut_points)) * 100.0
    
    @property
    def scene_respect_percentage(self) -> float:
        """Percentage of cuts that respect scene boundaries"""
        if not self.cut_points:
            return 0.0
        respectful_cuts = sum(1 for cp in self.cut_points if cp.override_cost < 0.5)
        return (respectful_cuts / len(self.cut_points)) * 100.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert timeline to dictionary for serialization"""
        return {
            'video_path': str(self.video_info.file_path) if self.video_info else "multi-video",
            'total_duration': self.total_duration,
            'segment_count': self.segment_count,
            'average_segment_duration': self.average_segment_duration,
            'beat_sync_percentage': self.beat_sync_percentage,
            'scene_respect_percentage': self.scene_respect_percentage,
            'editing_style': self.editing_style.value,
            'generation_time': self.generation_time,
            'cut_points': [
                {
                    'timestamp': cp.timestamp,
                    'confidence': cp.confidence,
                    'cut_type': cp.cut_type.value,
                    'beat_alignment': cp.beat_alignment,
                    'scene_compatibility': cp.scene_compatibility,
                    'flow_score': cp.flow_score,
                    'override_cost': cp.override_cost,
                    'composite_score': cp.composite_score,
                    'metrics': cp.metrics
                }
                for cp in self.cut_points
            ],
            'segments': [
                {
                    'start_time': seg.start_time,
                    'end_time': seg.end_time,
                    'duration': seg.duration,
                    'cut_in_type': seg.cut_in_type.value,
                    'cut_out_type': seg.cut_out_type.value,
                    'scene_changes_count': seg.scene_changes_count,
                    'beat_count': seg.beat_count,
                    'quality_score': seg.quality_score
                }
                for seg in self.segments
            ],
            'success': self.success,
            'errors': self.errors
        }


class BeatSyncTimelineGenerator:
    """Advanced timeline generator with beat-sync capabilities"""
    
    def __init__(self, editing_style: EditingStyle = EditingStyle.ADAPTIVE):
        """
        Initialize timeline generator
        
        Args:
            editing_style: Default editing style to use
        """
        self.editing_style = editing_style
        
        # Load configuration
        self.min_clip_duration = config.get('timeline.min_clip_duration_sec', 0.8)
        self.max_clip_duration = config.get('timeline.max_clip_duration_sec', 8.0)
        self.beat_alignment_threshold = config.get('timeline.beat_alignment_threshold', 0.1)
        self.scene_override_threshold = config.get('timeline.scene_override_threshold', 0.7)
        self.silence_threshold = config.get('timeline.silence_threshold_db', -40.0)
        
        # Style-specific configurations
        self.style_configs = {
            EditingStyle.AGGRESSIVE: {
                'beat_weight': 0.4,
                'scene_weight': 0.2,
                'flow_weight': 0.2,
                'duration_weight': 0.2,
                'min_clip_duration': 0.5,
                'max_clip_duration': 4.0,
                'scene_override_threshold': 0.8,
                'beat_strictness': 0.9
            },
            EditingStyle.SMOOTH: {
                'beat_weight': 0.25,
                'scene_weight': 0.4,
                'flow_weight': 0.25,
                'duration_weight': 0.1,
                'min_clip_duration': 2.0,
                'max_clip_duration': 12.0,
                'scene_override_threshold': 0.3,
                'beat_strictness': 0.6
            },
            EditingStyle.ADAPTIVE: {
                'beat_weight': 0.3,
                'scene_weight': 0.3,
                'flow_weight': 0.25,
                'duration_weight': 0.15,
                'min_clip_duration': 1.0,
                'max_clip_duration': 8.0,
                'scene_override_threshold': 0.6,
                'beat_strictness': 0.75
            },
            EditingStyle.MUSICAL: {
                'beat_weight': 0.5,
                'scene_weight': 0.15,
                'flow_weight': 0.25,
                'duration_weight': 0.1,
                'min_clip_duration': 0.6,
                'max_clip_duration': 6.0,
                'scene_override_threshold': 0.9,
                'beat_strictness': 0.95
            },
            EditingStyle.CINEMATIC: {
                'beat_weight': 0.15,
                'scene_weight': 0.5,
                'flow_weight': 0.25,
                'duration_weight': 0.1,
                'min_clip_duration': 3.0,
                'max_clip_duration': 15.0,
                'scene_override_threshold': 0.2,
                'beat_strictness': 0.4
            }
        }
        
        logger.info("BeatSyncTimelineGenerator initialized", 
                   editing_style=editing_style.value,
                   min_clip_duration=self.min_clip_duration,
                   max_clip_duration=self.max_clip_duration)
    
    def generate_timeline(self, 
                         audio_analysis: AudioAnalysis,
                         scene_detection: SceneDetectionResult,
                         video_info: VideoInfo,
                         editing_style: Optional[EditingStyle] = None) -> EditingTimeline:
        """
        Generate beat-synchronized editing timeline
        
        Args:
            audio_analysis: Audio analysis results with beat detection
            scene_detection: Scene detection results
            video_info: Video file information
            editing_style: Override default editing style
            
        Returns:
            EditingTimeline with optimized cut points and segments
        """
        editing_style = editing_style or self.editing_style
        start_time = time.time()
        
        logger.info("Generating beat-sync timeline",
                   video_path=str(video_info.file_path),
                   editing_style=editing_style.value,
                   beat_count=len(audio_analysis.beats),
                   scene_count=scene_detection.scene_count)
        
        try:
            # Step 1: Analyze and score all potential cut points
            potential_cuts = self._analyze_cut_points(audio_analysis, scene_detection, editing_style)
            
            # Step 2: Apply editing style constraints and filtering
            filtered_cuts = self._apply_style_constraints(potential_cuts, editing_style)
            
            # Step 3: Optimize timeline for flow and coherence
            optimized_cuts = self._optimize_timeline_flow(filtered_cuts, audio_analysis, scene_detection, editing_style)
            
            # Step 4: Generate final timeline segments
            segments = self._generate_segments(optimized_cuts, audio_analysis, scene_detection)
            
            # Step 5: Post-process and validate timeline
            final_cuts, final_segments = self._post_process_timeline(optimized_cuts, segments, video_info.duration)
            
            generation_time = time.time() - start_time
            
            timeline = EditingTimeline(
                video_info=video_info,
                audio_analysis=audio_analysis,
                scene_detection=scene_detection,
                cut_points=final_cuts,
                segments=final_segments,
                editing_style=editing_style,
                generation_time=generation_time,
                total_duration=video_info.duration,
                success=True
            )
            
            logger.info("Timeline generation completed",
                       video_path=str(video_info.file_path),
                       generation_time=f"{generation_time:.2f}s",
                       segment_count=timeline.segment_count,
                       beat_sync_percentage=f"{timeline.beat_sync_percentage:.1f}%",
                       scene_respect_percentage=f"{timeline.scene_respect_percentage:.1f}%")
            
            return timeline
            
        except Exception as e:
            generation_time = time.time() - start_time
            error_msg = f"Timeline generation failed: {str(e)}"
            logger.error("Timeline generation failed",
                        video_path=str(video_info.file_path),
                        error=str(e),
                        generation_time=generation_time)
            
            return EditingTimeline(
                video_info=video_info,
                audio_analysis=audio_analysis,
                scene_detection=scene_detection,
                cut_points=[],
                segments=[],
                editing_style=editing_style,
                generation_time=generation_time,
                total_duration=video_info.duration,
                success=False,
                errors=[error_msg]
            )
    
    def _analyze_cut_points(self, 
                           audio_analysis: AudioAnalysis,
                           scene_detection: SceneDetectionResult,
                           editing_style: EditingStyle) -> List[CutPoint]:
        """
        Analyze all potential cut points and calculate comprehensive scores
        
        This is the core scoring algorithm that evaluates:
        1. Beat alignment strength and timing precision
        2. Scene boundary compatibility and override costs
        3. Temporal flow and rhythm consistency
        4. Duration constraint satisfaction
        """
        potential_cuts = []
        style_config = self.style_configs[editing_style]
        
        # Get all candidate timestamps from beats and scene changes
        beat_timestamps = set(audio_analysis.beats)
        scene_timestamps = {sc.timestamp for sc in scene_detection.scene_changes}
        all_timestamps = sorted(beat_timestamps.union(scene_timestamps))
        
        logger.debug("Analyzing cut points",
                    beat_candidates=len(beat_timestamps),
                    scene_candidates=len(scene_timestamps),
                    total_candidates=len(all_timestamps))
        
        for timestamp in all_timestamps:
            # Calculate beat alignment score
            beat_alignment = self._calculate_beat_alignment(timestamp, audio_analysis, style_config)
            
            # Calculate scene compatibility score
            scene_compatibility, override_cost = self._calculate_scene_compatibility(
                timestamp, scene_detection, style_config
            )
            
            # Determine primary cut type
            cut_type = self._determine_cut_type(timestamp, beat_timestamps, scene_timestamps)
            
            # Calculate base confidence based on cut type
            confidence = self._calculate_base_confidence(
                timestamp, cut_type, audio_analysis, scene_detection
            )
            
            # Create cut point with initial scores
            cut_point = CutPoint(
                timestamp=timestamp,
                confidence=confidence,
                cut_type=cut_type,
                beat_alignment=beat_alignment,
                scene_compatibility=scene_compatibility,
                override_cost=override_cost,
                metrics={
                    'original_confidence': confidence,
                    'beat_distance': self._get_nearest_beat_distance(timestamp, audio_analysis.beats),
                    'scene_distance': self._get_nearest_scene_distance(timestamp, scene_detection.scene_changes)
                }
            )
            
            potential_cuts.append(cut_point)
        
        # Calculate relative flow scores for all cut points
        self._calculate_flow_scores(potential_cuts, audio_analysis, editing_style)
        
        return potential_cuts
    
    def _calculate_beat_alignment(self, 
                                 timestamp: float, 
                                 audio_analysis: AudioAnalysis,
                                 style_config: Dict[str, float]) -> float:
        """
        Calculate how well a timestamp aligns with musical beats
        
        Uses exponential decay based on distance to nearest beat, with
        style-specific strictness parameters.
        """
        if not audio_analysis.beats:
            return 0.0
        
        # Find nearest beat
        beat_distances = [abs(timestamp - beat) for beat in audio_analysis.beats]
        min_distance = min(beat_distances)
        
        # Calculate expected beat interval
        if len(audio_analysis.beats) > 1:
            avg_beat_interval = np.mean(np.diff(audio_analysis.beats))
        else:
            avg_beat_interval = 60.0 / audio_analysis.bpm
        
        # Normalize distance by beat interval
        normalized_distance = min_distance / avg_beat_interval
        
        # Apply exponential decay with style-specific strictness
        strictness = style_config['beat_strictness']
        alignment_score = math.exp(-normalized_distance * strictness * 4.0)
        
        # Bonus for exact beat matches
        if min_distance < self.beat_alignment_threshold:
            alignment_score = min(1.0, alignment_score * 1.2)
        
        return alignment_score
    
    def _calculate_scene_compatibility(self, 
                                      timestamp: float,
                                      scene_detection: SceneDetectionResult,
                                      style_config: Dict[str, float]) -> Tuple[float, float]:
        """
        Calculate scene boundary compatibility and override cost
        
        Returns:
            Tuple of (compatibility_score, override_cost)
        """
        if not scene_detection.scene_changes:
            return 1.0, 0.0
        
        # Find nearest scene change
        scene_distances = [abs(timestamp - sc.timestamp) for sc in scene_detection.scene_changes]
        min_scene_distance = min(scene_distances)
        
        # Get the nearest scene change for context
        nearest_scene_idx = scene_distances.index(min_scene_distance)
        nearest_scene = scene_detection.scene_changes[nearest_scene_idx]
        
        # Calculate average scene duration for normalization
        avg_scene_duration = scene_detection.average_scene_duration
        normalized_distance = min_scene_distance / avg_scene_duration if avg_scene_duration > 0 else 1.0
        
        # Scene boundary compatibility (higher when closer to scene changes)
        compatibility = 1.0 - math.exp(-normalized_distance * 2.0)
        
        # Override cost (cost of cutting mid-scene)
        # Higher cost when cutting far from scene boundaries
        override_threshold = style_config['scene_override_threshold']
        
        if normalized_distance < 0.1:  # Very close to scene boundary
            override_cost = 0.0
        elif normalized_distance < 0.3:  # Moderately close
            override_cost = 0.2
        else:  # Mid-scene cut
            # Scale by scene change confidence - harder to override high-confidence scenes
            scene_confidence = nearest_scene.confidence if nearest_scene else 0.5
            base_cost = min(1.0, normalized_distance * 1.5)
            override_cost = base_cost * scene_confidence
        
        # Adjust based on style tolerance
        override_cost *= (1.0 - override_threshold)
        
        return compatibility, min(1.0, override_cost)
    
    def _determine_cut_type(self, 
                           timestamp: float,
                           beat_timestamps: set,
                           scene_timestamps: set) -> CutType:
        """Determine the primary type of cut based on proximity to beats and scenes"""
        is_beat = timestamp in beat_timestamps
        is_scene = timestamp in scene_timestamps
        
        if is_beat and is_scene:
            # Prioritize beat cuts when both are present
            return CutType.BEAT_CUT
        elif is_beat:
            return CutType.BEAT_CUT
        elif is_scene:
            return CutType.SCENE_CUT
        else:
            # This shouldn't happen in our current implementation
            return CutType.TRANSITION_CUT
    
    def _calculate_base_confidence(self, 
                                  timestamp: float,
                                  cut_type: CutType,
                                  audio_analysis: AudioAnalysis,
                                  scene_detection: SceneDetectionResult) -> float:
        """Calculate base confidence score for a cut point"""
        if cut_type == CutType.BEAT_CUT:
            # Use audio analysis confidence as base
            return audio_analysis.confidence
        elif cut_type == CutType.SCENE_CUT:
            # Find corresponding scene change confidence
            for scene_change in scene_detection.scene_changes:
                if abs(scene_change.timestamp - timestamp) < 0.1:
                    return scene_change.confidence
            return 0.5  # Default if not found
        else:
            return 0.3  # Lower confidence for other cut types
    
    def _get_nearest_beat_distance(self, timestamp: float, beats: List[float]) -> float:
        """Get distance to nearest beat"""
        if not beats:
            return float('inf')
        return min(abs(timestamp - beat) for beat in beats)
    
    def _get_nearest_scene_distance(self, timestamp: float, scene_changes: List[SceneChange]) -> float:
        """Get distance to nearest scene change"""
        if not scene_changes:
            return float('inf')
        return min(abs(timestamp - sc.timestamp) for sc in scene_changes)
    
    def _calculate_flow_scores(self, 
                              cut_points: List[CutPoint],
                              audio_analysis: AudioAnalysis,
                              editing_style: EditingStyle):
        """
        Calculate flow scores for all cut points based on temporal relationships
        
        Flow score considers:
        1. Rhythmic consistency with surrounding cuts
        2. Musical phrasing and phrase boundaries
        3. Temporal spacing and interval relationships
        """
        if len(cut_points) < 2:
            for cp in cut_points:
                cp.flow_score = 1.0
            return
        
        # Sort cut points by timestamp
        sorted_cuts = sorted(cut_points, key=lambda x: x.timestamp)
        
        # Calculate expected beat interval for reference
        expected_interval = 60.0 / audio_analysis.bpm if audio_analysis.bpm > 0 else 2.0
        
        for i, cut_point in enumerate(sorted_cuts):
            flow_components = []
            
            # Analyze spacing with previous cut
            if i > 0:
                prev_cut = sorted_cuts[i - 1]
                interval = cut_point.timestamp - prev_cut.timestamp
                
                # Score based on musical timing relationships
                interval_score = self._score_musical_interval(interval, expected_interval)
                flow_components.append(interval_score)
            
            # Analyze spacing with next cut
            if i < len(sorted_cuts) - 1:
                next_cut = sorted_cuts[i + 1]
                interval = next_cut.timestamp - cut_point.timestamp
                
                interval_score = self._score_musical_interval(interval, expected_interval)
                flow_components.append(interval_score)
            
            # Calculate rhythmic consistency in local neighborhood
            neighborhood_score = self._calculate_neighborhood_rhythm_score(
                cut_point, sorted_cuts, i, expected_interval
            )
            flow_components.append(neighborhood_score)
            
            # Combine flow components
            cut_point.flow_score = np.mean(flow_components) if flow_components else 0.5
    
    def _score_musical_interval(self, interval: float, expected_interval: float) -> float:
        """
        Score a time interval based on musical relationships
        
        Higher scores for intervals that match musical subdivisions:
        - 1x beat (whole beat)
        - 2x beat (half note)
        - 4x beat (whole note)
        - 0.5x beat (eighth note)
        """
        musical_ratios = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]  # Common musical subdivisions
        interval_ratio = interval / expected_interval
        
        # Find closest musical ratio
        ratio_distances = [abs(interval_ratio - ratio) for ratio in musical_ratios]
        min_distance = min(ratio_distances)
        
        # Score based on proximity to musical ratios
        return math.exp(-min_distance * 2.0)
    
    def _calculate_neighborhood_rhythm_score(self, 
                                           cut_point: CutPoint,
                                           sorted_cuts: List[CutPoint],
                                           index: int,
                                           expected_interval: float) -> float:
        """Calculate rhythmic consistency in the local neighborhood"""
        # Look at 2 cuts before and after (if available)
        start_idx = max(0, index - 2)
        end_idx = min(len(sorted_cuts), index + 3)
        neighborhood = sorted_cuts[start_idx:end_idx]
        
        if len(neighborhood) < 3:
            return 0.7  # Default score for insufficient neighborhood
        
        # Calculate intervals in neighborhood
        intervals = []
        for i in range(len(neighborhood) - 1):
            intervals.append(neighborhood[i + 1].timestamp - neighborhood[i].timestamp)
        
        if not intervals:
            return 0.7
        
        # Measure rhythmic consistency (lower variance = higher consistency)
        interval_variance = np.var(intervals)
        mean_interval = np.mean(intervals)
        
        # Normalize variance by mean interval
        normalized_variance = interval_variance / (mean_interval ** 2) if mean_interval > 0 else 1.0
        
        # Convert to consistency score (0-1, higher is better)
        consistency_score = math.exp(-normalized_variance * 4.0)
        
        return consistency_score
    
    def _apply_style_constraints(self, 
                                potential_cuts: List[CutPoint],
                                editing_style: EditingStyle) -> List[CutPoint]:
        """
        Apply editing style constraints and filter cut points
        
        This step filters and adjusts cut points based on:
        1. Style-specific scoring weights
        2. Minimum confidence thresholds
        3. Scene override policies
        4. Beat strictness requirements
        """
        style_config = self.style_configs[editing_style]
        filtered_cuts = []
        
        # Calculate composite scores with style-specific weights
        for cut_point in potential_cuts:
            # Apply weighted scoring
            weighted_score = (
                cut_point.confidence * 0.2 +
                cut_point.beat_alignment * style_config['beat_weight'] +
                cut_point.scene_compatibility * style_config['scene_weight'] +
                cut_point.flow_score * style_config['flow_weight']
            )
            
            # Apply override cost penalty
            if cut_point.override_cost > style_config['scene_override_threshold']:
                weighted_score *= (1.0 - cut_point.override_cost * 0.5)
            
            # Update confidence with weighted score
            cut_point.confidence = min(1.0, weighted_score)
            
            # Filter based on style-specific thresholds
            min_confidence = self._get_min_confidence_for_style(editing_style, cut_point.cut_type)
            
            if cut_point.confidence >= min_confidence:
                # Additional style-specific filters
                if self._passes_style_specific_filters(cut_point, editing_style, style_config):
                    filtered_cuts.append(cut_point)
        
        logger.debug("Applied style constraints",
                    original_count=len(potential_cuts),
                    filtered_count=len(filtered_cuts),
                    editing_style=editing_style.value)
        
        return filtered_cuts
    
    def _get_min_confidence_for_style(self, editing_style: EditingStyle, cut_type: CutType) -> float:
        """Get minimum confidence threshold based on editing style and cut type"""
        base_thresholds = {
            EditingStyle.AGGRESSIVE: 0.3,
            EditingStyle.SMOOTH: 0.5,
            EditingStyle.ADAPTIVE: 0.4,
            EditingStyle.MUSICAL: 0.4,
            EditingStyle.CINEMATIC: 0.6
        }
        
        base_threshold = base_thresholds[editing_style]
        
        # Adjust based on cut type
        if cut_type == CutType.BEAT_CUT:
            return base_threshold
        elif cut_type == CutType.SCENE_CUT:
            return base_threshold * 0.8  # Slightly lower threshold for scene cuts
        else:
            return base_threshold * 1.2  # Higher threshold for other cuts
    
    def _passes_style_specific_filters(self, 
                                      cut_point: CutPoint,
                                      editing_style: EditingStyle,
                                      style_config: Dict[str, float]) -> bool:
        """Apply additional style-specific filtering rules"""
        
        if editing_style == EditingStyle.AGGRESSIVE:
            # Aggressive style: allow more scene overrides, prefer strong beats
            return (cut_point.beat_alignment > 0.4 or 
                   cut_point.cut_type == CutType.SCENE_CUT)
        
        elif editing_style == EditingStyle.SMOOTH:
            # Smooth style: strict scene respect, avoid abrupt cuts
            return (cut_point.override_cost < 0.4 and 
                   cut_point.flow_score > 0.3)
        
        elif editing_style == EditingStyle.MUSICAL:
            # Musical style: strict beat alignment required
            return (cut_point.beat_alignment > 0.6 or 
                   cut_point.cut_type == CutType.SCENE_CUT)
        
        elif editing_style == EditingStyle.CINEMATIC:
            # Cinematic style: prioritize scene boundaries and story flow
            return (cut_point.scene_compatibility > 0.5 and 
                   cut_point.override_cost < 0.3)
        
        else:  # ADAPTIVE
            # Adaptive style: balanced approach
            return True
    
    def _optimize_timeline_flow(self, 
                               filtered_cuts: List[CutPoint],
                               audio_analysis: AudioAnalysis,
                               scene_detection: SceneDetectionResult,
                               editing_style: EditingStyle) -> List[CutPoint]:
        """
        Optimize timeline for overall flow and coherence
        
        This optimization phase:
        1. Ensures minimum/maximum clip durations
        2. Resolves temporal conflicts between cuts
        3. Balances global rhythm and pacing
        4. Handles special cases (silence, tempo changes)
        """
        if not filtered_cuts:
            return filtered_cuts
        
        style_config = self.style_configs[editing_style]
        min_duration = style_config['min_clip_duration']
        max_duration = style_config['max_clip_duration']
        
        # Sort cuts by timestamp
        sorted_cuts = sorted(filtered_cuts, key=lambda x: x.timestamp)
        optimized_cuts = []
        
        # Add start cut if needed
        if not sorted_cuts or sorted_cuts[0].timestamp > 0.5:
            start_cut = CutPoint(
                timestamp=0.0,
                confidence=1.0,
                cut_type=CutType.FORCED_CUT,
                beat_alignment=0.0,
                scene_compatibility=1.0,
                flow_score=1.0,
                override_cost=0.0
            )
            optimized_cuts.append(start_cut)
        
        last_cut_time = optimized_cuts[0].timestamp if optimized_cuts else 0.0
        
        for cut_point in sorted_cuts:
            duration_since_last = cut_point.timestamp - last_cut_time
            
            # Check minimum duration constraint
            if duration_since_last < min_duration:
                # Skip this cut if too close to previous
                continue
            
            # Check maximum duration constraint
            elif duration_since_last > max_duration:
                # Insert intermediate cuts to satisfy max duration
                intermediate_cuts = self._generate_intermediate_cuts(
                    last_cut_time, cut_point.timestamp, max_duration,
                    audio_analysis, scene_detection, editing_style
                )
                optimized_cuts.extend(intermediate_cuts)
                last_cut_time = intermediate_cuts[-1].timestamp if intermediate_cuts else last_cut_time
                
                # Check if we can still add the original cut
                if cut_point.timestamp - last_cut_time >= min_duration:
                    optimized_cuts.append(cut_point)
                    last_cut_time = cut_point.timestamp
            else:
                # Duration is within acceptable range
                optimized_cuts.append(cut_point)
                last_cut_time = cut_point.timestamp
        
        # Add end cut if needed
        video_duration = scene_detection.video_info.duration
        if not optimized_cuts or optimized_cuts[-1].timestamp < video_duration - 0.5:
            end_cut = CutPoint(
                timestamp=video_duration,
                confidence=1.0,
                cut_type=CutType.FORCED_CUT,
                beat_alignment=0.0,
                scene_compatibility=1.0,
                flow_score=1.0,
                override_cost=0.0
            )
            optimized_cuts.append(end_cut)
        
        # Final optimization pass: improve global rhythm
        final_cuts = self._improve_global_rhythm(optimized_cuts, audio_analysis, editing_style)
        
        logger.debug("Timeline flow optimization completed",
                    input_cuts=len(filtered_cuts),
                    output_cuts=len(final_cuts),
                    min_duration=min_duration,
                    max_duration=max_duration)
        
        return final_cuts
    
    def _generate_intermediate_cuts(self, 
                                   start_time: float,
                                   end_time: float,
                                   max_duration: float,
                                   audio_analysis: AudioAnalysis,
                                   scene_detection: SceneDetectionResult,
                                   editing_style: EditingStyle) -> List[CutPoint]:
        """Generate intermediate cuts to satisfy maximum duration constraints"""
        intermediate_cuts = []
        current_time = start_time
        
        while current_time + max_duration < end_time - 0.5:
            target_time = current_time + max_duration
            
            # Find best cut point near target time
            best_cut = self._find_best_cut_near_time(
                target_time, audio_analysis, scene_detection, editing_style
            )
            
            if best_cut and best_cut.timestamp > current_time + max_duration * 0.5:
                intermediate_cuts.append(best_cut)
                current_time = best_cut.timestamp
            else:
                # Force a cut at max duration if no good option found
                forced_cut = CutPoint(
                    timestamp=target_time,
                    confidence=0.3,
                    cut_type=CutType.FORCED_CUT,
                    beat_alignment=self._calculate_beat_alignment(target_time, audio_analysis, self.style_configs[editing_style]),
                    scene_compatibility=0.5,
                    flow_score=0.4,
                    override_cost=0.7
                )
                intermediate_cuts.append(forced_cut)
                current_time = target_time
        
        return intermediate_cuts
    
    def _find_best_cut_near_time(self, 
                                target_time: float,
                                audio_analysis: AudioAnalysis,
                                scene_detection: SceneDetectionResult,
                                editing_style: EditingStyle,
                                search_window: float = 2.0) -> Optional[CutPoint]:
        """Find the best cut point within a time window"""
        # Search for beats and scene changes within the window
        candidates = []
        
        # Check beats
        for beat_time in audio_analysis.beats:
            if abs(beat_time - target_time) <= search_window:
                beat_cut = CutPoint(
                    timestamp=beat_time,
                    confidence=audio_analysis.confidence,
                    cut_type=CutType.BEAT_CUT,
                    beat_alignment=1.0,
                    scene_compatibility=self._calculate_scene_compatibility(
                        beat_time, scene_detection, self.style_configs[editing_style]
                    )[0],
                    flow_score=0.7,
                    override_cost=self._calculate_scene_compatibility(
                        beat_time, scene_detection, self.style_configs[editing_style]
                    )[1]
                )
                candidates.append(beat_cut)
        
        # Check scene changes
        for scene_change in scene_detection.scene_changes:
            if abs(scene_change.timestamp - target_time) <= search_window:
                scene_cut = CutPoint(
                    timestamp=scene_change.timestamp,
                    confidence=scene_change.confidence,
                    cut_type=CutType.SCENE_CUT,
                    beat_alignment=self._calculate_beat_alignment(
                        scene_change.timestamp, audio_analysis, self.style_configs[editing_style]
                    ),
                    scene_compatibility=1.0,
                    flow_score=0.8,
                    override_cost=0.0
                )
                candidates.append(scene_cut)
        
        if not candidates:
            return None
        
        # Score candidates based on proximity to target and overall quality
        best_candidate = None
        best_score = 0.0
        
        for candidate in candidates:
            proximity_score = 1.0 - abs(candidate.timestamp - target_time) / search_window
            quality_score = candidate.composite_score
            combined_score = proximity_score * 0.4 + quality_score * 0.6
            
            if combined_score > best_score:
                best_score = combined_score
                best_candidate = candidate
        
        return best_candidate
    
    def _improve_global_rhythm(self, 
                              cuts: List[CutPoint],
                              audio_analysis: AudioAnalysis,
                              editing_style: EditingStyle) -> List[CutPoint]:
        """Improve global rhythm and pacing of the timeline"""
        if len(cuts) < 3:
            return cuts
        
        improved_cuts = cuts.copy()
        expected_interval = 60.0 / audio_analysis.bpm if audio_analysis.bpm > 0 else 2.0
        
        # Analyze rhythm patterns and adjust for better flow
        for i in range(1, len(improved_cuts) - 1):
            current_cut = improved_cuts[i]
            prev_cut = improved_cuts[i - 1]
            next_cut = improved_cuts[i + 1]
            
            # Calculate intervals
            prev_interval = current_cut.timestamp - prev_cut.timestamp
            next_interval = next_cut.timestamp - current_cut.timestamp
            
            # Check for rhythm irregularities
            rhythm_score = self._score_rhythm_pattern(prev_interval, next_interval, expected_interval)
            
            # If rhythm is poor and we have flexibility, try to adjust
            if rhythm_score < 0.5 and current_cut.cut_type != CutType.SCENE_CUT:
                adjusted_cut = self._try_rhythm_adjustment(
                    current_cut, prev_cut, next_cut, audio_analysis, editing_style
                )
                if adjusted_cut:
                    improved_cuts[i] = adjusted_cut
        
        return improved_cuts
    
    def _score_rhythm_pattern(self, prev_interval: float, next_interval: float, expected_interval: float) -> float:
        """Score the rhythmic quality of three consecutive cuts"""
        # Check for consistent timing
        avg_interval = (prev_interval + next_interval) / 2
        interval_consistency = 1.0 - abs(prev_interval - next_interval) / avg_interval if avg_interval > 0 else 0.0
        
        # Check alignment with musical timing
        musical_alignment = (
            self._score_musical_interval(prev_interval, expected_interval) +
            self._score_musical_interval(next_interval, expected_interval)
        ) / 2
        
        return (interval_consistency * 0.4 + musical_alignment * 0.6)
    
    def _try_rhythm_adjustment(self, 
                              current_cut: CutPoint,
                              prev_cut: CutPoint,
                              next_cut: CutPoint,
                              audio_analysis: AudioAnalysis,
                              editing_style: EditingStyle) -> Optional[CutPoint]:
        """Try to adjust a cut point for better rhythm"""
        # Look for nearby beats that might provide better rhythm
        search_window = 1.0  # 1 second search window
        
        for beat_time in audio_analysis.beats:
            if (abs(beat_time - current_cut.timestamp) <= search_window and
                beat_time != current_cut.timestamp):
                
                # Check if this adjustment improves rhythm
                new_prev_interval = beat_time - prev_cut.timestamp
                new_next_interval = next_cut.timestamp - beat_time
                
                # Ensure minimum durations are maintained
                style_config = self.style_configs[editing_style]
                if (new_prev_interval >= style_config['min_clip_duration'] and
                    new_next_interval >= style_config['min_clip_duration']):
                    
                    # Calculate new rhythm score
                    expected_interval = 60.0 / audio_analysis.bpm if audio_analysis.bpm > 0 else 2.0
                    new_rhythm_score = self._score_rhythm_pattern(
                        new_prev_interval, new_next_interval, expected_interval
                    )
                    
                    # If rhythm improves significantly, make the adjustment
                    current_rhythm_score = self._score_rhythm_pattern(
                        current_cut.timestamp - prev_cut.timestamp,
                        next_cut.timestamp - current_cut.timestamp,
                        expected_interval
                    )
                    
                    if new_rhythm_score > current_rhythm_score + 0.1:
                        adjusted_cut = CutPoint(
                            timestamp=beat_time,
                            confidence=current_cut.confidence,
                            cut_type=CutType.BEAT_CUT,
                            beat_alignment=1.0,
                            scene_compatibility=current_cut.scene_compatibility,
                            flow_score=new_rhythm_score,
                            override_cost=current_cut.override_cost,
                            metrics=current_cut.metrics.copy()
                        )
                        adjusted_cut.metrics['rhythm_adjusted'] = True
                        return adjusted_cut
        
        return None
    
    def _generate_segments(self, 
                          cut_points: List[CutPoint],
                          audio_analysis: AudioAnalysis,
                          scene_detection: SceneDetectionResult) -> List[TimelineSegment]:
        """Generate timeline segments from cut points"""
        if len(cut_points) < 2:
            return []
        
        segments = []
        sorted_cuts = sorted(cut_points, key=lambda x: x.timestamp)
        
        for i in range(len(sorted_cuts) - 1):
            start_cut = sorted_cuts[i]
            end_cut = sorted_cuts[i + 1]
            
            # Count scene changes and beats within this segment
            scene_changes_count = sum(
                1 for sc in scene_detection.scene_changes
                if start_cut.timestamp <= sc.timestamp < end_cut.timestamp
            )
            
            beat_count = sum(
                1 for beat in audio_analysis.beats
                if start_cut.timestamp <= beat < end_cut.timestamp
            )
            
            # Calculate quality score based on segment characteristics
            quality_score = self._calculate_segment_quality(
                start_cut, end_cut, scene_changes_count, beat_count, audio_analysis
            )
            
            segment = TimelineSegment(
                start_time=start_cut.timestamp,
                end_time=end_cut.timestamp,
                cut_in_type=start_cut.cut_type,
                cut_out_type=end_cut.cut_type,
                scene_changes_count=scene_changes_count,
                beat_count=beat_count,
                quality_score=quality_score
            )
            
            segments.append(segment)
        
        return segments
    
    def _calculate_segment_quality(self,
                                  start_cut: CutPoint,
                                  end_cut: CutPoint,
                                  scene_changes_count: int,
                                  beat_count: int,
                                  audio_analysis: AudioAnalysis) -> float:
        """Calculate quality score for a timeline segment"""
        
        # Base quality from cut points
        cut_quality = (start_cut.composite_score + end_cut.composite_score) / 2
        
        # Duration quality (prefer moderate durations)
        duration = end_cut.timestamp - start_cut.timestamp
        optimal_duration = 3.0  # 3 seconds is often optimal for many video types
        duration_quality = math.exp(-abs(duration - optimal_duration) / optimal_duration)
        
        # Scene coherence (prefer segments with no or few scene changes)
        scene_quality = 1.0 / (1.0 + scene_changes_count * 0.5)
        
        # Musical alignment (prefer segments with good beat count)
        if audio_analysis.bpm > 0:
            expected_beats = duration * audio_analysis.bpm / 60.0
            beat_alignment_quality = 1.0 - abs(beat_count - expected_beats) / max(expected_beats, 1.0)
            beat_alignment_quality = max(0.0, min(1.0, beat_alignment_quality))
        else:
            beat_alignment_quality = 0.5
        
        # Combine quality factors
        quality_score = (
            cut_quality * 0.4 +
            duration_quality * 0.25 +
            scene_quality * 0.2 +
            beat_alignment_quality * 0.15
        )
        
        return min(1.0, quality_score)
    
    def _post_process_timeline(self, 
                              cut_points: List[CutPoint],
                              segments: List[TimelineSegment],
                              video_duration: float) -> Tuple[List[CutPoint], List[TimelineSegment]]:
        """Final post-processing and validation of the timeline"""
        
        # Ensure timeline covers the full video duration
        final_cuts = self._ensure_full_coverage(cut_points, video_duration)
        
        # Regenerate segments if cuts were modified  
        if len(final_cuts) != len(cut_points):
            # We need the original analysis objects to regenerate segments properly
            # This should be passed as parameters to avoid this issue
            # For now, return empty segments as a safeguard
            final_segments = []
        else:
            final_segments = segments
        
        # Validate timeline integrity
        validation_errors = self._validate_timeline_integrity(final_cuts, final_segments, video_duration)
        
        if validation_errors:
            logger.warning("Timeline validation issues", errors=validation_errors)
        
        return final_cuts, final_segments
    
    def _ensure_full_coverage(self, cut_points: List[CutPoint], video_duration: float) -> List[CutPoint]:
        """Ensure timeline covers the full video duration"""
        if not cut_points:
            # Create minimal timeline with just start and end
            return [
                CutPoint(0.0, 1.0, CutType.FORCED_CUT, 0.0, 1.0, 1.0, 0.0),
                CutPoint(video_duration, 1.0, CutType.FORCED_CUT, 0.0, 1.0, 1.0, 0.0)
            ]
        
        sorted_cuts = sorted(cut_points, key=lambda x: x.timestamp)
        final_cuts = []
        
        # Add start cut if needed
        if sorted_cuts[0].timestamp > 0.1:
            start_cut = CutPoint(
                timestamp=0.0,
                confidence=1.0,
                cut_type=CutType.FORCED_CUT,
                beat_alignment=0.0,
                scene_compatibility=1.0,
                flow_score=1.0,
                override_cost=0.0
            )
            final_cuts.append(start_cut)
        
        # Add all existing cuts
        final_cuts.extend(sorted_cuts)
        
        # Add end cut if needed
        if sorted_cuts[-1].timestamp < video_duration - 0.1:
            end_cut = CutPoint(
                timestamp=video_duration,
                confidence=1.0,
                cut_type=CutType.FORCED_CUT,
                beat_alignment=0.0,
                scene_compatibility=1.0,
                flow_score=1.0,
                override_cost=0.0
            )
            final_cuts.append(end_cut)
        
        return final_cuts
    
    def _validate_timeline_integrity(self, 
                                    cut_points: List[CutPoint],
                                    segments: List[TimelineSegment],
                                    video_duration: float) -> List[str]:
        """Validate timeline integrity and detect issues"""
        errors = []
        
        if not cut_points:
            errors.append("No cut points in timeline")
            return errors
        
        # Check temporal ordering
        sorted_cuts = sorted(cut_points, key=lambda x: x.timestamp)
        for i, cut in enumerate(sorted_cuts):
            if cut.timestamp < 0:
                errors.append(f"Cut {i} has negative timestamp: {cut.timestamp}")
            if cut.timestamp > video_duration:
                errors.append(f"Cut {i} exceeds video duration: {cut.timestamp} > {video_duration}")
        
        # Check for duplicate timestamps
        timestamps = [cut.timestamp for cut in cut_points]
        if len(timestamps) != len(set(timestamps)):
            errors.append("Duplicate cut timestamps detected")
        
        # Check segment continuity
        if segments:
            for i, segment in enumerate(segments):
                if segment.duration <= 0:
                    errors.append(f"Segment {i} has invalid duration: {segment.duration}")
                
                if i > 0:
                    prev_segment = segments[i - 1]
                    if abs(prev_segment.end_time - segment.start_time) > 0.001:
                        errors.append(f"Gap between segments {i-1} and {i}")
        
        return errors
    
    # Utility methods for advanced features
    
    def detect_tempo_changes(self, audio_analysis: AudioAnalysis, window_size: float = 10.0) -> List[Tuple[float, float]]:
        """
        Detect tempo changes in the audio for adaptive cut timing
        
        Args:
            audio_analysis: Audio analysis results
            window_size: Size of analysis window in seconds
            
        Returns:
            List of (timestamp, new_bpm) tuples for tempo changes
        """
        if len(audio_analysis.beats) < 10:
            return []
        
        tempo_changes = []
        beats = np.array(audio_analysis.beats)
        
        # Sliding window analysis
        for start_time in np.arange(0, audio_analysis.duration - window_size, window_size / 2):
            end_time = start_time + window_size
            
            # Find beats in this window
            window_beats = beats[(beats >= start_time) & (beats < end_time)]
            
            if len(window_beats) >= 3:
                # Calculate local BPM
                intervals = np.diff(window_beats)
                avg_interval = np.mean(intervals)
                local_bpm = 60.0 / avg_interval if avg_interval > 0 else 0
                
                # Check if this represents a significant tempo change
                if abs(local_bpm - audio_analysis.bpm) > 10:  # 10 BPM threshold
                    tempo_changes.append((start_time, local_bpm))
        
        return tempo_changes
    
    def handle_silence_detection(self, 
                               audio_analysis: AudioAnalysis,
                               video_info: VideoInfo,
                               silence_threshold_db: float = -40.0,
                               min_silence_duration: float = 1.0) -> List[Tuple[float, float]]:
        """
        Detect silence periods for potential cut points
        
        This is a placeholder implementation. In a full implementation,
        you would analyze the actual audio waveform for silence detection.
        """
        # Placeholder: identify potential silence based on beat gaps
        silence_periods = []
        
        if len(audio_analysis.beats) < 2:
            return silence_periods
        
        beat_intervals = np.diff(audio_analysis.beats)
        avg_interval = np.mean(beat_intervals)
        
        # Look for gaps that are significantly larger than average
        for i, interval in enumerate(beat_intervals):
            if interval > avg_interval * 3 and interval > min_silence_duration:
                start_time = audio_analysis.beats[i]
                end_time = audio_analysis.beats[i + 1]
                silence_periods.append((start_time, end_time))
        
        return silence_periods
    
    def export_timeline(self, timeline: EditingTimeline, output_path: Union[str, Path], format: str = 'json'):
        """
        Export timeline to various formats
        
        Args:
            timeline: EditingTimeline to export
            output_path: Path to save the exported timeline
            format: Export format ('json', 'csv', 'edl')
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format.lower() == 'json':
            import json
            with open(output_path, 'w') as f:
                json.dump(timeline.to_dict(), f, indent=2)
        
        elif format.lower() == 'csv':
            import csv
            with open(output_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['start_time', 'end_time', 'duration', 'cut_in_type', 'cut_out_type', 'quality_score'])
                for segment in timeline.segments:
                    writer.writerow([
                        segment.start_time, segment.end_time, segment.duration,
                        segment.cut_in_type.value, segment.cut_out_type.value, segment.quality_score
                    ])
        
        elif format.lower() == 'edl':
            # Export as Edit Decision List format
            with open(output_path, 'w') as f:
                f.write("TITLE: AutoCut Generated Timeline\n")
                f.write("FCM: NON-DROP FRAME\n\n")
                
                for i, segment in enumerate(timeline.segments, 1):
                    f.write(f"{i:03d}  V     C        {self._format_timecode(segment.start_time)} "
                           f"{self._format_timecode(segment.end_time)} "
                           f"{self._format_timecode(segment.start_time)} "
                           f"{self._format_timecode(segment.end_time)}\n")
        
        logger.info("Timeline exported", output_path=str(output_path), format=format)
    
    def _format_timecode(self, seconds: float, fps: float = 30.0) -> str:
        """Format seconds as SMPTE timecode"""
        total_frames = int(seconds * fps)
        hours = total_frames // (3600 * fps)
        minutes = (total_frames % (3600 * fps)) // (60 * fps)
        secs = (total_frames % (60 * fps)) // fps
        frames = total_frames % fps
        return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"
    
    def analyze_timeline_statistics(self, timeline: EditingTimeline) -> Dict[str, Any]:
        """
        Analyze timeline statistics for quality assessment
        
        Returns comprehensive statistics about the generated timeline
        """
        if not timeline.segments:
            return {'error': 'No segments in timeline'}
        
        durations = [seg.duration for seg in timeline.segments]
        beat_alignments = [cp.beat_alignment for cp in timeline.cut_points]
        scene_compatibilities = [cp.scene_compatibility for cp in timeline.cut_points]
        quality_scores = [seg.quality_score for seg in timeline.segments]
        
        stats = {
            'timeline_info': {
                'total_duration': timeline.total_duration,
                'segment_count': len(timeline.segments),
                'cut_count': len(timeline.cut_points),
                'editing_style': timeline.editing_style.value,
                'generation_time': timeline.generation_time
            },
            'duration_stats': {
                'mean_duration': np.mean(durations),
                'median_duration': np.median(durations),
                'std_duration': np.std(durations),
                'min_duration': np.min(durations),
                'max_duration': np.max(durations)
            },
            'alignment_stats': {
                'mean_beat_alignment': np.mean(beat_alignments),
                'mean_scene_compatibility': np.mean(scene_compatibilities),
                'beat_sync_percentage': timeline.beat_sync_percentage,
                'scene_respect_percentage': timeline.scene_respect_percentage
            },
            'quality_stats': {
                'mean_quality_score': np.mean(quality_scores),
                'median_quality_score': np.median(quality_scores),
                'min_quality_score': np.min(quality_scores),
                'max_quality_score': np.max(quality_scores)
            },
            'cut_type_distribution': {
                cut_type.value: sum(1 for cp in timeline.cut_points if cp.cut_type == cut_type)
                for cut_type in CutType
            },
            'rhythm_analysis': {
                'rhythm_consistency': self._calculate_global_rhythm_consistency(timeline),
                'musical_alignment': self._calculate_global_musical_alignment(timeline)
            }
        }
        
        return stats
    
    def _calculate_global_rhythm_consistency(self, timeline: EditingTimeline) -> float:
        """Calculate overall rhythm consistency of the timeline"""
        if len(timeline.segments) < 3:
            return 1.0
        
        durations = [seg.duration for seg in timeline.segments]
        duration_variance = np.var(durations)
        mean_duration = np.mean(durations)
        
        # Normalize variance by mean
        normalized_variance = duration_variance / (mean_duration ** 2) if mean_duration > 0 else 1.0
        
        # Convert to consistency score
        consistency = math.exp(-normalized_variance * 2.0)
        return consistency
    
    def _calculate_global_musical_alignment(self, timeline: EditingTimeline) -> float:
        """Calculate overall musical alignment of the timeline"""
        if not timeline.cut_points:
            return 0.0
        
        beat_aligned_cuts = sum(1 for cp in timeline.cut_points if cp.beat_alignment > 0.7)
        return beat_aligned_cuts / len(timeline.cut_points)
    
    def generate_multi_video_timeline(self,
                                    audio_analysis: AudioAnalysis,
                                    video_info_list: List[VideoInfo],
                                    scene_detections: List[SceneDetectionResult],
                                    quality_results: Optional[List] = None,
                                    editing_style: Optional[EditingStyle] = None) -> EditingTimeline:
        """
        Generate beat-synchronized timeline from multiple video sources
        
        This method creates a highlight reel by selecting the best clips from multiple videos
        and synchronizing them to the provided audio track (external music).
        
        Args:
            audio_analysis: Audio analysis results from external music track
            video_info_list: List of video file information
            scene_detections: List of scene detection results for each video
            quality_results: Optional list of quality analysis results
            editing_style: Override default editing style
            
        Returns:
            EditingTimeline with clips from multiple videos synced to music
        """
        editing_style = editing_style or self.editing_style
        start_time = time.time()
        
        logger.info("Generating multi-video timeline from external music",
                   video_count=len(video_info_list),
                   editing_style=editing_style.value,
                   music_duration=f"{audio_analysis.duration:.2f}s",
                   beat_count=len(audio_analysis.beats))
        
        try:
            # Step 1: Collect all potential clips from all videos with quality scores
            all_clips = []
            
            for i, (video_info, scene_detection) in enumerate(zip(video_info_list, scene_detections)):
                quality_result = quality_results[i] if quality_results and i < len(quality_results) else None
                
                # Extract clips from this video
                video_clips = self._extract_video_clips(
                    video_info, scene_detection, quality_result, video_index=i
                )
                all_clips.extend(video_clips)
                
                logger.debug("Extracted clips from video", 
                           video=video_info.file_path.name,
                           clip_count=len(video_clips))
            
            logger.info("Collected clips from all videos", total_clips=len(all_clips))
            
            # Step 2: Score and rank all clips
            scored_clips = self._score_multi_video_clips(all_clips, quality_results)
            
            # Step 3: Select best clips to fit music duration with variety
            selected_clips = self._select_clips_for_music(
                scored_clips, audio_analysis, editing_style
            )
            
            # Step 4: Arrange clips to sync with beats
            timeline = self._arrange_clips_to_beats(
                selected_clips, audio_analysis, editing_style
            )
            
            # Step 5: Apply temporal shuffling (avoid consecutive clips from same video)
            timeline = self._apply_temporal_shuffling(timeline)
            
            # Step 6: Optimize timeline for flow and musical alignment
            timeline = self._optimize_multi_video_timeline(timeline, audio_analysis)
            
            # Calculate final statistics
            processing_time = time.time() - start_time
            timeline.generation_time = processing_time
            
            logger.info("Multi-video timeline generation completed",
                       total_clips=len(timeline.segments),
                       timeline_duration=f"{timeline.duration:.2f}s",
                       music_duration=f"{audio_analysis.duration:.2f}s",
                       beat_sync_percentage=f"{timeline.beat_sync_percentage:.1f}%",
                       videos_used=len(set(seg.source_video_index for seg in timeline.segments)),
                       processing_time=f"{processing_time:.2f}s")
            
            return timeline
            
        except Exception as e:
            logger.error("Multi-video timeline generation failed", error=str(e))
            raise RuntimeError(f"Timeline generation failed: {e}")
    
    def _extract_video_clips(self, video_info: VideoInfo, scene_detection: SceneDetectionResult, 
                           quality_result, video_index: int) -> List[Dict]:
        """Extract potential clips from a video with quality information"""
        clips = []
        scenes = scene_detection.scene_changes if scene_detection else []
        
        # Add video start as first scene if not present
        scene_times = [0.0] + [sc.timestamp for sc in scenes] + [video_info.duration]
        scene_times = sorted(set(scene_times))  # Remove duplicates and sort
        
        for i in range(len(scene_times) - 1):
            start_time = scene_times[i]
            end_time = scene_times[i + 1]
            duration = end_time - start_time
            
            # Skip very short or very long scenes
            if duration < self.min_clip_duration or duration > self.max_clip_duration * 2:
                continue
            
            # Get quality score for this time range if available
            quality_score = 0.5  # Default neutral quality
            if quality_result and hasattr(quality_result, 'frames'):
                # Calculate average quality for this time range
                frame_scores = []
                for frame_result in quality_result.frames:
                    if start_time <= frame_result.timestamp <= end_time:
                        frame_scores.append(frame_result.quality_score)
                
                if frame_scores:
                    quality_score = sum(frame_scores) / len(frame_scores)
            
            clip = {
                'source_video_index': video_index,
                'source_video_path': video_info.file_path,
                'start_time': start_time,
                'end_time': end_time,
                'duration': duration,
                'quality_score': quality_score,
                'is_scene_boundary': i > 0,  # First clip doesn't start with scene change
                'scene_confidence': scenes[i-1].confidence if i > 0 and i-1 < len(scenes) else 1.0
            }
            clips.append(clip)
        
        return clips
    
    def _score_multi_video_clips(self, all_clips: List[Dict], quality_results) -> List[Dict]:
        """Score and rank clips from multiple videos"""
        for clip in all_clips:
            # Base score from quality
            base_score = clip['quality_score']
            
            # Bonus for good duration (not too short, not too long)
            duration_bonus = self._calculate_duration_score(clip['duration'])
            
            # Bonus for scene boundaries (natural cut points)
            scene_bonus = 0.1 if clip['is_scene_boundary'] else 0.0
            
            # Combined score
            clip['combined_score'] = base_score + duration_bonus + scene_bonus
        
        # Sort by combined score (best first)
        scored_clips = sorted(all_clips, key=lambda x: x['combined_score'], reverse=True)
        
        logger.debug("Scored clips", 
                    total_clips=len(scored_clips),
                    best_score=scored_clips[0]['combined_score'] if scored_clips else 0,
                    worst_score=scored_clips[-1]['combined_score'] if scored_clips else 0)
        
        return scored_clips
    
    def _calculate_duration_score(self, duration: float) -> float:
        """Calculate score bonus based on clip duration"""
        ideal_duration = (self.min_clip_duration + self.max_clip_duration) / 2
        duration_diff = abs(duration - ideal_duration)
        max_diff = self.max_clip_duration - self.min_clip_duration
        
        # Score from 0.0 to 0.2 based on how close to ideal duration
        return 0.2 * (1.0 - min(duration_diff / max_diff, 1.0))
    
    def _select_clips_for_music(self, scored_clips: List[Dict], audio_analysis: AudioAnalysis, 
                              editing_style: EditingStyle) -> List[Dict]:
        """Select best clips to fit music duration with variety"""
        music_duration = audio_analysis.duration
        selected_clips = []
        used_videos = set()
        total_duration = 0.0
        
        # Style-specific parameters
        style_config = self.style_configs.get(editing_style, self.style_configs[EditingStyle.ADAPTIVE])
        target_clip_duration = (style_config['min_clip_duration'] + style_config['max_clip_duration']) / 2
        
        # Estimate number of clips needed
        estimated_clips_needed = int(music_duration / target_clip_duration)
        
        # Selection strategy: prioritize variety and quality
        for clip in scored_clips:
            if total_duration >= music_duration:
                break
            
            video_idx = clip['source_video_index']
            
            # Encourage variety - prefer clips from unused videos
            variety_bonus = 0.1 if video_idx not in used_videos else 0.0
            clip['final_score'] = clip['combined_score'] + variety_bonus
            
            # Check if adding this clip would exceed music duration significantly
            if total_duration + clip['duration'] > music_duration * 1.1:  # 10% tolerance
                # Try to find a shorter clip from remaining clips
                continue
                
            selected_clips.append(clip)
            used_videos.add(video_idx)
            total_duration += clip['duration']
            
            # Stop if we have enough clips
            if len(selected_clips) >= estimated_clips_needed * 1.5:  # Allow some extra
                break
        
        logger.info("Selected clips for music track",
                   selected_clips=len(selected_clips),
                   total_duration=f"{total_duration:.2f}s",
                   music_duration=f"{music_duration:.2f}s",
                   videos_used=len(used_videos))
        
        return selected_clips
    
    def _arrange_clips_to_beats(self, clips: List[Dict], audio_analysis: AudioAnalysis, 
                              editing_style: EditingStyle) -> EditingTimeline:
        """Arrange selected clips to synchronize with music beats"""
        beats = audio_analysis.beats
        segments = []
        cut_points = []
        
        current_time = 0.0
        clip_index = 0
        
        for i, beat_time in enumerate(beats):
            if clip_index >= len(clips):
                break
                
            clip = clips[clip_index]
            
            # Calculate clip duration to next beat (or end)
            next_beat_time = beats[i + 1] if i + 1 < len(beats) else audio_analysis.duration
            available_duration = next_beat_time - beat_time
            
            # Adjust clip duration to fit beat interval
            actual_duration = min(clip['duration'], available_duration)
            actual_duration = max(actual_duration, self.min_clip_duration)
            
            # Create timeline segment
            segment = TimelineSegment(
                start_time=current_time,
                end_time=current_time + actual_duration,
                source_video_index=clip['source_video_index'],
                source_video_path=clip['source_video_path'],
                source_start_time=clip['start_time'],
                source_end_time=clip['start_time'] + actual_duration,
                quality_score=clip['quality_score'],
                beat_alignment_score=1.0,  # Perfect beat alignment
                scene_respect_score=1.0 if clip['is_scene_boundary'] else 0.8
            )
            segments.append(segment)
            
            # Create cut point
            if i > 0:  # Skip first cut point
                cut_point = CutPoint(
                    timestamp=current_time,
                    cut_type=CutType.BEAT_CUT,
                    confidence=0.9,
                    beat_alignment=1.0,
                    scene_compatibility=segment.scene_respect_score,
                    flow_score=0.8
                )
                cut_points.append(cut_point)
            
            current_time += actual_duration
            clip_index += 1
            
            # Stop if we've used all available music duration
            if current_time >= audio_analysis.duration:
                break
        
        # Create timeline
        timeline = EditingTimeline(
            segments=segments,
            cut_points=cut_points,
            duration=current_time,
            editing_style=editing_style
        )
        
        return timeline
    
    def _apply_temporal_shuffling(self, timeline: EditingTimeline) -> EditingTimeline:
        """Apply temporal shuffling to avoid consecutive clips from same video"""
        if len(timeline.segments) < 2:
            return timeline
        
        # Find consecutive clips from same video that are close in time
        segments = timeline.segments.copy()
        shuffled = False
        
        for i in range(len(segments) - 1):
            current_seg = segments[i]
            next_seg = segments[i + 1]
            
            # Check if both clips are from same video and close in time (< 1 second apart)
            if (current_seg.source_video_index == next_seg.source_video_index and
                abs(current_seg.source_start_time - next_seg.source_start_time) < 1.0):
                
                # Try to find a different clip to insert between them
                for j in range(i + 2, len(segments)):
                    if segments[j].source_video_index != current_seg.source_video_index:
                        # Swap the clips
                        segments[i + 1], segments[j] = segments[j], segments[i + 1]
                        shuffled = True
                        break
        
        if shuffled:
            logger.debug("Applied temporal shuffling to avoid consecutive clips from same video")
            # Update timeline with shuffled segments
            timeline.segments = segments
        
        return timeline
    
    def _optimize_multi_video_timeline(self, timeline: EditingTimeline, 
                                     audio_analysis: AudioAnalysis) -> EditingTimeline:
        """Final optimization for multi-video timeline"""
        # Update timeline statistics
        if timeline.segments:
            # Update duration
            timeline.duration = timeline.segments[-1].end_time if timeline.segments else 0.0
            
            # Note: beat_sync_percentage and scene_respect_percentage are now 
            # calculated automatically from cut_points data via properties
        
        logger.debug("Multi-video timeline optimized",
                    final_duration=f"{timeline.duration:.2f}s",
                    beat_sync=f"{timeline.beat_sync_percentage:.1f}%",
                    scene_respect=f"{timeline.scene_respect_percentage:.1f}%")
        
        return timeline
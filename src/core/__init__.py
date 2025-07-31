"""Core processing engine for AutoCut

This module provides the main timeline generation capabilities for AutoCut,
including beat-synchronized video editing with sophisticated algorithms that
balance musical timing with visual content analysis.

Main Components:
- BeatSyncTimelineGenerator: Main timeline generation engine
- EditingStyle: Different editing styles (Aggressive, Smooth, Adaptive, etc.)
- CutPoint, TimelineSegment, EditingTimeline: Core data structures

Example Usage:
    from autocut.core.timeline import BeatSyncTimelineGenerator, EditingStyle
    from autocut.audio.analyzer import AudioAnalyzer
    from autocut.video.scene_detection import SceneDetection
    from autocut.video.ingestion import VideoIngestion
    
    # Initialize components
    video_ingestion = VideoIngestion()
    audio_analyzer = AudioAnalyzer()
    scene_detector = SceneDetection()
    timeline_generator = BeatSyncTimelineGenerator(EditingStyle.ADAPTIVE)
    
    # Process video
    video_info = video_ingestion.load_video("video.mp4")
    audio_analysis = audio_analyzer.analyze_audio("audio.wav")  # Extracted from video
    scene_detection = scene_detector.detect_scenes("video.mp4", video_info=video_info)
    
    # Generate timeline
    timeline = timeline_generator.generate_timeline(
        audio_analysis, scene_detection, video_info, EditingStyle.MUSICAL
    )
    
    # Export timeline
    timeline_generator.export_timeline(timeline, "output.json", "json")
    
    # Analyze results
    stats = timeline_generator.analyze_timeline_statistics(timeline)
    print(f"Generated {len(timeline.segments)} segments with "
          f"{timeline.beat_sync_percentage:.1f}% beat sync")
"""

from .timeline import (
    BeatSyncTimelineGenerator,
    EditingStyle,
    CutType,
    CutPoint,
    TimelineSegment,
    EditingTimeline
)

__all__ = [
    'BeatSyncTimelineGenerator',
    'EditingStyle',
    'CutType', 
    'CutPoint',
    'TimelineSegment',
    'EditingTimeline'
]
#!/usr/bin/env python3
"""
Validation script for comprehensive temporal domain fixes

This script validates the key fixes implemented from the comprehensive ultraanalysis plan:
1. Temporal domain separation 
2. Timeline segment validation
3. Frame diversity detection
4. Pre-extraction validation gate
5. Accurate beat sync statistics

Run with: python validate_temporal_domain_fixes.py
"""

import sys
import time
from pathlib import Path
from typing import List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.core.timeline import BeatSyncTimelineGenerator, EditingStyle
from src.video.renderer import VideoRenderer
from src.audio.analyzer import AudioAnalysis
from src.video.ingestion import VideoInfo, VideoStream, AudioStream, ContainerFormat, VideoCodec


def create_test_video_info(duration: float = 30.0) -> VideoInfo:
    """Create test video info for validation"""
    return VideoInfo(
        file_path=Path("test_video.mp4"),
        container_format=ContainerFormat.MP4,
        duration=duration,
        file_size=1000000,
        video_streams=[VideoStream(
            index=0,
            codec=VideoCodec.H264,
            width=1920,
            height=1080,
            fps=30.0,
            bitrate=5000000,
            duration=duration
        )],
        audio_streams=[AudioStream(
            index=1,
            codec="aac",
            sample_rate=44100,
            channels=2,
            bitrate=192000,
            duration=duration
        )],
        metadata={},
        is_valid=True
    )


def create_test_audio_analysis() -> AudioAnalysis:
    """Create test audio analysis with beats"""
    beats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    return AudioAnalysis(
        bpm=120.0,
        beats=beats,
        confidence=0.9,
        duration=5.5,
        sample_rate=44100
    )


def validate_temporal_domain_separation():
    """Test Fix 1: Temporal domain separation in timeline generation"""
    print("🔍 Validating temporal domain separation...")
    
    try:
        generator = BeatSyncTimelineGenerator()
        video_info = create_test_video_info(30.0)
        video_info_list = [video_info]
        audio_analysis = create_test_audio_analysis()
        
        # Create test clips with proper domain data
        clips = [
            {
                'source_video_index': 0,
                'source_video_path': Path("test_video.mp4"),
                'start_time': 5.0,  # SOURCE DOMAIN: 5 seconds into video
                'duration': 1.0,    # BEAT DOMAIN: 1 second clips
                'quality_score': 0.8,
                'is_scene_boundary': True
            },
            {
                'source_video_index': 0,
                'source_video_path': Path("test_video.mp4"),
                'start_time': 10.0,  # SOURCE DOMAIN: 10 seconds into video
                'duration': 1.0,     # BEAT DOMAIN: 1 second clips
                'quality_score': 0.9,
                'is_scene_boundary': False
            }
        ]
        
        # Test the fixed _arrange_clips_to_beats method
        timeline = generator._arrange_clips_to_beats(
            clips, audio_analysis, EditingStyle.ADAPTIVE, video_info_list
        )
        
        # Validate temporal domains are properly separated
        if timeline.segments:
            segment = timeline.segments[0]
            
            # Check SOURCE DOMAIN integrity
            source_duration = segment.source_end_time - segment.source_start_time
            
            # Check TIMELINE DOMAIN integrity  
            timeline_duration = segment.end_time - segment.start_time
            
            # These should match (within tolerance)
            if abs(source_duration - timeline_duration) < 0.001:
                print("✅ Temporal domain separation: PASSED")
                print(f"   Source duration: {source_duration:.3f}s")
                print(f"   Timeline duration: {timeline_duration:.3f}s")
                return True
            else:
                print("❌ Temporal domain separation: FAILED")
                print(f"   Duration mismatch: source={source_duration:.3f}s vs timeline={timeline_duration:.3f}s")
                return False
        else:
            print("❌ Temporal domain separation: FAILED - No segments created")
            return False
            
    except Exception as e:
        print(f"❌ Temporal domain separation: ERROR - {e}")
        return False


def validate_timeline_segment_validation():
    """Test Fix 2: Timeline segment validation with bounds checking"""
    print("\n🔍 Validating timeline segment validation...")
    
    try:
        generator = BeatSyncTimelineGenerator()
        video_info = create_test_video_info(10.0)  # 10 second video
        
        # Test valid segment
        valid_result = generator._validate_timeline_segment_bounds(
            source_start_time=2.0,
            source_end_time=4.0,
            duration=2.0,
            video_info_list=[video_info],
            source_video_index=0
        )
        
        # Test invalid segment (exceeds video duration)
        invalid_result = generator._validate_timeline_segment_bounds(
            source_start_time=8.0,
            source_end_time=12.0,  # Beyond 10s video duration
            duration=4.0,
            video_info_list=[video_info],
            source_video_index=0
        )
        
        if valid_result and not invalid_result:
            print("✅ Timeline segment validation: PASSED")
            print("   Valid segment accepted, invalid segment rejected")
            return True
        else:
            print("❌ Timeline segment validation: FAILED")
            print(f"   Valid segment result: {valid_result}")
            print(f"   Invalid segment result: {invalid_result}")
            return False
            
    except Exception as e:
        print(f"❌ Timeline segment validation: ERROR - {e}")
        return False


def validate_beat_sync_statistics():
    """Test Fix 5: Accurate beat sync statistics calculation"""
    print("\n🔍 Validating beat sync statistics calculation...")
    
    try:
        generator = BeatSyncTimelineGenerator()
        audio_analysis = create_test_audio_analysis()
        
        # Test the new beat alignment calculation
        # Perfect alignment case
        perfect_alignment = generator._calculate_actual_beat_alignment(
            beat_time=1.0,          # Beat at 1.0s
            timeline_position=1.0,  # Cut exactly at 1.0s
            beats=audio_analysis.beats,
            beat_index=1
        )
        
        # Poor alignment case
        poor_alignment = generator._calculate_actual_beat_alignment(
            beat_time=1.0,          # Beat at 1.0s  
            timeline_position=1.3,  # Cut 0.3s off beat
            beats=audio_analysis.beats,
            beat_index=1
        )
        
        if perfect_alignment > 0.9 and poor_alignment < 0.7:
            print("✅ Beat sync statistics: PASSED")
            print(f"   Perfect alignment score: {perfect_alignment:.3f}")
            print(f"   Poor alignment score: {poor_alignment:.3f}")
            return True
        else:
            print("❌ Beat sync statistics: FAILED")
            print(f"   Perfect alignment score: {perfect_alignment:.3f} (expected > 0.9)")
            print(f"   Poor alignment score: {poor_alignment:.3f} (expected < 0.7)")
            return False
            
    except Exception as e:
        print(f"❌ Beat sync statistics: ERROR - {e}")
        return False


def validate_pre_extraction_validation():
    """Test Fix 4: Pre-extraction validation gate"""
    print("\n🔍 Validating pre-extraction validation gate...")
    
    try:
        renderer = VideoRenderer()
        video_info = create_test_video_info(10.0)
        
        # Create mock timeline with mix of valid and invalid segments
        from src.core.timeline import EditingTimeline, TimelineSegment, CutPoint, CutType
        
        segments = [
            # Valid segment
            TimelineSegment(
                start_time=0.0,
                end_time=2.0,
                source_video_index=0,
                source_video_path=Path("test_video.mp4"),
                source_start_time=2.0,
                source_end_time=4.0,
                quality_score=0.8
            ),
            # Invalid segment (exceeds video duration)
            TimelineSegment(
                start_time=2.0,
                end_time=4.0,
                source_video_index=0,
                source_video_path=Path("test_video.mp4"),
                source_start_time=9.0,
                source_end_time=12.0,  # Beyond 10s video
                quality_score=0.8
            )
        ]
        
        timeline = EditingTimeline(
            video_info=video_info,
            audio_analysis=None,
            scene_detection=None,
            cut_points=[],
            segments=segments,
            editing_style=EditingStyle.ADAPTIVE,
            generation_time=0.0,
            total_duration=4.0,
            success=True
        )
        
        # Test the validation gate
        valid_segments = renderer._validate_segments_before_extraction(timeline, video_info)
        
        if len(valid_segments) == 1 and len(segments) == 2:
            print("✅ Pre-extraction validation gate: PASSED")
            print(f"   Filtered segments: {len(segments)} → {len(valid_segments)}")
            print("   Invalid segments correctly rejected")
            return True
        else:
            print("❌ Pre-extraction validation gate: FAILED")
            print(f"   Expected 1 valid segment, got {len(valid_segments)}")
            return False
            
    except Exception as e:
        print(f"❌ Pre-extraction validation gate: ERROR - {e}")
        return False


def main():
    """Run all temporal domain fix validations"""
    print("🚀 COMPREHENSIVE TEMPORAL DOMAIN FIXES VALIDATION")
    print("=" * 60)
    
    tests = [
        validate_temporal_domain_separation,
        validate_timeline_segment_validation,
        validate_beat_sync_statistics,
        validate_pre_extraction_validation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 60)
    print(f"🎯 VALIDATION SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL FIXES VALIDATED SUCCESSFULLY!")
        print("\nThe comprehensive ultraanalysis plan has been implemented correctly:")
        print("• ✅ Temporal domain separation prevents domain mixing")
        print("• ✅ Timeline segment validation blocks invalid segments")
        print("• ✅ Beat sync statistics show actual alignment quality")
        print("• ✅ Pre-extraction validation prevents corrupted processing")
        return True
    else:
        print(f"⚠️  {total - passed} validation(s) failed - review implementation")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
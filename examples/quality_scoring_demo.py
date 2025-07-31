"""
Comprehensive demo of the quality scoring system for AutoCut.

This demo shows how to use the quality scoring engine to:
1. Analyze video frame quality with multiple factors
2. Integrate with face detection results
3. Use different quality profiles for different content types
4. Export quality timelines and identify hotspots
5. Optimize for real-time processing performance

Usage:
    python examples/quality_scoring_demo.py path/to/video.mp4
"""

import sys
import time
from pathlib import Path
import numpy as np

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from video.ingestion import VideoIngestion
from video.face_detection import create_face_detection_engine, create_video_frame_generator
from core.quality_scoring import (
    QualityScoring, QualityProfile, 
    create_quality_scorer, create_video_frame_generator_with_quality
)
from utils.logging import get_logger

logger = get_logger(__name__)


def demo_basic_quality_assessment(video_path: Path):
    """Demo basic quality assessment on a video"""
    print(f"\n=== Basic Quality Assessment Demo ===")
    print(f"Video: {video_path}")
    
    # Load video information
    video_ingestion = VideoIngestion()
    video_info = video_ingestion.load_video(video_path)
    
    print(f"Video Duration: {video_info.duration:.1f}s")
    print(f"Resolution: {video_info.resolution[0]}x{video_info.resolution[1]}")
    print(f"FPS: {video_info.primary_video_stream.fps if video_info.primary_video_stream else 'Unknown'}")
    
    # Create quality scorer
    quality_scorer = create_quality_scorer(
        video_info=video_info,
        target_realtime_multiple=15.0,
        content_type="adaptive"
    )
    
    # Process video for quality assessment
    frame_generator = create_video_frame_generator_with_quality(video_path)
    
    print(f"\nProcessing video with profile: {quality_scorer.profile.value}")
    start_time = time.time()
    
    def progress_callback(processed_count, timestamp):
        if processed_count % 10 == 0:
            print(f"Processed {processed_count} frames, timestamp: {timestamp:.1f}s")
    
    result = quality_scorer.process_video_quality(
        video_info=video_info,
        frame_generator=frame_generator,
        progress_callback=progress_callback
    )
    
    processing_time = time.time() - start_time
    
    # Display results
    print(f"\n=== Quality Analysis Results ===")
    print(f"Total frames processed: {result.total_frames_processed}")
    print(f"Processing time: {processing_time:.2f}s")
    print(f"Processing speed: {result.average_fps:.1f}x real-time")
    print(f"Mean quality score: {result.mean_quality:.1f}/100")
    print(f"Quality std deviation: {result.quality_std:.1f}")
    print(f"Quality trend: {result.quality_trend}")
    
    if result.best_frame:
        print(f"Best frame: {result.best_frame.timestamp:.1f}s (quality: {result.best_frame.overall_quality:.1f})")
    if result.worst_frame:
        print(f"Worst frame: {result.worst_frame.timestamp:.1f}s (quality: {result.worst_frame.overall_quality:.1f})")
    
    return result


def demo_face_integration(video_path: Path):
    """Demo quality assessment with face detection integration"""
    print(f"\n=== Face Integration Demo ===")
    
    # Load video information
    video_ingestion = VideoIngestion()
    video_info = video_ingestion.load_video(video_path)
    
    # Create face detection engine
    face_engine = create_face_detection_engine(video_info, target_realtime_multiple=15.0)
    
    # Create quality scorer with face integration
    quality_scorer = QualityScoring(
        profile=QualityProfile.TALKING_HEAD,
        target_fps=15.0,
        enable_face_integration=True
    )
    
    print("Running face detection...")
    # Get face detection results
    frame_generator = create_video_frame_generator(video_path)
    face_result = face_engine.process_video_frames(
        video_info=video_info,
        frame_generator=frame_generator
    )
    
    print(f"Face detection completed: {len(face_result.frame_results)} frames with {face_result.faces_per_second:.1f} faces/sec")
    
    # Process quality with face results
    print("Running quality assessment with face integration...")
    frame_generator = create_video_frame_generator_with_quality(video_path)
    face_results_iter = iter(face_result.frame_results)
    
    quality_result = quality_scorer.process_video_quality(
        video_info=video_info,
        frame_generator=frame_generator,
        face_results_generator=face_results_iter
    )
    
    print(f"\n=== Face-Integrated Quality Results ===")
    print(f"Mean quality with faces: {quality_result.mean_quality:.1f}/100")
    
    # Analyze face quality contribution
    face_quality_scores = [r.metrics.face_quality for r in quality_result.frame_results]
    mean_face_quality = np.mean([f for f in face_quality_scores if f > 0])
    
    print(f"Mean face quality factor: {mean_face_quality:.2f}")
    print(f"Frames with faces: {sum(1 for r in quality_result.frame_results if r.face_count > 0)}")
    
    return quality_result


def demo_profile_comparison(video_path: Path):
    """Demo different quality profiles on the same video"""
    print(f"\n=== Profile Comparison Demo ===")
    
    video_ingestion = VideoIngestion()
    video_info = video_ingestion.load_video(video_path)
    
    profiles_to_test = [
        QualityProfile.TALKING_HEAD,
        QualityProfile.ACTION,
        QualityProfile.LANDSCAPE,
        QualityProfile.DOCUMENTARY,
        QualityProfile.ADAPTIVE
    ]
    
    results = {}
    
    for profile in profiles_to_test:
        print(f"\nTesting profile: {profile.value}")
        
        # Create scorer with specific profile
        scorer = QualityScoring(
            profile=profile,
            target_fps=10.0,  # Faster processing for comparison
            enable_face_integration=False
        )
        
        # Process video
        frame_generator = create_video_frame_generator_with_quality(video_path)
        result = scorer.process_video_quality(
            video_info=video_info,
            frame_generator=frame_generator
        )
        
        results[profile.value] = result
        print(f"  Mean quality: {result.mean_quality:.1f}")
        print(f"  Processing speed: {result.average_fps:.1f}x")
    
    # Compare results
    print(f"\n=== Profile Comparison Results ===")
    for profile_name, result in results.items():
        print(f"{profile_name:15} | Quality: {result.mean_quality:5.1f} | Speed: {result.average_fps:5.1f}x")
    
    return results


def demo_quality_hotspots(video_path: Path):
    """Demo quality hotspot identification"""
    print(f"\n=== Quality Hotspots Demo ===")
    
    # Get basic quality results
    video_ingestion = VideoIngestion()
    video_info = video_ingestion.load_video(video_path)
    
    scorer = create_quality_scorer(video_info, target_realtime_multiple=10.0)
    frame_generator = create_video_frame_generator_with_quality(video_path)
    
    result = scorer.process_video_quality(
        video_info=video_info,
        frame_generator=frame_generator
    )
    
    # Identify quality hotspots
    hotspots = scorer.get_quality_hotspots(result, top_percent=15.0)
    
    print(f"Identified {len(hotspots)} quality hotspots:")
    for i, (start, end, quality) in enumerate(hotspots):
        duration = end - start
        print(f"  Hotspot {i+1}: {start:.1f}s - {end:.1f}s ({duration:.1f}s) | Quality: {quality:.1f}")
    
    # Get quality segments above threshold
    high_quality_segments = result.get_quality_segments(min_quality=70.0)
    
    print(f"\nHigh quality segments (>70.0):")
    total_duration = 0
    for start, end in high_quality_segments:
        duration = end - start
        total_duration += duration
        print(f"  {start:.1f}s - {end:.1f}s ({duration:.1f}s)")
    
    print(f"Total high-quality duration: {total_duration:.1f}s ({total_duration/video_info.duration*100:.1f}% of video)")
    
    return hotspots


def demo_export_formats(video_path: Path):
    """Demo exporting quality timeline in different formats"""
    print(f"\n=== Export Formats Demo ===")
    
    # Get quality results
    video_ingestion = VideoIngestion()
    video_info = video_ingestion.load_video(video_path)
    
    scorer = create_quality_scorer(video_info, target_realtime_multiple=10.0)
    frame_generator = create_video_frame_generator_with_quality(video_path)
    
    result = scorer.process_video_quality(
        video_info=video_info,
        frame_generator=frame_generator
    )
    
    # Create output directory
    output_dir = Path("quality_analysis_output")
    output_dir.mkdir(exist_ok=True)
    
    # Export in different formats
    formats = ['json', 'csv', 'xml']
    
    for format_type in formats:
        output_file = output_dir / f"quality_timeline.{format_type}"
        scorer.export_quality_timeline(result, output_file, format=format_type)
        
        file_size = output_file.stat().st_size / 1024  # KB
        print(f"Exported {format_type.upper()}: {output_file} ({file_size:.1f} KB)")
    
    print(f"\nAll exports completed in: {output_dir.absolute()}")


def demo_adaptive_profile_selection(video_path: Path):
    """Demo automatic profile selection based on content analysis"""
    print(f"\n=== Adaptive Profile Selection Demo ===")
    
    video_ingestion = VideoIngestion()
    video_info = video_ingestion.load_video(video_path)
    
    # Sample some frames for analysis
    frame_generator = create_video_frame_generator_with_quality(video_path)
    sample_frames = []
    
    for i, (frame, timestamp, frame_index) in enumerate(frame_generator):
        if i % 30 == 0:  # Sample every 30th frame
            sample_frames.append(frame)
        if len(sample_frames) >= 10:  # Limit to 10 samples
            break
    
    print(f"Sampled {len(sample_frames)} frames for content analysis")
    
    # Create scorer for adaptive selection
    scorer = QualityScoring(profile=QualityProfile.ADAPTIVE)
    
    # Select optimal profile
    recommended_profile = scorer.adaptive_profile_selection(
        video_info=video_info,
        sample_frames=sample_frames,
        face_detection_available=False
    )
    
    print(f"Recommended profile: {recommended_profile.value}")
    
    # Compare with default adaptive
    print("\nComparing recommended vs. adaptive profile...")
    
    # Test with recommended profile
    scorer_recommended = QualityScoring(profile=recommended_profile, target_fps=10.0)
    frame_generator = create_video_frame_generator_with_quality(video_path)
    result_recommended = scorer_recommended.process_video_quality(video_info, frame_generator)
    
    # Test with adaptive profile
    scorer_adaptive = QualityScoring(profile=QualityProfile.ADAPTIVE, target_fps=10.0)
    frame_generator = create_video_frame_generator_with_quality(video_path)
    result_adaptive = scorer_adaptive.process_video_quality(video_info, frame_generator)
    
    print(f"Recommended ({recommended_profile.value}): {result_recommended.mean_quality:.1f}")
    print(f"Adaptive: {result_adaptive.mean_quality:.1f}")
    
    return recommended_profile


def demo_performance_analysis(video_path: Path):
    """Demo performance analysis and optimization"""
    print(f"\n=== Performance Analysis Demo ===")
    
    video_ingestion = VideoIngestion()
    video_info = video_ingestion.load_video(video_path)
    
    # Test different performance settings
    test_configs = [
        {"target_fps": 5.0, "workers": 1, "name": "Conservative"},
        {"target_fps": 10.0, "workers": 2, "name": "Balanced"},
        {"target_fps": 15.0, "workers": 4, "name": "Aggressive"},
    ]
    
    for config in test_configs:
        print(f"\nTesting {config['name']} configuration:")
        print(f"  Target FPS: {config['target_fps']}, Workers: {config['workers']}")
        
        scorer = QualityScoring(
            profile=QualityProfile.ADAPTIVE,
            target_fps=config['target_fps'],
            max_workers=config['workers']
        )
        
        start_time = time.time()
        frame_generator = create_video_frame_generator_with_quality(video_path)
        result = scorer.process_video_quality(video_info, frame_generator)
        processing_time = time.time() - start_time
        
        stats = scorer.get_performance_stats()
        
        print(f"  Processing time: {processing_time:.2f}s")
        print(f"  Actual speed: {result.average_fps:.1f}x real-time")
        print(f"  Frames processed: {stats['total_frames_processed']}")
        print(f"  Avg time per frame: {stats['average_time_per_frame']*1000:.1f}ms")


def main():
    if len(sys.argv) != 2:
        print("Usage: python quality_scoring_demo.py <video_path>")
        sys.exit(1)
    
    video_path = Path(sys.argv[1])
    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
    
    print("AutoCut Quality Scoring System Demo")
    print("=" * 50)
    
    try:
        # Run all demos
        basic_result = demo_basic_quality_assessment(video_path)
        
        # Only run face integration if video seems suitable
        if basic_result.mean_quality > 30:  # Reasonable quality threshold
            try:
                demo_face_integration(video_path)
            except Exception as e:
                print(f"Face integration demo failed: {e}")
        
        demo_profile_comparison(video_path)
        demo_quality_hotspots(video_path)
        demo_export_formats(video_path)
        demo_adaptive_profile_selection(video_path)
        demo_performance_analysis(video_path)
        
        print(f"\n=== Demo Complete ===")
        print("Check the 'quality_analysis_output' directory for exported files.")
        
    except Exception as e:
        logger.error("Demo failed", error=str(e))
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
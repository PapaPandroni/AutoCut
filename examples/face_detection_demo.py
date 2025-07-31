#!/usr/bin/env python3
"""
Face Detection Demo for AutoCut

This demo shows how to use the high-performance face detection module
to analyze video files and extract face detection data for quality scoring.

Usage:
    python examples/face_detection_demo.py [video_file] [--mode=balanced] [--target-fps=15]
"""

import sys
import argparse
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from video.ingestion import VideoIngestion
from video.face_detection import (
    create_face_detection_engine,
    create_video_frame_generator,
    ProcessingMode,
    FaceQuality
)
from utils.logging import setup_logging

def format_time(seconds):
    """Format seconds into human readable time"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs:.1f}s"

def print_face_quality_distribution(results):
    """Print distribution of face quality levels"""
    quality_counts = {quality: 0 for quality in FaceQuality}
    
    for frame_result in results.frame_results:
        for face in frame_result.faces:
            quality_counts[face.quality_level] += 1
    
    total_faces = sum(quality_counts.values())
    if total_faces == 0:
        print("  No faces detected")
        return
    
    print("  Face Quality Distribution:")
    for quality, count in quality_counts.items():
        percentage = (count / total_faces) * 100
        print(f"    {quality.name}: {count} faces ({percentage:.1f}%)")

def print_frame_statistics(results):
    """Print frame-level statistics"""
    frames_with_faces = [r for r in results.frame_results if r.faces]
    total_frames = len(results.frame_results)
    frames_with_faces_count = len(frames_with_faces)
    
    print("  Frame Statistics:")
    print(f"    Total frames processed: {total_frames}")
    print(f"    Frames with faces: {frames_with_faces_count} ({frames_with_faces_count/total_frames*100:.1f}%)")
    
    if frames_with_faces:
        avg_faces_per_frame = sum(len(r.faces) for r in frames_with_faces) / len(frames_with_faces)
        print(f"    Average faces per frame (with faces): {avg_faces_per_frame:.1f}")
        
        avg_processing_time = sum(r.processing_time for r in results.frame_results) / len(results.frame_results)
        print(f"    Average processing time per frame: {avg_processing_time*1000:.1f}ms")

def analyze_best_moments(results):
    """Analyze and report the best moments for video cuts"""
    print("\n🎯 Best Moments for Video Cuts:")
    
    # Find frames with high-quality faces
    high_quality_frames = []
    for frame_result in results.frame_results:
        if frame_result.faces:
            best_face = max(frame_result.faces, key=lambda f: f.quality_score)
            if best_face.quality_score >= 0.7:  # High quality threshold
                high_quality_frames.append((frame_result, best_face))
    
    if not high_quality_frames:
        print("  No high-quality face moments found")
        return
    
    # Sort by quality score
    high_quality_frames.sort(key=lambda x: x[1].quality_score, reverse=True)
    
    print(f"  Found {len(high_quality_frames)} high-quality face moments:")
    
    # Show top 5 moments
    for i, (frame_result, best_face) in enumerate(high_quality_frames[:5]):
        timestamp = frame_result.timestamp
        quality_score = best_face.quality_score
        quality_level = best_face.quality_level.name
        face_size = best_face.relative_size
        confidence = best_face.confidence
        
        print(f"    {i+1}. Time: {format_time(timestamp)} | "
              f"Quality: {quality_score:.2f} ({quality_level}) | "
              f"Size: {face_size:.3f} | Confidence: {confidence:.2f}")

def main():
    parser = argparse.ArgumentParser(description="Face Detection Demo for AutoCut")
    parser.add_argument("video_file", nargs="?", help="Path to video file")
    parser.add_argument("--mode", default="balanced", 
                       choices=["realtime", "balanced", "quality"],
                       help="Processing quality mode")
    parser.add_argument("--target-fps", type=float, default=15.0,
                       help="Target processing FPS")
    parser.add_argument("--realtime-multiple", type=float, default=15.0,
                       help="Target realtime processing multiple (15x = 15x real-time)")
    parser.add_argument("--log-level", default="INFO",
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="Logging level")
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(level=args.log_level, structured=True)
    
    if not args.video_file:
        print("🎬 AutoCut Face Detection Demo")
        print("\nUsage: python examples/face_detection_demo.py <video_file> [options]")
        print("\nExample:")
        print("  python examples/face_detection_demo.py my_video.mp4 --mode=quality --target-fps=10")
        return
    
    video_path = Path(args.video_file)
    if not video_path.exists():
        print(f"❌ Error: Video file not found: {video_path}")
        return
    
    print("🎬 AutoCut Face Detection Demo")
    print(f"📹 Processing: {video_path.name}")
    print(f"⚙️  Mode: {args.mode}")
    print(f"🎯 Target: {args.realtime_multiple}x real-time processing")
    print()
    
    try:
        # Load video information
        print("📊 Loading video information...")
        ingestion = VideoIngestion()
        video_info = ingestion.load_video(video_path)
        
        # Display video info
        duration = format_time(video_info.duration)
        resolution = f"{video_info.resolution[0]}x{video_info.resolution[1]}"
        fps = video_info.primary_video_stream.fps if video_info.primary_video_stream else "Unknown"
        codec = video_info.primary_video_stream.codec.value if video_info.primary_video_stream else "Unknown"
        
        print(f"  Duration: {duration}")
        print(f"  Resolution: {resolution}")
        print(f"  FPS: {fps}")
        print(f"  Codec: {codec}")
        print(f"  Hardware Decodable: {'Yes' if video_info.hardware_decodable else 'No'}")
        print()
        
        # Create face detection engine
        print("🧠 Initializing face detection engine...")
        engine = create_face_detection_engine(
            video_info=video_info,
            target_realtime_multiple=args.realtime_multiple,
            quality_mode=args.mode
        )
        print()
        
        # Process video
        print("🔍 Processing video for face detection...")
        start_time = time.time()
        
        processed_frames = 0
        def progress_callback(frame_count, timestamp):
            nonlocal processed_frames
            processed_frames = frame_count
            if frame_count % 50 == 0:  # Update every 50 frames
                elapsed = time.time() - start_time
                progress = timestamp / video_info.duration if video_info.duration > 0 else 0
                print(f"  Progress: {progress*100:.1f}% | "
                      f"Frames: {frame_count} | "
                      f"Time: {format_time(elapsed)}")
        
        # Create frame generator and process
        frame_generator = create_video_frame_generator(video_path)
        results = engine.process_video_frames(
            video_info=video_info,
            frame_generator=frame_generator,
            progress_callback=progress_callback
        )
        
        processing_time = time.time() - start_time
        
        # Display results
        print()
        print("✅ Processing Complete!")
        print(f"⏱️  Total processing time: {format_time(processing_time)}")
        print(f"🚀 Processing speed: {results.average_fps:.1f} FPS")
        
        realtime_multiple = (video_info.duration / processing_time) if processing_time > 0 else 0
        print(f"⚡ Real-time multiple: {realtime_multiple:.1f}x")
        print()
        
        # Detailed statistics
        print("📈 Detection Statistics:")
        print(f"  Total faces detected: {sum(r.total_faces for r in results.frame_results)}")
        print(f"  Faces per second: {results.faces_per_second:.1f}")
        print(f"  Overall quality score: {results.overall_quality_score:.2f}")
        
        print_frame_statistics(results)
        print()
        print_face_quality_distribution(results)
        
        # Best moments analysis
        analyze_best_moments(results)
        
        # Performance stats
        print()
        print("⚡ Performance Statistics:")
        perf_stats = engine.get_performance_stats()
        print(f"  Average time per frame: {perf_stats['average_time_per_frame']*1000:.1f}ms")
        print(f"  Estimated processing FPS: {perf_stats['estimated_fps']:.1f}")
        print(f"  Target FPS: {perf_stats['target_fps']:.1f}")
        print(f"  Processing mode: {perf_stats['mode']}")
        
        # Save results option
        output_file = video_path.with_suffix('.face_detection.json')
        print()
        response = input(f"💾 Save detailed results to {output_file.name}? (y/N): ")
        if response.lower() in ['y', 'yes']:
            import json
            with open(output_file, 'w') as f:
                json.dump(results.to_dict(), f, indent=2)
            print(f"✅ Results saved to {output_file}")
        
    except Exception as e:
        logger.error("Face detection demo failed", error=str(e))
        print(f"❌ Error: {e}")
        return 1
    
    print()
    print("🎬 Demo completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
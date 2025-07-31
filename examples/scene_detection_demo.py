#!/usr/bin/env python3
"""
Scene Detection Demo for AutoCut

This script demonstrates how to use the scene detection module to analyze videos
and identify scene changes with different algorithms and processing modes.
"""

import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from video.scene_detection import (
    SceneDetection, 
    SceneDetectionAlgorithm, 
    ProcessingMode
)
from utils.logging import setup_logging


def main():
    """Main demo function"""
    # Setup logging
    logger = setup_logging(level="INFO")
    
    # Example video file path (replace with your actual video file)
    video_path = "/path/to/your/video.mp4"
    
    if not Path(video_path).exists():
        print(f"Please update the video_path variable to point to an actual video file.")
        print(f"Current path: {video_path}")
        return
    
    print("=== AutoCut Scene Detection Demo ===\n")
    
    # Demo 1: Speed mode with histogram detection (fastest)
    print("1. Speed Mode - Histogram Detection (15x+ real-time)")
    detector_speed = SceneDetection(ProcessingMode.SPEED)
    
    start_time = time.time()
    result_speed = detector_speed.detect_scenes(
        video_path, 
        SceneDetectionAlgorithm.HISTOGRAM
    )
    end_time = time.time()
    
    if result_speed.success:
        print(f"   ✓ Detected {result_speed.scene_count} scenes")
        print(f"   ✓ Processing time: {end_time - start_time:.2f}s")
        print(f"   ✓ Speed: {result_speed.processing_speed_multiplier:.1f}x real-time")
        print(f"   ✓ Frames processed: {result_speed.frames_processed} (skipped: {result_speed.frames_skipped})")
        
        if result_speed.scene_changes:
            print("   Scene changes:")
            for change in result_speed.scene_changes[:3]:  # Show first 3
                print(f"     - {change.timestamp:.1f}s (confidence: {change.confidence:.2f})")
            if len(result_speed.scene_changes) > 3:
                print(f"     ... and {len(result_speed.scene_changes) - 3} more")
    else:
        print(f"   ✗ Failed: {result_speed.errors}")
    
    print()
    
    # Demo 2: Balanced mode with multiple algorithms
    print("2. Balanced Mode - Multiple Algorithms (10x real-time)")
    detector_balanced = SceneDetection(ProcessingMode.BALANCED)
    
    start_time = time.time()
    result_balanced = detector_balanced.detect_scenes(
        video_path,
        SceneDetectionAlgorithm.COMBINED  # Uses multiple algorithms
    )
    end_time = time.time()
    
    if result_balanced.success:
        print(f"   ✓ Detected {result_balanced.scene_count} scenes")
        print(f"   ✓ Processing time: {end_time - start_time:.2f}s")
        print(f"   ✓ Speed: {result_balanced.processing_speed_multiplier:.1f}x real-time")
        print(f"   ✓ Frames processed: {result_balanced.frames_processed} (skipped: {result_balanced.frames_skipped})")
        
        # Show algorithm breakdown
        algorithms_used = set(change.algorithm for change in result_balanced.scene_changes)
        print(f"   ✓ Algorithms used: {', '.join(alg.value for alg in algorithms_used)}")
    else:
        print(f"   ✗ Failed: {result_balanced.errors}")
    
    print()
    
    # Demo 3: Batch processing multiple videos
    print("3. Batch Processing Demo")
    video_paths = [video_path]  # Add more paths if you have them
    
    if len(video_paths) == 1:
        print("   (Only one video available for batch demo)")
    
    start_time = time.time()
    batch_results = detector_speed.batch_detect_scenes(
        video_paths,
        SceneDetectionAlgorithm.HISTOGRAM,
        max_workers=2
    )
    end_time = time.time()
    
    successful = sum(1 for r in batch_results if r.success)
    total_scenes = sum(r.scene_count for r in batch_results if r.success)
    
    print(f"   ✓ Processed {len(video_paths)} videos in {end_time - start_time:.2f}s")
    print(f"   ✓ Success rate: {successful}/{len(video_paths)}")
    print(f"   ✓ Total scenes detected: {total_scenes}")
    
    print()
    
    # Demo 4: Scene segments extraction
    print("4. Scene Segments Analysis")
    if result_speed.success:
        segments = result_speed.get_scene_segments()
        print(f"   Video duration: {result_speed.video_info.duration:.1f}s")
        print(f"   Average scene duration: {result_speed.average_scene_duration:.1f}s")
        print("   Scene segments:")
        
        for i, (start, end) in enumerate(segments[:5]):  # Show first 5 segments
            duration = end - start
            print(f"     Scene {i+1}: {start:.1f}s - {end:.1f}s ({duration:.1f}s)")
        
        if len(segments) > 5:
            print(f"     ... and {len(segments) - 5} more scenes")
    
    print()
    
    # Demo 5: Export results
    print("5. Export Results")
    if result_balanced.success:
        result_dict = result_balanced.to_dict()
        
        # Save to JSON (optional)
        import json
        output_file = Path("scene_detection_results.json")
        with open(output_file, 'w') as f:
            json.dump(result_dict, f, indent=2)
        
        print(f"   ✓ Results exported to: {output_file}")
        print(f"   ✓ Contains {len(result_dict['scene_changes'])} scene changes")
        print(f"   ✓ Processing metadata included")
    
    print("\n=== Demo Complete ===")
    print("Tips for optimal performance:")
    print("- Use SPEED mode for quick analysis (15x+ real-time)")
    print("- Use BALANCED mode for good quality/speed trade-off")
    print("- Use QUALITY mode for detailed analysis")
    print("- Use PRECISION mode for maximum accuracy")
    print("- Enable hardware acceleration on M1/M2 Macs for better performance")


if __name__ == "__main__":
    main()
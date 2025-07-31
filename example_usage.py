#!/usr/bin/env python3
"""
AutoCut Prototype Usage Examples

This script demonstrates various ways to use the AutoCut prototype
both from command line and programmatically.
"""

import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from autocut_prototype import AutoCutPrototype
from src.core.timeline import EditingStyle
from src.core.quality_scoring import QualityProfile
from src.utils.logging import setup_logging


def example_basic_usage():
    """Basic usage example - process a video with default settings"""
    print("=" * 60)
    print("EXAMPLE 1: Basic Usage")
    print("=" * 60)
    
    # Initialize the prototype
    prototype = AutoCutPrototype()
    
    # Example with a hypothetical video file
    input_video = Path("example_video.mp4")
    output_video = Path("example_edited.mp4")
    
    print(f"Input:  {input_video}")
    print(f"Output: {output_video}")
    print("Processing with default settings...")
    
    if input_video.exists():
        # Process the video
        results = prototype.process_video(
            input_path=input_video,
            output_path=output_video
        )
        
        if results['success']:
            stats = results['processing_stats']
            print(f"✅ Success! Processed in {stats['total_time']:.2f}s")
            print(f"   Speed factor: {stats['overall_speed_factor']:.1f}x real-time")
            print(f"   Timeline segments: {results['timeline']['segment_count']}")
        else:
            print(f"❌ Failed: {results['error']}")
    else:
        print("ℹ️  Video file not found - this is just an example")
        print("   Use a real video file path to test")


def example_advanced_settings():
    """Advanced usage example with custom settings"""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Advanced Settings")
    print("=" * 60)
    
    prototype = AutoCutPrototype()
    
    input_video = Path("music_video.mp4")
    output_video = Path("music_video_aggressive_edit.mp4")
    
    print(f"Input:  {input_video}")
    print(f"Output: {output_video}")
    print("Settings:")
    print("  - Style: Aggressive (frequent cuts)")
    print("  - Profile: Action (motion-optimized)")
    print("  - Performance: Quality mode")
    print("  - Export: Timeline and statistics")
    
    if input_video.exists():
        # Custom progress callback
        def progress_callback(message, progress):
            print(f"  Progress: {progress:3.0f}% - {message}")
        
        # Advanced processing options
        export_options = {
            'enable_face_detection': True,
            'enable_quality_scoring': True,
            'render_quality': 'high',
            'output_format': 'mp4',
            'export_timeline': True,
            'export_stats': True,
            'timeline_format': 'json',
            'export_dir': './advanced_exports'
        }
        
        results = prototype.process_video(
            input_path=input_video,
            output_path=output_video,
            editing_style=EditingStyle.AGGRESSIVE,
            quality_profile=QualityProfile.ACTION,
            performance_mode="quality",
            export_options=export_options,
            progress_callback=progress_callback
        )
        
        if results['success']:
            print("✅ Advanced processing completed!")
            
            # Print detailed results
            timeline = results['timeline']
            print(f"   Timeline segments: {timeline['segment_count']}")
            print(f"   Beat synchronization: {timeline['beat_sync_percentage']:.1f}%")
            print(f"   Scene respect: {timeline['scene_respect_percentage']:.1f}%")
            
            if results['export_results']:
                print("   Exported files:")
                for export_type, path in results['export_results'].items():
                    print(f"     {export_type}: {path}")
        else:
            print(f"❌ Advanced processing failed: {results['error']}")
    else:
        print("ℹ️  Video file not found - this is just an example")


def example_analysis_only():
    """Example of running analysis without rendering"""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Analysis Only")
    print("=" * 60)
    
    prototype = AutoCutPrototype()
    
    input_video = Path("documentary.mp4")
    
    print(f"Input: {input_video}")
    print("Mode: Analysis only (no rendering)")
    print("Exports: Timeline, audio analysis, quality data")
    
    if input_video.exists():
        export_options = {
            'export_timeline': True,
            'export_audio_analysis': True,
            'export_quality_timeline': True,
            'export_stats': True,
            'timeline_format': 'json',
            'quality_format': 'csv',
            'export_dir': './analysis_exports'
        }
        
        results = prototype.process_video(
            input_path=input_video,
            output_path=None,  # No rendering
            editing_style=EditingStyle.SMOOTH,
            quality_profile=QualityProfile.DOCUMENTARY,
            performance_mode="balanced",
            export_options=export_options
        )
        
        if results['success']:
            print("✅ Analysis completed!")
            
            # Show analysis results
            audio = results['audio_analysis']
            scenes = results['scene_detection']
            timeline = results['timeline']
            
            print(f"   Audio: {audio['bpm']:.1f} BPM, {audio['beat_count']} beats")
            print(f"   Scenes: {scenes['scene_count']} detected")
            print(f"   Timeline: {timeline['segment_count']} segments")
            
            if results['quality_scoring']:
                quality = results['quality_scoring']
                print(f"   Quality: {quality['mean_quality']:.1f} average")
            
            print("   Exported analysis data - review before rendering")
        else:
            print(f"❌ Analysis failed: {results['error']}")
    else:
        print("ℹ️  Video file not found - this is just an example")


def example_demo_mode():
    """Example of using demo mode with mock data"""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Demo Mode")
    print("=" * 60)
    
    prototype = AutoCutPrototype()
    
    print("Running demo mode with mock data (no video file needed)")
    print("Mock video: 90 seconds, 1920x1080")
    
    # Generate mock data
    mock_data = prototype.generate_mock_data(duration=90.0, resolution=(1920, 1080))
    
    print("✅ Mock data generated!")
    print(f"   Duration: {mock_data['video_info'].duration}s")
    print(f"   Resolution: {mock_data['video_info'].resolution[0]}x{mock_data['video_info'].resolution[1]}")
    print(f"   Audio BPM: {mock_data['audio_analysis'].bpm:.1f}")
    print(f"   Beats: {len(mock_data['audio_analysis'].beats)}")
    print(f"   Scenes: {len(mock_data['scene_detection'].scene_changes)}")
    print(f"   Timeline segments: {mock_data['timeline'].segment_count}")
    print(f"   Beat sync: {mock_data['timeline'].beat_sync_percentage:.1f}%")
    print()
    print("This demonstrates the complete AutoCut pipeline structure")
    print("without requiring an actual video file.")


def example_benchmark():
    """Example of running performance benchmarks"""
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Performance Benchmark")
    print("=" * 60)
    
    prototype = AutoCutPrototype()
    
    print("Running performance benchmark with test cases...")
    
    # Custom test cases
    test_cases = [
        {
            'name': 'Short_1080p',
            'duration': 30.0,
            'resolution': (1920, 1080),
            'fps': 30.0,
            'expected_analysis_speed': 12.0
        },
        {
            'name': 'Medium_720p',
            'duration': 120.0,
            'resolution': (1280, 720),
            'fps': 30.0,
            'expected_analysis_speed': 15.0
        }
    ]
    
    benchmark_results = prototype.benchmark_performance(test_cases)
    
    print("✅ Benchmark completed!")
    
    summary = benchmark_results['summary']
    print(f"   Tests passed: {summary['tests_passed']}/{summary['total_tests']}")
    print(f"   Average analysis speed: {summary['average_analysis_speed']:.1f}x real-time")
    print(f"   Average lossless render: {summary['average_lossless_render_speed']:.1f}x real-time")
    print(f"   Total benchmark time: {summary['total_benchmark_time']:.2f}s")
    
    print("\n   Detailed results:")
    for result in benchmark_results['test_results']:
        test = result['test_case']
        status = "✅ PASS" if result['meets_performance_target'] else "❌ FAIL"
        print(f"     {test['name']:<15} {result['analysis_speed_factor']:>6.1f}x  {status}")


def example_batch_processing():
    """Example of processing multiple videos"""
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Batch Processing")
    print("=" * 60)
    
    prototype = AutoCutPrototype()
    
    # Example video list
    video_files = [
        "video1.mp4",
        "video2.mp4",
        "video3.mp4"
    ]
    
    print(f"Batch processing {len(video_files)} videos...")
    print("Configuration:")
    print("  - Style: Adaptive")
    print("  - Quality: Lossless")
    print("  - Performance: Balanced")
    
    successful = 0
    failed = 0
    
    for i, video_file in enumerate(video_files, 1):
        input_path = Path(video_file)
        output_path = Path(f"{input_path.stem}_edited{input_path.suffix}")
        
        print(f"\n[{i}/{len(video_files)}] Processing: {video_file}")
        
        if input_path.exists():
            try:
                results = prototype.process_video(
                    input_path=input_path,
                    output_path=output_path,
                    editing_style=EditingStyle.ADAPTIVE,
                    performance_mode="balanced"
                )
                
                if results['success']:
                    print(f"  ✅ Completed in {results['processing_stats']['total_time']:.1f}s")
                    successful += 1
                else:
                    print(f"  ❌ Failed: {results['error']}")
                    failed += 1
                    
            except Exception as e:
                print(f"  ❌ Error: {e}")
                failed += 1
        else:
            print(f"  ⚠️  File not found - skipping")
            failed += 1
    
    print(f"\nBatch processing summary:")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Total: {len(video_files)}")


def main():
    """Run all examples"""
    
    # Setup logging
    setup_logging(level="INFO")
    
    print("🎬 AutoCut Prototype Usage Examples")
    print()
    print("This script demonstrates various ways to use the AutoCut prototype.")
    print("Note: Examples use hypothetical video files - replace with real paths to test.")
    
    try:
        # Run all examples
        example_basic_usage()
        example_advanced_settings()
        example_analysis_only()
        example_demo_mode()
        example_benchmark()
        example_batch_processing()
        
        print("\n" + "=" * 60)
        print("ALL EXAMPLES COMPLETED")
        print("=" * 60)
        print()
        print("Key takeaways:")
        print("1. Basic usage requires just input/output paths")
        print("2. Advanced settings allow fine-tuning for different content types")
        print("3. Analysis-only mode is useful for reviewing before rendering")
        print("4. Demo mode works without video files for testing")
        print("5. Benchmarks help validate system performance")
        print("6. Batch processing handles multiple videos efficiently")
        print()
        print("For more information, see:")
        print("  - PROTOTYPE_USAGE.md for detailed documentation")
        print("  - autocut_config_example.yaml for configuration options")
        print("  - Run: python autocut_prototype.py --help")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Examples interrupted by user")
    
    except Exception as e:
        print(f"\n\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
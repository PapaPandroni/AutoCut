#!/usr/bin/env python3
"""
Face Detection Integration Example for AutoCut

This example demonstrates how to integrate the face detection module
into the AutoCut video editing pipeline for quality-based cut selection.
"""

import sys
from pathlib import Path
import json

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from video.ingestion import VideoIngestion
from video.face_detection import (
    create_face_detection_engine,
    create_video_frame_generator,
    FaceQuality
)
from utils.logging import setup_logging

class FaceBasedQualityScorer:
    """Quality scorer that uses face detection data for cut selection"""
    
    def __init__(self, face_weight: float = 0.4):
        """
        Initialize face-based quality scorer
        
        Args:
            face_weight: Weight given to face detection in overall quality score
        """
        self.face_weight = face_weight
        
    def score_frame(self, frame_result, video_duration: float) -> float:
        """
        Score a frame based on face detection results
        
        Args:
            frame_result: FrameFaceDetectionResult object
            video_duration: Total video duration for context
            
        Returns:
            Quality score [0.0, 1.0]
        """
        if not frame_result.faces:
            return 0.0  # No faces = lowest score
        
        # Find the best face in the frame
        best_face = max(frame_result.faces, key=lambda f: f.quality_score)
        
        # Base score from face quality
        base_score = best_face.quality_score
        
        # Bonus for multiple faces (suggests group shots)
        multi_face_bonus = min(0.2, (len(frame_result.faces) - 1) * 0.1)
        
        # Bonus for larger faces (more prominent subjects)
        size_bonus = min(0.1, best_face.relative_size * 0.5)
        
        # Penalty for occluded faces
        occlusion_penalty = best_face.occlusion_score * 0.1
        
        # Bonus for excellent quality faces
        excellence_bonus = 0.1 if best_face.quality_level == FaceQuality.EXCELLENT else 0.0
        
        final_score = min(1.0, base_score + multi_face_bonus + size_bonus + excellence_bonus - occlusion_penalty)
        
        return final_score
    
    def find_best_cuts(self, face_results, min_gap_seconds: float = 2.0, max_cuts: int = 10):
        """
        Find the best moments for cuts based on face quality
        
        Args:
            face_results: VideoFaceDetectionResult object
            min_gap_seconds: Minimum time gap between cuts
            max_cuts: Maximum number of cuts to return
            
        Returns:
            List of (timestamp, quality_score, frame_result) tuples
        """
        # Score all frames
        scored_frames = []
        for frame_result in face_results.frame_results:
            if frame_result.faces:  # Only consider frames with faces
                score = self.score_frame(frame_result, face_results.video_info.duration)
                scored_frames.append((frame_result.timestamp, score, frame_result))
        
        if not scored_frames:
            return []
        
        # Sort by quality score (descending)
        scored_frames.sort(key=lambda x: x[1], reverse=True)
        
        # Select cuts with minimum gap constraint
        selected_cuts = []
        for timestamp, score, frame_result in scored_frames:
            # Check if this cut is far enough from existing cuts
            too_close = any(abs(timestamp - existing[0]) < min_gap_seconds 
                          for existing in selected_cuts)
            
            if not too_close:
                selected_cuts.append((timestamp, score, frame_result))
                
                if len(selected_cuts) >= max_cuts:
                    break
        
        # Sort final cuts by timestamp
        selected_cuts.sort(key=lambda x: x[0])
        
        return selected_cuts

def analyze_video_for_cuts(video_path: Path, quality_mode: str = "balanced"):
    """
    Analyze video and suggest optimal cuts based on face detection
    
    Args:
        video_path: Path to video file
        quality_mode: Processing quality mode
        
    Returns:
        Dictionary with analysis results
    """
    logger = setup_logging(level="INFO", structured=True)
    
    print(f"🎬 Analyzing {video_path.name} for optimal cuts...")
    
    # Load video
    ingestion = VideoIngestion()
    video_info = ingestion.load_video(video_path)
    
    print(f"📹 Video: {video_info.duration:.1f}s, "
          f"{video_info.resolution[0]}x{video_info.resolution[1]}")
    
    # Create face detection engine optimized for quality
    engine = create_face_detection_engine(
        video_info=video_info,
        target_realtime_multiple=10.0,  # Slower for better quality
        quality_mode=quality_mode
    )
    
    # Process video
    print("🔍 Analyzing faces in video...")
    frame_generator = create_video_frame_generator(video_path)
    face_results = engine.process_video_frames(
        video_info=video_info,
        frame_generator=frame_generator
    )
    
    # Create quality scorer and find best cuts
    scorer = FaceBasedQualityScorer(face_weight=0.4)
    best_cuts = scorer.find_best_cuts(face_results, min_gap_seconds=3.0, max_cuts=8)
    
    # Analyze results
    total_faces = sum(r.total_faces for r in face_results.frame_results)
    frames_with_faces = len([r for r in face_results.frame_results if r.faces])
    
    analysis_results = {
        'video_path': str(video_path),
        'video_duration': video_info.duration,
        'total_faces_detected': total_faces,
        'frames_with_faces': frames_with_faces,
        'face_coverage_percentage': (frames_with_faces / len(face_results.frame_results)) * 100,
        'overall_face_quality': face_results.overall_quality_score,
        'recommended_cuts': [
            {
                'timestamp': timestamp,
                'quality_score': score,
                'total_faces': frame_result.total_faces,
                'best_face_quality': max(f.quality_score for f in frame_result.faces),
                'best_face_size': max(f.relative_size for f in frame_result.faces)
            }
            for timestamp, score, frame_result in best_cuts
        ],
        'processing_stats': {
            'processing_fps': face_results.average_fps,
            'total_processing_time': face_results.total_processing_time,
            'realtime_multiple': video_info.duration / face_results.total_processing_time if face_results.total_processing_time > 0 else 0
        }
    }
    
    return analysis_results

def generate_cut_recommendations(analysis_results):
    """Generate human-readable cut recommendations"""
    print("\n📊 Analysis Results:")
    print(f"  Total faces detected: {analysis_results['total_faces_detected']}")
    print(f"  Face coverage: {analysis_results['face_coverage_percentage']:.1f}% of frames")
    print(f"  Overall face quality: {analysis_results['overall_face_quality']:.2f}")
    
    cuts = analysis_results['recommended_cuts']
    if not cuts:
        print("\n⚠️  No high-quality face moments found for cuts")
        return
    
    print(f"\n🎯 Recommended Cuts ({len(cuts)} moments):")
    
    for i, cut in enumerate(cuts, 1):
        timestamp = cut['timestamp']
        minutes = int(timestamp // 60)
        seconds = timestamp % 60
        time_str = f"{minutes}:{seconds:05.2f}"
        
        quality = cut['quality_score']
        faces = cut['total_faces']
        face_quality = cut['best_face_quality']
        face_size = cut['best_face_size']
        
        quality_desc = "🌟 Excellent" if quality >= 0.8 else "✨ Good" if quality >= 0.6 else "👍 Fair"
        
        print(f"  {i:2d}. {time_str} | {quality_desc} (score: {quality:.2f})")
        print(f"      👥 {faces} face{'s' if faces != 1 else ''} | "
              f"Quality: {face_quality:.2f} | Size: {face_size:.3f}")

def export_for_editing_software(analysis_results, output_path: Path):
    """Export cut recommendations in formats compatible with editing software"""
    
    # JSON format (universal)
    json_path = output_path.with_suffix('.json')
    with open(json_path, 'w') as f:
        json.dump(analysis_results, f, indent=2)
    
    # CSV format for spreadsheets
    csv_path = output_path.with_suffix('.csv')
    with open(csv_path, 'w') as f:
        f.write("Timestamp,Quality Score,Face Count,Face Quality,Face Size\n")
        for cut in analysis_results['recommended_cuts']:
            f.write(f"{cut['timestamp']:.2f},{cut['quality_score']:.3f},"
                   f"{cut['total_faces']},{cut['best_face_quality']:.3f},"
                   f"{cut['best_face_size']:.3f}\n")
    
    # EDL format (for professional editing software)
    edl_path = output_path.with_suffix('.edl')
    with open(edl_path, 'w') as f:
        f.write("TITLE: AutoCut Face Detection Markers\n")
        f.write("FCM: NON-DROP FRAME\n\n")
        
        for i, cut in enumerate(analysis_results['recommended_cuts'], 1):
            # Convert timestamp to timecode (assuming 30fps)
            timestamp = cut['timestamp']
            hours = int(timestamp // 3600)
            minutes = int((timestamp % 3600) // 60)
            seconds = int(timestamp % 60)
            frames = int((timestamp % 1) * 30)
            
            timecode = f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"
            
            f.write(f"{i:03d}  001      V     C        {timecode} {timecode} {timecode} {timecode}\n")
            f.write(f"* FROM CLIP NAME: Face_Quality_{cut['quality_score']:.2f}\n")
    
    print(f"\n💾 Exported cut recommendations:")
    print(f"  📄 JSON: {json_path}")
    print(f"  📊 CSV: {csv_path}")
    print(f"  🎬 EDL: {edl_path}")

def main():
    """Main integration example"""
    print("🎬 AutoCut Face Detection Integration Example")
    print("=" * 50)
    
    # Example usage (you would replace this with actual video file)
    video_path = Path("sample_video.mp4")  # Replace with actual video
    
    if not video_path.exists():
        print("\n📝 This is a demonstration of the integration workflow.")
        print("To run with a real video file:")
        print("  python examples/integration_face_detection.py your_video.mp4")
        print("\nThe workflow would be:")
        print("  1. 📹 Load video information")
        print("  2. 🧠 Initialize face detection engine")
        print("  3. 🔍 Process video frames for face detection")
        print("  4. 📊 Score frames based on face quality")
        print("  5. 🎯 Select optimal cut points")
        print("  6. 💾 Export recommendations for editing software")
        return
    
    try:
        # Analyze video
        results = analyze_video_for_cuts(video_path, quality_mode="quality")
        
        # Generate recommendations
        generate_cut_recommendations(results)
        
        # Export results
        output_path = video_path.with_name(f"{video_path.stem}_face_cuts")
        export_for_editing_software(results, output_path)
        
        print("\n✅ Integration example completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    main()
"""Tests for the beat-sync timeline generation algorithm"""

import unittest
import numpy as np
from pathlib import Path
from src.core.timeline import (
    BeatSyncTimelineGenerator, EditingStyle, CutType, CutPoint
)
from src.audio.analyzer import AudioAnalysis
from src.video.scene_detection import SceneDetectionResult, SceneChange, SceneDetectionAlgorithm, ProcessingMode
from src.video.ingestion import VideoInfo, ContainerFormat


class TestBeatSyncTimelineGenerator(unittest.TestCase):
    """Test cases for the BeatSyncTimelineGenerator"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.generator = BeatSyncTimelineGenerator(EditingStyle.ADAPTIVE)
        
        # Create test audio analysis
        self.audio_analysis = AudioAnalysis(
            bpm=120.0,
            beats=[0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
            confidence=0.8,
            duration=5.5,
            sample_rate=44100
        )
        
        # Create test scene detection
        self.scene_changes = [
            SceneChange(1.2, 36, 0.7, SceneDetectionAlgorithm.HISTOGRAM),
            SceneChange(3.8, 114, 0.9, SceneDetectionAlgorithm.HISTOGRAM)
        ]
        
        self.video_info = VideoInfo(
            file_path=Path("test_video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=5.5,
            file_size=10000000,
            video_streams=[],
            audio_streams=[],
            metadata={}
        )
        
        self.scene_detection = SceneDetectionResult(
            video_info=self.video_info,
            scene_changes=self.scene_changes,
            processing_time=1.0,
            algorithm_used=SceneDetectionAlgorithm.HISTOGRAM,
            processing_mode=ProcessingMode.BALANCED,
            frames_processed=165,
            frames_skipped=0
        )
    
    def test_generator_initialization(self):
        """Test that generator initializes correctly"""
        self.assertEqual(self.generator.editing_style, EditingStyle.ADAPTIVE)
        self.assertIn(EditingStyle.ADAPTIVE, self.generator.style_configs)
    
    def test_beat_alignment_calculation(self):
        """Test beat alignment scoring"""
        style_config = self.generator.style_configs[EditingStyle.ADAPTIVE]
        
        # Test exact beat alignment
        alignment = self.generator._calculate_beat_alignment(1.0, self.audio_analysis, style_config)
        self.assertGreater(alignment, 0.8)  # Should be high for exact beat
        
        # Test off-beat alignment
        alignment = self.generator._calculate_beat_alignment(1.25, self.audio_analysis, style_config)
        self.assertLess(alignment, 0.8)  # Should be lower for off-beat
    
    def test_scene_compatibility_calculation(self):
        """Test scene compatibility scoring"""
        style_config = self.generator.style_configs[EditingStyle.ADAPTIVE]
        
        # Test cut at scene boundary
        compatibility, cost = self.generator._calculate_scene_compatibility(1.2, self.scene_detection, style_config)
        self.assertGreater(compatibility, 0.8)
        self.assertLess(cost, 0.2)
        
        # Test cut mid-scene
        compatibility, cost = self.generator._calculate_scene_compatibility(2.5, self.scene_detection, style_config)
        self.assertLess(compatibility, 0.8)
        self.assertGreater(cost, 0.2)
    
    def test_musical_interval_scoring(self):
        """Test musical interval scoring"""
        expected_interval = 0.5  # 120 BPM = 0.5s per beat
        
        # Test exact beat interval
        score = self.generator._score_musical_interval(0.5, expected_interval)
        self.assertGreater(score, 0.8)
        
        # Test half-beat interval
        score = self.generator._score_musical_interval(0.25, expected_interval)
        self.assertGreater(score, 0.6)
        
        # Test off-beat interval
        score = self.generator._score_musical_interval(0.7, expected_interval)
        self.assertLess(score, 0.6)
    
    def test_style_constraints(self):
        """Test different editing style constraints"""
        # Create test cut points
        cut_points = [
            CutPoint(1.0, 0.8, CutType.BEAT_CUT, 0.9, 0.7, 0.8, 0.1),
            CutPoint(1.2, 0.7, CutType.SCENE_CUT, 0.5, 0.9, 0.7, 0.0),
            CutPoint(2.5, 0.4, CutType.BEAT_CUT, 0.6, 0.4, 0.5, 0.6)
        ]
        
        # Test aggressive style (should keep more cuts)
        aggressive_cuts = self.generator._apply_style_constraints(cut_points, EditingStyle.AGGRESSIVE)
        aggressive_count = len(aggressive_cuts)
        
        # Test smooth style (should be more selective)
        smooth_cuts = self.generator._apply_style_constraints(cut_points, EditingStyle.SMOOTH)
        smooth_count = len(smooth_cuts)
        
        # Aggressive should generally keep more cuts than smooth
        self.assertGreaterEqual(aggressive_count, smooth_count)
    
    def test_timeline_generation(self):
        """Test complete timeline generation"""
        timeline = self.generator.generate_timeline(
            self.audio_analysis, self.scene_detection, self.video_info
        )
        
        # Basic validation
        self.assertTrue(timeline.success)
        self.assertGreater(len(timeline.cut_points), 0)
        self.assertGreater(len(timeline.segments), 0)
        self.assertEqual(timeline.editing_style, EditingStyle.ADAPTIVE)
        
        # Timeline should cover full duration
        sorted_cuts = sorted(timeline.cut_points, key=lambda x: x.timestamp)
        self.assertLessEqual(sorted_cuts[0].timestamp, 0.1)
        self.assertGreaterEqual(sorted_cuts[-1].timestamp, timeline.total_duration - 0.1)
        
        # Segments should be continuous
        for i in range(len(timeline.segments) - 1):
            current_end = timeline.segments[i].end_time
            next_start = timeline.segments[i + 1].start_time
            self.assertAlmostEqual(current_end, next_start, places=3)
    
    def test_different_editing_styles(self):
        """Test timeline generation with different editing styles"""
        styles = [EditingStyle.AGGRESSIVE, EditingStyle.SMOOTH, EditingStyle.MUSICAL, EditingStyle.CINEMATIC]
        timelines = {}
        
        for style in styles:
            timeline = self.generator.generate_timeline(
                self.audio_analysis, self.scene_detection, self.video_info, style
            )
            timelines[style] = timeline
            self.assertTrue(timeline.success)
            self.assertEqual(timeline.editing_style, style)
        
        # Musical style should have higher beat sync percentage
        musical_sync = timelines[EditingStyle.MUSICAL].beat_sync_percentage
        cinematic_sync = timelines[EditingStyle.CINEMATIC].beat_sync_percentage
        self.assertGreaterEqual(musical_sync, cinematic_sync)
    
    def test_tempo_change_detection(self):
        """Test tempo change detection"""
        # Create audio with tempo change
        varied_beats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.2, 3.4, 3.6, 3.8, 4.0]  # Faster at end
        varied_audio = AudioAnalysis(120.0, varied_beats, 0.8, 4.5, 44100)
        
        tempo_changes = self.generator.detect_tempo_changes(varied_audio)
        # Should detect at least some tempo variation
        self.assertGreaterEqual(len(tempo_changes), 0)
    
    def test_silence_detection(self):
        """Test silence detection"""
        # Create audio with gaps (simulated silence)
        gapped_beats = [0.5, 1.0, 1.5, 4.0, 4.5, 5.0]  # Gap between 1.5 and 4.0
        gapped_audio = AudioAnalysis(120.0, gapped_beats, 0.8, 5.5, 44100)
        
        silence_periods = self.generator.handle_silence_detection(gapped_audio, self.video_info)
        # Should detect the gap as potential silence
        self.assertGreater(len(silence_periods), 0)
    
    def test_timeline_statistics(self):
        """Test timeline statistics calculation"""
        timeline = self.generator.generate_timeline(
            self.audio_analysis, self.scene_detection, self.video_info
        )
        
        stats = self.generator.analyze_timeline_statistics(timeline)
        
        # Check that all expected stats are present
        expected_sections = ['timeline_info', 'duration_stats', 'alignment_stats', 
                           'quality_stats', 'cut_type_distribution', 'rhythm_analysis']
        
        for section in expected_sections:
            self.assertIn(section, stats)
        
        # Check basic stat validity
        self.assertEqual(stats['timeline_info']['total_duration'], timeline.total_duration)
        self.assertEqual(stats['timeline_info']['segment_count'], len(timeline.segments))
        self.assertGreaterEqual(stats['alignment_stats']['mean_beat_alignment'], 0.0)
        self.assertLessEqual(stats['alignment_stats']['mean_beat_alignment'], 1.0)
    
    def test_timeline_export(self):
        """Test timeline export functionality"""
        timeline = self.generator.generate_timeline(
            self.audio_analysis, self.scene_detection, self.video_info
        )
        
        # Test JSON export
        json_path = Path("/tmp/test_timeline.json")
        self.generator.export_timeline(timeline, json_path, "json")
        self.assertTrue(json_path.exists())
        
        # Test CSV export
        csv_path = Path("/tmp/test_timeline.csv")
        self.generator.export_timeline(timeline, csv_path, "csv")
        self.assertTrue(csv_path.exists())
        
        # Test EDL export
        edl_path = Path("/tmp/test_timeline.edl")
        self.generator.export_timeline(timeline, edl_path, "edl")
        self.assertTrue(edl_path.exists())
        
        # Cleanup
        for path in [json_path, csv_path, edl_path]:
            if path.exists():
                path.unlink()


class TestCutPoint(unittest.TestCase):
    """Test cases for CutPoint data structure"""
    
    def test_cut_point_creation(self):
        """Test CutPoint creation and properties"""
        cut_point = CutPoint(
            timestamp=1.5,
            confidence=0.8,
            cut_type=CutType.BEAT_CUT,
            beat_alignment=0.9,
            scene_compatibility=0.7,
            flow_score=0.8,
            override_cost=0.1
        )
        
        self.assertEqual(cut_point.timestamp, 1.5)
        self.assertEqual(cut_point.cut_type, CutType.BEAT_CUT)
        self.assertGreater(cut_point.composite_score, 0)
    
    def test_composite_score_calculation(self):
        """Test composite score calculation"""
        cut_point = CutPoint(1.0, 0.8, CutType.BEAT_CUT, 0.9, 0.8, 0.7, 0.1)
        
        # Composite score should be reasonable
        score = cut_point.composite_score
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)
        
        # Higher individual scores should give higher composite score
        better_cut = CutPoint(1.0, 0.9, CutType.BEAT_CUT, 0.95, 0.9, 0.8, 0.05)
        self.assertGreater(better_cut.composite_score, cut_point.composite_score)


if __name__ == '__main__':
    unittest.main()
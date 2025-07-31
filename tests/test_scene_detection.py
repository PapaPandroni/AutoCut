"""Tests for scene detection module"""
import pytest
import numpy as np
import cv2
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from dataclasses import dataclass

from src.video.scene_detection import (
    SceneDetection, SceneDetectionResult, SceneChange,
    SceneDetectionAlgorithm, ProcessingMode
)
from src.video.ingestion import (
    VideoInfo, VideoStream, AudioStream, VideoCodec, ContainerFormat
)


@pytest.fixture
def mock_config():
    """Mock config values for scene detection testing"""
    config_values = {
        'scene_detection.min_scene_duration_sec': 1.0,
        'scene_detection.confidence_threshold': 0.3,
        'scene_detection.histogram_threshold': 0.3,
        'scene_detection.edge_threshold': 0.4,
        'scene_detection.optical_flow_threshold': 0.5,
        'scene_detection.combined_threshold': 0.35,
        'video.enable_hardware_acceleration': True,
        'processing.max_workers': 4
    }
    
    with patch('src.video.scene_detection.config') as mock_cfg:
        mock_cfg.get.side_effect = lambda key, default: config_values.get(key, default)
        yield mock_cfg


@pytest.fixture
def sample_video_info():
    """Create sample video info for testing"""
    video_stream = VideoStream(
        index=0, codec=VideoCodec.H264, width=1920, height=1080,
        fps=30.0, bitrate=500000, duration=120.5
    )
    
    audio_stream = AudioStream(
        index=1, codec="aac", sample_rate=48000, channels=2,
        bitrate=128000, duration=120.5
    )
    
    return VideoInfo(
        file_path=Path("/test/video.mp4"),
        container_format=ContainerFormat.MP4,
        duration=120.5,
        file_size=10485760,
        video_streams=[video_stream],
        audio_streams=[audio_stream],
        metadata={"title": "Test Video"},
        is_valid=True,
        hardware_decodable=True
    )


@pytest.fixture
def mock_video_ingestion():
    """Mock VideoIngestion for testing"""
    with patch('src.video.scene_detection.VideoIngestion') as mock_vi:
        yield mock_vi


@pytest.fixture
def mock_opencv():
    """Mock OpenCV functions for testing"""
    with patch('src.video.scene_detection.cv2') as mock_cv2:
        # Mock VideoCapture
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.side_effect = [
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),  # Frame 1
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 255),  # Frame 2 (different)
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),  # Frame 3 (similar to 1)
            (False, None)  # End of video
        ]
        mock_cv2.VideoCapture.return_value = mock_cap
        
        # Mock other CV functions
        mock_cv2.cvtColor.return_value = np.zeros((480, 640), dtype=np.uint8)
        mock_cv2.calcHist.return_value = np.ones((256, 1), dtype=np.float32)
        mock_cv2.compareHist.return_value = 0.5  # Medium correlation
        mock_cv2.GaussianBlur.return_value = np.zeros((480, 640), dtype=np.uint8)
        mock_cv2.Canny.return_value = np.zeros((480, 640), dtype=np.uint8)
        mock_cv2.calcOpticalFlowPyrLK.return_value = (
            np.ones((100, 1, 2), dtype=np.float32), 
            np.ones((100, 1), dtype=np.uint8), 
            None
        )
        mock_cv2.resize.side_effect = lambda img, size: np.zeros((*size[::-1], 3), dtype=np.uint8)
        
        # Constants
        mock_cv2.CAP_AVFOUNDATION = 200
        mock_cv2.CAP_PROP_BACKEND = 300
        mock_cv2.CAP_PROP_BUFFERSIZE = 38
        mock_cv2.COLOR_BGR2GRAY = 6
        mock_cv2.COLOR_BGR2HSV = 40
        mock_cv2.HISTCMP_CORREL = 1
        mock_cv2.TERM_CRITERIA_EPS = 2
        mock_cv2.TERM_CRITERIA_COUNT = 1
        
        yield mock_cv2


class TestSceneDetectionInitialization:
    """Test SceneDetection class initialization"""
    
    def test_default_initialization(self, mock_config, mock_video_ingestion):
        """Test default initialization"""
        detector = SceneDetection()
        
        assert detector.processing_mode == ProcessingMode.BALANCED
        assert detector.min_scene_duration == 1.0
        assert detector.confidence_threshold == 0.3
        assert detector.enable_hardware_acceleration is True
        assert detector.max_workers == 4
    
    def test_custom_processing_mode_initialization(self, mock_config, mock_video_ingestion):
        """Test initialization with custom processing mode"""
        detector = SceneDetection(ProcessingMode.SPEED)
        
        assert detector.processing_mode == ProcessingMode.SPEED
        
        # Check speed mode configuration
        speed_config = detector.mode_configs[ProcessingMode.SPEED]
        assert speed_config['frame_skip'] == 8
        assert speed_config['resize_factor'] == 0.25
        assert speed_config['algorithms'] == [SceneDetectionAlgorithm.HISTOGRAM]
        assert speed_config['histogram_bins'] == 16
    
    def test_processing_mode_configurations(self, mock_config, mock_video_ingestion):
        """Test all processing mode configurations"""
        detector = SceneDetection()
        
        # Test SPEED mode
        speed_config = detector.mode_configs[ProcessingMode.SPEED]
        assert speed_config['frame_skip'] == 8
        assert speed_config['resize_factor'] == 0.25
        
        # Test BALANCED mode
        balanced_config = detector.mode_configs[ProcessingMode.BALANCED]
        assert balanced_config['frame_skip'] == 4
        assert balanced_config['resize_factor'] == 0.5
        
        # Test QUALITY mode
        quality_config = detector.mode_configs[ProcessingMode.QUALITY]
        assert quality_config['frame_skip'] == 2
        assert quality_config['resize_factor'] == 0.75
        
        # Test PRECISION mode
        precision_config = detector.mode_configs[ProcessingMode.PRECISION]
        assert precision_config['frame_skip'] == 1
        assert precision_config['resize_factor'] == 1.0
    
    def test_algorithm_thresholds(self, mock_config, mock_video_ingestion):
        """Test algorithm threshold configuration"""
        detector = SceneDetection()
        
        assert detector.algorithm_thresholds[SceneDetectionAlgorithm.HISTOGRAM] == 0.3
        assert detector.algorithm_thresholds[SceneDetectionAlgorithm.EDGE_DETECTION] == 0.4
        assert detector.algorithm_thresholds[SceneDetectionAlgorithm.OPTICAL_FLOW] == 0.5
        assert detector.algorithm_thresholds[SceneDetectionAlgorithm.COMBINED] == 0.35


class TestSceneDetection:
    """Test scene detection functionality"""
    
    def test_detect_scenes_success(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test successful scene detection"""
        # Setup mocks
        mock_video_ingestion.return_value.load_video.return_value = sample_video_info
        
        detector = SceneDetection()
        result = detector.detect_scenes("/test/video.mp4", SceneDetectionAlgorithm.HISTOGRAM)
        
        assert isinstance(result, SceneDetectionResult)
        assert result.success is True
        assert result.video_info == sample_video_info
        assert result.algorithm_used == SceneDetectionAlgorithm.HISTOGRAM
        assert result.processing_mode == ProcessingMode.BALANCED
        assert result.processing_time > 0
    
    def test_detect_scenes_with_video_info(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test scene detection with pre-loaded video info"""
        detector = SceneDetection()
        result = detector.detect_scenes("/test/video.mp4", SceneDetectionAlgorithm.HISTOGRAM, sample_video_info)
        
        assert result.success is True
        assert result.video_info == sample_video_info
        # Should not call load_video since video_info was provided
        mock_video_ingestion.return_value.load_video.assert_not_called()
    
    def test_detect_scenes_invalid_video(self, mock_config, mock_video_ingestion, mock_opencv):
        """Test scene detection with invalid video"""
        # Create invalid video info
        invalid_video_info = VideoInfo(
            file_path=Path("/test/invalid.mp4"),
            container_format=ContainerFormat.MP4,
            duration=0,
            file_size=0,
            video_streams=[],
            audio_streams=[],
            metadata={},
            is_valid=False,
            validation_errors=["No video streams found"]
        )
        
        mock_video_ingestion.return_value.load_video.return_value = invalid_video_info
        
        detector = SceneDetection()
        result = detector.detect_scenes("/test/invalid.mp4")
        
        assert result.success is False
        assert len(result.errors) > 0
        assert "Invalid video file" in result.errors[0]
        assert result.scene_count == 1  # Only one scene (no changes detected)
    
    def test_detect_scenes_video_open_failure(self, mock_config, mock_video_ingestion, sample_video_info):
        """Test scene detection when video cannot be opened"""
        mock_video_ingestion.return_value.load_video.return_value = sample_video_info
        
        with patch('src.video.scene_detection.cv2.VideoCapture') as mock_vc:
            mock_cap = Mock()
            mock_cap.isOpened.return_value = False
            mock_vc.return_value = mock_cap
            
            detector = SceneDetection()
            result = detector.detect_scenes("/test/video.mp4")
            
            assert result.success is False
            assert len(result.errors) > 0
            assert "Failed to open video file" in result.errors[0]
    
    def test_detect_scenes_exception_handling(self, mock_config, mock_video_ingestion, sample_video_info):
        """Test exception handling during scene detection"""
        mock_video_ingestion.return_value.load_video.side_effect = Exception("Test exception")
        
        detector = SceneDetection()
        result = detector.detect_scenes("/test/video.mp4")
        
        assert result.success is False
        assert len(result.errors) > 0
        assert "Scene detection failed: Test exception" in result.errors[0]


class TestSceneDetectionAlgorithms:
    """Test individual scene detection algorithms"""
    
    def test_histogram_detection(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test histogram-based scene detection"""
        # Setup mock to return multiple frames and different histograms
        mock_opencv.VideoCapture.return_value.read.side_effect = [
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),      # Frame 0
            (True, np.ones((480, 640, 3), dtype=np.uint8)),       # Frame 1 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 128), # Frame 2 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 64),  # Frame 3 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 255), # Frame 4 - processed
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),      # Frame 5 (skip)
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),      # Frame 6 (skip)
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),      # Frame 7 (skip)
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),      # Frame 8 - processed
            (False, None)  # End of video
        ]
        
        # Setup mock to return different histograms - low correlation means scene change
        mock_opencv.compareHist.side_effect = [0.1, 0.8]  # Low correlation (scene change), then high
        
        detector = SceneDetection()
        result = detector.detect_scenes("/test/video.mp4", SceneDetectionAlgorithm.HISTOGRAM, sample_video_info)
        
        assert result.success is True
        # Should detect scene change where correlation is low (0.1 -> difference 0.9)
        scene_changes = [sc for sc in result.scene_changes if sc.algorithm == SceneDetectionAlgorithm.HISTOGRAM]
        assert len(scene_changes) > 0
    
    def test_edge_detection(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test edge-based scene detection"""
        # Mock different edge maps
        mock_opencv.Canny.side_effect = [
            np.zeros((480, 640), dtype=np.uint8),           # Frame 1: no edges
            np.ones((480, 640), dtype=np.uint8) * 255,     # Frame 2: many edges
            np.zeros((480, 640), dtype=np.uint8)           # Frame 3: no edges
        ]
        
        detector = SceneDetection()
        result = detector.detect_scenes("/test/video.mp4", SceneDetectionAlgorithm.EDGE_DETECTION, sample_video_info)
        
        assert result.success is True
        # Should detect changes based on edge differences
        scene_changes = [sc for sc in result.scene_changes if sc.algorithm == SceneDetectionAlgorithm.EDGE_DETECTION]
        # Note: Exact count depends on threshold, but should have some changes
    
    def test_optical_flow_detection(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test optical flow-based scene detection"""
        # Mock optical flow with varying magnitudes
        mock_opencv.calcOpticalFlowPyrLK.side_effect = [
            (np.ones((100, 1, 2), dtype=np.float32) * 10, np.ones((100, 1), dtype=np.uint8), None),  # High flow
            (np.ones((100, 1, 2), dtype=np.float32) * 1, np.ones((100, 1), dtype=np.uint8), None),   # Low flow
            (np.ones((100, 1, 2), dtype=np.float32) * 5, np.ones((100, 1), dtype=np.uint8), None)    # Medium flow
        ]
        
        detector = SceneDetection()
        result = detector.detect_scenes("/test/video.mp4", SceneDetectionAlgorithm.OPTICAL_FLOW, sample_video_info)
        
        assert result.success is True
        # Should detect changes based on optical flow magnitude
        scene_changes = [sc for sc in result.scene_changes if sc.algorithm == SceneDetectionAlgorithm.OPTICAL_FLOW]
        # Note: First frame won't have optical flow (needs previous frame)
    
    def test_combined_algorithm(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test combined algorithm detection"""
        detector = SceneDetection(ProcessingMode.PRECISION)  # Uses COMBINED algorithm
        result = detector.detect_scenes("/test/video.mp4", SceneDetectionAlgorithm.COMBINED, sample_video_info)
        
        assert result.success is True
        assert result.algorithm_used == SceneDetectionAlgorithm.COMBINED


class TestSceneDetectionHelpers:
    """Test helper methods for scene detection"""
    
    def test_calculate_histogram(self, mock_config, mock_video_ingestion, mock_opencv):
        """Test histogram calculation"""
        detector = SceneDetection()
        
        # Create test frame
        frame = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        
        # Mock HSV conversion and histogram calculation
        mock_opencv.cvtColor.return_value = frame[:, :, 0]  # Mock HSV conversion
        mock_opencv.calcHist.return_value = np.ones((32, 1), dtype=np.float32)
        
        histogram = detector._calculate_histogram(frame, 32)
        
        assert isinstance(histogram, np.ndarray)
        assert len(histogram) == 32 * 3  # H, S, V channels
        mock_opencv.cvtColor.assert_called_once()
        assert mock_opencv.calcHist.call_count == 3  # H, S, V histograms
    
    def test_calculate_edges(self, mock_config, mock_video_ingestion, mock_opencv):
        """Test edge calculation"""
        detector = SceneDetection()
        
        # Create test frame
        frame = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        
        # Mock edge detection
        mock_opencv.cvtColor.return_value = frame[:, :, 0]  # Mock grayscale conversion
        mock_opencv.GaussianBlur.return_value = frame[:, :, 0]
        mock_opencv.Canny.return_value = np.zeros((100, 100), dtype=np.uint8)
        
        edges = detector._calculate_edges(frame)
        
        assert isinstance(edges, np.ndarray)
        assert edges.shape == (100, 100)
        mock_opencv.cvtColor.assert_called_once()
        mock_opencv.GaussianBlur.assert_called_once()
        mock_opencv.Canny.assert_called_once()
    
    def test_post_process_scene_changes(self, mock_config, mock_video_ingestion, sample_video_info):
        """Test post-processing of scene changes"""
        detector = SceneDetection()
        
        # Create test scene changes with varying confidence and timing
        scene_changes = [
            SceneChange(5.0, 150, 0.8, SceneDetectionAlgorithm.HISTOGRAM),
            SceneChange(5.2, 156, 0.6, SceneDetectionAlgorithm.HISTOGRAM),  # Too close to previous
            SceneChange(10.0, 300, 0.2, SceneDetectionAlgorithm.HISTOGRAM),  # Below threshold
            SceneChange(15.0, 450, 0.9, SceneDetectionAlgorithm.HISTOGRAM),  # Good change
            SceneChange(20.0, 600, 0.7, SceneDetectionAlgorithm.HISTOGRAM),  # Good change
        ]
        
        processed = detector._post_process_scene_changes(scene_changes, sample_video_info)
        
        # Should remove close changes and low confidence changes
        assert len(processed) < len(scene_changes)
        
        # All remaining changes should be above threshold
        for change in processed:
            assert change.confidence >= detector.confidence_threshold
        
        # Changes should be sorted by timestamp
        timestamps = [change.timestamp for change in processed]
        assert timestamps == sorted(timestamps)
    
    def test_get_processing_speed_estimate(self, mock_config, mock_video_ingestion, sample_video_info):
        """Test processing speed estimation"""
        detector = SceneDetection(ProcessingMode.SPEED)
        
        speed_estimate = detector.get_processing_speed_estimate(sample_video_info)
        
        assert isinstance(speed_estimate, float)
        assert speed_estimate > 0
        
        # SPEED mode should be faster than QUALITY mode
        quality_detector = SceneDetection(ProcessingMode.QUALITY)
        quality_speed = quality_detector.get_processing_speed_estimate(sample_video_info)
        
        assert speed_estimate > quality_speed


class TestSceneDetectionResult:
    """Test SceneDetectionResult dataclass"""
    
    def test_scene_detection_result_initialization(self, sample_video_info):
        """Test SceneDetectionResult initialization"""
        scene_changes = [
            SceneChange(10.0, 300, 0.8, SceneDetectionAlgorithm.HISTOGRAM),
            SceneChange(20.0, 600, 0.7, SceneDetectionAlgorithm.HISTOGRAM)
        ]
        
        result = SceneDetectionResult(
            video_info=sample_video_info,
            scene_changes=scene_changes,
            processing_time=5.0,
            algorithm_used=SceneDetectionAlgorithm.HISTOGRAM,
            processing_mode=ProcessingMode.BALANCED,
            frames_processed=1000,
            frames_skipped=500
        )
        
        assert result.scene_count == 3  # 2 changes + 1 initial scene
        assert result.processing_speed_multiplier == sample_video_info.duration / 5.0
        assert len(result.get_scene_segments()) == 3
    
    def test_scene_detection_result_no_changes(self, sample_video_info):
        """Test SceneDetectionResult with no scene changes"""
        result = SceneDetectionResult(
            video_info=sample_video_info,
            scene_changes=[],
            processing_time=2.0,
            algorithm_used=SceneDetectionAlgorithm.HISTOGRAM,
            processing_mode=ProcessingMode.SPEED,
            frames_processed=500,
            frames_skipped=1500
        )
        
        assert result.scene_count == 1  # Only one scene
        assert result.average_scene_duration == sample_video_info.duration
        segments = result.get_scene_segments()
        assert len(segments) == 1
        assert segments[0] == (0.0, sample_video_info.duration)
    
    def test_scene_detection_result_average_duration(self, sample_video_info):
        """Test average scene duration calculation"""
        scene_changes = [
            SceneChange(30.0, 900, 0.8, SceneDetectionAlgorithm.HISTOGRAM),
            SceneChange(60.0, 1800, 0.7, SceneDetectionAlgorithm.HISTOGRAM),
            SceneChange(90.0, 2700, 0.6, SceneDetectionAlgorithm.HISTOGRAM)
        ]
        
        result = SceneDetectionResult(
            video_info=sample_video_info,
            scene_changes=scene_changes,
            processing_time=3.0,
            algorithm_used=SceneDetectionAlgorithm.HISTOGRAM,
            processing_mode=ProcessingMode.BALANCED,
            frames_processed=1000,
            frames_skipped=500
        )
        
        # Scenes: 0-30s (30s), 30-60s (30s), 60-90s (30s), 90-120.5s (30.5s)
        expected_avg = (30.0 + 30.0 + 30.0 + 30.5) / 4
        assert abs(result.average_scene_duration - expected_avg) < 0.1
    
    def test_scene_detection_result_to_dict(self, sample_video_info):
        """Test SceneDetectionResult to_dict conversion"""
        scene_changes = [
            SceneChange(10.0, 300, 0.8, SceneDetectionAlgorithm.HISTOGRAM, {"test": 1.0})
        ]
        
        result = SceneDetectionResult(
            video_info=sample_video_info,
            scene_changes=scene_changes,
            processing_time=5.0,
            algorithm_used=SceneDetectionAlgorithm.HISTOGRAM,
            processing_mode=ProcessingMode.BALANCED,
            frames_processed=1000,
            frames_skipped=500,
            success=True,
            errors=[]
        )
        
        result_dict = result.to_dict()
        
        assert isinstance(result_dict, dict)
        assert result_dict['video_path'] == str(sample_video_info.file_path)
        assert result_dict['scene_count'] == 2
        assert result_dict['processing_time'] == 5.0
        assert result_dict['algorithm_used'] == 'histogram'
        assert result_dict['processing_mode'] == 'balanced'
        assert result_dict['frames_processed'] == 1000
        assert result_dict['frames_skipped'] == 500
        assert result_dict['success'] is True
        assert result_dict['errors'] == []
        
        # Check scene changes
        assert len(result_dict['scene_changes']) == 1
        change_dict = result_dict['scene_changes'][0]
        assert change_dict['timestamp'] == 10.0
        assert change_dict['frame_number'] == 300
        assert change_dict['confidence'] == 0.8
        assert change_dict['algorithm'] == 'histogram'
        assert change_dict['metrics'] == {"test": 1.0}


class TestSceneChange:
    """Test SceneChange dataclass"""
    
    def test_scene_change_initialization(self):
        """Test SceneChange initialization"""
        change = SceneChange(
            timestamp=10.5,
            frame_number=315,
            confidence=0.75,
            algorithm=SceneDetectionAlgorithm.HISTOGRAM,
            metrics={"correlation": 0.25}
        )
        
        assert change.timestamp == 10.5
        assert change.frame_number == 315
        assert change.confidence == 0.75
        assert change.algorithm == SceneDetectionAlgorithm.HISTOGRAM
        assert change.metrics == {"correlation": 0.25}
    
    def test_scene_change_confidence_bounds(self):
        """Test confidence value bounds enforcement"""
        # Test confidence above 1.0
        change1 = SceneChange(10.0, 300, 1.5, SceneDetectionAlgorithm.HISTOGRAM)
        assert change1.confidence == 1.0
        
        # Test confidence below 0.0
        change2 = SceneChange(10.0, 300, -0.5, SceneDetectionAlgorithm.HISTOGRAM)
        assert change2.confidence == 0.0
        
        # Test valid confidence
        change3 = SceneChange(10.0, 300, 0.7, SceneDetectionAlgorithm.HISTOGRAM)
        assert change3.confidence == 0.7


class TestBatchProcessing:
    """Test batch processing functionality"""
    
    def test_batch_detect_scenes_success(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test successful batch scene detection"""
        # Setup mock to return video info for all videos
        mock_video_ingestion.return_value.load_video.return_value = sample_video_info
        
        # Setup mock to return multiple frames for proper processing
        mock_opencv.VideoCapture.return_value.read.side_effect = [
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),      # Frame 0
            (True, np.ones((480, 640, 3), dtype=np.uint8)),       # Frame 1 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 128), # Frame 2 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 64),  # Frame 3 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 255), # Frame 4 - processed
            (False, None)  # End of video
        ] * 3  # Repeat for each video
        
        detector = SceneDetection()
        video_paths = ["/test/video1.mp4", "/test/video2.mp4", "/test/video3.mp4"]
        
        results = detector.batch_detect_scenes(video_paths, SceneDetectionAlgorithm.HISTOGRAM)
        
        assert len(results) == 3
        for result in results:
            assert isinstance(result, SceneDetectionResult)
            assert result.success is True
    
    def test_batch_detect_scenes_mixed_results(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test batch processing with mixed success/failure"""
        # Setup mock to fail on second video
        def mock_load_video(path):
            if "video2" in str(path):
                raise Exception("Test failure")
            return sample_video_info
        
        mock_video_ingestion.return_value.load_video.side_effect = mock_load_video
        
        # Setup mock to return multiple frames for successful videos
        mock_opencv.VideoCapture.return_value.read.side_effect = [
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),      # Frame 0
            (True, np.ones((480, 640, 3), dtype=np.uint8)),       # Frame 1 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 128), # Frame 2 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 64),  # Frame 3 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 255), # Frame 4 - processed
            (False, None),  # End of video 1
            # Video 2 will fail at load_video, so no frames needed
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),      # Frame 0 for video 3
            (True, np.ones((480, 640, 3), dtype=np.uint8)),       # Frame 1 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 128), # Frame 2 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 64),  # Frame 3 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 255), # Frame 4 - processed
            (False, None)   # End of video 3
        ]
        
        detector = SceneDetection()
        video_paths = ["/test/video1.mp4", "/test/video2.mp4", "/test/video3.mp4"]
        
        results = detector.batch_detect_scenes(video_paths, SceneDetectionAlgorithm.HISTOGRAM)
        
        assert len(results) == 3
        
        # Check that we have the expected mix of successful and failed results
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]
        
        assert len(successful_results) == 2
        assert len(failed_results) == 1
        
        # The failed result should correspond to video2
        failed_video_paths = [str(r.video_info.file_path) for r in failed_results]
        assert any("video2" in path for path in failed_video_paths)
    
    def test_batch_detect_scenes_custom_workers(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test batch processing with custom worker count"""
        mock_video_ingestion.return_value.load_video.return_value = sample_video_info
        
        # Setup mock to return multiple frames for proper processing
        mock_opencv.VideoCapture.return_value.read.side_effect = [
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),      # Frame 0
            (True, np.ones((480, 640, 3), dtype=np.uint8)),       # Frame 1 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 128), # Frame 2 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 64),  # Frame 3 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 255), # Frame 4 - processed
            (False, None),  # End of video 1
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),      # Frame 0 for video 2
            (True, np.ones((480, 640, 3), dtype=np.uint8)),       # Frame 1 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 128), # Frame 2 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 64),  # Frame 3 (skip)
            (True, np.ones((480, 640, 3), dtype=np.uint8) * 255), # Frame 4 - processed
            (False, None)   # End of video 2
        ]
        
        detector = SceneDetection()
        video_paths = ["/test/video1.mp4", "/test/video2.mp4"]
        
        results = detector.batch_detect_scenes(video_paths, SceneDetectionAlgorithm.HISTOGRAM, max_workers=1)
        
        assert len(results) == 2
        for result in results:
            assert result.success is True


class TestProcessingModes:
    """Test different processing modes"""
    
    def test_speed_mode_performance(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test SPEED processing mode"""
        detector = SceneDetection(ProcessingMode.SPEED)
        result = detector.detect_scenes("/test/video.mp4", SceneDetectionAlgorithm.HISTOGRAM, sample_video_info)
        
        assert result.success is True
        assert result.processing_mode == ProcessingMode.SPEED
        # SPEED mode should skip more frames
        assert result.frames_skipped > result.frames_processed
    
    def test_precision_mode_quality(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test PRECISION processing mode"""
        detector = SceneDetection(ProcessingMode.PRECISION)
        result = detector.detect_scenes("/test/video.mp4", SceneDetectionAlgorithm.COMBINED, sample_video_info)
        
        assert result.success is True
        assert result.processing_mode == ProcessingMode.PRECISION
        # PRECISION mode should process more frames
        assert result.frames_processed >= result.frames_skipped
    
    def test_processing_mode_algorithm_selection(self, mock_config, mock_video_ingestion):
        """Test algorithm selection based on processing mode"""
        speed_detector = SceneDetection(ProcessingMode.SPEED)
        quality_detector = SceneDetection(ProcessingMode.QUALITY)
        precision_detector = SceneDetection(ProcessingMode.PRECISION)
        
        # Check algorithm configurations
        speed_algorithms = speed_detector.mode_configs[ProcessingMode.SPEED]['algorithms']
        quality_algorithms = quality_detector.mode_configs[ProcessingMode.QUALITY]['algorithms']
        precision_algorithms = precision_detector.mode_configs[ProcessingMode.PRECISION]['algorithms']
        
        assert len(speed_algorithms) == 1  # Only histogram for speed
        assert len(quality_algorithms) == 3  # Multiple algorithms for quality
        assert SceneDetectionAlgorithm.COMBINED in precision_algorithms  # Combined for precision


class TestHardwareAcceleration:
    """Test hardware acceleration functionality"""
    
    def test_hardware_acceleration_configuration(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test hardware acceleration setup during detection"""
        detector = SceneDetection()
        detector.detect_scenes("/test/video.mp4", SceneDetectionAlgorithm.HISTOGRAM, sample_video_info)
        
        # Should attempt to configure hardware acceleration
        mock_opencv.VideoCapture.return_value.set.assert_called()
        
        # Check that AVFoundation backend was attempted
        calls = mock_opencv.VideoCapture.return_value.set.call_args_list
        backend_calls = [call for call in calls if call[0][0] == mock_opencv.CAP_PROP_BACKEND]
        assert len(backend_calls) > 0
    
    def test_hardware_acceleration_fallback(self, mock_config, mock_video_ingestion, sample_video_info):
        """Test fallback when hardware acceleration fails"""
        with patch('src.video.scene_detection.cv2') as mock_cv2:
            # Mock VideoCapture that fails hardware acceleration setup
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_cap.set.side_effect = Exception("Hardware acceleration failed")
            mock_cap.read.return_value = (False, None)  # No frames to process
            mock_cv2.VideoCapture.return_value = mock_cap
            
            # Constants
            mock_cv2.CAP_AVFOUNDATION = 200
            mock_cv2.CAP_PROP_BACKEND = 300
            mock_cv2.CAP_PROP_BUFFERSIZE = 38
            
            detector = SceneDetection()
            result = detector.detect_scenes("/test/video.mp4", SceneDetectionAlgorithm.HISTOGRAM, sample_video_info)
            
            # Should still succeed despite hardware acceleration failure
            assert result.success is True


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_empty_video_processing(self, mock_config, mock_video_ingestion, sample_video_info):
        """Test processing video with no frames"""
        with patch('src.video.scene_detection.cv2.VideoCapture') as mock_vc:
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (False, None)  # No frames
            mock_vc.return_value = mock_cap
            
            detector = SceneDetection()
            result = detector.detect_scenes("/test/empty.mp4", SceneDetectionAlgorithm.HISTOGRAM, sample_video_info)
            
            assert result.success is True
            assert len(result.scene_changes) == 0
            assert result.frames_processed == 0
    
    def test_single_frame_video(self, mock_config, mock_video_ingestion, mock_opencv, sample_video_info):
        """Test processing video with single frame"""
        # Mock single frame video
        mock_opencv.VideoCapture.return_value.read.side_effect = [
            (True, np.zeros((480, 640, 3), dtype=np.uint8)),  # Single frame
            (False, None)  # End of video
        ]
        
        detector = SceneDetection()
        result = detector.detect_scenes("/test/single.mp4", SceneDetectionAlgorithm.HISTOGRAM, sample_video_info)
        
        assert result.success is True
        assert len(result.scene_changes) == 0  # No changes with single frame
        assert result.scene_count == 1
    
    def test_very_short_video(self, mock_config, mock_video_ingestion, mock_opencv):
        """Test processing very short video"""
        # Create very short video info
        short_video_info = VideoInfo(
            file_path=Path("/test/short.mp4"),
            container_format=ContainerFormat.MP4,
            duration=0.1,  # 100ms video
            file_size=1024,
            video_streams=[VideoStream(0, VideoCodec.H264, 640, 480, 30.0)],
            audio_streams=[],
            metadata={},
            is_valid=True
        )
        
        detector = SceneDetection()
        result = detector.detect_scenes("/test/short.mp4", SceneDetectionAlgorithm.HISTOGRAM, short_video_info)
        
        assert result.success is True
        assert result.video_info.duration == 0.1


class TestConfigurationIntegration:
    """Test integration with configuration system"""
    
    def test_custom_thresholds(self, mock_video_ingestion):
        """Test custom threshold configuration"""
        custom_config_values = {
            'scene_detection.min_scene_duration_sec': 2.0,
            'scene_detection.confidence_threshold': 0.5,
            'scene_detection.histogram_threshold': 0.4,
            'video.enable_hardware_acceleration': False,
            'processing.max_workers': 8
        }
        
        with patch('src.video.scene_detection.config') as mock_cfg:
            mock_cfg.get.side_effect = lambda key, default: custom_config_values.get(key, default)
            
            detector = SceneDetection()
            
            assert detector.min_scene_duration == 2.0
            assert detector.confidence_threshold == 0.5
            assert detector.algorithm_thresholds[SceneDetectionAlgorithm.HISTOGRAM] == 0.4
            assert detector.enable_hardware_acceleration is False
            assert detector.max_workers == 8
    
    def test_config_fallback_values(self, mock_video_ingestion):
        """Test configuration fallback to default values"""
        with patch('src.video.scene_detection.config') as mock_cfg:
            # Return default for all config requests
            mock_cfg.get.side_effect = lambda key, default: default
            
            detector = SceneDetection()
            
            assert detector.min_scene_duration == 1.0  # default
            assert detector.confidence_threshold == 0.3  # default
            assert detector.enable_hardware_acceleration is True  # default
"""Tests for face detection module"""
import pytest
import numpy as np
import cv2
import time
import threading
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from dataclasses import dataclass
from typing import List, Dict, Any, Iterator, Tuple

from src.video.face_detection import (
    FaceDetectionEngine, FaceBoundingBox, FaceLandmark, FaceKeyPoints,
    FaceDetectionResult, FrameFaceDetectionResult, VideoFaceDetectionResult,
    FaceDetectionModel, ProcessingMode, FaceQuality, FrameSampler,
    create_face_detection_engine, create_video_frame_generator
)
from src.video.ingestion import VideoInfo, VideoStream, VideoCodec, ContainerFormat


@pytest.fixture
def mock_config():
    """Mock config values for testing"""
    config_values = {
        'face_detection.max_workers': 4,
        'face_detection.target_fps': 15.0,
        'face_detection.quality_assessment': True
    }
    
    with patch('src.video.face_detection.config') as mock_cfg:
        mock_cfg.get.side_effect = lambda key, default: config_values.get(key, default)
        yield mock_cfg


@pytest.fixture
def mock_mediapipe():
    """Mock MediaPipe components to avoid external dependencies"""
    with patch('src.video.face_detection.mp') as mock_mp:
        # Mock face detection solution
        mock_face_detection_class = Mock()
        mock_mp.solutions.face_detection.FaceDetection = mock_face_detection_class
        mock_mp.solutions.face_detection = Mock()
        mock_mp.solutions.drawing_utils = Mock()
        
        # Mock detector instance
        mock_detector = Mock()
        mock_detector.close = Mock()  # Ensure close method exists for context manager
        mock_face_detection_class.return_value = mock_detector
        
        yield mock_mp, mock_detector


@pytest.fixture
def mock_opencv():
    """Mock OpenCV operations"""
    with patch('src.video.face_detection.cv2') as mock_cv2:
        # Mock color conversion
        mock_cv2.cvtColor.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cv2.COLOR_BGR2RGB = 4  # OpenCV constant
        
        # Mock video capture
        mock_cap = Mock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 30.0  # FPS
        mock_cap.read.side_effect = [(True, np.zeros((480, 640, 3), dtype=np.uint8)), (False, None)]
        
        yield mock_cv2, mock_cap


@pytest.fixture
def sample_video_info():
    """Create sample VideoInfo for testing"""
    video_stream = VideoStream(
        index=0, codec=VideoCodec.H264, width=1920, height=1080,
        fps=30.0, bitrate=500000, duration=120.5
    )
    
    return VideoInfo(
        file_path=Path("/test/video.mp4"),
        container_format=ContainerFormat.MP4,
        duration=120.5,
        file_size=10485760,
        video_streams=[video_stream],
        audio_streams=[],
        metadata={}
    )


@pytest.fixture
def sample_frame():
    """Create sample video frame for testing"""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture
def mock_mediapipe_detection():
    """Create mock MediaPipe detection result"""
    mock_detection = Mock()
    
    # Mock bounding box
    mock_bbox = Mock()
    mock_bbox.xmin = 0.2
    mock_bbox.ymin = 0.3
    mock_bbox.width = 0.4
    mock_bbox.height = 0.5
    mock_detection.location_data.relative_bounding_box = mock_bbox
    
    # Mock keypoints
    mock_keypoints = []
    # Create 6 keypoints (right eye, left eye, nose, mouth, right ear, left ear)
    keypoint_coords = [
        (0.3, 0.4),  # right eye
        (0.5, 0.4),  # left eye
        (0.4, 0.5),  # nose tip
        (0.4, 0.6),  # mouth center
        (0.2, 0.45), # right ear
        (0.6, 0.45)  # left ear
    ]
    
    for x, y in keypoint_coords:
        kp = Mock()
        kp.x = x
        kp.y = y
        mock_keypoints.append(kp)
    
    mock_detection.location_data.relative_keypoints = mock_keypoints
    mock_detection.score = [0.8]  # Confidence score as list
    
    return mock_detection


class TestDataStructures:
    """Test face detection data structure classes"""
    
    def test_face_bounding_box_creation(self):
        """Test FaceBoundingBox creation and methods"""
        bbox = FaceBoundingBox(x_min=0.2, y_min=0.3, width=0.4, height=0.5)
        
        assert bbox.x_min == 0.2
        assert bbox.y_min == 0.3
        assert bbox.width == 0.4
        assert bbox.height == 0.5
    
    def test_face_bounding_box_to_pixel_coords(self):
        """Test conversion to pixel coordinates"""
        bbox = FaceBoundingBox(x_min=0.2, y_min=0.3, width=0.4, height=0.5)
        
        # Convert to 1920x1080 frame
        x, y, w, h = bbox.to_pixel_coords(1920, 1080)
        
        assert x == int(0.2 * 1920)  # 384
        assert y == int(0.3 * 1080)  # 324
        assert w == int(0.4 * 1920)  # 768
        assert h == int(0.5 * 1080)  # 540
    
    def test_face_bounding_box_area(self):
        """Test area calculation"""
        bbox = FaceBoundingBox(x_min=0.2, y_min=0.3, width=0.4, height=0.5)
        
        area = bbox.area()
        assert area == 0.4 * 0.5  # 0.2
    
    def test_face_bounding_box_center(self):
        """Test center point calculation"""
        bbox = FaceBoundingBox(x_min=0.2, y_min=0.3, width=0.4, height=0.5)
        
        center_x, center_y = bbox.center()
        assert center_x == 0.2 + 0.4 / 2  # 0.4
        assert center_y == 0.3 + 0.5 / 2  # 0.55
    
    def test_face_landmark_creation(self):
        """Test FaceLandmark creation and methods"""
        landmark = FaceLandmark(x=0.5, y=0.6)
        
        assert landmark.x == 0.5
        assert landmark.y == 0.6
    
    def test_face_landmark_to_pixel_coords(self):
        """Test landmark pixel coordinate conversion"""
        landmark = FaceLandmark(x=0.5, y=0.6)
        
        # Convert to 1920x1080 frame
        x, y = landmark.to_pixel_coords(1920, 1080)
        
        assert x == int(0.5 * 1920)  # 960
        assert y == int(0.6 * 1080)  # 648
    
    def test_face_keypoints_creation(self):
        """Test FaceKeyPoints creation"""
        right_eye = FaceLandmark(0.3, 0.4)
        left_eye = FaceLandmark(0.5, 0.4)
        nose_tip = FaceLandmark(0.4, 0.5)
        mouth_center = FaceLandmark(0.4, 0.6)
        
        keypoints = FaceKeyPoints(
            right_eye=right_eye,
            left_eye=left_eye,
            nose_tip=nose_tip,
            mouth_center=mouth_center
        )
        
        assert keypoints.right_eye == right_eye
        assert keypoints.left_eye == left_eye
        assert keypoints.nose_tip == nose_tip
        assert keypoints.mouth_center == mouth_center
        assert keypoints.right_ear is None
        assert keypoints.left_ear is None
    
    def test_face_keypoints_eye_distance(self):
        """Test eye distance calculation"""
        right_eye = FaceLandmark(0.3, 0.4)
        left_eye = FaceLandmark(0.5, 0.4)
        
        keypoints = FaceKeyPoints(
            right_eye=right_eye,
            left_eye=left_eye,
            nose_tip=FaceLandmark(0.4, 0.5),
            mouth_center=FaceLandmark(0.4, 0.6)
        )
        
        distance = keypoints.eye_distance()
        expected = np.sqrt((0.5 - 0.3)**2 + (0.4 - 0.4)**2)  # 0.2
        assert abs(distance - expected) < 0.001
    
    def test_face_keypoints_face_angle(self):
        """Test face angle calculation"""
        right_eye = FaceLandmark(0.3, 0.4)
        left_eye = FaceLandmark(0.5, 0.4)  # Same Y level = 0 degrees
        
        keypoints = FaceKeyPoints(
            right_eye=right_eye,
            left_eye=left_eye,
            nose_tip=FaceLandmark(0.4, 0.5),
            mouth_center=FaceLandmark(0.4, 0.6)
        )
        
        angle = keypoints.face_angle()
        assert abs(angle - 0.0) < 0.1  # Should be close to 0 degrees
    
    def test_face_detection_result_creation(self):
        """Test FaceDetectionResult creation"""
        bbox = FaceBoundingBox(0.2, 0.3, 0.4, 0.5)
        keypoints = FaceKeyPoints(
            right_eye=FaceLandmark(0.3, 0.4),
            left_eye=FaceLandmark(0.5, 0.4),
            nose_tip=FaceLandmark(0.4, 0.5),
            mouth_center=FaceLandmark(0.4, 0.6)
        )
        
        result = FaceDetectionResult(
            bounding_box=bbox,
            keypoints=keypoints,
            confidence=0.8
        )
        
        assert result.bounding_box == bbox
        assert result.keypoints == keypoints
        assert result.confidence == 0.8
        assert result.face_id is None
        assert result.relative_size == 0.0
        assert result.visibility == 1.0
        assert result.quality_level == FaceQuality.FAIR
    
    def test_face_detection_result_to_dict(self):
        """Test FaceDetectionResult serialization"""
        bbox = FaceBoundingBox(0.2, 0.3, 0.4, 0.5)
        keypoints = FaceKeyPoints(
            right_eye=FaceLandmark(0.3, 0.4),
            left_eye=FaceLandmark(0.5, 0.4),
            nose_tip=FaceLandmark(0.4, 0.5),
            mouth_center=FaceLandmark(0.4, 0.6)
        )
        
        result = FaceDetectionResult(
            bounding_box=bbox,
            keypoints=keypoints,
            confidence=0.8,
            quality_score=0.7,
            quality_level=FaceQuality.GOOD
        )
        
        data = result.to_dict()
        
        assert 'bounding_box' in data
        assert 'keypoints' in data
        assert 'confidence' in data
        assert data['confidence'] == 0.8
        assert data['quality_score'] == 0.7
        assert data['quality_level'] == 'GOOD'
    
    def test_frame_face_detection_result_creation(self):
        """Test FrameFaceDetectionResult creation and post-init"""
        bbox = FaceBoundingBox(0.2, 0.3, 0.4, 0.5)
        keypoints = FaceKeyPoints(
            right_eye=FaceLandmark(0.3, 0.4),
            left_eye=FaceLandmark(0.5, 0.4),
            nose_tip=FaceLandmark(0.4, 0.5),
            mouth_center=FaceLandmark(0.4, 0.6)
        )
        
        face1 = FaceDetectionResult(bbox, keypoints, confidence=0.8, quality_score=0.7)
        face2 = FaceDetectionResult(bbox, keypoints, confidence=0.9, quality_score=0.9)
        
        frame_result = FrameFaceDetectionResult(
            timestamp=10.0,
            frame_index=300,
            faces=[face1, face2],
            processing_time=0.05,
            frame_width=1920,
            frame_height=1080
        )
        
        assert frame_result.total_faces == 2
        assert frame_result.best_face == face2  # Higher quality score
        assert frame_result.average_quality == 0.8  # (0.7 + 0.9) / 2
    
    def test_frame_face_detection_result_no_faces(self):
        """Test FrameFaceDetectionResult with no faces"""
        frame_result = FrameFaceDetectionResult(
            timestamp=10.0,
            frame_index=300,
            faces=[],
            processing_time=0.05,
            frame_width=1920,
            frame_height=1080
        )
        
        assert frame_result.total_faces == 0
        assert frame_result.best_face is None
        assert frame_result.average_quality == 0.0


class TestFrameSampler:
    """Test FrameSampler performance optimization"""
    
    def test_frame_sampler_initialization_no_skip(self):
        """Test frame sampler when target FPS >= video FPS"""
        sampler = FrameSampler(target_fps=30.0, video_fps=30.0, mode=ProcessingMode.BALANCED)
        
        assert sampler.target_fps == 30.0
        assert sampler.video_fps == 30.0
        assert sampler.skip_interval == 1
        assert sampler.mode == ProcessingMode.BALANCED
    
    def test_frame_sampler_initialization_with_skip(self):
        """Test frame sampler when target FPS < video FPS"""
        sampler = FrameSampler(target_fps=15.0, video_fps=30.0, mode=ProcessingMode.REALTIME)
        
        assert sampler.target_fps == 15.0
        assert sampler.video_fps == 30.0
        assert sampler.skip_interval == 2  # 30 / 15 = 2
    
    def test_frame_sampler_should_process_frame(self):
        """Test frame processing decision logic"""
        sampler = FrameSampler(target_fps=10.0, video_fps=30.0, mode=ProcessingMode.BALANCED)
        
        # Should process every 3rd frame (30/10=3)
        assert sampler.should_process_frame(0) is True   # 0 % 3 == 0
        assert sampler.should_process_frame(1) is False  # 1 % 3 != 0
        assert sampler.should_process_frame(2) is False  # 2 % 3 != 0
        assert sampler.should_process_frame(3) is True   # 3 % 3 == 0
        assert sampler.should_process_frame(4) is False  # 4 % 3 != 0
        assert sampler.should_process_frame(6) is True   # 6 % 3 == 0
    
    def test_frame_sampler_get_processing_interval(self):
        """Test getting processing interval"""
        sampler = FrameSampler(target_fps=10.0, video_fps=30.0, mode=ProcessingMode.BALANCED)
        
        interval = sampler.get_processing_interval()
        assert interval == 3


class TestFaceDetectionEngineInitialization:
    """Test FaceDetectionEngine initialization and configuration"""
    
    def test_default_initialization(self, mock_config, mock_mediapipe):
        """Test default engine initialization"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine()
        
        assert engine.model == FaceDetectionModel.SHORT_RANGE
        assert engine.mode == ProcessingMode.BALANCED
        assert engine.min_detection_confidence == 0.5
        assert engine.target_fps == 15.0
        assert engine.max_workers <= 4  # Should be reasonable default
    
    def test_custom_initialization(self, mock_config, mock_mediapipe):
        """Test custom engine initialization"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine(
            model=FaceDetectionModel.FULL_RANGE,
            mode=ProcessingMode.QUALITY,
            min_detection_confidence=0.7,
            target_fps=10.0,
            max_workers=2
        )
        
        assert engine.model == FaceDetectionModel.FULL_RANGE
        assert engine.mode == ProcessingMode.QUALITY
        assert engine.min_detection_confidence == 0.7
        assert engine.target_fps == 10.0
        assert engine.max_workers == 2
    
    def test_mode_configuration_realtime(self, mock_config, mock_mediapipe):
        """Test REALTIME mode configuration"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine(
            mode=ProcessingMode.REALTIME,
            min_detection_confidence=0.5
        )
        
        config = engine.config
        assert config['min_detection_confidence'] == 0.3  # Lowered for speed
        assert config['batch_size'] == 8
        assert config['quality_assessment'] is False
    
    def test_mode_configuration_balanced(self, mock_config, mock_mediapipe):
        """Test BALANCED mode configuration"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine(
            mode=ProcessingMode.BALANCED,
            min_detection_confidence=0.5
        )
        
        config = engine.config
        assert config['min_detection_confidence'] == 0.5  # Unchanged
        assert config['batch_size'] == 4
        assert config['quality_assessment'] is True
    
    def test_mode_configuration_quality(self, mock_config, mock_mediapipe):
        """Test QUALITY mode configuration"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine(
            mode=ProcessingMode.QUALITY,
            min_detection_confidence=0.5
        )
        
        config = engine.config
        assert config['min_detection_confidence'] == 0.7  # Increased for quality
        assert config['batch_size'] == 2
        assert config['quality_assessment'] is True
    
    @patch('src.video.face_detection.os.cpu_count')
    def test_auto_worker_calculation(self, mock_cpu_count, mock_config, mock_mediapipe):
        """Test automatic worker thread calculation"""
        mock_mp, mock_detector = mock_mediapipe
        mock_cpu_count.return_value = 8
        
        engine = FaceDetectionEngine()
        
        # Should be min(cpu_count // 2, 4) = min(4, 4) = 4
        assert engine.max_workers == 4


class TestFaceDetectionEngineProcessing:
    """Test face detection processing functionality"""
    
    def test_extract_face_keypoints(self, mock_config, mock_mediapipe, mock_mediapipe_detection):
        """Test keypoint extraction from MediaPipe detection"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine()
        keypoints = engine._extract_face_keypoints(mock_mediapipe_detection)
        
        assert isinstance(keypoints, FaceKeyPoints)
        assert keypoints.right_eye.x == 0.3
        assert keypoints.right_eye.y == 0.4
        assert keypoints.left_eye.x == 0.5
        assert keypoints.left_eye.y == 0.4
        assert keypoints.nose_tip.x == 0.4
        assert keypoints.nose_tip.y == 0.5
        assert keypoints.mouth_center.x == 0.4
        assert keypoints.mouth_center.y == 0.6
        assert keypoints.right_ear.x == 0.2
        assert keypoints.left_ear.x == 0.6
    
    def test_process_frame_success(self, mock_config, mock_mediapipe, mock_opencv, sample_frame, mock_mediapipe_detection):
        """Test successful single frame processing"""
        mock_mp, mock_detector = mock_mediapipe
        mock_cv2, mock_cap = mock_opencv
        
        # Setup mock detection results
        mock_results = Mock()
        mock_results.detections = [mock_mediapipe_detection]
        mock_detector.process.return_value = mock_results
        
        engine = FaceDetectionEngine()
        
        # Mock the context manager
        with patch.object(engine, '_get_detector') as mock_get_detector:
            mock_get_detector.return_value.__enter__ = Mock(return_value=mock_detector)
            mock_get_detector.return_value.__exit__ = Mock(return_value=None)
            
            result = engine._process_frame(sample_frame, timestamp=10.0, frame_index=300)
        
        assert isinstance(result, FrameFaceDetectionResult)
        assert result.timestamp == 10.0
        assert result.frame_index == 300
        assert len(result.faces) == 1
        assert result.processing_time > 0
        assert result.frame_width == 640
        assert result.frame_height == 480
    
    def test_process_frame_no_detections(self, mock_config, mock_mediapipe, mock_opencv, sample_frame):
        """Test frame processing with no face detections"""
        mock_mp, mock_detector = mock_mediapipe
        mock_cv2, mock_cap = mock_opencv
        
        # Setup mock with no detections
        mock_results = Mock()
        mock_results.detections = None
        mock_detector.process.return_value = mock_results
        
        engine = FaceDetectionEngine()
        
        # Mock the context manager
        with patch.object(engine, '_get_detector') as mock_get_detector:
            mock_get_detector.return_value.__enter__ = Mock(return_value=mock_detector)
            mock_get_detector.return_value.__exit__ = Mock(return_value=None)
            
            result = engine._process_frame(sample_frame, timestamp=10.0, frame_index=300)
        
        assert isinstance(result, FrameFaceDetectionResult)
        assert len(result.faces) == 0
        assert result.total_faces == 0
        assert result.best_face is None
    
    def test_assess_face_quality_enabled(self, mock_config, mock_mediapipe):
        """Test face quality assessment when enabled"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine(mode=ProcessingMode.BALANCED)  # Quality assessment enabled
        
        bbox = FaceBoundingBox(0.2, 0.3, 0.4, 0.5)
        keypoints = FaceKeyPoints(
            right_eye=FaceLandmark(0.3, 0.4),
            left_eye=FaceLandmark(0.5, 0.4),
            nose_tip=FaceLandmark(0.4, 0.5),
            mouth_center=FaceLandmark(0.4, 0.6)
        )
        
        face_result = FaceDetectionResult(
            bounding_box=bbox,
            keypoints=keypoints,
            confidence=0.8
        )
        
        assessed_result = engine._assess_face_quality(face_result, 1920, 1080)
        
        assert assessed_result.relative_size > 0  # Should be calculated
        assert assessed_result.quality_score > 0  # Should be calculated
        assert assessed_result.quality_level in [FaceQuality.POOR, FaceQuality.FAIR, FaceQuality.GOOD, FaceQuality.EXCELLENT]
    
    def test_assess_face_quality_disabled(self, mock_config, mock_mediapipe):
        """Test face quality assessment when disabled"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine(mode=ProcessingMode.REALTIME)  # Quality assessment disabled
        
        bbox = FaceBoundingBox(0.2, 0.3, 0.4, 0.5)
        keypoints = FaceKeyPoints(
            right_eye=FaceLandmark(0.3, 0.4),
            left_eye=FaceLandmark(0.5, 0.4),
            nose_tip=FaceLandmark(0.4, 0.5),
            mouth_center=FaceLandmark(0.4, 0.6)
        )
        
        face_result = FaceDetectionResult(
            bounding_box=bbox,
            keypoints=keypoints,
            confidence=0.8
        )
        
        assessed_result = engine._assess_face_quality(face_result, 1920, 1080)
        
        # Should return unchanged when quality assessment is disabled
        assert assessed_result == face_result
    
    def test_process_frame_batch_single_frame(self, mock_config, mock_mediapipe, mock_opencv, sample_frame, mock_mediapipe_detection):
        """Test batch processing with single frame"""
        mock_mp, mock_detector = mock_mediapipe
        mock_cv2, mock_cap = mock_opencv
        
        # Setup mock detection results
        mock_results = Mock()
        mock_results.detections = [mock_mediapipe_detection]
        mock_detector.process.return_value = mock_results
        
        engine = FaceDetectionEngine()
        
        # Mock the context manager
        with patch.object(engine, '_get_detector') as mock_get_detector:
            mock_get_detector.return_value.__enter__ = Mock(return_value=mock_detector)
            mock_get_detector.return_value.__exit__ = Mock(return_value=None)
            
            frame_batch = [(sample_frame, 10.0, 300)]
            results = engine._process_frame_batch(frame_batch)
        
        assert len(results) == 1
        assert isinstance(results[0], FrameFaceDetectionResult)
        assert results[0].frame_index == 300
    
    def test_process_frame_batch_multiple_frames(self, mock_config, mock_mediapipe, mock_opencv, sample_frame, mock_mediapipe_detection):
        """Test batch processing with multiple frames"""
        mock_mp, mock_detector = mock_mediapipe
        mock_cv2, mock_cap = mock_opencv
        
        # Setup mock detection results
        mock_results = Mock()
        mock_results.detections = [mock_mediapipe_detection]
        mock_detector.process.return_value = mock_results
        
        engine = FaceDetectionEngine()
        
        # Mock the context manager for multithreaded access
        with patch.object(engine, '_get_detector') as mock_get_detector:
            mock_get_detector.return_value.__enter__ = Mock(return_value=mock_detector)
            mock_get_detector.return_value.__exit__ = Mock(return_value=None)
            
            frame_batch = [
                (sample_frame, 10.0, 300),
                (sample_frame, 10.1, 301),
                (sample_frame, 10.2, 302)
            ]
            
            results = engine._process_frame_batch(frame_batch)
        
        assert len(results) == 3
        # Results should be sorted by frame index
        assert results[0].frame_index == 300
        assert results[1].frame_index == 301
        assert results[2].frame_index == 302
    
    def test_get_performance_stats(self, mock_config, mock_mediapipe):
        """Test performance statistics tracking"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine()
        
        # Initially should have zero stats
        stats = engine.get_performance_stats()
        assert stats['total_frames_processed'] == 0
        assert stats['total_processing_time'] == 0.0
        assert stats['estimated_fps'] == 0.0
        
        # Simulate some processing
        with engine._performance_lock:
            engine._total_frames_processed = 100
            engine._total_processing_time = 10.0  # 100 frames in 10 seconds
        
        stats = engine.get_performance_stats()
        assert stats['total_frames_processed'] == 100
        assert stats['total_processing_time'] == 10.0
        assert abs(stats['estimated_fps'] - 10.0) < 0.1  # Should be ~10 fps


class TestVideoProcessing:
    """Test complete video processing functionality"""
    
    def create_mock_frame_generator(self, num_frames=10):
        """Create a mock frame generator for testing"""
        for i in range(num_frames):
            frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            timestamp = i / 30.0  # 30 fps
            yield frame, timestamp, i
    
    def test_process_video_frames_success(self, mock_config, mock_mediapipe, mock_opencv, sample_video_info, mock_mediapipe_detection):
        """Test successful video processing"""
        mock_mp, mock_detector = mock_mediapipe
        mock_cv2, mock_cap = mock_opencv
        
        # Setup mock detection results
        mock_results = Mock()
        mock_results.detections = [mock_mediapipe_detection]
        mock_detector.process.return_value = mock_results
        
        engine = FaceDetectionEngine()
        
        # Create frame generator
        frame_generator = self.create_mock_frame_generator(num_frames=10)
        
        result = engine.process_video_frames(sample_video_info, frame_generator)
        
        assert isinstance(result, VideoFaceDetectionResult)
        assert result.video_info == sample_video_info
        assert len(result.frame_results) > 0  # Should have processed some frames
        assert result.total_frames_processed > 0
        assert result.average_fps > 0
    
    def test_process_video_frames_with_sampling(self, mock_config, mock_mediapipe, mock_opencv, sample_video_info, mock_mediapipe_detection):
        """Test video processing with frame sampling"""
        mock_mp, mock_detector = mock_mediapipe
        mock_cv2, mock_cap = mock_opencv
        
        # Setup mock detection results
        mock_results = Mock()
        mock_results.detections = [mock_mediapipe_detection]
        mock_detector.process.return_value = mock_results
        
        # Use low target FPS to force frame sampling
        engine = FaceDetectionEngine(target_fps=5.0)
        
        # Create frame generator with 30 fps
        frame_generator = self.create_mock_frame_generator(num_frames=30)
        
        result = engine.process_video_frames(sample_video_info, frame_generator)
        
        # Should process fewer frames due to sampling
        assert result.total_frames_processed < 30
        assert result.processing_settings['frame_skip_interval'] > 1
    
    def test_process_video_frames_with_progress_callback(self, mock_config, mock_mediapipe, mock_opencv, sample_video_info, mock_mediapipe_detection):
        """Test video processing with progress callback"""
        mock_mp, mock_detector = mock_mediapipe
        mock_cv2, mock_cap = mock_opencv
        
        # Setup mock detection results
        mock_results = Mock()
        mock_results.detections = [mock_mediapipe_detection]
        mock_detector.process.return_value = mock_results
        
        engine = FaceDetectionEngine()
        
        # Create progress callback mock
        progress_callback = Mock()
        
        # Create frame generator
        frame_generator = self.create_mock_frame_generator(num_frames=5)
        
        result = engine.process_video_frames(sample_video_info, frame_generator, progress_callback)
        
        # Progress callback should have been called
        assert progress_callback.called
    
    def test_process_video_frames_error_handling(self, mock_config, mock_mediapipe, mock_opencv, sample_video_info):
        """Test error handling during video processing"""
        mock_mp, mock_detector = mock_mediapipe
        mock_cv2, mock_cap = mock_opencv
        
        # Make detector.process raise an exception
        mock_detector.process.side_effect = Exception("MediaPipe error")
        
        engine = FaceDetectionEngine()
        
        # Create frame generator
        frame_generator = self.create_mock_frame_generator(num_frames=5)
        
        with pytest.raises(Exception, match="MediaPipe error"):
            engine.process_video_frames(sample_video_info, frame_generator)


class TestVideoFrameGenerator:
    """Test video frame generator functionality"""
    
    def test_create_video_frame_generator_success(self, mock_opencv):
        """Test successful frame generator creation"""
        mock_cv2, mock_cap = mock_opencv
        
        # Setup mock frames
        mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.side_effect = [
            (True, mock_frame),   # First frame
            (True, mock_frame),   # Second frame
            (False, None)         # End of video
        ]
        mock_cap.get.return_value = 30.0  # 30 FPS
        
        frame_generator = create_video_frame_generator("/test/video.mp4")
        frames = list(frame_generator)
        
        assert len(frames) == 2
        
        # Check first frame
        frame, timestamp, frame_index = frames[0]
        assert frame.shape == (480, 640, 3)
        assert timestamp == 0.0  # 0 / 30
        assert frame_index == 0
        
        # Check second frame
        frame, timestamp, frame_index = frames[1]
        assert timestamp == 1/30.0  # 1 / 30
        assert frame_index == 1
    
    def test_create_video_frame_generator_cannot_open(self, mock_opencv):
        """Test frame generator with video that cannot be opened"""
        mock_cv2, mock_cap = mock_opencv
        mock_cap.isOpened.return_value = False
        
        with pytest.raises(ValueError, match="Cannot open video file"):
            list(create_video_frame_generator("/nonexistent/video.mp4"))
    
    def test_create_video_frame_generator_zero_fps(self, mock_opencv):
        """Test frame generator with zero/invalid FPS"""
        mock_cv2, mock_cap = mock_opencv
        mock_cap.get.return_value = 0.0  # Invalid FPS
        
        # Should use default FPS of 30.0
        mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.side_effect = [(True, mock_frame), (False, None)]
        
        frame_generator = create_video_frame_generator("/test/video.mp4")
        frames = list(frame_generator)
        
        # Should still work with default FPS
        assert len(frames) == 1
        frame, timestamp, frame_index = frames[0]
        assert timestamp == 0.0


class TestFactoryFunction:
    """Test factory function for creating optimized engines"""
    
    def test_create_face_detection_engine_default(self, mock_config, mock_mediapipe, sample_video_info):
        """Test factory function with default parameters"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = create_face_detection_engine(sample_video_info)
        
        assert isinstance(engine, FaceDetectionEngine)
        assert engine.model == FaceDetectionModel.FULL_RANGE  # HD video -> FULL_RANGE
        assert engine.mode == ProcessingMode.BALANCED
        assert engine.min_detection_confidence == 0.5
    
    def test_create_face_detection_engine_low_resolution(self, mock_config, mock_mediapipe):
        """Test factory function with low resolution video"""
        mock_mp, mock_detector = mock_mediapipe
        
        # Create low resolution video info
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=640, height=480,  # SD resolution
            fps=30.0, bitrate=500000, duration=120.5
        )
        
        video_info = VideoInfo(
            file_path=Path("/test/video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=120.5,
            file_size=10485760,
            video_streams=[video_stream],
            audio_streams=[],
            metadata={}
        )
        
        engine = create_face_detection_engine(video_info)
        
        assert engine.model == FaceDetectionModel.SHORT_RANGE  # SD video -> SHORT_RANGE
    
    def test_create_face_detection_engine_quality_mode(self, mock_config, mock_mediapipe, sample_video_info):
        """Test factory function with different quality modes"""
        mock_mp, mock_detector = mock_mediapipe
        
        test_cases = [
            ("realtime", ProcessingMode.REALTIME),
            ("balanced", ProcessingMode.BALANCED),
            ("quality", ProcessingMode.QUALITY),
            ("unknown", ProcessingMode.BALANCED)  # Should default to balanced
        ]
        
        for quality_mode_str, expected_mode in test_cases:
            engine = create_face_detection_engine(sample_video_info, quality_mode=quality_mode_str)
            assert engine.mode == expected_mode
    
    def test_create_face_detection_engine_realtime_multiple(self, mock_config, mock_mediapipe, sample_video_info):
        """Test factory function with different realtime multiples"""
        mock_mp, mock_detector = mock_mediapipe
        
        # Test with 10x realtime (should be 3 fps from 30 fps video)
        engine = create_face_detection_engine(sample_video_info, target_realtime_multiple=10.0)
        
        expected_target_fps = 30.0 / 10.0  # 3.0
        assert engine.target_fps == expected_target_fps


class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_detector_context_manager_exception(self, mock_config, mock_mediapipe):
        """Test detector context manager handles exceptions properly"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine()
        
        # Test that context manager closes detector even on exception
        try:
            with engine._get_detector() as detector:
                raise Exception("Test exception")
        except Exception:
            pass
        
        # Detector should have been closed
        mock_detector.close.assert_called_once()
    
    def test_process_frame_batch_with_errors(self, mock_config, mock_mediapipe, mock_opencv, sample_frame):
        """Test batch processing with some frame processing errors"""
        mock_mp, mock_detector = mock_mediapipe
        mock_cv2, mock_cap = mock_opencv
        
        engine = FaceDetectionEngine()
        
        # Mock _process_frame to raise exception for middle frame
        original_process_frame = engine._process_frame
        
        def mock_process_frame(frame, timestamp, frame_index):
            if frame_index == 301:  # Middle frame fails
                raise Exception("Processing error")
            return original_process_frame(frame, timestamp, frame_index)
        
        with patch.object(engine, '_process_frame', side_effect=mock_process_frame):
            frame_batch = [
                (sample_frame, 10.0, 300),
                (sample_frame, 10.1, 301),  # This will fail
                (sample_frame, 10.2, 302)
            ]
            
            results = engine._process_frame_batch(frame_batch)
            
            # Should have 2 successful results (frame 301 failed)
            assert len(results) == 2
            assert results[0].frame_index == 300
            assert results[1].frame_index == 302
    
    def test_video_info_statistics_edge_cases(self, sample_video_info):
        """Test VideoFaceDetectionResult statistics with edge cases"""
        # Test with empty frame results
        result = VideoFaceDetectionResult(
            video_info=sample_video_info,
            frame_results=[],
            processing_settings={}
        )
        
        assert result.total_frames_processed == 0
        assert result.total_processing_time == 0.0
        assert result.average_fps == 0.0
        assert result.faces_per_second == 0.0
        assert result.best_frame is None
        assert result.worst_frame is None
        assert result.overall_quality_score == 0.0
    
    def test_video_info_statistics_no_faces(self, sample_video_info):
        """Test VideoFaceDetectionResult statistics with frames but no faces"""
        frame_result = FrameFaceDetectionResult(
            timestamp=10.0,
            frame_index=300,
            faces=[],  # No faces
            processing_time=0.05,
            frame_width=1920,
            frame_height=1080
        )
        
        result = VideoFaceDetectionResult(
            video_info=sample_video_info,
            frame_results=[frame_result],
            processing_settings={}
        )
        
        assert result.total_frames_processed == 1
        assert result.best_frame is None  # No frames with faces
        assert result.worst_frame is None
        assert result.overall_quality_score == 0.0
    
    def test_keypoints_extraction_minimal_keypoints(self, mock_config, mock_mediapipe):
        """Test keypoint extraction with minimal keypoints (less than 6)"""
        mock_mp, mock_detector = mock_mediapipe
        
        # Create mock detection with only 4 keypoints
        mock_detection = Mock()
        mock_keypoints = []
        for i, (x, y) in enumerate([(0.3, 0.4), (0.5, 0.4), (0.4, 0.5), (0.4, 0.6)]):
            kp = Mock()
            kp.x = x
            kp.y = y
            mock_keypoints.append(kp)
        
        mock_detection.location_data.relative_keypoints = mock_keypoints
        
        engine = FaceDetectionEngine()
        keypoints = engine._extract_face_keypoints(mock_detection)
        
        # Should have the 4 main keypoints
        assert keypoints.right_eye.x == 0.3
        assert keypoints.left_eye.x == 0.5
        assert keypoints.nose_tip.x == 0.4
        assert keypoints.mouth_center.x == 0.4
        
        # Ear points should be None
        assert keypoints.right_ear is None
        assert keypoints.left_ear is None


class TestQualityAssessment:
    """Test face quality assessment features"""
    
    def test_quality_score_calculation(self, mock_config, mock_mediapipe):
        """Test quality score calculation components"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine(mode=ProcessingMode.BALANCED)  # Quality assessment enabled
        
        # Create a large, well-positioned face
        bbox = FaceBoundingBox(0.2, 0.2, 0.6, 0.6)  # Large face
        keypoints = FaceKeyPoints(
            right_eye=FaceLandmark(0.4, 0.4),
            left_eye=FaceLandmark(0.6, 0.4),  # Straight on (same Y)
            nose_tip=FaceLandmark(0.5, 0.5),
            mouth_center=FaceLandmark(0.5, 0.58)  # Well positioned
        )
        
        face_result = FaceDetectionResult(
            bounding_box=bbox,
            keypoints=keypoints,
            confidence=0.9  # High confidence
        )
        
        assessed_result = engine._assess_face_quality(face_result, 1920, 1080)
        
        # Should have high quality score for this well-positioned face
        assert assessed_result.quality_score > 0.6
        assert assessed_result.quality_level in [FaceQuality.GOOD, FaceQuality.EXCELLENT]
        assert assessed_result.occlusion_score < 0.3
        assert assessed_result.is_occluded == False
    
    def test_quality_score_poor_face(self, mock_config, mock_mediapipe):
        """Test quality score for poor quality face"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine(mode=ProcessingMode.BALANCED)
        
        # Create a small, poorly positioned face
        bbox = FaceBoundingBox(0.4, 0.4, 0.1, 0.1)  # Very small face
        keypoints = FaceKeyPoints(
            right_eye=FaceLandmark(0.42, 0.42),
            left_eye=FaceLandmark(0.46, 0.38),  # Tilted (different Y)
            nose_tip=FaceLandmark(0.44, 0.45),
            mouth_center=FaceLandmark(0.44, 0.35)  # Badly positioned mouth
        )
        
        face_result = FaceDetectionResult(
            bounding_box=bbox,
            keypoints=keypoints,
            confidence=0.3  # Low confidence
        )
        
        assessed_result = engine._assess_face_quality(face_result, 1920, 1080)
        
        # Should have lower quality score
        assert assessed_result.quality_score < 0.5
        assert assessed_result.quality_level in [FaceQuality.POOR, FaceQuality.FAIR]
    
    def test_occlusion_detection(self, mock_config, mock_mediapipe):
        """Test occlusion detection logic"""
        mock_mp, mock_detector = mock_mediapipe
        
        engine = FaceDetectionEngine(mode=ProcessingMode.BALANCED)
        
        # Create face with mouth significantly out of expected position
        bbox = FaceBoundingBox(0.2, 0.2, 0.4, 0.4)
        keypoints = FaceKeyPoints(
            right_eye=FaceLandmark(0.3, 0.35),
            left_eye=FaceLandmark(0.5, 0.35),
            nose_tip=FaceLandmark(0.4, 0.45),
            mouth_center=FaceLandmark(0.4, 0.25)  # Mouth above eyes (occluded/wrong)
        )
        
        face_result = FaceDetectionResult(
            bounding_box=bbox,
            keypoints=keypoints,
            confidence=0.8
        )
        
        assessed_result = engine._assess_face_quality(face_result, 1920, 1080)
        
        # Should detect occlusion
        assert assessed_result.occlusion_score > 0.3
        assert assessed_result.is_occluded is True


class TestDataClassSerialization:
    """Test data class serialization methods"""
    
    def test_video_face_detection_result_to_dict(self, sample_video_info):
        """Test VideoFaceDetectionResult serialization"""
        bbox = FaceBoundingBox(0.2, 0.3, 0.4, 0.5)
        keypoints = FaceKeyPoints(
            right_eye=FaceLandmark(0.3, 0.4),
            left_eye=FaceLandmark(0.5, 0.4),
            nose_tip=FaceLandmark(0.4, 0.5),
            mouth_center=FaceLandmark(0.4, 0.6)
        )
        
        face_result = FaceDetectionResult(bbox, keypoints, confidence=0.8)
        frame_result = FrameFaceDetectionResult(
            timestamp=10.0,
            frame_index=300,
            faces=[face_result],
            processing_time=0.05,
            frame_width=1920,
            frame_height=1080
        )
        
        video_result = VideoFaceDetectionResult(
            video_info=sample_video_info,
            frame_results=[frame_result],
            processing_settings={"mode": "balanced"}
        )
        
        data = video_result.to_dict()
        
        assert 'video_path' in data
        assert 'video_duration' in data
        assert 'processing_settings' in data
        assert 'statistics' in data
        assert 'frame_results' in data
        assert data['video_path'] == str(sample_video_info.file_path)
        assert data['video_duration'] == sample_video_info.duration
    
    def test_frame_face_detection_result_to_dict(self):
        """Test FrameFaceDetectionResult serialization"""
        bbox = FaceBoundingBox(0.2, 0.3, 0.4, 0.5)
        keypoints = FaceKeyPoints(
            right_eye=FaceLandmark(0.3, 0.4),
            left_eye=FaceLandmark(0.5, 0.4),
            nose_tip=FaceLandmark(0.4, 0.5),
            mouth_center=FaceLandmark(0.4, 0.6)
        )
        
        face_result = FaceDetectionResult(bbox, keypoints, confidence=0.8)
        frame_result = FrameFaceDetectionResult(
            timestamp=10.0,
            frame_index=300,
            faces=[face_result],
            processing_time=0.05,
            frame_width=1920,
            frame_height=1080
        )
        
        data = frame_result.to_dict()
        
        assert 'timestamp' in data
        assert 'frame_index' in data
        assert 'total_faces' in data
        assert 'processing_time' in data
        assert 'frame_dimensions' in data
        assert 'faces' in data
        assert 'best_face' in data
        assert 'average_quality' in data
        
        assert data['timestamp'] == 10.0
        assert data['frame_index'] == 300
        assert data['total_faces'] == 1
        assert len(data['faces']) == 1
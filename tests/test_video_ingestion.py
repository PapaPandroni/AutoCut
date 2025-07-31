"""Tests for video ingestion module"""
import pytest
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from dataclasses import dataclass

from src.video.ingestion import (
    VideoIngestion, VideoInfo, VideoStream, AudioStream,
    VideoCodec, ContainerFormat
)


@pytest.fixture
def mock_config():
    """Mock config values for testing"""
    config_values = {
        'video.max_probe_size_mb': 50,
        'video.probe_timeout_sec': 30,
        'video.enable_hardware_acceleration': True,
        'video.max_file_size_gb': 10
    }
    
    with patch('src.video.ingestion.config') as mock_cfg:
        mock_cfg.get.side_effect = lambda key, default: config_values.get(key, default)
        yield mock_cfg


@pytest.fixture
def mock_subprocess():
    """Mock subprocess calls for FFmpeg operations"""
    with patch('src.video.ingestion.subprocess') as mock_sp:
        # Default FFmpeg version check success
        version_result = Mock()
        version_result.returncode = 0
        version_result.stdout = "ffmpeg version 4.4.0"
        
        # Default hardware acceleration check success
        hwaccel_result = Mock()
        hwaccel_result.returncode = 0
        hwaccel_result.stdout = "Hardware acceleration methods:\nvideotoolbox"
        
        mock_sp.run.side_effect = [version_result, hwaccel_result]
        yield mock_sp


@pytest.fixture
def sample_video_file():
    """Create a temporary file path for testing"""
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
        f.write(b"fake video content")
        file_path = Path(f.name)
    
    # Mock file stats
    with patch.object(Path, 'stat') as mock_stat:
        mock_stat.return_value.st_size = 1024 * 1024  # 1MB
        yield file_path
    
    # Cleanup
    if file_path.exists():
        file_path.unlink()


@pytest.fixture
def mock_ffprobe_response():
    """Mock FFprobe JSON response for a typical video file"""
    return {
        "format": {
            "filename": "/path/to/video.mp4",
            "nb_streams": 2,
            "nb_programs": 0,
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "format_long_name": "QuickTime / MOV",
            "start_time": "0.000000",
            "duration": "120.500000",
            "size": "10485760",
            "bit_rate": "697456",
            "probe_score": 100,
            "tags": {
                "major_brand": "mp42",
                "minor_version": "0",
                "compatible_brands": "mp42isom",
                "creation_time": "2023-01-01T00:00:00.000000Z"
            }
        },
        "streams": [
            {
                "index": 0,
                "codec_name": "h264",
                "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
                "profile": "High",
                "codec_type": "video",
                "codec_tag_string": "avc1",
                "codec_tag": "0x31637661",
                "width": 1920,
                "height": 1080,
                "coded_width": 1920,
                "coded_height": 1080,
                "closed_captions": 0,
                "has_b_frames": 0,
                "pix_fmt": "yuv420p",
                "level": 40,
                "color_range": "tv",
                "color_space": "bt709",
                "color_transfer": "bt709",
                "color_primaries": "bt709",
                "refs": 1,
                "r_frame_rate": "30/1",
                "avg_frame_rate": "30/1",
                "time_base": "1/30000",
                "start_pts": 0,
                "start_time": "0.000000",
                "duration_ts": 3615000,
                "duration": "120.500000",
                "bit_rate": "500000",
                "nb_frames": "3615"
            },
            {
                "index": 1,
                "codec_name": "aac",
                "codec_long_name": "AAC (Advanced Audio Coding)",
                "profile": "LC",
                "codec_type": "audio",
                "codec_tag_string": "mp4a",
                "codec_tag": "0x6134706d",
                "sample_fmt": "fltp",
                "sample_rate": "48000",
                "channels": 2,
                "channel_layout": "stereo",
                "bits_per_raw_sample": 0,
                "r_frame_rate": "0/0",
                "avg_frame_rate": "0/0",
                "time_base": "1/48000",
                "start_pts": 0,
                "start_time": "0.000000",
                "duration_ts": 5784000,
                "duration": "120.500000",
                "bit_rate": "128000",
                "nb_frames": "5654"
            }
        ]
    }


class TestVideoIngestionInitialization:
    """Test VideoIngestion class initialization"""
    
    def test_default_initialization(self, mock_config, mock_subprocess):
        """Test default initialization with config values"""
        ingestion = VideoIngestion()
        
        assert ingestion.max_probe_size == 50 * 1024 * 1024
        assert ingestion.probe_timeout == 30
        assert ingestion.enable_hardware_acceleration is True
        assert ingestion.max_file_size_gb == 10
        
        # Verify FFmpeg verification was called
        assert mock_subprocess.run.call_count == 2
        mock_subprocess.run.assert_any_call(
            ['ffmpeg', '-version'], capture_output=True, text=True, timeout=10
        )
        mock_subprocess.run.assert_any_call(
            ['ffmpeg', '-hwaccels'], capture_output=True, text=True, timeout=10
        )
    
    def test_hardware_acceleration_detection_success(self, mock_config, mock_subprocess):
        """Test successful hardware acceleration detection"""
        ingestion = VideoIngestion()
        assert ingestion.enable_hardware_acceleration is True
    
    def test_hardware_acceleration_detection_failure(self, mock_config):
        """Test hardware acceleration fallback when not available"""
        with patch('src.video.ingestion.subprocess') as mock_sp:
            # FFmpeg version check success
            version_result = Mock()
            version_result.returncode = 0
            version_result.stdout = "ffmpeg version 4.4.0"
            
            # Hardware acceleration check - no videotoolbox
            hwaccel_result = Mock()
            hwaccel_result.returncode = 0
            hwaccel_result.stdout = "Hardware acceleration methods:\ncuda\nnvenc"
            
            mock_sp.run.side_effect = [version_result, hwaccel_result]
            
            ingestion = VideoIngestion()
            assert ingestion.enable_hardware_acceleration is False
    
    def test_ffmpeg_verification_failure(self, mock_config):
        """Test FFmpeg verification failure"""
        with patch('src.video.ingestion.subprocess') as mock_sp:
            mock_sp.run.side_effect = FileNotFoundError("FFmpeg not found")
            mock_sp.TimeoutExpired = subprocess.TimeoutExpired
            
            with pytest.raises(RuntimeError, match="FFmpeg not available"):
                VideoIngestion()
    
    def test_ffmpeg_version_check_failure(self, mock_config):
        """Test FFmpeg version check failure"""
        with patch('src.video.ingestion.subprocess') as mock_sp:
            version_result = Mock()
            version_result.returncode = 1
            version_result.stderr = "Command failed"
            mock_sp.run.return_value = version_result
            mock_sp.TimeoutExpired = subprocess.TimeoutExpired
            
            with pytest.raises(RuntimeError, match="FFmpeg not properly installed"):
                VideoIngestion()


class TestVideoLoading:
    """Test video loading functionality"""
    
    def test_load_video_success(self, mock_config, mock_subprocess, sample_video_file, mock_ffprobe_response):
        """Test successful video loading"""
        # Setup FFprobe mock response
        probe_result = Mock()
        probe_result.returncode = 0
        probe_result.stdout = json.dumps(mock_ffprobe_response)
        mock_subprocess.run.side_effect = [
            Mock(returncode=0, stdout="ffmpeg version 4.4.0"),  # version check
            Mock(returncode=0, stdout="videotoolbox"),  # hwaccel check
            probe_result  # ffprobe call
        ]
        
        with patch.object(Path, 'exists', return_value=True):
            ingestion = VideoIngestion()
            video_info = ingestion.load_video(sample_video_file)
            
            assert isinstance(video_info, VideoInfo)
            assert video_info.file_path == sample_video_file
            assert video_info.container_format == ContainerFormat.MP4
            assert video_info.duration == 120.5
            assert video_info.file_size == 10485760
            assert len(video_info.video_streams) == 1
            assert len(video_info.audio_streams) == 1
            assert video_info.is_valid is True
            assert video_info.hardware_decodable is True
    
    def test_load_video_file_not_found(self, mock_config, mock_subprocess):
        """Test FileNotFoundError for non-existent files"""
        ingestion = VideoIngestion()
        
        with pytest.raises(FileNotFoundError, match="Video file not found"):
            ingestion.load_video("/nonexistent/file.mp4")
    
    def test_load_video_file_too_large(self, mock_config, mock_subprocess):
        """Test ValueError for files that are too large"""
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            file_path = Path(f.name)
        
        try:
            # Mock file size to be larger than limit (10GB)
            with patch.object(Path, 'stat') as mock_stat, \
                 patch.object(Path, 'exists', return_value=True):
                mock_stat.return_value.st_size = 11 * 1024 * 1024 * 1024  # 11GB
                
                ingestion = VideoIngestion()
                
                with pytest.raises(ValueError, match="File too large"):
                    ingestion.load_video(file_path)
        finally:
            if file_path.exists():
                file_path.unlink()
    
    def test_load_video_ffprobe_failure(self, mock_config, mock_subprocess, sample_video_file):
        """Test RuntimeError for FFprobe failures"""
        # Setup FFprobe failure
        probe_result = Mock()
        probe_result.returncode = 1
        probe_result.stderr = "FFprobe failed"
        mock_subprocess.run.side_effect = [
            Mock(returncode=0, stdout="ffmpeg version 4.4.0"),  # version check
            Mock(returncode=0, stdout="videotoolbox"),  # hwaccel check
            probe_result  # ffprobe failure
        ]
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired
        
        with patch.object(Path, 'exists', return_value=True):
            ingestion = VideoIngestion()
            
            with pytest.raises(RuntimeError, match="FFprobe failed"):
                ingestion.load_video(sample_video_file)
    
    def test_load_video_ffprobe_timeout(self, mock_config, mock_subprocess, sample_video_file):
        """Test RuntimeError for FFprobe timeout"""
        # Import TimeoutExpired properly for the test
        from subprocess import TimeoutExpired
        
        mock_subprocess.run.side_effect = [
            Mock(returncode=0, stdout="ffmpeg version 4.4.0"),  # version check
            Mock(returncode=0, stdout="videotoolbox"),  # hwaccel check
            TimeoutExpired("ffprobe", 30)  # ffprobe timeout
        ]
        mock_subprocess.TimeoutExpired = TimeoutExpired
        
        with patch.object(Path, 'exists', return_value=True):
            ingestion = VideoIngestion()
            
            with pytest.raises(RuntimeError, match="Video probing timed out"):
                ingestion.load_video(sample_video_file)
    
    def test_load_video_json_parse_error(self, mock_config, mock_subprocess, sample_video_file):
        """Test RuntimeError for JSON parsing errors"""
        # Setup invalid JSON response
        probe_result = Mock()
        probe_result.returncode = 0
        probe_result.stdout = "invalid json response"
        mock_subprocess.run.side_effect = [
            Mock(returncode=0, stdout="ffmpeg version 4.4.0"),  # version check
            Mock(returncode=0, stdout="videotoolbox"),  # hwaccel check
            probe_result  # invalid json
        ]
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired
        
        with patch.object(Path, 'exists', return_value=True):
            ingestion = VideoIngestion()
            
            with pytest.raises(RuntimeError, match="Failed to parse FFprobe output"):
                ingestion.load_video(sample_video_file)


class TestFormatDetection:
    """Test format detection and codec parsing"""
    
    def test_container_format_detection_from_extension(self, mock_config, mock_subprocess):
        """Test container format detection from file extensions"""
        ingestion = VideoIngestion()
        
        test_cases = [
            ('.mp4', ContainerFormat.MP4),
            ('.mov', ContainerFormat.MOV),
            ('.avi', ContainerFormat.AVI),
            ('.mkv', ContainerFormat.MKV),
            ('.webm', ContainerFormat.WEBM),
            ('.flv', ContainerFormat.FLV),
            ('.m4v', ContainerFormat.M4V)
        ]
        
        for extension, expected_format in test_cases:
            file_path = Path(f"/test/video{extension}")
            detected_format = ingestion._detect_container_format(file_path, "")
            assert detected_format == expected_format
        
        # Test unknown extension with truly unknown format name
        file_path = Path("/test/video.unknown")
        detected_format = ingestion._detect_container_format(file_path, "completely_unknown_format")
        assert detected_format == ContainerFormat.UNKNOWN
    
    def test_container_format_detection_from_format_name(self, mock_config, mock_subprocess):
        """Test container format detection from FFprobe format name"""
        ingestion = VideoIngestion()
        
        # Test format name detection - logic checks if format_name is IN fmt_pattern string
        # Note: Dictionary iteration order matters - first match wins
        test_cases = [
            ('mp4', ContainerFormat.MP4),  # 'mp4' is in 'mov,mp4,m4a,3gp,3g2,mj2'
            ('mov', ContainerFormat.MP4),  # 'mov' is in 'mov,mp4,m4a,3gp,3g2,mj2' (first match)
            ('avi', ContainerFormat.AVI),  # 'avi' matches 'avi'
            ('matroska', ContainerFormat.MKV),  # 'matroska' is in 'matroska,webm'
            ('webm', ContainerFormat.MKV),  # 'webm' matches 'matroska,webm' first (dict order)
            ('flv', ContainerFormat.FLV),  # 'flv' matches 'flv'
            ('unknown_format', ContainerFormat.UNKNOWN)  # no match
        ]
        
        for format_name, expected_format in test_cases:
            file_path = Path("/test/video.unknown")
            detected_format = ingestion._detect_container_format(file_path, format_name)
            assert detected_format == expected_format
    
    def test_codec_detection_from_probe_data(self, mock_config, mock_subprocess):
        """Test codec detection from FFprobe data"""
        ingestion = VideoIngestion()
        
        test_cases = [
            ('h264', 'avc1', VideoCodec.H264),
            ('hevc', 'hev1', VideoCodec.H265),
            ('mpeg4', 'mp4v', VideoCodec.MPEG4),
            ('vp8', '', VideoCodec.VP8),
            ('vp9', '', VideoCodec.VP9),
            ('av01', '', VideoCodec.AV1),
            ('prores', 'apch', VideoCodec.PRORES),
            ('dnxhd', '', VideoCodec.DNX),
            ('unknown_codec', '', VideoCodec.UNKNOWN)
        ]
        
        for codec_name, codec_tag, expected_codec in test_cases:
            stream_data = {
                'index': 0,
                'codec_name': codec_name,
                'codec_tag_string': codec_tag,
                'codec_type': 'video',
                'width': 1920,
                'height': 1080,
                'r_frame_rate': '30/1'
            }
            
            video_stream = ingestion._parse_video_stream(stream_data)
            assert video_stream.codec == expected_codec


class TestVideoValidation:
    """Test video validation methods"""
    
    def test_validate_video_content_success(self, mock_config, mock_subprocess):
        """Test successful video content validation"""
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
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
        
        ingestion._validate_video_content(video_info)
        
        assert video_info.is_valid is True
        assert len(video_info.validation_errors) == 0
    
    def test_validate_video_content_no_streams(self, mock_config, mock_subprocess):
        """Test validation error for no video streams"""
        ingestion = VideoIngestion()
        
        video_info = VideoInfo(
            file_path=Path("/test/video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=120.5,
            file_size=10485760,
            video_streams=[],
            audio_streams=[],
            metadata={}
        )
        
        ingestion._validate_video_content(video_info)
        
        assert video_info.is_valid is False
        assert "No video streams found" in video_info.validation_errors
    
    def test_validate_video_content_invalid_resolution(self, mock_config, mock_subprocess):
        """Test validation error for invalid resolution"""
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=0, height=0,
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
        
        ingestion._validate_video_content(video_info)
        
        assert video_info.is_valid is False
        assert "Invalid resolution: 0x0" in video_info.validation_errors
    
    def test_validate_video_content_invalid_fps(self, mock_config, mock_subprocess):
        """Test validation error for invalid frame rate"""
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
            fps=0.0, bitrate=500000, duration=120.5
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
        
        ingestion._validate_video_content(video_info)
        
        assert video_info.is_valid is False
        assert "Invalid frame rate: 0.0" in video_info.validation_errors
    
    def test_validate_video_content_invalid_duration(self, mock_config, mock_subprocess):
        """Test validation error for invalid duration"""
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
            fps=30.0, bitrate=500000, duration=120.5
        )
        
        video_info = VideoInfo(
            file_path=Path("/test/video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=0.0,  # Invalid duration
            file_size=10485760,
            video_streams=[video_stream],
            audio_streams=[],
            metadata={}
        )
        
        ingestion._validate_video_content(video_info)
        
        assert video_info.is_valid is False
        assert "Invalid duration: 0.0" in video_info.validation_errors
    
    def test_validate_video_content_extreme_resolution(self, mock_config, mock_subprocess):
        """Test validation warning for extremely high resolution"""
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=10000, height=10000,
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
        
        ingestion._validate_video_content(video_info)
        
        assert video_info.is_valid is False
        assert "Extremely high resolution: 10000x10000" in video_info.validation_errors


class TestHardwareAcceleration:
    """Test hardware acceleration detection and usage"""
    
    def test_hardware_compatibility_check_supported(self, mock_config, mock_subprocess):
        """Test hardware compatibility check for supported codec"""
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
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
        
        ingestion._check_hardware_compatibility(video_info)
        
        assert video_info.hardware_decodable is True
    
    def test_hardware_compatibility_check_unsupported(self, mock_config, mock_subprocess):
        """Test hardware compatibility check for unsupported codec"""
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.VP9, width=1920, height=1080,
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
        
        ingestion._check_hardware_compatibility(video_info)
        
        assert video_info.hardware_decodable is False
    
    def test_hardware_compatibility_disabled(self, mock_config):
        """Test hardware compatibility when acceleration is disabled"""
        with patch('src.video.ingestion.subprocess') as mock_sp:
            # FFmpeg version check success
            version_result = Mock()
            version_result.returncode = 0
            version_result.stdout = "ffmpeg version 4.4.0"
            
            # Hardware acceleration check - no videotoolbox
            hwaccel_result = Mock()
            hwaccel_result.returncode = 0
            hwaccel_result.stdout = "Hardware acceleration methods:\ncuda"
            
            mock_sp.run.side_effect = [version_result, hwaccel_result]
            
            ingestion = VideoIngestion()
            
            video_stream = VideoStream(
                index=0, codec=VideoCodec.H264, width=1920, height=1080,
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
            
            ingestion._check_hardware_compatibility(video_info)
            
            assert video_info.hardware_decodable is False
    
    def test_get_optimal_decoder_hardware(self, mock_config, mock_subprocess):
        """Test optimal decoder selection with hardware acceleration"""
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
            fps=30.0, bitrate=500000, duration=120.5
        )
        
        video_info = VideoInfo(
            file_path=Path("/test/video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=120.5,
            file_size=10485760,
            video_streams=[video_stream],
            audio_streams=[],
            metadata={},
            hardware_decodable=True
        )
        
        decoder = ingestion.get_optimal_decoder(video_info)
        assert decoder == "h264_videotoolbox"
    
    def test_get_optimal_decoder_software(self, mock_config, mock_subprocess):
        """Test optimal decoder selection with software decoding"""
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.VP9, width=1920, height=1080,
            fps=30.0, bitrate=500000, duration=120.5
        )
        
        video_info = VideoInfo(
            file_path=Path("/test/video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=120.5,
            file_size=10485760,
            video_streams=[video_stream],
            audio_streams=[],
            metadata={},
            hardware_decodable=False
        )
        
        decoder = ingestion.get_optimal_decoder(video_info)
        assert decoder == "vp9"
    
    def test_get_optimal_decoder_no_video_stream(self, mock_config, mock_subprocess):
        """Test optimal decoder selection with no video streams"""
        ingestion = VideoIngestion()
        
        video_info = VideoInfo(
            file_path=Path("/test/video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=120.5,
            file_size=10485760,
            video_streams=[],
            audio_streams=[],
            metadata={}
        )
        
        decoder = ingestion.get_optimal_decoder(video_info)
        assert decoder == "copy"


class TestFrameExtraction:
    """Test frame extraction functionality"""
    
    @patch('src.video.ingestion.ffmpeg')
    def test_extract_frame_success(self, mock_ffmpeg, mock_config, mock_subprocess):
        """Test successful frame extraction"""
        # Setup mocks
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_ffmpeg.output.return_value = mock_output
        mock_ffmpeg.run.return_value = None
        
        # Setup video stream and filter chain
        mock_input.video = Mock()
        mock_input.video.filter.return_value = mock_input
        mock_input.filter.return_value = mock_input
        
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
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
        
        result = ingestion.extract_frame(video_info, 60.0, "/test/frame.jpg")
        
        assert result is True
        mock_ffmpeg.input.assert_called_once_with("/test/video.mp4")
        mock_ffmpeg.run.assert_called_once()
    
    @patch('src.video.ingestion.ffmpeg')
    def test_extract_frame_with_resize(self, mock_ffmpeg, mock_config, mock_subprocess):
        """Test frame extraction with resizing"""
        # Setup mocks
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_ffmpeg.output.return_value = mock_output
        mock_ffmpeg.run.return_value = None
        
        # Setup video stream and filter chain
        mock_input.video = Mock()
        mock_input.video.filter.return_value = mock_input
        mock_input.filter.return_value = mock_input
        
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
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
        
        result = ingestion.extract_frame(video_info, 60.0, "/test/frame.jpg", 640, 480)
        
        assert result is True
        mock_ffmpeg.input.assert_called_once_with("/test/video.mp4")
        mock_ffmpeg.run.assert_called_once()
    
    @patch('src.video.ingestion.ffmpeg')
    def test_extract_frame_failure(self, mock_ffmpeg, mock_config, mock_subprocess):
        """Test frame extraction failure"""
        # Setup mocks to raise exception
        mock_ffmpeg.input.side_effect = Exception("FFmpeg error")
        
        ingestion = VideoIngestion()
        
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
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
        
        result = ingestion.extract_frame(video_info, 60.0, "/test/frame.jpg")
        
        assert result is False


class TestVideoInfoDataclass:
    """Test VideoInfo dataclass functionality"""
    
    def test_video_info_initialization(self):
        """Test VideoInfo initialization"""
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
            fps=30.0, bitrate=500000, duration=120.5
        )
        
        audio_stream = AudioStream(
            index=1, codec="aac", sample_rate=48000, channels=2,
            bitrate=128000, duration=120.5
        )
        
        video_info = VideoInfo(
            file_path=Path("/test/video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=120.5,
            file_size=10485760,
            video_streams=[video_stream],
            audio_streams=[audio_stream],
            metadata={"title": "Test Video"}
        )
        
        assert video_info.file_path == Path("/test/video.mp4")
        assert video_info.container_format == ContainerFormat.MP4
        assert video_info.duration == 120.5
        assert video_info.file_size == 10485760
        assert len(video_info.video_streams) == 1
        assert len(video_info.audio_streams) == 1
        assert video_info.is_valid is True
        assert video_info.validation_errors == []
        assert video_info.hardware_decodable is False
    
    def test_video_info_primary_streams(self):
        """Test primary stream properties"""
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
            fps=30.0, bitrate=500000, duration=120.5
        )
        
        audio_stream = AudioStream(
            index=1, codec="aac", sample_rate=48000, channels=2,
            bitrate=128000, duration=120.5
        )
        
        video_info = VideoInfo(
            file_path=Path("/test/video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=120.5,
            file_size=10485760,
            video_streams=[video_stream],
            audio_streams=[audio_stream],
            metadata={}
        )
        
        assert video_info.primary_video_stream == video_stream
        assert video_info.primary_audio_stream == audio_stream
    
    def test_video_info_no_streams(self):
        """Test VideoInfo with no streams"""
        video_info = VideoInfo(
            file_path=Path("/test/video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=120.5,
            file_size=10485760,
            video_streams=[],
            audio_streams=[],
            metadata={}
        )
        
        assert video_info.primary_video_stream is None
        assert video_info.primary_audio_stream is None
    
    def test_video_info_resolution_property(self):
        """Test resolution property"""
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
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
        
        assert video_info.resolution == (1920, 1080)
    
    def test_video_info_resolution_no_video(self):
        """Test resolution property with no video streams"""
        video_info = VideoInfo(
            file_path=Path("/test/video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=120.5,
            file_size=10485760,
            video_streams=[],
            audio_streams=[],
            metadata={}
        )
        
        assert video_info.resolution == (0, 0)
    
    def test_video_info_aspect_ratio_property(self):
        """Test aspect ratio property"""
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
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
        
        assert abs(video_info.aspect_ratio - 16/9) < 0.01
    
    def test_video_info_aspect_ratio_zero_height(self):
        """Test aspect ratio property with zero height"""
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=0,
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
        
        assert video_info.aspect_ratio == 0.0
    
    def test_video_info_to_dict(self):
        """Test to_dict method"""
        video_stream = VideoStream(
            index=0, codec=VideoCodec.H264, width=1920, height=1080,
            fps=30.0, bitrate=500000, duration=120.5
        )
        
        audio_stream = AudioStream(
            index=1, codec="aac", sample_rate=48000, channels=2,
            bitrate=128000, duration=120.5
        )
        
        video_info = VideoInfo(
            file_path=Path("/test/video.mp4"),
            container_format=ContainerFormat.MP4,
            duration=120.5,
            file_size=10485760,
            video_streams=[video_stream],
            audio_streams=[audio_stream],
            metadata={"title": "Test Video"},
            is_valid=True,
            validation_errors=[],
            hardware_decodable=True
        )
        
        result = video_info.to_dict()
        
        expected_keys = [
            'file_path', 'container_format', 'duration', 'file_size',
            'resolution', 'aspect_ratio', 'fps', 'video_codec', 'audio_codec',
            'is_valid', 'validation_errors', 'hardware_decodable', 'metadata'
        ]
        
        for key in expected_keys:
            assert key in result
        
        assert result['file_path'] == "/test/video.mp4"
        assert result['container_format'] == "mp4"
        assert result['duration'] == 120.5
        assert result['file_size'] == 10485760
        assert result['resolution'] == (1920, 1080)
        assert abs(result['aspect_ratio'] - 16/9) < 0.01
        assert result['fps'] == 30.0
        assert result['video_codec'] == "h264"
        assert result['audio_codec'] == "aac"
        assert result['is_valid'] is True
        assert result['validation_errors'] == []
        assert result['hardware_decodable'] is True
        assert result['metadata'] == {"title": "Test Video"}


class TestUtilityMethods:
    """Test utility methods"""
    
    def test_is_format_supported(self, mock_config, mock_subprocess):
        """Test format support checking"""
        ingestion = VideoIngestion()
        
        supported_formats = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.m4v']
        for ext in supported_formats:
            assert ingestion.is_format_supported(f"/test/video{ext}") is True
        
        assert ingestion.is_format_supported("/test/video.txt") is False
        assert ingestion.is_format_supported("/test/video.unknown") is False
    
    def test_get_supported_formats(self, mock_config, mock_subprocess):
        """Test getting list of supported formats"""
        ingestion = VideoIngestion()
        
        formats = ingestion.get_supported_formats()
        expected_formats = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.m4v']
        
        assert isinstance(formats, list)
        assert len(formats) == len(expected_formats)
        for fmt in expected_formats:
            assert fmt in formats


class TestStreamParsing:
    """Test stream parsing functionality"""
    
    def test_parse_video_stream_complete(self, mock_config, mock_subprocess):
        """Test parsing complete video stream data"""
        ingestion = VideoIngestion()
        
        stream_data = {
            'index': 0,
            'codec_name': 'h264',
            'codec_tag_string': 'avc1',
            'codec_type': 'video',
            'width': 1920,
            'height': 1080,
            'r_frame_rate': '30/1',
            'bit_rate': '500000',
            'duration': '120.5',
            'pix_fmt': 'yuv420p',
            'color_space': 'bt709',
            'profile': 'High',
            'level': '40'
        }
        
        video_stream = ingestion._parse_video_stream(stream_data)
        
        assert video_stream is not None
        assert video_stream.index == 0
        assert video_stream.codec == VideoCodec.H264
        assert video_stream.width == 1920
        assert video_stream.height == 1080
        assert video_stream.fps == 30.0
        assert video_stream.bitrate == 500000
        assert video_stream.duration == 120.5
        assert video_stream.pixel_format == 'yuv420p'
        assert video_stream.color_space == 'bt709'
        assert video_stream.profile == 'High'
        assert video_stream.level == '40'
    
    def test_parse_video_stream_minimal(self, mock_config, mock_subprocess):
        """Test parsing minimal video stream data"""
        ingestion = VideoIngestion()
        
        stream_data = {
            'index': 0,
            'codec_name': 'h264',
            'codec_type': 'video',
            'width': 1920,
            'height': 1080,
            'r_frame_rate': '25/1'
        }
        
        video_stream = ingestion._parse_video_stream(stream_data)
        
        assert video_stream is not None
        assert video_stream.index == 0
        assert video_stream.codec == VideoCodec.H264
        assert video_stream.width == 1920
        assert video_stream.height == 1080
        assert video_stream.fps == 25.0
        assert video_stream.bitrate is None
        assert video_stream.duration is None
    
    def test_parse_video_stream_complex_fps(self, mock_config, mock_subprocess):
        """Test parsing complex frame rate formats"""
        ingestion = VideoIngestion()
        
        test_cases = [
            ('30/1', 30.0),
            ('25/1', 25.0),
            ('24000/1001', 23.976),
            ('30000/1001', 29.97),
            ('0/1', 0.0),
            ('invalid', 0.0)
        ]
        
        for fps_str, expected_fps in test_cases:
            stream_data = {
                'index': 0,
                'codec_name': 'h264',
                'codec_type': 'video',
                'width': 1920,
                'height': 1080,
                'r_frame_rate': fps_str
            }
            
            video_stream = ingestion._parse_video_stream(stream_data)
            assert abs(video_stream.fps - expected_fps) < 0.01
    
    def test_parse_video_stream_invalid_data(self, mock_config, mock_subprocess):
        """Test parsing invalid video stream data"""
        ingestion = VideoIngestion()
        
        invalid_stream_data = {
            'index': 'invalid',  # Should be int
            'codec_name': 'h264',
            'codec_type': 'video',
            'width': 'invalid',  # Should be int
            'height': 1080,
            'r_frame_rate': '30/1'
        }
        
        video_stream = ingestion._parse_video_stream(invalid_stream_data)
        assert video_stream is None
    
    def test_parse_audio_stream_complete(self, mock_config, mock_subprocess):
        """Test parsing complete audio stream data"""
        ingestion = VideoIngestion()
        
        stream_data = {
            'index': 1,
            'codec_name': 'aac',
            'codec_type': 'audio',
            'sample_rate': '48000',
            'channels': '2',
            'bit_rate': '128000',
            'duration': '120.5'
        }
        
        audio_stream = ingestion._parse_audio_stream(stream_data)
        
        assert audio_stream is not None
        assert audio_stream.index == 1
        assert audio_stream.codec == 'aac'
        assert audio_stream.sample_rate == 48000
        assert audio_stream.channels == 2
        assert audio_stream.bitrate == 128000
        assert audio_stream.duration == 120.5
    
    def test_parse_audio_stream_minimal(self, mock_config, mock_subprocess):
        """Test parsing minimal audio stream data"""
        ingestion = VideoIngestion()
        
        stream_data = {
            'index': 1,
            'codec_name': 'aac',
            'codec_type': 'audio',
            'sample_rate': '48000',
            'channels': '2'
        }
        
        audio_stream = ingestion._parse_audio_stream(stream_data)
        
        assert audio_stream is not None
        assert audio_stream.index == 1
        assert audio_stream.codec == 'aac'
        assert audio_stream.sample_rate == 48000
        assert audio_stream.channels == 2
        assert audio_stream.bitrate is None
        assert audio_stream.duration is None
    
    def test_parse_audio_stream_invalid_data(self, mock_config, mock_subprocess):
        """Test parsing invalid audio stream data"""
        ingestion = VideoIngestion()
        
        invalid_stream_data = {
            'index': 1,
            'codec_name': 'aac',
            'codec_type': 'audio',
            'sample_rate': 'invalid',  # Should be int
            'channels': 2
        }
        
        audio_stream = ingestion._parse_audio_stream(invalid_stream_data)
        assert audio_stream is None


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_parse_probe_data_missing_format(self, mock_config, mock_subprocess):
        """Test parsing probe data with missing format section"""
        ingestion = VideoIngestion()
        
        probe_data = {
            'streams': []
        }
        
        video_info = ingestion._parse_probe_data(Path("/test/video.mp4"), probe_data)
        
        assert video_info.duration == 0.0
        assert video_info.file_size == 0
        assert video_info.container_format == ContainerFormat.MP4  # From extension
        assert len(video_info.video_streams) == 0
        assert len(video_info.audio_streams) == 0
    
    def test_parse_probe_data_missing_streams(self, mock_config, mock_subprocess):
        """Test parsing probe data with missing streams section"""
        ingestion = VideoIngestion()
        
        probe_data = {
            'format': {
                'duration': '120.5',
                'size': '10485760',
                'format_name': 'mov,mp4,m4a,3gp,3g2,mj2'
            }
        }
        
        video_info = ingestion._parse_probe_data(Path("/test/video.mp4"), probe_data)
        
        assert video_info.duration == 120.5
        assert video_info.file_size == 10485760
        assert len(video_info.video_streams) == 0
        assert len(video_info.audio_streams) == 0
    
    def test_parse_probe_data_mixed_streams(self, mock_config, mock_subprocess):
        """Test parsing probe data with mixed valid and invalid streams"""
        ingestion = VideoIngestion()
        
        probe_data = {
            'format': {
                'duration': '120.5',
                'size': '10485760',
                'format_name': 'mov,mp4,m4a,3gp,3g2,mj2'
            },
            'streams': [
                {
                    'index': 0,
                    'codec_name': 'h264',
                    'codec_type': 'video',
                    'width': 1920,
                    'height': 1080,
                    'r_frame_rate': '30/1'
                },
                {
                    'index': 1,
                    'codec_type': 'video',
                    'width': 'invalid',  # This should be ignored
                    'height': 1080,
                    'r_frame_rate': '30/1'
                },
                {
                    'index': 2,
                    'codec_name': 'aac',
                    'codec_type': 'audio',
                    'sample_rate': '48000',
                    'channels': '2'
                }
            ]
        }
        
        video_info = ingestion._parse_probe_data(Path("/test/video.mp4"), probe_data)
        
        assert len(video_info.video_streams) == 1  # Only valid video stream
        assert len(video_info.audio_streams) == 1
        assert video_info.video_streams[0].codec == VideoCodec.H264
    
    def test_load_video_empty_file(self, mock_config, mock_subprocess):
        """Test loading empty video file"""
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            file_path = Path(f.name)
        
        try:
            # Mock empty file
            with patch.object(Path, 'stat') as mock_stat, \
                 patch.object(Path, 'exists', return_value=True):
                mock_stat.return_value.st_size = 0
                
                # Setup minimal probe response for empty file
                probe_result = Mock()
                probe_result.returncode = 0
                probe_result.stdout = json.dumps({
                    'format': {'duration': '0.0', 'size': '0'},
                    'streams': []
                })
                
                mock_subprocess.run.side_effect = [
                    Mock(returncode=0, stdout="ffmpeg version 4.4.0"),
                    Mock(returncode=0, stdout="videotoolbox"),
                    probe_result
                ]
                
                ingestion = VideoIngestion()
                video_info = ingestion.load_video(file_path)
                
                assert video_info.file_size == 0
                assert video_info.duration == 0.0
                assert len(video_info.video_streams) == 0
                assert video_info.is_valid is False  # Should fail validation
        finally:
            if file_path.exists():
                file_path.unlink()
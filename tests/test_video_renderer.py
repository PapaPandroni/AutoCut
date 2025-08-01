"""Tests for video rendering module"""
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from dataclasses import replace

from src.video.renderer import (
    VideoRenderer, RenderOptions, OutputFormat, QualityPreset, RenderingMode,
    RenderProgress, RenderStats, RenderingResult, create_render_options, estimate_render_time
)
from src.core.timeline import EditingTimeline, TimelineSegment, CutPoint, CutType, EditingStyle
from src.video.ingestion import VideoInfo, VideoStream, AudioStream, VideoCodec, ContainerFormat
from src.audio.analyzer import AudioAnalysis
from src.video.scene_detection import SceneDetectionResult, SceneChange


@pytest.fixture
def mock_config():
    """Mock config values for testing"""
    config_values = {
        'video.enable_hardware_acceleration': True,
        'rendering.max_concurrent_renders': 2,
        'rendering.chunk_duration_sec': 30.0,
        'rendering.progress_update_interval_sec': 0.5,
        'processing.max_workers': 4
    }
    
    with patch('src.video.renderer.config') as mock_cfg:
        mock_cfg.get.side_effect = lambda key, default: config_values.get(key, default)
        yield mock_cfg


@pytest.fixture
def mock_subprocess():
    """Mock subprocess calls for FFmpeg operations"""
    with patch('src.video.renderer.subprocess') as mock_sp:
        # Default FFmpeg version check success
        version_result = Mock()
        version_result.returncode = 0
        version_result.stdout = "ffmpeg version 4.4.0"
        
        # Default hardware acceleration check success
        hwaccel_result = Mock()
        hwaccel_result.returncode = 0
        hwaccel_result.stdout = "Hardware acceleration methods:\nvideotoolbox"
        
        # Default encoders check
        encoders_result = Mock()
        encoders_result.returncode = 0
        encoders_result.stdout = "h264_videotoolbox\nh265_videotoolbox\nlibx264\nlibx265"
        
        mock_sp.run.side_effect = [version_result, hwaccel_result, encoders_result]
        yield mock_sp


@pytest.fixture
def sample_video_info():
    """Create sample VideoInfo for testing"""
    video_stream = VideoStream(
        index=0,
        codec=VideoCodec.H264,
        width=1920,
        height=1080,
        fps=30.0,
        bitrate=5000000,
        duration=60.0
    )
    
    audio_stream = AudioStream(
        index=1,
        codec="aac",
        sample_rate=44100,
        channels=2,
        bitrate=192000,
        duration=60.0
    )
    
    return VideoInfo(
        file_path=Path("/test/input.mp4"),
        container_format=ContainerFormat.MP4,
        duration=60.0,
        file_size=50000000,
        video_streams=[video_stream],
        audio_streams=[audio_stream],
        metadata={},
        is_valid=True,
        hardware_decodable=True
    )


@pytest.fixture
def sample_audio_analysis():
    """Create sample AudioAnalysis for testing"""
    return AudioAnalysis(
        bpm=120.0,
        beats=[0.5, 1.0, 1.5, 2.0, 2.5, 3.0],  # Every 0.5 seconds
        confidence=0.8,
        duration=60.0,
        sample_rate=44100,
        tempo_times=[],
        beat_frames=[100, 200, 300, 400, 500, 600]
    )


@pytest.fixture
def sample_scene_detection():
    """Create sample SceneDetectionResult for testing"""
    from src.video.scene_detection import SceneDetectionAlgorithm, ProcessingMode
    
    scene_changes = [
        SceneChange(timestamp=0.0, frame_number=0, confidence=1.0, algorithm=SceneDetectionAlgorithm.HISTOGRAM),
        SceneChange(timestamp=10.0, frame_number=300, confidence=0.8, algorithm=SceneDetectionAlgorithm.HISTOGRAM),
        SceneChange(timestamp=25.0, frame_number=750, confidence=0.9, algorithm=SceneDetectionAlgorithm.EDGE_DETECTION),
        SceneChange(timestamp=45.0, frame_number=1350, confidence=0.7, algorithm=SceneDetectionAlgorithm.OPTICAL_FLOW),
        SceneChange(timestamp=60.0, frame_number=1800, confidence=1.0, algorithm=SceneDetectionAlgorithm.HISTOGRAM)
    ]
    
    return SceneDetectionResult(
        video_info=None,  # Will be set by test
        scene_changes=scene_changes,
        processing_time=2.5,
        algorithm_used=SceneDetectionAlgorithm.COMBINED,
        processing_mode=ProcessingMode.BALANCED,
        frames_processed=1800,
        frames_skipped=200,
        success=True
    )


@pytest.fixture
def sample_timeline(sample_video_info, sample_audio_analysis, sample_scene_detection):
    """Create sample EditingTimeline for testing"""
    sample_scene_detection.video_info = sample_video_info
    
    # Create cut points at scene boundaries
    cut_points = [
        CutPoint(0.0, 1.0, CutType.FORCED_CUT, 0.0, 1.0, 1.0, 0.0),
        CutPoint(10.0, 0.8, CutType.SCENE_CUT, 0.9, 1.0, 0.8, 0.0),
        CutPoint(25.0, 0.9, CutType.SCENE_CUT, 0.8, 1.0, 0.9, 0.0),
        CutPoint(45.0, 0.7, CutType.SCENE_CUT, 0.7, 1.0, 0.7, 0.0),
        CutPoint(60.0, 1.0, CutType.FORCED_CUT, 0.0, 1.0, 1.0, 0.0)
    ]
    
    # Create segments
    segments = [
        TimelineSegment(0.0, 10.0, CutType.FORCED_CUT, CutType.SCENE_CUT),
        TimelineSegment(10.0, 25.0, CutType.SCENE_CUT, CutType.SCENE_CUT),
        TimelineSegment(25.0, 45.0, CutType.SCENE_CUT, CutType.SCENE_CUT),
        TimelineSegment(45.0, 60.0, CutType.SCENE_CUT, CutType.FORCED_CUT)
    ]
    
    return EditingTimeline(
        video_info=sample_video_info,
        audio_analysis=sample_audio_analysis,
        scene_detection=sample_scene_detection,
        cut_points=cut_points,
        segments=segments,
        editing_style=EditingStyle.ADAPTIVE,
        generation_time=1.5,
        total_duration=60.0,
        success=True
    )


class TestVideoRenderer:
    """Test cases for VideoRenderer class"""
    
    def test_renderer_initialization(self, mock_config, mock_subprocess):
        """Test renderer initialization with configuration"""
        renderer = VideoRenderer()
        
        assert renderer.enable_hardware_acceleration is True
        assert renderer.max_concurrent_renders == 2
        assert renderer.chunk_duration == 30.0
        assert renderer._active_renders == {}
        
        # Verify FFmpeg verification was called
        assert mock_subprocess.run.call_count >= 2
    
    def test_renderer_initialization_no_hardware_acceleration(self, mock_config, mock_subprocess):
        """Test renderer initialization when hardware acceleration is not available"""
        # Mock no hardware acceleration available
        hwaccel_result = Mock()
        hwaccel_result.returncode = 0
        hwaccel_result.stdout = "No hardware acceleration methods found"
        
        mock_subprocess.run.side_effect = [
            Mock(returncode=0, stdout="ffmpeg version 4.4.0"),  # version check
            hwaccel_result,  # hwaccel check
            Mock(returncode=0, stdout="libx264\nlibx265")  # encoders check
        ]
        
        renderer = VideoRenderer()
        assert renderer.enable_hardware_acceleration is False
    
    def test_ffmpeg_verification_failure(self, mock_config):
        """Test renderer initialization when FFmpeg is not available"""
        with patch('src.video.renderer.subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("FFmpeg not found")
            
            with pytest.raises(RuntimeError, match="FFmpeg not available"):
                VideoRenderer()
    
    def test_can_use_stream_copy_lossless(self, mock_config, mock_subprocess, sample_video_info):
        """Test stream copy detection for lossless rendering"""
        renderer = VideoRenderer()
        
        options = RenderOptions(
            quality_preset=QualityPreset.LOSSLESS,
            output_format=OutputFormat.MP4
        )
        
        assert renderer._can_use_stream_copy(sample_video_info, options) is True
    
    def test_can_use_stream_copy_with_resolution_change(self, mock_config, mock_subprocess, sample_video_info):
        """Test stream copy detection when resolution change is requested"""
        renderer = VideoRenderer()
        
        options = RenderOptions(
            quality_preset=QualityPreset.LOSSLESS,
            output_format=OutputFormat.MP4,
            target_resolution=(1280, 720)
        )
        
        assert renderer._can_use_stream_copy(sample_video_info, options) is False
    
    def test_can_use_stream_copy_non_lossless(self, mock_config, mock_subprocess, sample_video_info):
        """Test stream copy detection for non-lossless quality"""
        renderer = VideoRenderer()
        
        options = RenderOptions(
            quality_preset=QualityPreset.HIGH,
            output_format=OutputFormat.MP4
        )
        
        assert renderer._can_use_stream_copy(sample_video_info, options) is False
    
    def test_get_optimal_video_codec_stream_copy(self, mock_config, mock_subprocess, sample_video_info):
        """Test optimal codec selection for stream copy"""
        renderer = VideoRenderer()
        
        options = RenderOptions(enable_hardware_acceleration=True)
        quality_settings = {'video_codec': 'copy'}
        
        codec = renderer._get_optimal_video_codec(sample_video_info, options, quality_settings)
        assert codec == 'copy'
    
    def test_get_optimal_video_codec_hardware(self, mock_config, mock_subprocess, sample_video_info):
        """Test optimal codec selection with hardware acceleration"""
        renderer = VideoRenderer()
        
        options = RenderOptions(enable_hardware_acceleration=True)
        quality_settings = {'video_codec': 'libx264'}
        
        with patch.object(renderer, '_is_encoder_available', return_value=True):
            codec = renderer._get_optimal_video_codec(sample_video_info, options, quality_settings)
            assert codec == 'h264_videotoolbox'
    
    def test_get_optimal_video_codec_software_fallback(self, mock_config, mock_subprocess, sample_video_info):
        """Test optimal codec selection falls back to software"""
        renderer = VideoRenderer()
        
        options = RenderOptions(enable_hardware_acceleration=False)
        quality_settings = {'video_codec': 'libx264'}
        
        codec = renderer._get_optimal_video_codec(sample_video_info, options, quality_settings)
        assert codec == 'libx264'
    
    def test_validate_render_inputs_valid(self, mock_config, mock_subprocess, sample_timeline):
        """Test validation of valid render inputs"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            options = RenderOptions()
            
            # Should not raise any exception
            renderer._validate_render_inputs(sample_timeline, output_path, options)
    
    def test_validate_render_inputs_failed_timeline(self, mock_config, mock_subprocess, sample_timeline):
        """Test validation with failed timeline"""
        renderer = VideoRenderer()
        
        # Make timeline failed
        sample_timeline.success = False
        sample_timeline.errors = ["Timeline generation failed"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            options = RenderOptions()
            
            with pytest.raises(ValueError, match="Timeline has errors"):
                renderer._validate_render_inputs(sample_timeline, output_path, options)
    
    def test_validate_render_inputs_no_segments(self, mock_config, mock_subprocess, sample_timeline):
        """Test validation with no segments"""
        renderer = VideoRenderer()
        
        # Remove segments
        sample_timeline.segments = []
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            options = RenderOptions()
            
            with pytest.raises(ValueError, match="Timeline has no segments"):
                renderer._validate_render_inputs(sample_timeline, output_path, options)
    
    def test_validate_render_inputs_invalid_video(self, mock_config, mock_subprocess, sample_timeline):
        """Test validation with invalid video info"""
        renderer = VideoRenderer()
        
        # Make video info invalid
        sample_timeline.video_info.is_valid = False
        sample_timeline.video_info.validation_errors = ["Invalid codec"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            options = RenderOptions()
            
            with pytest.raises(ValueError, match="Video info is invalid"):
                renderer._validate_render_inputs(sample_timeline, output_path, options)
    
    def test_validate_render_inputs_invalid_resolution(self, mock_config, mock_subprocess, sample_timeline):
        """Test validation with invalid target resolution"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            options = RenderOptions(target_resolution=(0, 720))  # Invalid width
            
            with pytest.raises(ValueError, match="Invalid target resolution"):
                renderer._validate_render_inputs(sample_timeline, output_path, options)
    
    def test_extract_segment_stream_copy(self, mock_config, mock_subprocess, sample_video_info):
        """Test segment extraction using stream copy"""
        renderer = VideoRenderer()
        
        segment = TimelineSegment(10.0, 20.0, CutType.SCENE_CUT, CutType.SCENE_CUT)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "segment.mp4"
            options = RenderOptions()
            
            # Mock successful FFmpeg execution
            with patch('src.video.renderer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr="")
                
                renderer._extract_segment_stream_copy(sample_video_info, segment, output_file, options)
                
                # Verify FFmpeg was called with correct parameters
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                
                assert 'ffmpeg' in call_args
                assert '-ss' in call_args
                assert '10.0' in call_args
                assert '-t' in call_args 
                assert '10.0' in call_args  # duration = end - start
                assert '-c' in call_args
                assert 'copy' in call_args
    
    def test_extract_segment_stream_copy_failure(self, mock_config, mock_subprocess, sample_video_info):
        """Test segment extraction failure handling"""
        renderer = VideoRenderer()
        
        segment = TimelineSegment(10.0, 20.0, CutType.SCENE_CUT, CutType.SCENE_CUT)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "segment.mp4"
            options = RenderOptions()
            
            # Mock FFmpeg failure
            with patch('src.video.renderer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=1, stderr="Encoding failed")
                
                with pytest.raises(RuntimeError, match="FFmpeg segment extraction failed"):
                    renderer._extract_segment_stream_copy(sample_video_info, segment, output_file, options)
    
    def test_concatenate_segments(self, mock_config, mock_subprocess):
        """Test segment concatenation"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # Create dummy segment files
            segment_files = []
            for i in range(3):
                segment_file = temp_dir_path / f"segment_{i}.mp4"
                segment_file.touch()
                segment_files.append(segment_file)
            
            output_path = temp_dir_path / "output.mp4"
            options = RenderOptions()
            
            # Mock successful concatenation
            with patch('src.video.renderer.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stderr="")
                
                renderer._concatenate_segments(segment_files, output_path, options)
                
                # Verify FFmpeg concat was called
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                
                assert 'ffmpeg' in call_args
                assert '-f' in call_args
                assert 'concat' in call_args
                assert '-c' in call_args
                assert 'copy' in call_args
    
    def test_is_encoder_available(self, mock_config, mock_subprocess):
        """Test encoder availability checking"""
        renderer = VideoRenderer()
        
        with patch('src.video.renderer.subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="h264_videotoolbox\nlibx264\nh265_videotoolbox"
            )
            
            assert renderer._is_encoder_available('h264_videotoolbox') is True
            assert renderer._is_encoder_available('libx264') is True
            assert renderer._is_encoder_available('unknown_encoder') is False
    
    def test_is_hardware_codec(self, mock_config, mock_subprocess):
        """Test hardware codec detection"""
        renderer = VideoRenderer()
        
        assert renderer._is_hardware_codec('h264_videotoolbox') is True
        assert renderer._is_hardware_codec('h265_nvenc') is True
        assert renderer._is_hardware_codec('h264_qsv') is True
        assert renderer._is_hardware_codec('libx264') is False
        assert renderer._is_hardware_codec('libx265') is False
    
    def test_cancel_render(self, mock_config, mock_subprocess):
        """Test render cancellation"""
        renderer = VideoRenderer()
        
        render_id = "test_render_123"
        renderer._active_renders[render_id] = True
        
        assert renderer.cancel_render(render_id) is True
        assert renderer._active_renders[render_id] is False
        
        # Cancelling non-existent render should return False
        assert renderer.cancel_render("non_existent") is False
    
    def test_get_active_renders(self, mock_config, mock_subprocess):
        """Test getting active renders list"""
        renderer = VideoRenderer()
        
        renderer._active_renders = {
            "render_1": True,
            "render_2": False,
            "render_3": True
        }
        
        active = renderer.get_active_renders()
        assert "render_1" in active
        assert "render_3" in active
        assert "render_2" not in active
        assert len(active) == 2
    
    def test_cleanup_temp_files(self, mock_config, mock_subprocess):
        """Test temporary files cleanup"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir) / "test_cleanup"
            temp_dir_path.mkdir()
            
            # Create some files
            (temp_dir_path / "file1.txt").touch()
            (temp_dir_path / "file2.txt").touch()
            
            assert temp_dir_path.exists()
            
            renderer._cleanup_temp_files(temp_dir_path)
            
            assert not temp_dir_path.exists()
    
    def test_shutdown(self, mock_config, mock_subprocess):
        """Test renderer shutdown"""
        renderer = VideoRenderer()
        
        # Add some active renders
        renderer._active_renders = {"render_1": True, "render_2": True}
        
        renderer.shutdown()
        
        # All renders should be cancelled
        for render_id, active in renderer._active_renders.items():
            assert active is False


class TestRenderOptions:
    """Test cases for RenderOptions class"""
    
    def test_render_options_defaults(self):
        """Test RenderOptions default values"""
        options = RenderOptions()
        
        assert options.output_format == OutputFormat.MP4
        assert options.quality_preset == QualityPreset.LOSSLESS
        assert options.target_resolution is None
        assert options.target_fps is None
        assert options.audio_bitrate == "192k"
        assert options.video_bitrate is None
        assert options.enable_hardware_acceleration is True
        assert options.use_stream_copy is True
        assert options.parallel_processing is True
        assert options.preserve_metadata is True
        assert options.frame_accurate_cuts is True
    
    def test_render_options_post_init(self):
        """Test RenderOptions post-initialization"""
        with patch('src.video.renderer.config') as mock_cfg:
            mock_cfg.get.return_value = 8
            
            options = RenderOptions()
            
            # max_workers should be the minimum of 4 and config value
            assert options.max_workers == 4  # min(4, config value)
            # temp_dir should be set
            assert options.temp_dir is not None
            assert "autocut_render" in str(options.temp_dir)


class TestUtilityFunctions:
    """Test cases for utility functions"""
    
    def test_create_render_options_defaults(self):
        """Test create_render_options with defaults"""
        options = create_render_options()
        
        assert options.quality_preset == QualityPreset.LOSSLESS
        assert options.output_format == OutputFormat.MP4
        assert options.target_resolution is None
        assert options.target_fps is None
    
    def test_create_render_options_quality_presets(self):
        """Test create_render_options with different quality presets"""
        options = create_render_options(quality="high")
        assert options.quality_preset == QualityPreset.HIGH
        
        options = create_render_options(quality="medium")
        assert options.quality_preset == QualityPreset.MEDIUM
        
        options = create_render_options(quality="draft")
        assert options.quality_preset == QualityPreset.DRAFT
        
        # Unknown quality should default to lossless
        options = create_render_options(quality="unknown")
        assert options.quality_preset == QualityPreset.LOSSLESS
    
    def test_create_render_options_output_formats(self):
        """Test create_render_options with different output formats"""
        options = create_render_options(output_format="mov")
        assert options.output_format == OutputFormat.MOV
        
        options = create_render_options(output_format="avi")
        assert options.output_format == OutputFormat.AVI
        
        options = create_render_options(output_format="mkv")
        assert options.output_format == OutputFormat.MKV
        
        options = create_render_options(output_format="webm")
        assert options.output_format == OutputFormat.WEBM
        
        # Unknown format should default to MP4
        options = create_render_options(output_format="unknown")
        assert options.output_format == OutputFormat.MP4
    
    def test_create_render_options_resolutions(self):
        """Test create_render_options with different resolutions"""
        options = create_render_options(resolution="1080p")
        assert options.target_resolution == (1920, 1080)
        
        options = create_render_options(resolution="720p")
        assert options.target_resolution == (1280, 720)
        
        options = create_render_options(resolution="480p")
        assert options.target_resolution == (854, 480)
        
        # Custom resolution format
        options = create_render_options(resolution="1280x960")
        assert options.target_resolution == (1280, 960)
        
        # Invalid resolution format
        options = create_render_options(resolution="invalid")
        assert options.target_resolution is None
    
    def test_create_render_options_fps(self):
        """Test create_render_options with frame rate"""
        options = create_render_options(fps=60.0)
        assert options.target_fps == 60.0
        
        options = create_render_options(fps=24.0)
        assert options.target_fps == 24.0
    
    def test_estimate_render_time_lossless(self, sample_timeline):
        """Test render time estimation for lossless quality"""
        options = RenderOptions(quality_preset=QualityPreset.LOSSLESS, use_stream_copy=True)
        
        estimated_time = estimate_render_time(sample_timeline, options)
        
        # Should be very fast (15x real-time)
        expected_time = sample_timeline.total_duration / 15.0
        assert abs(estimated_time - expected_time) < 0.1
    
    def test_estimate_render_time_draft(self, sample_timeline):
        """Test render time estimation for draft quality"""
        options = RenderOptions(quality_preset=QualityPreset.DRAFT)
        
        estimated_time = estimate_render_time(sample_timeline, options)
        
        # Should be fast (4x real-time)
        expected_time = sample_timeline.total_duration / 4.0
        assert abs(estimated_time - expected_time) < 0.1
    
    def test_estimate_render_time_medium(self, sample_timeline):
        """Test render time estimation for medium quality"""
        options = RenderOptions(quality_preset=QualityPreset.MEDIUM)
        
        estimated_time = estimate_render_time(sample_timeline, options)
        
        # Should be moderate (2x real-time)
        expected_time = sample_timeline.total_duration / 2.0
        assert abs(estimated_time - expected_time) < 0.1
    
    def test_estimate_render_time_high(self, sample_timeline):
        """Test render time estimation for high quality"""
        options = RenderOptions(quality_preset=QualityPreset.HIGH)
        
        estimated_time = estimate_render_time(sample_timeline, options)
        
        # Should be slow (0.67x real-time)
        expected_time = sample_timeline.total_duration * 1.5
        assert abs(estimated_time - expected_time) < 0.1


class TestRenderStats:
    """Test cases for RenderStats class"""
    
    def test_render_stats_speed_factor(self):
        """Test speed factor calculation"""
        stats = RenderStats(
            total_duration=60.0,
            processing_time=4.0,  # 4 seconds to process 60 seconds
            average_fps=30.0,
            peak_fps=45.0,
            segments_processed=4,
            total_frames=1800,
            output_file_size=50000000,
            compression_ratio=1.2,
            quality_preset=QualityPreset.LOSSLESS,
            used_stream_copy=True,
            hardware_acceleration=False
        )
        
        # Speed factor should be 15x (60/4)
        assert abs(stats.speed_factor - 15.0) < 0.1
    
    def test_render_stats_speed_factor_zero_time(self):
        """Test speed factor with zero processing time"""
        stats = RenderStats(
            total_duration=60.0,
            processing_time=0.0,
            average_fps=30.0,
            peak_fps=45.0,
            segments_processed=4,
            total_frames=1800,
            output_file_size=50000000,
            compression_ratio=1.2,
            quality_preset=QualityPreset.LOSSLESS,
            used_stream_copy=True,
            hardware_acceleration=False
        )
        
        assert stats.speed_factor == 0.0


class TestRenderProgress:
    """Test cases for RenderProgress class"""
    
    def test_render_progress_percentage(self):
        """Test progress percentage calculation"""
        progress = RenderProgress(
            current_segment=2,
            total_segments=8,
            elapsed_time=10.0,
            estimated_remaining=30.0,
            current_fps=25.0,
            total_frames_processed=750,
            total_frames=3000
        )
        
        # Should be 25% (2/8 * 100)
        assert abs(progress.progress_percentage - 25.0) < 0.1
    
    def test_render_progress_percentage_zero_segments(self):
        """Test progress percentage with zero total segments"""
        progress = RenderProgress(
            current_segment=0,
            total_segments=0,
            elapsed_time=0.0,
            estimated_remaining=0.0,
            current_fps=0.0,
            total_frames_processed=0,
            total_frames=0
        )
        
        assert progress.progress_percentage == 0.0


class TestRenderMultiVideoTimeline:
    """Test cases for render_multi_video_timeline method"""
    
    @pytest.fixture
    def multi_video_timeline(self, sample_video_info):
        """Create timeline with segments from multiple videos"""
        # Create segments with different source videos
        segments = [
            TimelineSegment(0.0, 10.0, CutType.FORCED_CUT, CutType.SCENE_CUT, 
                          source_video_index=0, source_start_time=5.0, source_end_time=15.0),
            TimelineSegment(10.0, 25.0, CutType.SCENE_CUT, CutType.SCENE_CUT,
                          source_video_index=1, source_start_time=20.0, source_end_time=35.0),
            TimelineSegment(25.0, 35.0, CutType.SCENE_CUT, CutType.FORCED_CUT,
                          source_video_index=0, source_start_time=40.0, source_end_time=50.0)
        ]
        
        cut_points = [
            CutPoint(0.0, 1.0, CutType.FORCED_CUT, 0.0, 1.0, 1.0, 0.0),
            CutPoint(10.0, 0.8, CutType.SCENE_CUT, 0.9, 1.0, 0.8, 0.0),
            CutPoint(25.0, 0.9, CutType.SCENE_CUT, 0.8, 1.0, 0.9, 0.0),
            CutPoint(35.0, 1.0, CutType.FORCED_CUT, 0.0, 1.0, 1.0, 0.0)
        ]
        
        return EditingTimeline(
            video_info=sample_video_info,
            audio_analysis=None,
            scene_detection=None,
            cut_points=cut_points,
            segments=segments,
            editing_style=EditingStyle.ADAPTIVE,
            generation_time=1.5,
            total_duration=35.0,
            success=True
        )
    
    @pytest.fixture
    def multi_video_info_list(self, sample_video_info):
        """Create list of VideoInfo for multiple source videos"""
        video_info_2 = replace(sample_video_info, 
                             file_path=Path("/test/input2.mp4"),
                             duration=120.0)
        return [sample_video_info, video_info_2]
    
    def test_render_multi_video_timeline_success_with_music(self, mock_config, mock_subprocess, 
                                                          multi_video_timeline, multi_video_info_list):
        """Test successful multi-video rendering with music"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            output_path = temp_dir_path / "output.mp4"
            music_path = temp_dir_path / "music.mp3"
            music_path.touch()  # Create dummy music file
            
            progress_updates = []
            def progress_callback(message, progress):
                progress_updates.append((message, progress))
            
            # Mock the helper methods
            with patch.object(renderer, '_extract_timeline_clips') as mock_extract, \
                 patch.object(renderer, '_create_concat_file') as mock_concat, \
                 patch.object(renderer, '_render_final_video_with_music') as mock_render, \
                 patch.object(renderer, '_cleanup_temp_files') as mock_cleanup:
                
                # Setup mocks
                mock_clip_files = [temp_dir_path / f"clip_{i}.mp4" for i in range(3)]
                for clip_file in mock_clip_files:
                    clip_file.touch()
                mock_extract.return_value = mock_clip_files
                
                mock_concat_file = temp_dir_path / "concat.txt"
                mock_concat_file.touch()
                mock_concat.return_value = mock_concat_file
                
                # Create output file to simulate successful rendering
                output_path.write_bytes(b"fake video content" * 1000)
                
                # Execute test
                result = renderer.render_multi_video_timeline(
                    timeline=multi_video_timeline,
                    video_info_list=multi_video_info_list,
                    music_path=music_path,
                    output_path=output_path,
                    preset=QualityPreset.LOSSLESS,
                    progress_callback=progress_callback
                )
                
                # Verify result
                assert result.success is True
                assert result.output_path == output_path
                assert result.processing_time > 0
                assert result.output_file_size > 0
                assert result.timeline_duration == 35.0
                assert result.segments_rendered == 3
                assert result.speed_factor > 0
                assert result.quality_preset == "lossless"
                assert result.error_message is None
                
                # Verify progress callbacks
                assert len(progress_updates) > 0
                assert any("Extracting video clips" in msg for msg, _ in progress_updates)
                assert any("Rendering complete" in msg for msg, _ in progress_updates)
                
                # Verify helper methods were called
                mock_extract.assert_called_once_with(multi_video_timeline, multi_video_info_list, progress_callback)
                mock_concat.assert_called_once_with(mock_clip_files, multi_video_timeline)
                mock_render.assert_called_once()
                mock_cleanup.assert_called_once()
    
    def test_render_multi_video_timeline_success_without_music(self, mock_config, mock_subprocess,
                                                             multi_video_timeline, multi_video_info_list):
        """Test successful multi-video rendering without music"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            output_path = temp_dir_path / "output.mp4"
            
            with patch.object(renderer, '_extract_timeline_clips') as mock_extract, \
                 patch.object(renderer, '_create_concat_file') as mock_concat, \
                 patch.object(renderer, '_render_final_video_with_music') as mock_render, \
                 patch.object(renderer, '_cleanup_temp_files') as mock_cleanup:
                
                mock_clip_files = [temp_dir_path / f"clip_{i}.mp4" for i in range(3)]
                for clip_file in mock_clip_files:
                    clip_file.touch()
                mock_extract.return_value = mock_clip_files
                
                mock_concat_file = temp_dir_path / "concat.txt"
                mock_concat_file.touch()
                mock_concat.return_value = mock_concat_file
                
                output_path.write_bytes(b"fake video content" * 500)
                
                result = renderer.render_multi_video_timeline(
                    timeline=multi_video_timeline,
                    video_info_list=multi_video_info_list,
                    music_path=None,  # No music
                    output_path=output_path,
                    preset="high"  # Test string preset
                )
                
                assert result.success is True
                assert result.quality_preset == "high"
                
                # Verify render was called with None for music
                mock_render.assert_called_once()
                args, kwargs = mock_render.call_args
                # music_path should be None (could be in args[1] or kwargs['music_path'])
                if len(args) >= 2:
                    assert args[1] is None
                else:
                    assert kwargs.get('music_path') is None
    
    def test_render_multi_video_timeline_extract_clips_failure(self, mock_config, mock_subprocess,
                                                              multi_video_timeline, multi_video_info_list):
        """Test handling of clip extraction failure"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            
            with patch.object(renderer, '_extract_timeline_clips') as mock_extract:
                mock_extract.side_effect = RuntimeError("Failed to extract clips")
                
                result = renderer.render_multi_video_timeline(
                    timeline=multi_video_timeline,
                    video_info_list=multi_video_info_list,
                    output_path=output_path
                )
                
                assert result.success is False
                assert "Failed to extract clips" in result.error_message
                assert result.processing_time > 0
    
    def test_render_multi_video_timeline_final_render_failure(self, mock_config, mock_subprocess,
                                                            multi_video_timeline, multi_video_info_list):
        """Test handling of final render failure"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            output_path = temp_dir_path / "output.mp4"
            
            with patch.object(renderer, '_extract_timeline_clips') as mock_extract, \
                 patch.object(renderer, '_create_concat_file') as mock_concat, \
                 patch.object(renderer, '_render_final_video_with_music') as mock_render, \
                 patch.object(renderer, '_cleanup_temp_files') as mock_cleanup:
                
                mock_clip_files = [temp_dir_path / f"clip_{i}.mp4" for i in range(3)]
                mock_extract.return_value = mock_clip_files
                mock_concat.return_value = temp_dir_path / "concat.txt"
                mock_render.side_effect = RuntimeError("FFmpeg render failed")
                
                result = renderer.render_multi_video_timeline(
                    timeline=multi_video_timeline,
                    video_info_list=multi_video_info_list,
                    output_path=output_path
                )
                
                assert result.success is False
                assert "FFmpeg render failed" in result.error_message
                
                # Verify cleanup was attempted even on failure
                mock_cleanup.assert_called()
    
    def test_render_multi_video_timeline_different_quality_presets(self, mock_config, mock_subprocess,
                                                                  multi_video_timeline, multi_video_info_list):
        """Test different quality presets"""
        renderer = VideoRenderer()
        
        test_presets = [QualityPreset.LOSSLESS, QualityPreset.HIGH, QualityPreset.MEDIUM, QualityPreset.DRAFT]
        
        for preset in test_presets:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = Path(temp_dir) / f"output_{preset.value}.mp4"
                
                with patch.object(renderer, '_extract_timeline_clips'), \
                     patch.object(renderer, '_create_concat_file'), \
                     patch.object(renderer, '_render_final_video_with_music'), \
                     patch.object(renderer, '_cleanup_temp_files'):
                    
                    output_path.write_bytes(b"fake content")
                    
                    result = renderer.render_multi_video_timeline(
                        timeline=multi_video_timeline,
                        video_info_list=multi_video_info_list,
                        output_path=output_path,
                        preset=preset
                    )
                    
                    assert result.success is True
                    assert result.quality_preset == preset.value
    
    def test_render_multi_video_timeline_none_output_path(self, mock_config, mock_subprocess,
                                                        multi_video_timeline, multi_video_info_list):
        """Test that passing None as output_path raises ValueError"""
        renderer = VideoRenderer()
        
        with pytest.raises(ValueError, match="output_path parameter is required and cannot be None"):
            renderer.render_multi_video_timeline(
                timeline=multi_video_timeline,
                video_info_list=multi_video_info_list,
                output_path=None
            )
    
    def test_render_multi_video_timeline_boolean_output_path(self, mock_config, mock_subprocess,
                                                           multi_video_timeline, multi_video_info_list):
        """Test that passing True or False as output_path raises TypeError with specific message about boolean values"""
        renderer = VideoRenderer()
        
        # Test with True
        with pytest.raises(TypeError, match=r"output_path cannot be a boolean value \(received: True\)"):
            renderer.render_multi_video_timeline(
                timeline=multi_video_timeline,
                video_info_list=multi_video_info_list,
                output_path=True
            )
        
        # Test with False
        with pytest.raises(TypeError, match=r"output_path cannot be a boolean value \(received: False\)"):
            renderer.render_multi_video_timeline(
                timeline=multi_video_timeline,
                video_info_list=multi_video_info_list,
                output_path=False
            )
    
    def test_render_multi_video_timeline_invalid_output_path_type(self, mock_config, mock_subprocess,
                                                                multi_video_timeline, multi_video_info_list):
        """Test that passing invalid types (like int, list, etc.) raises TypeError"""
        renderer = VideoRenderer()
        
        invalid_paths = [
            (123, "int"),
            (["/path/to/file"], "list"),
            ({"path": "/test"}, "dict"),
            (object(), "object")
        ]
        
        for invalid_path, type_name in invalid_paths:
            with pytest.raises(TypeError, match=f"output_path must be a Path object or valid path string.*{type_name}"):
                renderer.render_multi_video_timeline(
                    timeline=multi_video_timeline,
                    video_info_list=multi_video_info_list,
                    output_path=invalid_path
                )
    
    def test_render_multi_video_timeline_string_output_path_conversion(self, mock_config, mock_subprocess,
                                                                     multi_video_timeline, multi_video_info_list):
        """Test that passing a valid string path gets converted to Path object successfully"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path_str = str(Path(temp_dir) / "output.mp4")
            
            with patch.object(renderer, '_extract_timeline_clips') as mock_extract, \
                 patch.object(renderer, '_create_concat_file') as mock_concat, \
                 patch.object(renderer, '_render_final_video_with_music') as mock_render, \
                 patch.object(renderer, '_cleanup_temp_files') as mock_cleanup:
                
                # Setup mocks for successful execution
                mock_clip_files = [Path(temp_dir) / f"clip_{i}.mp4" for i in range(3)]
                for clip_file in mock_clip_files:
                    clip_file.touch()
                mock_extract.return_value = mock_clip_files
                
                mock_concat_file = Path(temp_dir) / "concat.txt"
                mock_concat_file.touch()
                mock_concat.return_value = mock_concat_file
                
                # Create output file to simulate successful rendering
                Path(output_path_str).write_bytes(b"fake video content")
                
                # Execute test - string should be converted to Path successfully
                result = renderer.render_multi_video_timeline(
                    timeline=multi_video_timeline,
                    video_info_list=multi_video_info_list,
                    output_path=output_path_str,  # Pass as string
                    preset=QualityPreset.LOSSLESS
                )
                
                # Verify successful conversion and rendering
                assert result.success is True
                assert result.output_path == Path(output_path_str)
                assert isinstance(result.output_path, Path)
                
                # Verify the helper methods were called (meaning validation passed)
                mock_extract.assert_called_once()
                mock_concat.assert_called_once()
                mock_render.assert_called_once()
                mock_cleanup.assert_called_once()
    
    def test_render_final_video_with_music_ffmpeg_boolean_error(self, mock_config):
        """Test handling of FFmpeg boolean parameter error"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            concat_file = Path(temp_dir) / "concat.txt"
            music_path = Path(temp_dir) / "music.mp3"
            
            # Create dummy files
            concat_file.write_text("file '/fake/video.mp4'\n")
            music_path.write_bytes(b"fake music data")
            
            # Mock render options
            render_options = Mock()
            render_options.ffmpeg_params = {}
            
            # Mock ffmpeg to simulate the "True" filename error using subprocess approach
            with patch('src.video.renderer.ffmpeg.input') as mock_input, \
                 patch('src.video.renderer.ffmpeg.output') as mock_output, \
                 patch('src.video.renderer.subprocess.run') as mock_subprocess_run:
                
                # Configure mocks
                mock_video_input = Mock()
                mock_video_input.__getitem__ = Mock(return_value=Mock())
                mock_music_input = Mock()
                mock_music_input.__getitem__ = Mock(return_value=Mock())
                
                mock_input.side_effect = [mock_video_input, mock_music_input]
                
                # Mock the output stream with a compile method
                mock_output_stream = Mock()
                mock_output_stream.compile.return_value = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_file), str(output_path)]
                mock_output.return_value = mock_output_stream
                
                # Simulate subprocess returning FFmpeg error with "True" in stderr (original bug scenario)
                mock_subprocess_result = Mock()
                mock_subprocess_result.returncode = 1  # Error exit code
                mock_subprocess_result.stderr = "Unable to choose an output format for 'True'; use a standard extension"
                mock_subprocess_result.stdout = ""
                mock_subprocess_run.return_value = mock_subprocess_result
                
                # Test that our error handling correctly identifies this as an FFmpeg parameter issue
                with pytest.raises(RuntimeError) as exc_info:
                    renderer._render_final_video_with_music(
                        concat_file=concat_file,
                        music_path=music_path,
                        output_path=output_path,
                        render_options=render_options,
                        timeline_duration=60.0
                    )
                
                # Verify the error message correctly identifies this as a parameter issue (now fixed with subprocess)
                error_msg = str(exc_info.value)
                assert "FFmpeg parameter error" in error_msg
                assert "boolean value was incorrectly passed" in error_msg
                assert "subprocess execution" in error_msg or "should be fixed" in error_msg
                assert str(output_path) in error_msg
    
    def test_render_final_video_with_music_directory_creation(self, mock_config):
        """Test that output directory is created before FFmpeg execution"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested output path that doesn't exist yet
            output_dir = Path(temp_dir) / "nested" / "deep" / "path"
            output_path = output_dir / "output.mp4"
            concat_file = Path(temp_dir) / "concat.txt"
            
            # Create dummy concat file
            concat_file.write_text("file '/fake/video.mp4'\n")
            
            # Mock render options
            render_options = Mock()
            render_options.ffmpeg_params = {}
            
            # Verify the directory doesn't exist initially
            assert not output_dir.exists()
            
            # Mock ffmpeg to avoid actual execution using subprocess approach
            with patch('src.video.renderer.ffmpeg.input') as mock_input, \
                 patch('src.video.renderer.ffmpeg.output') as mock_output, \
                 patch('src.video.renderer.subprocess.run') as mock_subprocess_run:
                
                mock_input.return_value = Mock()
                
                # Mock the output stream with a compile method
                mock_output_stream = Mock()
                mock_output_stream.compile.return_value = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_file), str(output_path)]
                mock_output.return_value = mock_output_stream
                
                # Mock successful subprocess execution
                mock_subprocess_result = Mock()
                mock_subprocess_result.returncode = 0  # Success
                mock_subprocess_result.stderr = ""
                mock_subprocess_result.stdout = ""
                mock_subprocess_run.return_value = mock_subprocess_result
                
                # Test directory creation
                renderer._render_final_video_with_music(
                    concat_file=concat_file,
                    music_path=None,  # No music for this test
                    output_path=output_path,
                    render_options=render_options,
                    timeline_duration=60.0
                )
                
                # Verify the directory was created
                assert output_dir.exists()
                assert output_dir.is_dir()


class TestHelperMethods:
    """Test cases for helper methods used in multi-video rendering"""
    
    @pytest.fixture
    def multi_video_info_list(self, sample_video_info):
        """Create list of VideoInfo for multiple source videos"""
        video_info_2 = replace(sample_video_info, 
                             file_path=Path("/test/input2.mp4"),
                             duration=120.0)
        return [sample_video_info, video_info_2]
    
    def test_detect_output_format(self, mock_config, mock_subprocess):
        """Test output format detection from file extensions"""
        renderer = VideoRenderer()
        
        test_cases = [
            (Path("/test/output.mp4"), "mp4"),
            (Path("/test/output.mov"), "mov"),
            (Path("/test/output.avi"), "avi"),
            (Path("/test/output.mkv"), "mkv"),
            (Path("/test/output.webm"), "webm"),
            (Path("/test/output.MP4"), "mp4"),  # Case insensitive
            (Path("/test/output.unknown"), "mp4"),  # Default fallback
            (Path("/test/output"), "mp4"),  # No extension
            (None, "mp4")  # None input
        ]
        
        for input_path, expected_format in test_cases:
            result = renderer._detect_output_format(input_path)
            assert result == expected_format
    
    def test_extract_timeline_clips_success(self, mock_config, mock_subprocess, multi_video_info_list):
        """Test successful clip extraction"""
        renderer = VideoRenderer()
        
        # Create timeline with segments referencing different videos
        segments = [
            TimelineSegment(0.0, 10.0, source_video_index=0, source_start_time=5.0, source_end_time=15.0),
            TimelineSegment(10.0, 20.0, source_video_index=1, source_start_time=30.0, source_end_time=40.0)
        ]
        
        timeline = EditingTimeline(
            video_info=multi_video_info_list[0],
            audio_analysis=None,
            scene_detection=None,
            cut_points=[],
            segments=segments,
            editing_style=EditingStyle.ADAPTIVE,
            generation_time=0.0,
            total_duration=20.0,
            success=True
        )
        
        progress_updates = []
        def progress_callback(message, progress):
            progress_updates.append((message, progress))
        
        with patch('src.video.renderer.ffmpeg') as mock_ffmpeg, \
             patch('src.video.renderer.tempfile.mkdtemp') as mock_mkdtemp:
            
            # Mock temporary directory
            temp_dir = Path("/tmp/test_clips")
            mock_mkdtemp.return_value = str(temp_dir)
            
            # Mock ffmpeg operations
            mock_input = Mock()
            mock_output = Mock()
            mock_ffmpeg.input.return_value = mock_input
            mock_ffmpeg.output.return_value = mock_output
            mock_ffmpeg.run.return_value = None
            
            # Mock Path operations
            with patch('pathlib.Path.mkdir'), \
                 patch('pathlib.Path.exists', return_value=True):
                
                clip_files = renderer._extract_timeline_clips(timeline, multi_video_info_list, progress_callback)
                
                # Verify results
                assert len(clip_files) == 2
                assert all(isinstance(f, Path) for f in clip_files)
                assert all("clip_" in f.name for f in clip_files)
                
                # Verify progress callbacks
                assert len(progress_updates) == 2
                assert "Extracting clip 1/2" in progress_updates[0][0]
                assert "Extracting clip 2/2" in progress_updates[1][0]
                
                # Verify ffmpeg was called correctly
                assert mock_ffmpeg.input.call_count == 2
                assert mock_ffmpeg.output.call_count == 2
                assert mock_ffmpeg.run.call_count == 2
    
    def test_extract_timeline_clips_invalid_video_index(self, mock_config, mock_subprocess, multi_video_info_list):
        """Test clip extraction with invalid source_video_index"""
        renderer = VideoRenderer()
        
        # Create segment with invalid video index
        segments = [
            TimelineSegment(0.0, 10.0, source_video_index=5, source_start_time=5.0, source_end_time=15.0)  # Invalid index
        ]
        
        timeline = EditingTimeline(
            video_info=multi_video_info_list[0],
            audio_analysis=None,
            scene_detection=None,
            cut_points=[],
            segments=segments,
            editing_style=EditingStyle.ADAPTIVE,
            generation_time=0.0,
            total_duration=10.0,
            success=True
        )
        
        with pytest.raises(IndexError):
            renderer._extract_timeline_clips(timeline, multi_video_info_list)
    
    def test_extract_timeline_clips_ffmpeg_failure(self, mock_config, mock_subprocess, multi_video_info_list):
        """Test clip extraction with FFmpeg failure"""
        renderer = VideoRenderer()
        
        segments = [
            TimelineSegment(0.0, 10.0, source_video_index=0, source_start_time=5.0, source_end_time=15.0)
        ]
        
        timeline = EditingTimeline(
            video_info=multi_video_info_list[0],
            audio_analysis=None,
            scene_detection=None,
            cut_points=[],
            segments=segments,
            editing_style=EditingStyle.ADAPTIVE,
            generation_time=0.0,
            total_duration=10.0,
            success=True
        )
        
        with patch('src.video.renderer.ffmpeg') as mock_ffmpeg, \
             patch('src.video.renderer.tempfile.mkdtemp'):
            
            # Mock FFmpeg failure
            mock_error = Exception("FFmpeg failed")
            mock_error.stderr = "stderr output"
            mock_ffmpeg.run.side_effect = mock_error
            mock_ffmpeg.Error = Exception
            
            with pytest.raises(RuntimeError, match="Failed to extract clip"):
                renderer._extract_timeline_clips(timeline, multi_video_info_list)
    
    def test_create_concat_file(self, mock_config, mock_subprocess):
        """Test concat file creation"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # Create dummy clip files
            clip_files = []
            for i in range(3):
                clip_file = temp_dir_path / f"clip_{i:04d}.mp4"
                clip_file.touch()
                clip_files.append(clip_file)
            
            # Create dummy timeline (only needed for logging)
            timeline = Mock()
            
            concat_file = renderer._create_concat_file(clip_files, timeline)
            
            # Verify concat file was created
            assert concat_file.exists()
            assert concat_file.name == "concat_list.txt"
            assert concat_file.parent == temp_dir_path
            
            # Verify content
            content = concat_file.read_text()
            lines = content.strip().split('\n')
            assert len(lines) == 3
            
            for i, line in enumerate(lines):
                expected_path = clip_files[i].absolute()
                assert line == f"file '{expected_path}'"
    
    def test_create_concat_file_empty_clips(self, mock_config, mock_subprocess):
        """Test concat file creation with empty clip list"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            timeline = Mock()
            
            # Should handle empty list gracefully
            with patch('pathlib.Path.exists', return_value=True):
                concat_file = renderer._create_concat_file([], timeline)
                
                assert concat_file.name == "concat_list.txt"
                content = concat_file.read_text()
                assert content.strip() == ""
    
    def test_render_final_video_with_music(self, mock_config, mock_subprocess):
        """Test final video rendering with music"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            concat_file = temp_dir_path / "concat.txt"
            concat_file.touch()
            music_path = temp_dir_path / "music.mp3"
            music_path.touch()
            output_path = temp_dir_path / "output.mp4"
            
            render_options = Mock()
            render_options.ffmpeg_params = {}
            
            progress_updates = []
            def progress_callback(message, progress):
                progress_updates.append((message, progress))
            
            with patch('src.video.renderer.ffmpeg.input') as mock_input, \
                 patch('src.video.renderer.ffmpeg.output') as mock_output, \
                 patch('src.video.renderer.subprocess.run') as mock_subprocess_run:
                
                # Create mock objects with subscriptable behavior
                mock_video_input = Mock()
                mock_video_input.__getitem__ = Mock(return_value=Mock())  # For video_input['v']
                mock_music_input = Mock()
                mock_music_input.__getitem__ = Mock(return_value=Mock())  # For music_input['a']
                
                mock_input.side_effect = [mock_video_input, mock_music_input]
                
                # Mock the output stream with a compile method
                mock_output_stream = Mock()
                mock_output_stream.compile.return_value = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_file), str(output_path)]
                mock_output.return_value = mock_output_stream
                
                # Mock successful subprocess execution
                mock_subprocess_result = Mock()
                mock_subprocess_result.returncode = 0  # Success
                mock_subprocess_result.stderr = ""
                mock_subprocess_result.stdout = ""
                mock_subprocess_run.return_value = mock_subprocess_result
                
                renderer._render_final_video_with_music(
                    concat_file=concat_file,
                    music_path=music_path,
                    output_path=output_path,
                    render_options=render_options,
                    timeline_duration=60.0,
                    progress_callback=progress_callback
                )
                
                # Verify ffmpeg was called correctly for video + music
                assert mock_input.call_count == 2  # Video input + music input
                mock_output.assert_called_once()
                mock_subprocess_run.assert_called_once()
                
                # Check that video and music inputs were used in output
                output_call_args = mock_output.call_args[0]
                # Verify video stream is used (mock_video_input with video stream selector)
                assert len(output_call_args) >= 2  # Should have video and audio streams
    
    def test_render_final_video_without_music(self, mock_config, mock_subprocess):
        """Test final video rendering without music"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            concat_file = temp_dir_path / "concat.txt"
            concat_file.touch()
            output_path = temp_dir_path / "output.mp4"
            
            render_options = Mock()
            render_options.ffmpeg_params = {}
            
            with patch('src.video.renderer.ffmpeg.input') as mock_input, \
                 patch('src.video.renderer.ffmpeg.output') as mock_output, \
                 patch('src.video.renderer.subprocess.run') as mock_subprocess_run:
                
                mock_video_input = Mock()
                mock_input.return_value = mock_video_input
                
                # Mock the output stream with a compile method
                mock_output_stream = Mock()
                mock_output_stream.compile.return_value = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_file), str(output_path)]
                mock_output.return_value = mock_output_stream
                
                # Mock successful subprocess execution
                mock_subprocess_result = Mock()
                mock_subprocess_result.returncode = 0  # Success
                mock_subprocess_result.stderr = ""
                mock_subprocess_result.stdout = ""
                mock_subprocess_run.return_value = mock_subprocess_result
                
                renderer._render_final_video_with_music(
                    concat_file=concat_file,
                    music_path=None,  # No music
                    output_path=output_path,
                    render_options=render_options,
                    timeline_duration=60.0
                )
                
                # Verify ffmpeg was called correctly for video only
                assert mock_input.call_count == 1  # Only video input
                mock_output.assert_called_once()
                mock_subprocess_run.assert_called_once()
                
                # Check that only video input was used
                output_call_args = mock_output.call_args[0]
                assert mock_video_input in output_call_args
    
    def test_render_final_video_ffmpeg_failure(self, mock_config, mock_subprocess):
        """Test final video rendering with FFmpeg failure"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            concat_file = temp_dir_path / "concat.txt"
            concat_file.touch()
            output_path = temp_dir_path / "output.mp4"
            
            render_options = Mock()
            render_options.ffmpeg_params = {}
            
            with patch('src.video.renderer.ffmpeg') as mock_ffmpeg:
                mock_ffmpeg.input.return_value = Mock()
                mock_ffmpeg.output.return_value = Mock()
                # Create a proper ffmpeg.Error with required arguments
                mock_error = Exception("Render failed")
                mock_error.stderr = b"stderr output"
                mock_ffmpeg.run.side_effect = mock_error
                mock_ffmpeg.Error = Exception  # Mock the Error class
                
                with pytest.raises(RuntimeError, match="Video rendering failed"):
                    renderer._render_final_video_with_music(
                        concat_file=concat_file,
                        music_path=None,
                        output_path=output_path,
                        render_options=render_options,
                        timeline_duration=60.0
                    )
    
    def test_cleanup_temp_files_single_path(self, mock_config, mock_subprocess):
        """Test cleanup of single temporary directory"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "test_cleanup"
            temp_path.mkdir()
            
            # Create some test files
            (temp_path / "file1.txt").touch()
            (temp_path / "file2.txt").touch()
            (temp_path / "subdir").mkdir()
            (temp_path / "subdir" / "file3.txt").touch()
            
            assert temp_path.exists()
            assert len(list(temp_path.rglob("*"))) > 0
            
            renderer._cleanup_temp_files(temp_path)
            
            assert not temp_path.exists()
    
    def test_cleanup_temp_files_list_of_paths(self, mock_config, mock_subprocess):
        """Test cleanup of list of temporary files and directories"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # Create test files and directories
            test_files = [
                temp_dir_path / "file1.txt",
                temp_dir_path / "file2.txt",
                temp_dir_path / "subdir"
            ]
            
            test_files[0].touch()
            test_files[1].touch()
            test_files[2].mkdir()
            (test_files[2] / "nested_file.txt").touch()
            
            # Verify all exist
            for test_file in test_files:
                assert test_file.exists()
            
            renderer._cleanup_temp_files(test_files)
            
            # Verify all cleaned up
            for test_file in test_files:
                assert not test_file.exists()
    
    def test_cleanup_temp_files_nonexistent_paths(self, mock_config, mock_subprocess):
        """Test cleanup with non-existent paths (should not raise errors)"""
        renderer = VideoRenderer()
        
        # Test with non-existent single path
        non_existent_path = Path("/tmp/nonexistent_12345")
        renderer._cleanup_temp_files(non_existent_path)  # Should not raise
        
        # Test with list containing non-existent paths
        non_existent_files = [
            Path("/tmp/nonexistent1.txt"),
            Path("/tmp/nonexistent2.txt")
        ]
        renderer._cleanup_temp_files(non_existent_files)  # Should not raise
    
    def test_cleanup_temp_files_permission_error(self, mock_config, mock_subprocess):
        """Test cleanup with permission errors (should log warning, not raise)"""
        renderer = VideoRenderer()
        
        test_path = Path("/tmp/test_path")
        # Use a more specific patch for the path exists method
        with patch('pathlib.Path.exists', return_value=True), \
             patch('shutil.rmtree') as mock_rmtree:
            mock_rmtree.side_effect = PermissionError("Permission denied")
            
            # Should not raise exception, just log warning
            renderer._cleanup_temp_files(test_path)
            
            mock_rmtree.assert_called_once()


class TestRenderingResultDataclass:
    """Test cases for RenderingResult dataclass"""
    
    def test_rendering_result_success_initialization(self):
        """Test RenderingResult initialization for successful render"""
        output_path = Path("/test/output.mp4")
        
        result = RenderingResult(
            success=True,
            output_path=output_path,
            processing_time=10.5,
            output_file_size=50000000,
            timeline_duration=60.0,
            segments_rendered=4,
            speed_factor=5.7,
            quality_preset="high",
            hardware_acceleration_used=True
        )
        
        assert result.success is True
        assert result.output_path == output_path
        assert result.processing_time == 10.5
        assert result.output_file_size == 50000000
        assert result.timeline_duration == 60.0
        assert result.segments_rendered == 4
        assert result.speed_factor == 5.7
        assert result.quality_preset == "high"
        assert result.hardware_acceleration_used is True
        assert result.error_message is None
    
    def test_rendering_result_failure_initialization(self):
        """Test RenderingResult initialization for failed render"""
        error_message = "FFmpeg encoding failed"
        
        result = RenderingResult(
            success=False,
            error_message=error_message,
            processing_time=5.2
        )
        
        assert result.success is False
        assert result.output_path is None
        assert result.processing_time == 5.2
        assert result.output_file_size == 0
        assert result.timeline_duration == 0.0
        assert result.segments_rendered == 0
        assert result.speed_factor == 0.0
        assert result.quality_preset == "lossless"
        assert result.hardware_acceleration_used is False
        assert result.error_message == error_message
    
    def test_rendering_result_default_values(self):
        """Test RenderingResult default field values"""
        result = RenderingResult(success=True)
        
        assert result.success is True
        assert result.output_path is None
        assert result.processing_time == 0.0
        assert result.output_file_size == 0
        assert result.timeline_duration == 0.0
        assert result.segments_rendered == 0
        assert result.speed_factor == 0.0
        assert result.quality_preset == "lossless"
        assert result.hardware_acceleration_used is False
        assert result.error_message is None


class TestEdgeCases:
    """Test cases for edge cases identified in code review"""
    
    @pytest.fixture
    def multi_video_info_list(self, sample_video_info):
        """Create list of VideoInfo for multiple source videos"""
        video_info_2 = replace(sample_video_info, 
                             file_path=Path("/test/input2.mp4"),
                             duration=120.0)
        return [sample_video_info, video_info_2]
    
    @pytest.fixture
    def multi_video_timeline(self, sample_video_info):
        """Create timeline with segments from multiple videos"""
        # Create segments with different source videos
        segments = [
            TimelineSegment(0.0, 10.0, CutType.FORCED_CUT, CutType.SCENE_CUT, 
                          source_video_index=0, source_start_time=5.0, source_end_time=15.0),
            TimelineSegment(10.0, 25.0, CutType.SCENE_CUT, CutType.SCENE_CUT,
                          source_video_index=1, source_start_time=20.0, source_end_time=35.0),
            TimelineSegment(25.0, 35.0, CutType.SCENE_CUT, CutType.FORCED_CUT,
                          source_video_index=0, source_start_time=40.0, source_end_time=50.0)
        ]
        
        cut_points = [
            CutPoint(0.0, 1.0, CutType.FORCED_CUT, 0.0, 1.0, 1.0, 0.0),
            CutPoint(10.0, 0.8, CutType.SCENE_CUT, 0.9, 1.0, 0.8, 0.0),
            CutPoint(25.0, 0.9, CutType.SCENE_CUT, 0.8, 1.0, 0.9, 0.0),
            CutPoint(35.0, 1.0, CutType.FORCED_CUT, 0.0, 1.0, 1.0, 0.0)
        ]
        
        return EditingTimeline(
            video_info=sample_video_info,
            audio_analysis=None,
            scene_detection=None,
            cut_points=cut_points,
            segments=segments,
            editing_style=EditingStyle.ADAPTIVE,
            generation_time=1.5,
            total_duration=35.0,
            success=True
        )
    
    def test_invalid_source_video_index_in_segments(self, mock_config, mock_subprocess):
        """Test handling of invalid source_video_index in timeline segments"""
        renderer = VideoRenderer()
        
        # Create timeline with invalid source_video_index
        segments = [
            TimelineSegment(0.0, 10.0, source_video_index=999, source_start_time=0.0, source_end_time=10.0)
        ]
        
        timeline = EditingTimeline(
            video_info=Mock(),
            audio_analysis=None,
            scene_detection=None,
            cut_points=[],
            segments=segments,
            editing_style=EditingStyle.ADAPTIVE,
            generation_time=0.0,
            total_duration=10.0,
            success=True
        )
        
        video_info_list = [Mock()]  # Only one video available
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            
            result = renderer.render_multi_video_timeline(
                timeline=timeline,
                video_info_list=video_info_list,
                output_path=output_path
            )
            
            assert result.success is False
            assert "index" in result.error_message.lower() or "list" in result.error_message.lower()
    
    def test_empty_video_info_list(self, mock_config, mock_subprocess):
        """Test handling of empty video_info_list"""
        renderer = VideoRenderer()
        
        timeline = Mock()
        timeline.segments = [Mock()]
        timeline.total_duration = 10.0
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            
            result = renderer.render_multi_video_timeline(
                timeline=timeline,
                video_info_list=[],  # Empty list
                output_path=output_path
            )
            
            assert result.success is False
            assert result.error_message is not None
    
    def test_none_video_info_list(self, mock_config, mock_subprocess):
        """Test handling of None video_info_list"""
        renderer = VideoRenderer()
        
        timeline = Mock()
        timeline.segments = [Mock()]
        timeline.total_duration = 10.0
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            
            # This will fail early because of len(None), causing a TypeError
            # The current implementation doesn't handle this gracefully before the try block
            with pytest.raises(TypeError, match="object of type 'NoneType' has no len"):
                renderer.render_multi_video_timeline(
                    timeline=timeline,
                    video_info_list=None,  # None instead of list
                    output_path=output_path
                )
    
    def test_timeline_duration_inconsistency(self, mock_config, mock_subprocess, multi_video_info_list):
        """Test handling of inconsistent timeline duration"""
        renderer = VideoRenderer()
        
        # Create timeline where segments don't add up to total_duration
        segments = [
            TimelineSegment(0.0, 10.0, source_video_index=0),
            TimelineSegment(10.0, 20.0, source_video_index=0)
        ]
        
        timeline = EditingTimeline(
            video_info=multi_video_info_list[0],
            audio_analysis=None,
            scene_detection=None,
            cut_points=[],
            segments=segments,
            editing_style=EditingStyle.ADAPTIVE,
            generation_time=0.0,
            total_duration=100.0,  # Inconsistent with segment durations (should be 20.0)
            success=True
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            
            # Mock successful extraction but inconsistent durations
            with patch.object(renderer, '_extract_timeline_clips') as mock_extract, \
                 patch.object(renderer, '_create_concat_file'), \
                 patch.object(renderer, '_render_final_video_with_music'), \
                 patch.object(renderer, '_cleanup_temp_files'):
                
                mock_extract.return_value = [Path("/tmp/clip1.mp4"), Path("/tmp/clip2.mp4")]
                output_path.write_bytes(b"fake content")
                
                result = renderer.render_multi_video_timeline(
                    timeline=timeline,
                    video_info_list=multi_video_info_list,
                    output_path=output_path
                )
                
                # Should still succeed but with timeline's reported duration
                assert result.success is True
                assert result.timeline_duration == 100.0  # Uses timeline's duration
    
    def test_file_permission_errors(self, mock_config, mock_subprocess, multi_video_timeline, multi_video_info_list):
        """Test handling of file permission errors"""
        renderer = VideoRenderer()
        
        # Try to write to a read-only directory (simulated)
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "readonly" / "output.mp4"
            
            with patch.object(renderer, '_extract_timeline_clips') as mock_extract:
                mock_extract.side_effect = PermissionError("Permission denied")
                
                result = renderer.render_multi_video_timeline(
                    timeline=multi_video_timeline,
                    video_info_list=multi_video_info_list,
                    output_path=output_path
                )
                
                assert result.success is False
                assert "permission" in result.error_message.lower() or "denied" in result.error_message.lower()
    
    def test_missing_source_video_files(self, mock_config, mock_subprocess):
        """Test handling of missing source video files"""
        renderer = VideoRenderer()
        
        # Create VideoInfo pointing to non-existent files
        video_info = Mock()
        video_info.file_path = Path("/nonexistent/video.mp4")
        
        segments = [
            TimelineSegment(0.0, 10.0, source_video_index=0, source_start_time=0.0, source_end_time=10.0)
        ]
        
        timeline = EditingTimeline(
            video_info=video_info,
            audio_analysis=None,
            scene_detection=None,
            cut_points=[],
            segments=segments,
            editing_style=EditingStyle.ADAPTIVE,
            generation_time=0.0,
            total_duration=10.0,
            success=True
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            
            result = renderer.render_multi_video_timeline(
                timeline=timeline,
                video_info_list=[video_info],
                output_path=output_path
            )
            
            assert result.success is False
            assert result.error_message is not None


@pytest.mark.integration
class TestVideoRendererIntegration:
    """Integration tests for VideoRenderer (require actual FFmpeg)"""
    
    @pytest.mark.skip("Requires actual video file and FFmpeg")
    def test_full_render_pipeline(self, sample_timeline):
        """Test complete render pipeline with real FFmpeg"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.mp4"
            options = RenderOptions(quality_preset=QualityPreset.DRAFT)
            
            progress_updates = []
            
            def progress_callback(progress: RenderProgress):
                progress_updates.append(progress)
            
            stats = renderer.render_timeline(
                sample_timeline, output_path, options, progress_callback
            )
            
            # Verify output file was created
            assert output_path.exists()
            assert output_path.stat().st_size > 0
            
            # Verify stats
            assert stats.total_duration == sample_timeline.total_duration
            assert stats.processing_time > 0
            assert stats.segments_processed == len(sample_timeline.segments)
            
            # Verify progress updates were called
            assert len(progress_updates) > 0
            assert progress_updates[-1].progress_percentage == 100.0
    
    @pytest.mark.skip("Requires actual video file and FFmpeg")
    def test_segment_range_render(self, sample_timeline):
        """Test rendering specific segment range"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "segment_range.mp4"
            options = RenderOptions(quality_preset=QualityPreset.DRAFT)
            
            stats = renderer.render_segment_range(
                sample_timeline, 1, 3, output_path, options
            )
            
            # Should have processed 2 segments (index 1 and 2)
            assert stats.segments_processed == 2
            assert output_path.exists()
    
    @pytest.mark.skip("Requires actual video file and FFmpeg")
    def test_individual_clips_export(self, sample_timeline):
        """Test exporting individual clips"""
        renderer = VideoRenderer()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "clips"
            options = RenderOptions(quality_preset=QualityPreset.DRAFT)
            
            stats_list = renderer.export_individual_clips(
                sample_timeline, output_dir, options
            )
            
            # Should have one stats object per segment
            assert len(stats_list) == len(sample_timeline.segments)
            
            # Check that clip files were created  
            for i in range(len(sample_timeline.segments)):
                clip_file = output_dir / f"clip_{i:04d}.mp4"
                assert clip_file.exists()
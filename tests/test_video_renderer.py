"""Tests for video rendering module"""
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from dataclasses import replace

from src.video.renderer import (
    VideoRenderer, RenderOptions, OutputFormat, QualityPreset, RenderingMode,
    RenderProgress, RenderStats, create_render_options, estimate_render_time
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
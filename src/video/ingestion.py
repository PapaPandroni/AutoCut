"""Video ingestion module for AutoCut with multi-format support and hardware acceleration"""
import ffmpeg
import subprocess
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from enum import Enum

from ..utils.logging import get_logger
from ..utils.config import config

logger = get_logger(__name__)


class VideoCodec(Enum):
    """Supported video codecs"""
    H264 = "h264"
    H265 = "hevc"
    MPEG4 = "mpeg4"
    VP8 = "vp8"
    VP9 = "vp9"
    AV1 = "av1"
    PRORES = "prores"
    DNX = "dnxhd"
    UNKNOWN = "unknown"


class ContainerFormat(Enum):
    """Supported container formats"""
    MP4 = "mp4"
    MOV = "mov"
    AVI = "avi"
    MKV = "mkv"
    WEBM = "webm"
    FLV = "flv"
    M4V = "m4v"
    UNKNOWN = "unknown"


@dataclass
class VideoStream:
    """Video stream information"""
    index: int
    codec: VideoCodec
    width: int
    height: int
    fps: float
    bitrate: Optional[int] = None
    duration: Optional[float] = None
    pixel_format: Optional[str] = None
    color_space: Optional[str] = None
    profile: Optional[str] = None
    level: Optional[str] = None


@dataclass
class AudioStream:
    """Audio stream information"""
    index: int
    codec: str
    sample_rate: int
    channels: int
    bitrate: Optional[int] = None
    duration: Optional[float] = None


@dataclass
class VideoInfo:
    """Complete video file information"""
    file_path: Path
    container_format: ContainerFormat
    duration: float
    file_size: int
    video_streams: List[VideoStream]
    audio_streams: List[AudioStream]
    metadata: Dict[str, Any]
    is_valid: bool = True
    validation_errors: List[str] = None
    hardware_decodable: bool = False
    
    def __post_init__(self):
        if self.validation_errors is None:
            self.validation_errors = []
    
    @property
    def primary_video_stream(self) -> Optional[VideoStream]:
        """Get the primary video stream (usually the first one)"""
        return self.video_streams[0] if self.video_streams else None
    
    @property
    def primary_audio_stream(self) -> Optional[AudioStream]:
        """Get the primary audio stream (usually the first one)"""
        return self.audio_streams[0] if self.audio_streams else None
    
    @property
    def resolution(self) -> Tuple[int, int]:
        """Get video resolution as (width, height)"""
        if self.primary_video_stream:
            return (self.primary_video_stream.width, self.primary_video_stream.height)
        return (0, 0)
    
    @property
    def aspect_ratio(self) -> float:
        """Get video aspect ratio"""
        width, height = self.resolution
        return width / height if height > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'file_path': str(self.file_path),
            'container_format': self.container_format.value,
            'duration': self.duration,
            'file_size': self.file_size,
            'resolution': self.resolution,
            'aspect_ratio': self.aspect_ratio,
            'fps': self.primary_video_stream.fps if self.primary_video_stream else 0,
            'video_codec': self.primary_video_stream.codec.value if self.primary_video_stream else None,
            'audio_codec': self.primary_audio_stream.codec if self.primary_audio_stream else None,
            'is_valid': self.is_valid,
            'validation_errors': self.validation_errors,
            'hardware_decodable': self.hardware_decodable,
            'metadata': self.metadata
        }


class VideoIngestion:
    """Video ingestion engine with multi-format support and hardware acceleration"""
    
    # M1/M2 hardware-accelerated decoders
    HARDWARE_DECODERS = {
        VideoCodec.H264: "h264_videotoolbox",
        VideoCodec.H265: "hevc_videotoolbox", 
        VideoCodec.PRORES: "prores_videotoolbox",
        VideoCodec.MPEG4: "mpeg4_videotoolbox"
    }
    
    # Supported container formats mapping
    CONTAINER_EXTENSIONS = {
        '.mp4': ContainerFormat.MP4,
        '.mov': ContainerFormat.MOV,
        '.avi': ContainerFormat.AVI,
        '.mkv': ContainerFormat.MKV,
        '.webm': ContainerFormat.WEBM,
        '.flv': ContainerFormat.FLV,
        '.m4v': ContainerFormat.M4V
    }
    
    def __init__(self):
        """Initialize video ingestion engine"""
        self.max_probe_size = config.get('video.max_probe_size_mb', 50) * 1024 * 1024
        self.probe_timeout = config.get('video.probe_timeout_sec', 30)
        self.enable_hardware_acceleration = config.get('video.enable_hardware_acceleration', True)
        self.max_file_size_gb = config.get('video.max_file_size_gb', 10)
        
        # Codec mapping for detection
        self.codec_mapping = {
            'h264': VideoCodec.H264,
            'avc1': VideoCodec.H264,
            'h265': VideoCodec.H265,
            'hevc': VideoCodec.H265,
            'hev1': VideoCodec.H265,
            'mpeg4': VideoCodec.MPEG4,
            'mp4v': VideoCodec.MPEG4,
            'vp8': VideoCodec.VP8,
            'vp9': VideoCodec.VP9,
            'av01': VideoCodec.AV1,
            'prores': VideoCodec.PRORES,
            'apch': VideoCodec.PRORES,
            'apcn': VideoCodec.PRORES,
            'apcs': VideoCodec.PRORES,
            'apco': VideoCodec.PRORES,
            'ap4h': VideoCodec.PRORES,
            'dnxhd': VideoCodec.DNX
        }
        
        # Verify FFmpeg installation
        self._verify_ffmpeg()
        
        logger.info("VideoIngestion initialized", 
                   hardware_acceleration=self.enable_hardware_acceleration,
                   max_file_size_gb=self.max_file_size_gb)
    
    def _verify_ffmpeg(self):
        """Verify FFmpeg installation and capabilities"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise RuntimeError("FFmpeg not properly installed")
            
            # Check for hardware acceleration support on macOS
            if self.enable_hardware_acceleration:
                probe_result = subprocess.run(['ffmpeg', '-hwaccels'], 
                                            capture_output=True, text=True, timeout=10)
                has_videotoolbox = 'videotoolbox' in probe_result.stdout
                
                if not has_videotoolbox:
                    logger.warning("VideoToolbox hardware acceleration not available")
                    self.enable_hardware_acceleration = False
                else:
                    logger.info("VideoToolbox hardware acceleration available")
                    
        except (subprocess.TimeoutExpired, FileNotFoundError, RuntimeError) as e:
            logger.error("FFmpeg verification failed", error=str(e))
            raise RuntimeError(f"FFmpeg not available or not working: {e}")
    
    def load_video(self, file_path: Union[str, Path]) -> VideoInfo:
        """
        Load and analyze video file
        
        Args:
            file_path: Path to video file
            
        Returns:
            VideoInfo object with complete video information
            
        Raises:
            FileNotFoundError: If video file doesn't exist
            ValueError: If file is too large or unsupported
            RuntimeError: If video analysis fails
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Video file not found: {file_path}")
        
        logger.info("Loading video file", file_path=str(file_path))
        start_time = time.time()
        
        try:
            # Basic file validation
            self._validate_file_basic(file_path)
            
            # Probe video file
            video_info = self._probe_video(file_path)
            
            # Validate video content
            self._validate_video_content(video_info)
            
            # Check hardware acceleration compatibility
            self._check_hardware_compatibility(video_info)
            
            load_time = time.time() - start_time
            logger.info("Video loaded successfully",
                       file_path=str(file_path),
                       duration=f"{video_info.duration:.2f}s",
                       resolution=f"{video_info.resolution[0]}x{video_info.resolution[1]}",
                       codec=video_info.primary_video_stream.codec.value if video_info.primary_video_stream else "unknown",
                       load_time=f"{load_time:.2f}s")
            
            return video_info
            
        except Exception as e:
            logger.error("Video loading failed", file_path=str(file_path), error=str(e))
            raise
    
    def _validate_file_basic(self, file_path: Path):
        """Basic file validation"""
        # Check file size
        file_size = file_path.stat().st_size
        max_size = self.max_file_size_gb * 1024 * 1024 * 1024
        
        if file_size > max_size:
            raise ValueError(f"File too large: {file_size / (1024**3):.1f}GB > {self.max_file_size_gb}GB")
        
        # Check file extension
        extension = file_path.suffix.lower()
        if extension not in self.CONTAINER_EXTENSIONS:
            logger.warning("Unknown file extension", extension=extension)
        
        logger.debug("Basic file validation passed", 
                    file_size_mb=f"{file_size / (1024**2):.1f}",
                    extension=extension)
    
    def _probe_video(self, file_path: Path) -> VideoInfo:
        """Probe video file using FFmpeg"""
        try:
            # Use ffprobe to get detailed information
            probe_cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                '-probesize', str(self.max_probe_size),
                str(file_path)
            ]
            
            result = subprocess.run(probe_cmd, capture_output=True, text=True, 
                                  timeout=self.probe_timeout)
            
            if result.returncode != 0:
                raise RuntimeError(f"FFprobe failed: {result.stderr}")
            
            probe_data = json.loads(result.stdout)
            
            # Parse probe data
            return self._parse_probe_data(file_path, probe_data)
            
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Video probing timed out after {self.probe_timeout}s")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse FFprobe output: {e}")
        except Exception as e:
            raise RuntimeError(f"Video probing failed: {e}")
    
    def _parse_probe_data(self, file_path: Path, probe_data: Dict) -> VideoInfo:
        """Parse FFprobe output into VideoInfo"""
        format_info = probe_data.get('format', {})
        streams = probe_data.get('streams', [])
        
        # Extract basic information
        duration = float(format_info.get('duration', 0))
        file_size = int(format_info.get('size', 0))
        
        # Determine container format
        format_name = format_info.get('format_name', '').lower()
        container_format = self._detect_container_format(file_path, format_name)
        
        # Parse streams
        video_streams = []
        audio_streams = []
        
        for stream in streams:
            if stream.get('codec_type') == 'video':
                video_stream = self._parse_video_stream(stream)
                if video_stream:
                    video_streams.append(video_stream)
            elif stream.get('codec_type') == 'audio':
                audio_stream = self._parse_audio_stream(stream)
                if audio_stream:
                    audio_streams.append(audio_stream)
        
        # Extract metadata
        metadata = format_info.get('tags', {})
        
        return VideoInfo(
            file_path=file_path,
            container_format=container_format,
            duration=duration,
            file_size=file_size,
            video_streams=video_streams,
            audio_streams=audio_streams,
            metadata=metadata
        )
    
    def _detect_container_format(self, file_path: Path, format_name: str) -> ContainerFormat:
        """Detect container format from file extension and format name"""
        # Try file extension first
        extension = file_path.suffix.lower()
        if extension in self.CONTAINER_EXTENSIONS:
            return self.CONTAINER_EXTENSIONS[extension]
        
        # Try format name
        format_mapping = {
            'mov,mp4,m4a,3gp,3g2,mj2': ContainerFormat.MP4,
            'mov': ContainerFormat.MOV,
            'avi': ContainerFormat.AVI,
            'matroska,webm': ContainerFormat.MKV,
            'webm': ContainerFormat.WEBM,
            'flv': ContainerFormat.FLV
        }
        
        for fmt_pattern, container in format_mapping.items():
            if format_name in fmt_pattern:
                return container
        
        logger.warning("Unknown container format", format_name=format_name, extension=extension)
        return ContainerFormat.UNKNOWN
    
    def _parse_video_stream(self, stream: Dict) -> Optional[VideoStream]:
        """Parse video stream information"""
        try:
            codec_name = stream.get('codec_name', '').lower()
            codec_tag = stream.get('codec_tag_string', '').lower()
            
            # Detect codec
            codec = self.codec_mapping.get(codec_name) or self.codec_mapping.get(codec_tag)
            if not codec:
                logger.warning("Unknown video codec", codec_name=codec_name, codec_tag=codec_tag)
                codec = VideoCodec.UNKNOWN
            
            # Parse basic properties
            width = int(stream.get('width', 0))
            height = int(stream.get('height', 0))
            
            # Parse frame rate
            fps_str = stream.get('r_frame_rate', '0/1')
            try:
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den) if float(den) != 0 else 0
                else:
                    fps = float(fps_str)
            except (ValueError, ZeroDivisionError):
                fps = 0.0
            
            # Parse optional properties
            bitrate = None
            bitrate_str = stream.get('bit_rate')
            if bitrate_str:
                try:
                    bitrate = int(bitrate_str)
                except ValueError:
                    pass
            
            duration = None
            duration_str = stream.get('duration')
            if duration_str:
                try:
                    duration = float(duration_str)
                except ValueError:
                    pass
            
            return VideoStream(
                index=int(stream.get('index', 0)),
                codec=codec,
                width=width,
                height=height,
                fps=fps,
                bitrate=bitrate,
                duration=duration,
                pixel_format=stream.get('pix_fmt'),
                color_space=stream.get('color_space'),
                profile=stream.get('profile'),
                level=stream.get('level')
            )
            
        except Exception as e:
            logger.error("Failed to parse video stream", error=str(e), stream_data=stream)
            return None
    
    def _parse_audio_stream(self, stream: Dict) -> Optional[AudioStream]:
        """Parse audio stream information"""
        try:
            codec = stream.get('codec_name', 'unknown')
            sample_rate = int(stream.get('sample_rate', 0))
            channels = int(stream.get('channels', 0))
            
            # Parse optional properties
            bitrate = None
            bitrate_str = stream.get('bit_rate')
            if bitrate_str:
                try:
                    bitrate = int(bitrate_str)
                except ValueError:
                    pass
            
            duration = None
            duration_str = stream.get('duration')
            if duration_str:
                try:
                    duration = float(duration_str)
                except ValueError:
                    pass
            
            return AudioStream(
                index=int(stream.get('index', 0)),
                codec=codec,
                sample_rate=sample_rate,
                channels=channels,
                bitrate=bitrate,
                duration=duration
            )
            
        except Exception as e:
            logger.error("Failed to parse audio stream", error=str(e), stream_data=stream)
            return None
    
    def _validate_video_content(self, video_info: VideoInfo):
        """Validate video content and detect issues"""
        errors = []
        
        # Check for video streams
        if not video_info.video_streams:
            errors.append("No video streams found")
        
        # Validate primary video stream
        if video_info.primary_video_stream:
            stream = video_info.primary_video_stream
            
            if stream.width <= 0 or stream.height <= 0:
                errors.append(f"Invalid resolution: {stream.width}x{stream.height}")
            
            if stream.fps <= 0:
                errors.append(f"Invalid frame rate: {stream.fps}")
            
            # Check for reasonable resolution limits
            if stream.width > 8192 or stream.height > 8192:
                errors.append(f"Extremely high resolution: {stream.width}x{stream.height}")
        
        # Check duration
        if video_info.duration <= 0:
            errors.append(f"Invalid duration: {video_info.duration}")
        
        # Update video info
        video_info.validation_errors = errors
        video_info.is_valid = len(errors) == 0
        
        if errors:
            logger.warning("Video validation issues", file_path=str(video_info.file_path), errors=errors)
        else:
            logger.debug("Video validation passed", file_path=str(video_info.file_path))
    
    def _check_hardware_compatibility(self, video_info: VideoInfo):
        """Check if video can be hardware decoded"""
        if not self.enable_hardware_acceleration:
            video_info.hardware_decodable = False
            return
        
        if video_info.primary_video_stream:
            codec = video_info.primary_video_stream.codec
            video_info.hardware_decodable = codec in self.HARDWARE_DECODERS
            
            logger.debug("Hardware compatibility check",
                        codec=codec.value,
                        hardware_decodable=video_info.hardware_decodable)
    
    def get_optimal_decoder(self, video_info: VideoInfo) -> str:
        """Get optimal decoder for the video"""
        if not video_info.primary_video_stream:
            return "copy"
        
        codec = video_info.primary_video_stream.codec
        
        if self.enable_hardware_acceleration and video_info.hardware_decodable:
            return self.HARDWARE_DECODERS.get(codec, codec.value)
        
        return codec.value
    
    def is_format_supported(self, file_path: Union[str, Path]) -> bool:
        """Check if video format is supported"""
        file_path = Path(file_path)
        extension = file_path.suffix.lower()
        return extension in self.CONTAINER_EXTENSIONS
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported file extensions"""
        return list(self.CONTAINER_EXTENSIONS.keys())
    
    def extract_frame(self, video_info: VideoInfo, timestamp: float, 
                     output_path: Union[str, Path], width: Optional[int] = None, 
                     height: Optional[int] = None) -> bool:
        """
        Extract a frame from video at specified timestamp
        
        Args:
            video_info: VideoInfo object
            timestamp: Time in seconds
            output_path: Path to save extracted frame
            width: Optional width for resizing
            height: Optional height for resizing
            
        Returns:
            True if successful, False otherwise
        """
        try:
            input_stream = ffmpeg.input(str(video_info.file_path))
            
            # Configure decoder
            decoder = self.get_optimal_decoder(video_info)
            if decoder != video_info.primary_video_stream.codec.value:
                input_stream = input_stream.video.filter('scale', 
                                                        codec=decoder)
            
            # Seek to timestamp
            input_stream = input_stream.filter('select', f'gte(t,{timestamp})')
            
            # Resize if requested
            if width and height:
                input_stream = input_stream.filter('scale', width, height)
            
            # Output first frame
            output_stream = ffmpeg.output(input_stream, str(output_path), 
                                        vframes=1, format='image2')
            
            # Extract FFmpeg command and add -y flag manually to avoid ffmpeg-python parameter issues
            cmd_args = output_stream.compile()
            
            # Insert -y flag after 'ffmpeg' for overwrite behavior
            if len(cmd_args) > 0 and cmd_args[0] == 'ffmpeg':
                final_cmd = ['ffmpeg', '-y'] + cmd_args[1:]
            else:
                final_cmd = cmd_args
                if '-y' not in final_cmd:
                    final_cmd.insert(1, '-y')  # Insert after first element
            
            # Execute FFmpeg via subprocess for precise control
            result = subprocess.run(
                final_cmd,
                capture_output=True,
                text=True,
                check=False  # We'll handle errors manually
            )
            
            # Check if subprocess execution failed
            if result.returncode != 0:
                logger.error("FFmpeg frame extraction failed", 
                           timestamp=timestamp,
                           output_path=str(output_path),
                           return_code=result.returncode,
                           stderr=result.stderr)
                return False
            
            logger.debug("Frame extracted", 
                        timestamp=timestamp,
                        output_path=str(output_path))
            return True
            
        except Exception as e:
            logger.error("Frame extraction failed", 
                        timestamp=timestamp,
                        error=str(e))
            return False
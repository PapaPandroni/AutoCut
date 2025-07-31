# AutoCut Troubleshooting Guide

This guide helps you resolve common issues when using AutoCut.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Performance Problems](#performance-problems)
- [Video Processing Errors](#video-processing-errors)
- [Audio Analysis Issues](#audio-analysis-issues)
- [Hardware Acceleration Problems](#hardware-acceleration-problems)
- [Memory and Resource Issues](#memory-and-resource-issues)
- [Output Quality Problems](#output-quality-problems)
- [Configuration Issues](#configuration-issues)

## Installation Issues

### Problem: Dependencies fail to install

**Symptoms:**
- `pip install -r requirements.txt` fails
- Import errors when running AutoCut

**Solutions:**

1. **Ensure you're in the virtual environment:**
   ```bash
   source env/bin/activate  # macOS/Linux
   # or
   env\Scripts\activate     # Windows
   ```

2. **Update pip and setuptools:**
   ```bash
   pip install --upgrade pip setuptools wheel
   ```

3. **Install specific problematic packages individually:**
   ```bash
   # Common problematic packages
   pip install numpy
   pip install opencv-python
   pip install librosa
   pip install mediapipe
   ```

4. **For M1/M2 Macs, use correct architecture:**
   ```bash
   # Check your architecture
   uname -m
   
   # For Apple Silicon, ensure you're using the right Python
   which python
   python --version
   ```

### Problem: FFmpeg not found

**Symptoms:**
- "FFmpeg not available" error
- Video processing fails

**Solutions:**

1. **Install FFmpeg:**
   ```bash
   # macOS with Homebrew
   brew install ffmpeg
   
   # Ubuntu/Debian
   sudo apt update
   sudo apt install ffmpeg
   
   # Windows - download from https://ffmpeg.org/
   ```

2. **Verify FFmpeg installation:**
   ```bash
   ffmpeg -version
   ffprobe -version
   ```

3. **Add FFmpeg to PATH if needed:**
   - Windows: Add FFmpeg bin directory to system PATH
   - macOS/Linux: Usually handled by package managers

### Problem: MediaPipe installation fails

**Symptoms:**
- MediaPipe fails to install or import
- Face detection not working

**Solutions:**

1. **Install MediaPipe with specific version:**
   ```bash
   pip install mediapipe==0.10.8
   ```

2. **For Apple Silicon Macs:**
   ```bash
   # Ensure you're using ARM64 Python
   python -c "import platform; print(platform.machine())"
   # Should output: arm64
   ```

3. **Alternative installation:**
   ```bash
   pip install --no-deps mediapipe
   pip install opencv-python numpy protobuf
   ```

## Performance Problems

### Problem: Processing slower than expected

**Symptoms:**
- Not achieving 15x real-time processing
- Long processing times

**Solutions:**

1. **Check system capabilities:**
   ```bash
   python validate_performance.py --quick-test
   ```

2. **Optimize performance mode:**
   ```bash
   # Use speed mode for fastest processing
   python autocut_prototype.py input.mp4 --performance speed
   ```

3. **Check hardware acceleration:**
   ```bash
   # Verify VideoToolbox is available (macOS)
   ffmpeg -hwaccels
   ```

4. **Reduce video resolution for testing:**
   ```bash
   # Use lower resolution input for faster processing
   ffmpeg -i input.mp4 -vf scale=1280:720 input_720p.mp4
   ```

5. **Monitor resource usage:**
   ```bash
   # Check CPU and memory usage
   top -pid $(pgrep -f autocut_prototype)
   ```

### Problem: Memory usage too high

**Symptoms:**
- Out of memory errors
- System becomes unresponsive

**Solutions:**

1. **Use streaming processing:**
   ```python
   # In your configuration
   video:
     enable_streaming_processing: true
     max_memory_mb: 2048
   ```

2. **Process shorter segments:**
   ```bash
   # Split large videos first
   ffmpeg -i large_video.mp4 -t 300 -c copy segment1.mp4
   ```

3. **Reduce batch size:**
   ```python
   # In configuration
   performance:
     batch_size: 8  # Reduce from default 16
     max_workers: 2  # Reduce parallel processing
   ```

## Video Processing Errors

### Problem: "Video file not found" or "Unsupported format"

**Symptoms:**
- File exists but AutoCut can't load it
- Format rejection errors
- Folder processing fails

**Solutions:**

1. **Check file paths:**
   ```bash
   # For single video files
   ls -la "path/to/video.mp4"
   
   # For folder processing
   ls -la "path/to/video_folder/"
   find "path/to/video_folder/" -name "*.mp4"
   ```

2. **Verify files are not corrupted:**
   ```bash
   ffprobe "path/to/video.mp4"
   
   # Check all videos in folder
   for video in video_folder/*.mp4; do
     echo "Checking: $video"
     ffprobe "$video" 2>/dev/null && echo "✅ Valid" || echo "❌ Invalid"
   done
   ```

3. **Convert unsupported formats:**
   ```bash
   ffmpeg -i input.mkv -c:v libx264 -c:a aac output.mp4
   ```

4. **Check supported formats:**
   ```python
   from src.video.ingestion import VideoIngestion
   ingestion = VideoIngestion()
   print(ingestion.get_supported_formats())
   ```

### Problem: Folder processing issues

**Symptoms:**
- "No video files found in folder"
- Only some videos processed from folder

**Solutions:**

1. **Check folder structure:**
   ```bash
   # Verify folder contains video files
   find video_folder/ -name "*.mp4" -o -name "*.mov" -o -name "*.avi"
   
   # Check folder permissions
   ls -la video_folder/
   ```

2. **Use correct folder path:**
   ```bash
   # Correct folder usage
   python autocut_prototype.py ./video_clips/ --music song.mp3
   python autocut_prototype.py /absolute/path/to/videos/ --music music.mp3
   ```

3. **Check for mixed file types:**
   ```bash
   # List all files in folder
   ls -la video_folder/
   
   # Convert unsupported files
   for file in video_folder/*.mkv; do
     ffmpeg -i "$file" -c:v libx264 -c:a aac "${file%.mkv}.mp4"
   done
   ```

### Problem: Scene detection not working properly

**Symptoms:**
- No scene changes detected
- Too many false positives

**Solutions:**

1. **Adjust scene detection sensitivity:**
   ```yaml
   # In config file
   scene_detection:
     histogram_threshold: 0.3  # Lower = more sensitive
     edge_threshold: 0.4
     optical_flow_threshold: 0.5
   ```

2. **Try different algorithms:**
   ```bash
   # Test different scene detection methods
   python autocut_prototype.py input.mp4 --scene-algorithm histogram
   python autocut_prototype.py input.mp4 --scene-algorithm edge
   python autocut_prototype.py input.mp4 --scene-algorithm combined
   ```

3. **Check video characteristics:**
   ```bash
   ffprobe -v quiet -show_streams -select_streams v:0 input.mp4
   ```

### Problem: Face detection fails or inaccurate

**Symptoms:**
- No faces detected in videos with clear faces
- False positive face detections

**Solutions:**

1. **Check video quality:**
   - Ensure faces are clearly visible
   - Check lighting conditions
   - Verify video resolution is adequate

2. **Adjust face detection settings:**
   ```yaml
   face_detection:
     confidence_threshold: 0.5  # Lower = more detections
     min_face_size: 50  # Pixels
     max_face_size: 400
   ```

3. **Test with different processing modes:**
   ```bash
   # Try quality mode for better accuracy
   python autocut_prototype.py input.mp4 --performance quality
   ```

4. **Verify MediaPipe installation:**
   ```python
   import mediapipe as mp
   print(mp.__version__)
   ```

## Audio Analysis Issues

### Problem: Beat detection inaccurate

**Symptoms:**
- Cuts not aligned with music beats
- Incorrect tempo detection

**Solutions:**

1. **Check audio quality:**
   ```bash
   # Analyze audio properties
   ffprobe -v quiet -show_streams -select_streams a:0 input.mp4
   
   # For external music files
   ffprobe -v quiet -show_streams music.mp3
   ```

2. **Adjust beat detection sensitivity:**
   ```yaml
   audio:
     beat_detection_sensitivity: 0.7  # Adjust 0.1-1.0
     min_tempo_bpm: 60
     max_tempo_bpm: 200
   ```

3. **Try different audio preprocessing:**
   ```yaml
   audio:
     enable_onset_detection: true
     onset_threshold: 0.3
     beat_tracking_method: "librosa"  # or "madmom" if available
   ```

4. **Test with high-quality audio:**
   ```bash
   # Extract high-quality audio from video
   ffmpeg -i input.mp4 -vn -acodec libmp3lame -ab 320k audio.mp3
   
   # Use high-quality external music
   python autocut_prototype.py video_folder/ --music high_quality_music.wav
   ```

### Problem: External music file not recognized

**Symptoms:**
- "Music file not found" or "Unsupported music format"
- Music analysis fails

**Solutions:**

1. **Check supported music formats:**
   ```python
   # Supported formats: MP3, WAV, FLAC, AAC, M4A
   python autocut_prototype.py video_folder/ --music song.mp3
   python autocut_prototype.py video_folder/ --music song.wav
   ```

2. **Verify music file path:**
   ```bash
   ls -la "path/to/music.mp3"
   ffprobe "path/to/music.mp3"
   ```

3. **Convert unsupported formats:**
   ```bash
   # Convert to supported format
   ffmpeg -i input.ogg -acodec libmp3lame -ab 192k output.mp3
   ffmpeg -i input.wma -acodec libmp3lame -ab 192k output.mp3
   ```

### Problem: No audio detected

**Symptoms:**
- "No audio stream found" error
- Silent video processing

**Solutions:**

1. **Check for audio streams:**
   ```bash
   ffprobe -v quiet -show_streams input.mp4 | grep audio
   ```

2. **Add audio track if missing:**
   ```bash
   # Add silent audio track
   ffmpeg -i input.mp4 -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000 \
     -c:v copy -c:a aac -shortest output.mp4
   ```

3. **Extract existing audio:**
   ```bash
   ffmpeg -i input.mp4 -vn -acodec copy audio.mp4
   ```

## Hardware Acceleration Problems

### Problem: Hardware acceleration not working

**Symptoms:**
- Processing slower than expected on Apple Silicon
- "Hardware acceleration not available" warnings

**Solutions:**

1. **Verify VideoToolbox support:**
   ```bash
   ffmpeg -hwaccels
   # Should show "videotoolbox" for macOS
   ```

2. **Check system information:**
   ```bash
   system_profiler SPHardwareDataType | grep "Chip"
   ```

3. **Force hardware acceleration:**
   ```yaml
   video:
     enable_hardware_acceleration: true
     preferred_decoder: "videotoolbox"
   ```

4. **Test hardware acceleration:**
   ```bash
   ffmpeg -hwaccel videotoolbox -i input.mp4 -c:v h264_videotoolbox -t 10 test_output.mp4
   ```

### Problem: "VideoToolbox" errors on macOS

**Symptoms:**
- VideoToolbox-related error messages
- Fallback to software encoding

**Solutions:**

1. **Update macOS:**
   - Ensure you're running macOS 10.15 or later
   - Update to latest version if possible

2. **Check codec compatibility:**
   ```bash
   # Test codec support
   ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=30 \
     -c:v h264_videotoolbox test.mp4
   ```

3. **Use fallback options:**
   ```yaml
   video:
     hardware_acceleration_fallback: true
     software_encoder: "libx264"
   ```

## Memory and Resource Issues

### Problem: System runs out of memory

**Symptoms:**
- Process killed by system
- "MemoryError" exceptions

**Solutions:**

1. **Enable streaming mode:**
   ```yaml
   performance:
     enable_streaming: true
     chunk_size_mb: 100
   ```

2. **Reduce parallel processing:**
   ```yaml
   performance:
     max_workers: 2  # Reduce from default
     batch_size: 4   # Smaller batches
   ```

3. **Process shorter segments:**
   ```bash
   # Split video into smaller parts
   ffmpeg -i input.mp4 -c copy -map 0 -segment_time 300 -f segment segment_%03d.mp4
   ```

4. **Monitor memory usage:**
   ```bash
   # macOS
   sudo memory_pressure
   
   # Linux
   free -h
   ```

### Problem: High CPU usage

**Symptoms:**
- System becomes unresponsive
- Fan noise increases significantly

**Solutions:**

1. **Limit CPU usage:**
   ```yaml
   performance:
     cpu_limit_percent: 80
     thread_count: 4  # Limit threads
   ```

2. **Use performance monitoring:**
   ```bash
   python autocut_prototype.py input.mp4 --monitor-performance
   ```

3. **Process during off-hours:**
   ```bash
   # Use nice to lower priority
   nice -n 10 python autocut_prototype.py input.mp4
   ```

## Output Quality Problems

### Problem: Poor output video quality

**Symptoms:**
- Blurry or pixelated output
- Color issues
- Artifacts in video

**Solutions:**

1. **Use higher quality preset:**
   ```bash
   python autocut_prototype.py input.mp4 --quality lossless
   ```

2. **Check source video quality:**
   ```bash
   ffprobe -v quiet -select_streams v:0 -show_entries stream=bit_rate,width,height input.mp4
   ```

3. **Avoid re-encoding when possible:**
   ```yaml
   rendering:
     prefer_stream_copy: true
     fallback_to_encode: false
   ```

4. **Adjust quality settings:**
   ```yaml
   rendering:
     video_bitrate: "5000k"
     audio_bitrate: "192k"
     preset: "slower"  # Better quality, slower encoding
   ```

### Problem: Audio-video sync issues

**Symptoms:**
- Audio and video out of sync
- Lip-sync problems

**Solutions:**

1. **Check source sync:**
   ```bash
   ffmpeg -i input.mp4 -c copy -t 10 test_sync.mp4
   ```

2. **Force sync correction:**
   ```yaml
   rendering:
     force_audio_sync: true
     sync_correction_threshold: 0.04  # 40ms
   ```

3. **Use frame-accurate cutting:**
   ```yaml
   timeline:
     frame_accurate_cuts: true
     keyframe_alignment: false
   ```

## Configuration Issues

### Problem: Configuration not loading

**Symptoms:**
- Default settings always used
- Custom settings ignored

**Solutions:**

1. **Check config file location:**
   ```bash
   python -c "from src.utils.config import config; print(config._config_path)"
   ```

2. **Validate YAML syntax:**
   ```bash
   python -c "import yaml; yaml.safe_load(open('autocut_config.yaml'))"
   ```

3. **Use absolute paths:**
   ```bash
   python autocut_prototype.py input.mp4 --config /absolute/path/to/config.yaml
   ```

4. **Check permissions:**
   ```bash
   ls -la autocut_config.yaml
   ```

### Problem: Settings not taking effect

**Symptoms:**
- Changes to config file ignored
- Unexpected behavior

**Solutions:**

1. **Restart application:**
   - Configuration is loaded at startup
   - Restart after making changes

2. **Check setting precedence:**
   - Command line arguments override config file
   - Environment variables override config file
   - Default values are used as fallback

3. **Validate setting names:**
   ```bash
   # Check available settings
   python -c "from src.utils.config import config; print(config.get_all_settings())"
   ```

## Getting Help

If you're still experiencing issues:

1. **Enable debug logging:**
   ```bash
   python autocut_prototype.py input.mp4 --log-level DEBUG
   ```

2. **Run system diagnostics:**
   ```bash
   python validate_performance.py --full-diagnostics
   ```

3. **Create a minimal test case:**
   ```bash
   # Test with a short, simple video
   ffmpeg -f lavfi -i testsrc=duration=10:size=640x480:rate=30 -pix_fmt yuv420p test.mp4
   python autocut_prototype.py test.mp4
   ```

4. **Check system requirements:**
   - macOS 10.15+ for hardware acceleration
   - Python 3.8+
   - At least 8GB RAM recommended
   - FFmpeg 4.0+

5. **Report issues with:**
   - Operating system and version
   - Python version
   - Complete error messages
   - Configuration file (if applicable)
   - Input file characteristics

For additional support, please check the GitHub issues or create a new issue with detailed information about your problem.
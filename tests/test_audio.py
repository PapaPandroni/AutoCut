"""Tests for audio analysis module"""
import pytest
import numpy as np
from pathlib import Path
import tempfile
import soundfile as sf

from src.audio.analyzer import AudioAnalyzer, AudioAnalysis


@pytest.fixture
def sample_audio_file():
    """Create a simple synthetic audio file for testing"""
    # Generate a simple sine wave at 440 Hz (A4) with a beat pattern
    duration = 10.0  # 10 seconds
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    
    # Create a simple beat pattern at 120 BPM (0.5 seconds per beat)
    beat_freq = 2.0  # 2 beats per second = 120 BPM
    
    # Sine wave with amplitude modulation to create beats
    frequency = 440.0  # A4
    beat_envelope = 0.5 * (1 + np.sin(2 * np.pi * beat_freq * t))
    audio = beat_envelope * np.sin(2 * np.pi * frequency * t)
    
    # Add some percussion-like clicks on beats
    beat_times = np.arange(0, duration, 0.5)  # Every 0.5 seconds
    for beat_time in beat_times:
        beat_sample = int(beat_time * sample_rate)
        if beat_sample < len(audio):
            # Add a short click
            click_duration = int(0.01 * sample_rate)  # 10ms click
            click_end = min(beat_sample + click_duration, len(audio))
            audio[beat_sample:click_end] += 0.3 * np.sin(2 * np.pi * 1000 * 
                                                        t[beat_sample:click_end])
    
    # Save to temporary file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        sf.write(f.name, audio, sample_rate)
        return Path(f.name)


def test_audio_analyzer_initialization():
    """Test AudioAnalyzer initialization"""
    analyzer = AudioAnalyzer()
    assert analyzer.sample_rate > 0
    assert analyzer.hop_length > 0
    assert 0 <= analyzer.confidence_threshold <= 1


def test_audio_analysis_creation():
    """Test AudioAnalysis object creation"""
    beats = [0.0, 0.5, 1.0, 1.5, 2.0]
    analysis = AudioAnalysis(
        bpm=120.0,
        beats=beats,
        confidence=0.85,
        duration=2.5,
        sample_rate=44100
    )
    
    assert analysis.bpm == 120.0
    assert analysis.beats == beats
    assert analysis.confidence == 0.85
    assert analysis.duration == 2.5
    assert analysis.sample_rate == 44100


def test_audio_analysis_to_dict():
    """Test AudioAnalysis to_dict conversion"""
    beats = [0.0, 0.5, 1.0, 1.5, 2.0]
    analysis = AudioAnalysis(
        bpm=120.0,
        beats=beats,
        confidence=0.85,
        duration=2.5,
        sample_rate=44100
    )
    
    result = analysis.to_dict()
    
    assert result['bpm'] == 120.0
    assert result['beats'] == beats
    assert result['confidence'] == 0.85
    assert result['duration'] == 2.5
    assert result['sample_rate'] == 44100
    assert result['beat_count'] == 5
    assert result['avg_beat_interval'] == 0.5


def test_analyze_nonexistent_file():
    """Test error handling for nonexistent file"""
    analyzer = AudioAnalyzer()
    
    with pytest.raises(FileNotFoundError):
        analyzer.analyze_audio("nonexistent_file.wav")


def test_analyze_sample_audio(sample_audio_file):
    """Test analysis of synthetic audio file"""
    analyzer = AudioAnalyzer()
    
    try:
        analysis = analyzer.analyze_audio(str(sample_audio_file))
        
        # Verify basic properties
        assert analysis.duration > 0
        assert analysis.sample_rate > 0
        assert len(analysis.beats) > 0
        assert 0 <= analysis.confidence <= 1
        assert analysis.bpm > 0
        
        # For our 120 BPM synthetic audio, expect roughly correct BPM
        # (allowing for detection variation)
        assert 80 <= analysis.bpm <= 160
        
        # Should detect reasonable number of beats for 10-second audio
        assert len(analysis.beats) >= 5  # At least some beats detected
        
        print(f"Detected BPM: {analysis.bpm:.1f}")
        print(f"Beat count: {len(analysis.beats)}")
        print(f"Confidence: {analysis.confidence:.3f}")
        
    finally:
        # Clean up temporary file
        sample_audio_file.unlink()


def test_get_beat_segments(sample_audio_file):
    """Test beat segment generation"""
    analyzer = AudioAnalyzer()
    
    try:
        analysis = analyzer.analyze_audio(str(sample_audio_file))
        segments = analyzer.get_beat_segments(analysis)
        
        # Should have segments
        assert len(segments) > 0
        
        # Each segment should be a tuple of (start, end)
        for start, end in segments:
            assert isinstance(start, float)
            assert isinstance(end, float)
            assert start < end
            assert start >= 0
            assert end <= analysis.duration
        
        # Segments should be in order
        for i in range(len(segments) - 1):
            assert segments[i][1] <= segments[i + 1][0]
        
        print(f"Generated {len(segments)} beat segments")
        
    finally:
        sample_audio_file.unlink()


def test_export_analysis(sample_audio_file):
    """Test exporting analysis to JSON"""
    analyzer = AudioAnalyzer()
    
    try:
        analysis = analyzer.analyze_audio(str(sample_audio_file))
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            export_path = Path(f.name)
        
        try:
            analyzer.export_analysis(analysis, str(export_path))
            
            # Verify file was created and contains data
            assert export_path.exists()
            
            import json
            with open(export_path, 'r') as f:
                data = json.load(f)
            
            # Verify required fields are present
            required_fields = ['bpm', 'beats', 'confidence', 'duration', 'sample_rate']
            for field in required_fields:
                assert field in data
            
        finally:
            if export_path.exists():
                export_path.unlink()
        
    finally:
        sample_audio_file.unlink()
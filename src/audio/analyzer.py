"""Audio analysis module for AutoCut using librosa"""
import numpy as np
import librosa
import librosa.display
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import time

from ..utils.logging import get_logger
from ..utils.config import config

logger = get_logger(__name__)


class AudioAnalysis:
    """Container for audio analysis results"""
    
    def __init__(
        self,
        bpm: float,
        beats: List[float],
        confidence: float,
        duration: float,
        sample_rate: int,
        tempo_times: Optional[List[float]] = None,
        beat_frames: Optional[List[int]] = None
    ):
        self.bpm = bpm
        self.beats = beats  # Beat timestamps in seconds
        self.confidence = confidence
        self.duration = duration
        self.sample_rate = sample_rate
        self.tempo_times = tempo_times or []
        self.beat_frames = beat_frames or []
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'bpm': self.bpm,
            'beats': self.beats,
            'confidence': self.confidence,
            'duration': self.duration,
            'sample_rate': self.sample_rate,
            'beat_count': len(self.beats),
            'avg_beat_interval': np.mean(np.diff(self.beats)) if len(self.beats) > 1 else 0.0
        }


class AudioAnalyzer:
    """Audio analysis engine using librosa"""
    
    def __init__(self):
        self.sample_rate = config.get('audio.sample_rate', 44100)
        self.hop_length = config.get('audio.hop_length', 512)
        self.confidence_threshold = config.get('audio.confidence_threshold', 0.7)
        
        logger.info("AudioAnalyzer initialized", 
                   sample_rate=self.sample_rate, 
                   hop_length=self.hop_length)
    
    def analyze_audio(self, file_path: str) -> AudioAnalysis:
        """
        Analyze audio file to extract BPM, beats, and other musical features
        
        Args:
            file_path: Path to audio file
            
        Returns:
            AudioAnalysis object with results
            
        Raises:
            FileNotFoundError: If audio file doesn't exist
            Exception: If audio analysis fails
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        
        logger.info("Starting audio analysis", file_path=str(file_path))
        start_time = time.time()
        
        try:
            # Load audio file
            y, sr = librosa.load(str(file_path), sr=self.sample_rate)
            duration = librosa.get_duration(y=y, sr=sr)
            
            logger.info("Audio loaded", duration=f"{duration:.2f}s", sample_rate=sr)
            
            # Tempo and beat detection
            tempo, beats = self._detect_beats(y, sr)
            beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=self.hop_length)
            
            # Calculate confidence based on beat consistency
            confidence = self._calculate_confidence(beat_times, tempo)
            
            analysis_time = time.time() - start_time
            logger.info("Audio analysis completed", 
                       analysis_time=f"{analysis_time:.2f}s",
                       bpm=f"{tempo:.1f}",
                       beat_count=len(beat_times),
                       confidence=f"{confidence:.2f}")
            
            return AudioAnalysis(
                bpm=tempo,
                beats=beat_times.tolist(),
                confidence=confidence,
                duration=duration,
                sample_rate=sr,
                beat_frames=beats.tolist()
            )
            
        except Exception as e:
            logger.error("Audio analysis failed", error=str(e), file_path=str(file_path))
            raise
    
    def _detect_beats(self, y: np.ndarray, sr: int) -> Tuple[float, np.ndarray]:
        """
        Detect tempo and beat positions using librosa
        
        Args:
            y: Audio time series
            sr: Sample rate
            
        Returns:
            Tuple of (tempo, beat_frames)
        """
        # Use multiple methods for robustness
        
        # Method 1: Standard beat tracking
        tempo, beats = librosa.beat.beat_track(
            y=y, sr=sr, hop_length=self.hop_length, units='frames'
        )
        
        # Ensure tempo is a scalar
        if isinstance(tempo, np.ndarray):
            tempo = float(tempo.item()) if tempo.size == 1 else float(tempo[0])
        
        # Method 2: Onset detection for validation
        onset_frames = librosa.onset.onset_detect(
            y=y, sr=sr, hop_length=self.hop_length, units='frames'
        )
        
        # Method 3: Tempo estimation with multiple approaches
        tempo_estimates = []
        
        # Dynamic programming beat tracker
        tempo_dp, beats_dp = librosa.beat.beat_track(
            y=y, sr=sr, hop_length=self.hop_length, 
            trim=False, start_bpm=120.0, tightness=100
        )
        
        # Ensure tempo_dp is a scalar
        if isinstance(tempo_dp, np.ndarray):
            tempo_dp = float(tempo_dp.item()) if tempo_dp.size == 1 else float(tempo_dp[0])
            
        tempo_estimates.append(tempo_dp)
        
        # Aggregate tempo estimates
        if len(tempo_estimates) > 1:
            # Use median for robustness
            final_tempo = float(np.median([tempo] + tempo_estimates))
        else:
            final_tempo = tempo
        
        logger.debug("Beat detection completed", 
                    primary_tempo=f"{tempo:.1f}",
                    final_tempo=f"{final_tempo:.1f}",
                    beat_count=len(beats),
                    onset_count=len(onset_frames))
        
        return final_tempo, beats
    
    def _calculate_confidence(self, beat_times: np.ndarray, tempo: float) -> float:
        """
        Calculate confidence score for beat detection
        
        Args:
            beat_times: Array of beat timestamps
            tempo: Detected tempo in BPM
            
        Returns:
            Confidence score between 0 and 1
        """
        if len(beat_times) < 3:
            return 0.0
        
        # Calculate beat intervals
        intervals = np.diff(beat_times)
        expected_interval = 60.0 / tempo  # Expected time between beats
        
        # Measure consistency of beat intervals
        interval_consistency = 1.0 - (np.std(intervals) / np.mean(intervals))
        interval_consistency = max(0.0, min(1.0, interval_consistency))
        
        # Check if intervals are close to expected
        interval_accuracy = 1.0 - np.mean(np.abs(intervals - expected_interval) / expected_interval)
        interval_accuracy = max(0.0, min(1.0, interval_accuracy))
        
        # Combine metrics
        confidence = (interval_consistency * 0.6 + interval_accuracy * 0.4)
        
        logger.debug("Confidence calculation",
                    interval_consistency=f"{interval_consistency:.3f}",
                    interval_accuracy=f"{interval_accuracy:.3f}",
                    confidence=f"{confidence:.3f}")
        
        return confidence
    
    def get_beat_segments(self, analysis: AudioAnalysis, min_segment_length: float = 0.5) -> List[Tuple[float, float]]:
        """
        Get time segments between beats for video synchronization
        
        Args:
            analysis: AudioAnalysis object
            min_segment_length: Minimum segment length in seconds
            
        Returns:
            List of (start_time, end_time) tuples
        """
        if len(analysis.beats) < 2:
            return [(0.0, analysis.duration)]
        
        segments = []
        beats = analysis.beats
        
        for i in range(len(beats) - 1):
            start = beats[i]
            end = beats[i + 1]
            
            # Ensure minimum segment length
            if end - start >= min_segment_length:
                segments.append((start, end))
            else:
                # Extend to next beat if too short
                if i + 2 < len(beats):
                    segments.append((start, beats[i + 2]))
        
        # Add final segment
        if beats[-1] < analysis.duration - min_segment_length:
            segments.append((beats[-1], analysis.duration))
        
        logger.debug("Beat segments created", segment_count=len(segments))
        return segments
    
    def export_analysis(self, analysis: AudioAnalysis, output_path: str):
        """
        Export analysis results to JSON file
        
        Args:
            analysis: AudioAnalysis object
            output_path: Path to output JSON file
        """
        import json
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(analysis.to_dict(), f, indent=2)
        
        logger.info("Analysis exported", output_path=str(output_path))
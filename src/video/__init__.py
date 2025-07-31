"""Video analysis modules for AutoCut"""

# Video ingestion
from .ingestion import (
    VideoIngestion,
    VideoInfo,
    VideoStream,
    AudioStream,
    VideoCodec,
    ContainerFormat
)

# Scene detection
from .scene_detection import (
    SceneDetection,
    SceneDetectionResult,
    SceneChange,
    SceneDetectionAlgorithm,
    ProcessingMode
)

__all__ = [
    # Ingestion
    'VideoIngestion',
    'VideoInfo', 
    'VideoStream',
    'AudioStream',
    'VideoCodec',
    'ContainerFormat',
    
    # Scene detection
    'SceneDetection',
    'SceneDetectionResult',
    'SceneChange',
    'SceneDetectionAlgorithm',
    'ProcessingMode'
]
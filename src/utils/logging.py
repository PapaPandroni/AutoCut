"""Logging configuration for AutoCut"""
import logging
import sys
from pathlib import Path
from typing import Optional
import structlog


def setup_logging(
    level: str = "INFO", 
    log_file: Optional[Path] = None,
    structured: bool = True
) -> structlog.BoundLogger:
    """
    Set up logging for AutoCut
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional path to log file
        structured: Whether to use structured logging
    
    Returns:
        Configured logger instance
    """
    
    # Configure standard library logging
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create formatters
    if structured:
        # Configure structlog
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        logger = structlog.get_logger("autocut")
    else:
        # Standard logging setup
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        logger = logging.getLogger("autocut")
        logger.setLevel(log_level)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        
        if not structured:
            file_handler.setFormatter(formatter)
        
        logging.getLogger("autocut").addHandler(file_handler)
    
    return logger


def get_logger(name: str = "autocut") -> structlog.BoundLogger:
    """Get a logger instance"""
    return structlog.get_logger(name)
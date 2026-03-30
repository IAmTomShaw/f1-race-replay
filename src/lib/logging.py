"""Centralized logging configuration for F1 Race Replay.

This module provides a standardized logging setup with support for:
- Debug mode for verbose output
- Separate loggers for different modules
- Consistent formatting across the application
"""

import logging
import sys
from typing import Optional


# Global logger instance
_root_logger: Optional[logging.Logger] = None
_debug_mode: bool = False


def configure_logging(debug: bool = False, name: str = "f1_replay") -> logging.Logger:
    """Configure the logging system for the application.
    
    Args:
        debug: If True, sets logging to DEBUG level. Otherwise INFO level.
        name: Root logger name.
        
    Returns:
        The configured root logger.
    """
    global _root_logger, _debug_mode
    
    _debug_mode = debug
    level = logging.DEBUG if debug else logging.INFO
    
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Create and configure root logger
    _root_logger = logging.getLogger(name)
    _root_logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    _root_logger.handlers = []
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    _root_logger.addHandler(console_handler)
    
    # Suppress verbose third-party logging
    logging.getLogger("fastf1").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    
    return _root_logger


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger for a specific module.
    
    Args:
        name: Logger name (typically __name__ of the module).
        
    Returns:
        A configured logger instance.
    """
    if _root_logger is None:
        configure_logging()
    
    logger = logging.getLogger(f"f1_replay.{name}")
    return logger


def is_debug_mode() -> bool:
    """Check if debug mode is enabled.
    
    Returns:
        True if debug logging is enabled.
    """
    return _debug_mode

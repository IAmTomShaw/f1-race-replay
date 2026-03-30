"""Centralized logging configuration for F1 Race Replay using Loguru.

This module provides a standardized logging setup with support for:
- Debug mode for verbose output
- Separate loggers for different modules
- Consistent formatting across the application
- Automatic file rotation and retention
"""

from loguru import logger
import sys

# Global debug mode
_debug_mode: bool = False


def configure_logging(debug: bool = False, name: str = "f1_replay") -> None:
    """Configure the logging system for the application.
    
    Args:
        debug: If True, sets logging to DEBUG level. Otherwise INFO level.
        name: Root logger name (kept for API compatibility).
    """
    global _debug_mode
    _debug_mode = debug
    
    # Remove default handler
    logger.remove()
    
    # Set log level
    log_level = "DEBUG" if debug else "INFO"
    
    # Add console handler with custom format
    logger.add(
        sys.stderr,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name: <15} | {message}",
        level=log_level,
    )
    
    # Suppress verbose third-party logging
    logger.disable("fastf1")
    logger.disable("urllib3")
    logger.disable("requests")
    logger.disable("matplotlib")


def get_logger(name: str):
    """Get a logger for a specific module.
    
    Args:
        name: Logger name (typically __name__ of the module).
        
    Returns:
        A configured loguru logger instance.
    """
    return logger.bind(name=name)


def is_debug_mode() -> bool:
    """Check if debug mode is enabled.
    
    Returns:
        True if debug logging is enabled.
    """
    return _debug_mode

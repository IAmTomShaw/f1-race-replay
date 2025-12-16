"""General utility functions for the F1 Race Replay application."""


def safe_int(value, default=1):
    """
    Safely convert a value to an integer.

    Args:
        value: The value to convert (can be int, float, str, etc.)
        default: The default value to return if conversion fails (default: 1)

    Returns:
        int: The converted integer value, or default if conversion fails

    Examples:
        >>> safe_int(5)
        5
        >>> safe_int("42")
        42
        >>> safe_int("invalid", default=0)
        0
        >>> safe_int(None, default=1)
        1
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

import os
import fastf1

def enable_cache(cache_dir: str = '.fastf1-cache'):
    """
    Enable FastF1 cache.
    
    Args:
        cache_dir: Directory to store cache files. Defaults to '.fastf1-cache'.
    """
    # Check if cache folder exists
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    # Enable local cache
    fastf1.Cache.enable_cache(cache_dir)

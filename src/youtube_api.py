"""
YouTube API wrapper for F1 Race Replay.
Uses yt-dlp for fetching video info and thumbnails.
"""

from typing import List, Dict, Any
import urllib.parse
import webbrowser
import json
import subprocess
import re


def search_with_yt_dlp(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search YouTube using yt-dlp to get actual video information.
    """
    try:
        cmd = [
            'yt-dlp',
            '--flat-playlist',
            '--dump-json',
            '--no-warnings',
            f"ytsearch{limit}:{query}"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        videos = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('{') and '"id":' in line:
                try:
                    data = json.loads(line)
                    video_id = data.get('id', '')
                    thumbnail = ''
                    if 'thumbnail' in data:
                        thumbnail = data['thumbnail']
                    elif video_id:
                        thumbnail = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
                    
                    videos.append({
                        'video_id': video_id,
                        'title': data.get('title', 'Unknown'),
                        'thumbnail': thumbnail,
                        'channel': data.get('channel', data.get('uploader', 'Unknown')),
                        'duration': _format_duration(data.get('duration')),
                        'duration_seconds': data.get('duration') or 0,
                        'link': f"https://www.youtube.com/watch?v={video_id}",
                    })
                except json.JSONDecodeError as e:
                    continue
        
        return videos
        
    except Exception as e:
        print(f"yt-dlp search error: {e}")
        return []


def _format_duration(seconds) -> str:
    """Format seconds to duration string."""
    if not seconds:
        return 'N/A'
    hours = int(seconds) // 3600
    minutes = (int(seconds) % 3600) // 60
    secs = int(seconds) % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def search_race_replay(event_name: str, year: int, limit: int = 6) -> List[Dict[str, Any]]:
    """
    Search for F1 race replay videos on YouTube.
    """
    query = f"{year} {event_name} F1 Race"
    
    videos = search_with_yt_dlp(query, limit)
    
    if not videos:
        videos = [
            {
                'video_id': '',
                'title': f"{year} {event_name} - Full Race Replay",
                'thumbnail': '',
                'channel': 'YouTube',
                'duration': 'Search',
                'duration_seconds': 0,
                'link': f"https://www.youtube.com/results?search_query={year}+{event_name}+F1+Race",
            }
        ]
    
    return videos


def search_qualifying_replay(event_name: str, year: int, limit: int = 4) -> List[Dict[str, Any]]:
    """Search for F1 qualifying videos."""
    query = f"{year} {event_name} F1 Qualifying"
    return search_with_yt_dlp(query, limit)


def get_youtube_embed_url(video_id: str, autoplay: bool = False) -> str:
    """Get YouTube embed URL."""
    autoplay_val = 1 if autoplay else 0
    return f"https://www.youtube.com/embed/{video_id}?autoplay={autoplay_val}"


def get_youtube_watch_url(video_id: str) -> str:
    """Get YouTube watch URL."""
    return f"https://www.youtube.com/watch?v={video_id}"


def format_duration(duration: str) -> str:
    """Format duration."""
    return duration


def get_thumbnail_url(video_id: str, quality: str = 'mq') -> str:
    """Get YouTube thumbnail URL."""
    return f"https://img.youtube.com/vi/{video_id}/{quality}default.jpg"


def open_youtube_search(event_name: str, year: int, session_type: str = 'race'):
    """Open YouTube search in browser."""
    if session_type == 'qualifying':
        query = f"{year} {event_name} F1 Qualifying"
    else:
        query = f"{year} {event_name} F1 Race"
    
    search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
    webbrowser.open(search_url)


def get_recommended_channels() -> List[Dict[str, str]]:
    """Return recommended F1 channels."""
    return [
        {
            'name': 'FORMULA 1',
            'handle': '@Formula1DRS',
            'description': 'Official F1 highlights',
            'url': 'https://www.youtube.com/@Formula1DRS/videos',
        },
        {
            'name': 'The Race',
            'handle': '@WeAreTheRace',
            'description': 'F1 replays and analysis',
            'url': 'https://www.youtube.com/@WeAreTheRace/videos',
        },
        {
            'name': 'Chain Bear',
            'handle': '@chainbear',
            'description': 'F1 technical analysis',
            'url': 'https://www.youtube.com/@chainbearf1/videos',
        },
    ]


if __name__ == "__main__":
    print("Testing YouTube search...")
    results = search_race_replay("Bahrain Grand Prix", 2025, limit=3)
    print(f"Found {len(results)} videos:")
    for v in results:
        print(f"  - {v['title']}")
        print(f"    ID: {v['video_id']}")
        print(f"    Duration: {v['duration']}")
        print(f"    Thumbnail: {v['thumbnail'][:60]}..." if v['thumbnail'] else "    No thumbnail")

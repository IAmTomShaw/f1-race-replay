"""
Session management and data retrieval service for the web API.
Handles loading from computed_data caches and on-demand session extraction.
"""

import os
import re
import pickle
from typing import Any, Dict, List, Optional
from src.lib.frame_store import FrameStore
from web.api.serializers import serialize_metadata, serialize_framestore_columnar


class SessionService:
    def __init__(self, computed_dir: str = "computed_data"):
        self.computed_dir = computed_dir
        self._memory_cache = {}  # session_key -> {"framestore": ..., "meta": ...}

    def list_cached_sessions(self) -> List[Dict[str, Any]]:
        """List all precomputed sessions ready for instant web replay."""
        if not os.path.exists(self.computed_dir):
            return []

        sessions = []
        files = [f for f in os.listdir(self.computed_dir) if f.endswith("_framestore.npz")]

        for filename in files:
            m = re.match(r"(\d{4})_Season_Round_(\d+):_(.+?)_-_([A-Za-z0-9 ]+?)_(\w+)_framestore\.npz", filename)
            if not m:
                continue

            year_str, round_str, event_slug, session_name, suffix = m.groups()
            base = filename[:-len("_framestore.npz")]
            meta_path = os.path.join(self.computed_dir, f"{base}_meta.pkl")

            event_title = event_slug.replace("_", " ")
            session_key = f"{year_str}_{round_str}_{suffix}"

            sessions.append({
                "session_key": session_key,
                "year": int(year_str),
                "round": int(round_str),
                "event_name": event_title,
                "session_name": session_name,
                "session_type": suffix.upper(),
                "framestore_file": filename,
                "has_meta": os.path.exists(meta_path)
            })

        sessions.sort(key=lambda s: (s["year"], s["round"]), reverse=True)
        return sessions

    def _find_cache_paths(self, year: int, round_no: int, session_type: str):
        """Find the matching .npz and .pkl file in computed_data."""
        if not os.path.exists(self.computed_dir):
            return None, None

        s_lower = session_type.lower()
        files = [f for f in os.listdir(self.computed_dir) if f.endswith("_framestore.npz")]

        for filename in files:
            m = re.match(r"(\d{4})_Season_Round_(\d+):_(.+?)_-_([A-Za-z0-9 ]+?)_(\w+)_framestore\.npz", filename)
            if m:
                y, r, _, _, sfx = m.groups()
                if int(y) == int(year) and int(r) == int(round_no) and sfx.lower() == s_lower:
                    base = filename[:-len("_framestore.npz")]
                    npz_path = os.path.join(self.computed_dir, filename)
                    meta_path = os.path.join(self.computed_dir, f"{base}_meta.pkl")
                    return npz_path, meta_path

        return None, None

    def get_session_data(self, year: int, round_no: int, session_type: str):
        """Load session FrameStore and metadata from cache or memory."""
        session_key = f"{year}_{round_no}_{session_type.lower()}"

        if session_key in self._memory_cache:
            return self._memory_cache[session_key]

        npz_path, meta_path = self._find_cache_paths(year, round_no, session_type)

        if not npz_path or not os.path.exists(npz_path):
            return None

        # Load FrameStore
        framestore = FrameStore.load(npz_path)

        # Load Meta
        meta = {}
        if meta_path and os.path.exists(meta_path):
            with open(meta_path, "rb") as f:
                meta = pickle.load(f)

        data = {
            "framestore": framestore,
            "meta": meta,
            "info": {
                "year": year,
                "round": round_no,
                "session_type": session_type.upper()
            }
        }
        self._memory_cache[session_key] = data
        return data

    def get_metadata(self, year: int, round_no: int, session_type: str) -> Optional[Dict[str, Any]]:
        """Get serialized track geometry and metadata for a session."""
        data = self.get_session_data(year, round_no, session_type)
        if not data:
            return None

        meta = data["meta"]
        info = data["info"]
        return serialize_metadata(meta, info)

    def get_frames(
        self,
        year: int,
        round_no: int,
        session_type: str,
        start: int = 0,
        limit: Optional[int] = None,
        step: int = 1
    ) -> Optional[Dict[str, Any]]:
        """Get serialized frames for a session in high-performance columnar format."""
        data = self.get_session_data(year, round_no, session_type)
        if not data:
            return None

        framestore = data["framestore"]
        return serialize_framestore_columnar(framestore, start=start, limit=limit, step=step)

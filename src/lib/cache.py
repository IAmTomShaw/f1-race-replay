import os
import pickle
from pathlib import Path
from typing import Any, Optional

from src.lib.settings import get_settings


CACHE_SCHEMA_VERSION = 2
_CACHE_SCHEMA_KEY = "_cache_schema_version"
_CACHE_PAYLOAD_KEY = "payload"


def get_computed_data_dir(create: bool = True) -> Path:
    path = Path(get_settings().computed_data_location).expanduser()
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_computed_data_file(filename: str, create_dir: bool = True) -> Path:
    return get_computed_data_dir(create=create_dir) / filename


def load_cached_payload(path: os.PathLike[str] | str) -> Optional[Any]:
    try:
        with open(path, "rb") as f:
            cached = pickle.load(f)
    except (EOFError, FileNotFoundError, pickle.UnpicklingError):
        return None

    if not isinstance(cached, dict):
        return None

    if cached.get(_CACHE_SCHEMA_KEY) != CACHE_SCHEMA_VERSION:
        return None

    return cached.get(_CACHE_PAYLOAD_KEY)


def save_cached_payload(path: os.PathLike[str] | str, payload: Any) -> None:
    wrapped = {
        _CACHE_SCHEMA_KEY: CACHE_SCHEMA_VERSION,
        _CACHE_PAYLOAD_KEY: payload,
    }
    with open(path, "wb") as f:
        pickle.dump(wrapped, f, protocol=pickle.HIGHEST_PROTOCOL)

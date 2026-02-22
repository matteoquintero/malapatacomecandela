# mpc/utils/cache.py
# -*- coding: utf-8 -*-
"""
Cache JSON con TTL. Thread-safe.
"""

import json
import hashlib
import threading
import time
from pathlib import Path
from typing import Any, Optional


class JSONCache:
    """Cache persistente en JSON con TTL por entrada. Thread-safe."""

    def __init__(self, path: str, ttl_days: int = 7):
        self.path = Path(path)
        self.ttl = ttl_days * 86400
        self._lock = threading.Lock()
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False),
            encoding="utf-8",
        )

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            if time.time() - entry["ts"] > self.ttl:
                del self._data[key]
                return None
            return entry["value"]

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = {"ts": time.time(), "value": value}
            self._save()

    @staticmethod
    def make_key(*args: Any) -> str:
        return hashlib.md5("|".join(str(a) for a in args).encode()).hexdigest()

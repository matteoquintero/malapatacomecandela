# mpc/acquisition/classifier_log.py
# -*- coding: utf-8 -*-
"""
Writer JSONL para el log de clasificaciones (Capa D1).
Una fila por track clasificado en cache/classifier_log.jsonl.

Permite:
  - Debugging de casos mal clasificados
  - Medir tasa de acierto de enrichment (MB/Discogs)
  - Dataset futuro para few-shot / fine-tuning
"""

import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

from mpc.config import PROJECT_DIR

logger = logging.getLogger("mpc.acquisition.classifier_log")

_LOG_PATH = os.getenv("CLASSIFIER_LOG_PATH", str(PROJECT_DIR / "cache" / "classifier_log.jsonl"))
_lock = threading.Lock()


def log_classification(row: Dict[str, Any], path: Optional[str] = None) -> None:
    """Appendea una fila JSONL. Nunca levanta excepción al caller."""
    target = path or _LOG_PATH
    try:
        row = {"ts": int(time.time()), **row}
        with _lock:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.debug("classifier_log write failed: %s", e)

# mpc/utils/ytdlp_updater.py
# -*- coding: utf-8 -*-
"""
Auto-update de yt-dlp con cache de 24h.

Detecta el método de instalación (brew / pip venv / standalone) y usa el
comando apropiado. Re-verifica la versión post-update para confirmar que
el binario que usa el pipeline realmente quedó actualizado.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

_CHECK_INTERVAL_SEC = 24 * 60 * 60  # 24 horas
_STALE_DAYS = 60  # si versión es más vieja que esto → update


def _cache_path() -> Path:
    from mpc.config import PROJECT_DIR
    return Path(PROJECT_DIR) / "cache" / "yt_dlp_last_check.txt"


def _last_check_ts() -> float:
    p = _cache_path()
    if not p.exists():
        return 0.0
    try:
        return float(p.read_text().strip())
    except (ValueError, OSError):
        return 0.0


def _touch_check() -> None:
    p = _cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(str(time.time()))
    except OSError:
        pass


def _resolve_ytdlp_bin() -> str:
    """Encuentra el binario yt-dlp que el pipeline va a invocar."""
    env_bin = os.getenv("YTDLP_BIN") or "yt-dlp"
    resolved = shutil.which(env_bin)
    return resolved or env_bin


def _all_ytdlp_installs() -> list:
    """Retorna lista deduplicada de paths a yt-dlp encontrados en PATH."""
    env_bin = os.getenv("YTDLP_BIN") or "yt-dlp"
    try:
        r = subprocess.run(
            ["which", "-a", env_bin],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            paths = []
            seen = set()
            for line in r.stdout.strip().split("\n"):
                p = line.strip()
                if not p or p in seen:
                    continue
                # Resolver symlinks para deduplicar
                real = os.path.realpath(p)
                if real in seen:
                    continue
                seen.add(p)
                seen.add(real)
                paths.append(p)
            return paths
    except Exception:
        pass
    return [_resolve_ytdlp_bin()]


def _get_version(bin_path: str) -> Optional[str]:
    try:
        r = subprocess.run(
            [bin_path, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _version_age_days(version: str) -> Optional[int]:
    """Parsea 'YYYY.MM.DD' y retorna días desde ese release. None si no parsea."""
    m = re.match(r"(\d{4})\.(\d{2})\.(\d{2})", version)
    if not m:
        return None
    try:
        d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return (datetime.now() - d).days
    except ValueError:
        return None


def _detect_install_method(bin_path: str) -> str:
    """Retorna 'brew', 'pip', o 'standalone'."""
    if not bin_path:
        return "standalone"
    p = bin_path.lower()
    if "/homebrew/" in p or "/linuxbrew/" in p:
        return "brew"
    if ".venv/" in p or "/site-packages/" in p or "/lib/python" in p:
        return "pip"
    # Fallback: chequear si es un entry_points de pip
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "show", "yt-dlp"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and "Location:" in r.stdout:
            return "pip"
    except Exception:
        pass
    return "standalone"


def _run(cmd: list, timeout: int = 120) -> Tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.returncode == 0, (r.stdout + r.stderr).strip())
    except subprocess.TimeoutExpired:
        return (False, "timeout")
    except FileNotFoundError:
        return (False, f"command not found: {cmd[0]}")


def _update_brew(quiet: bool) -> bool:
    ok, out = _run(["brew", "upgrade", "yt-dlp"])
    if not ok:
        # "already up-to-date" también es OK
        if "already installed" in out.lower() or "up-to-date" in out.lower():
            return True
        if not quiet:
            print(f"   ⚠️  brew upgrade falló: {out[:200]}", flush=True)
    return ok


def _update_pip(quiet: bool) -> bool:
    ok, out = _run([
        sys.executable, "-m", "pip", "install", "--upgrade",
        "--quiet", "--disable-pip-version-check", "yt-dlp",
    ])
    if not ok and not quiet:
        print(f"   ⚠️  pip upgrade falló: {out[:200]}", flush=True)
    return ok


def _update_standalone(bin_path: str, quiet: bool) -> bool:
    # yt-dlp puede auto-actualizarse
    ok, out = _run([bin_path, "-U"])
    if not ok and not quiet:
        print(f"   ⚠️  self-update falló: {out[:200]}", flush=True)
    return ok


def ensure_fresh_ytdlp(quiet: bool = False) -> None:
    """Verifica versión de TODOS los yt-dlp en PATH; si alguno es stale,
    actualiza con el método correcto. Cache 24h."""
    if time.time() - _last_check_ts() < _CHECK_INTERVAL_SEC:
        return

    installs = _all_ytdlp_installs()
    if not installs:
        if not quiet:
            print("   ⚠️  yt-dlp no disponible en PATH", flush=True)
        _touch_check()
        return

    all_fresh = True
    updated_any = False
    methods_attempted = set()

    for bin_path in installs:
        current_ver = _get_version(bin_path)
        if current_ver is None:
            continue
        age_days = _version_age_days(current_ver)
        if age_days is None or age_days < _STALE_DAYS:
            if not quiet and len(installs) > 1:
                print(f"🔄 {bin_path}: {current_ver} OK ({age_days}d)", flush=True)
            elif not quiet:
                print(f"🔄 yt-dlp {current_ver} OK ({age_days}d)", flush=True)
            continue

        all_fresh = False
        method = _detect_install_method(bin_path)
        if method in methods_attempted:
            continue  # no repetir mismo método (ej. 2 bins misma install)
        methods_attempted.add(method)

        if not quiet:
            print(f"🔄 {bin_path}: {current_ver} tiene {age_days}d → {method} update...",
                  flush=True)
        ok = False
        if method == "brew":
            ok = _update_brew(quiet)
        elif method == "pip":
            ok = _update_pip(quiet)
        else:
            ok = _update_standalone(bin_path, quiet)

        new_ver = _get_version(bin_path)
        if new_ver and new_ver != current_ver:
            if not quiet:
                print(f"   ✅ {current_ver} → {new_ver}", flush=True)
            updated_any = True
        elif not ok and not quiet:
            print(f"   ⚠️  update falló, sigue en {current_ver}", flush=True)

    if all_fresh or updated_any:
        _touch_check()
    # Si nada se actualizó pero hay stale → re-intenta próxima corrida

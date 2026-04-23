# mpc/curator/fixers/_file_ops.py
# -*- coding: utf-8 -*-
"""
Operaciones de filesystem compartidas por los fixers. Maneja el caso de
filesystems case-insensitive (APFS default en macOS) con rename 2-step.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple


def rename_with_2step_fallback(current: Path, target: Path) -> Tuple[bool, Path, str]:
    """
    Rename robusto: funciona en filesystems case-insensitive o con diferencias
    de Unicode normalization (NFC vs NFD).

    Retorna (success, final_path, error_message).
    - success=True si el rename aplicó (o no era necesario)
    - final_path: path efectivo del archivo después de la operación
    - error_message: vacío si success, descripción si no
    """
    if current == target:
        return True, current, ""

    if not current.exists():
        return False, current, f"source inexistente: {current}"

    try:
        is_same_file = target.exists() and current.samefile(target)
    except OSError:
        is_same_file = False

    if target.exists() and not is_same_file:
        return False, current, f"target existe (distinto archivo): {target}"

    try:
        if is_same_file:
            tmp = current.with_name(current.name + ".mp_rename.tmp")
            os.rename(str(current), str(tmp))
            os.rename(str(tmp), str(target))
        else:
            os.rename(str(current), str(target))
        return True, target, ""
    except OSError as e:
        return False, current, f"rename error: {e}"

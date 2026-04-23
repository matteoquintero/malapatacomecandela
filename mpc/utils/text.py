# mpc/utils/text.py
# -*- coding: utf-8 -*-
"""
Utilidades compartidas de normalización de texto.
Usado por request_to_csv, pipeline_music y spotify_to_csv.
"""

import re
import unicodedata
from typing import Optional

# ── Normalización base ────────────────────────────────────────────────────────

_NUM_WORDS_ES = {
    "un": 1, "una": 1, "uno": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "dieciséis": 16, "diecisiete": 17, "dieciocho": 18,
    "diecinueve": 19, "veinte": 20, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50,
}

LOWER_EXCEPTIONS = {
    "de", "del", "la", "las", "el", "los", "y", "o", "u", "en", "con",
    "por", "para", "a", "al", "un", "una", "uno", "unos", "unas",
    "the", "of", "and", "feat.", "ft.",
}


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    )


# macOS/APFS permite ? y " en filenames — los mantenemos para preservar títulos
# (ej. "¿por qué?"). Si se sincroniza a Windows, fix-metadata puede extenderse
# con un flag estricto.
_FS_RESERVED = set('/\\:*<>|')


def sanitize_filename_component(s: str) -> str:
    """
    SSOT: sanitizer único para metadatos consistentes en BD, tag y filename.

    Orden de operaciones:
      1. Title-case (conserva siglas como NG, FANIA, DJ y minúsculas como de/la/el/y)
      2. Reemplaza caracteres reservados por filesystem (/ \\ : * < > |) con ' - '
      3. Colapsa whitespace múltiple y separadores ' - ' duplicados
      4. Normaliza a Unicode NFC (precompuesto) — evita mismatches con NFD de macOS

    Preserva unicode/acentos.
    """
    if not s:
        return ""
    s = title_case_keep_caps(s)
    out = []
    for c in s:
        if c in _FS_RESERVED:
            out.append(" - ")
        else:
            out.append(c)
    result = "".join(out)
    result = re.sub(r"\s+", " ", result)
    result = re.sub(r"(\s*-\s*){2,}", " - ", result)
    result = result.strip(" -")
    # Normalizar a NFC — fix para comparaciones contra filenames NFD de macOS
    return unicodedata.normalize("NFC", result)


def nfc(s: str) -> str:
    """Normaliza string a Unicode NFC. Helper para comparaciones robustas."""
    return unicodedata.normalize("NFC", s or "")


def canonical_filename(artist: str, title: str, ext: str) -> str:
    """Nombre canónico garantizado consistente entre pipeline y fixers."""
    a = sanitize_filename_component(artist)
    t = sanitize_filename_component(title)
    return f"{a} - {t}{ext}"


def normalize_spaces(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s.strip())


def simp(s: str) -> str:
    """
    Normalización para deduplicación: minúsculas, sin acentos, sin puntuación.
    Compatible con la función 'simp' de request_to_csv.py y spotify_to_csv.py.
    """
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def simp_pipeline(s: str) -> str:
    """
    Variante usada en pipeline_music.py (_simp_text): conserva guiones.
    """
    s = strip_accents(s or "").lower().strip()
    s = re.sub(r"[^\w\s-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


_TITLE_STOPWORDS = {"en", "la", "el", "de", "y", "a", "los", "las", "the", "of", "con", "del"}


def title_similarity(query: str, candidate: str) -> float:
    """Jaccard sobre tokens: qué fracción del query está cubierta por el candidato."""
    q = {t for t in simp_pipeline(query).split() if t and t not in _TITLE_STOPWORDS}
    c = {t for t in simp_pipeline(candidate).split() if t}
    if not q:
        return 0.0
    return len(q & c) / len(q)


def key_pair(artist: str, title: str) -> str:
    return f"{simp(artist)}|{simp(title)}"


def norm_key(artist: str, title: str) -> str:
    """Alias de key_pair para compatibilidad con pipeline_music."""
    return f"{simp_pipeline(artist)}|{simp_pipeline(title)}"


def sanitize_filename(text: str) -> str:
    """Normaliza nombre de archivo: Title Case, sin chars especiales."""
    if not text:
        return text
    # NO quitar acentos - solo chars que crean carpetas
    # Quitar caracteres inválidos para文件名: < > : " / \ | ? * + #
    s = re.sub(r'[<>:"/\\|?*+#]', "", text)
    # Quitar comillas simples y dobles
    s = re.sub(r"['\"]", "", s)
    # Quitar paréntesis y corchetes - podem crear carpetas
    s = re.sub(r"[\[\]()]", "", s)
    # Quitar signos ¿ ¡ (no tildes)
    s = re.sub(r"[¿¡!]", "", s)
    # Title case (conserva mayúsculas de siglas)
    s = title_case_keep_caps(s)
    # Espacios múltiples a uno
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _cap_first_letter(w: str) -> str:
    """Lowercase + capitaliza la primera LETRA real, saltando puntuación inicial.
    Ej: '¡cubanismo!' → '¡Cubanismo!', '(live)' → '(Live)', '¿por?' → '¿Por?'."""
    w = w.lower()
    for i, c in enumerate(w):
        if c.isalpha():
            return w[:i] + c.upper() + w[i + 1:]
    return w


def title_case_keep_caps(text: str) -> str:
    text = normalize_spaces(text)
    if not text:
        return text
    out = []
    for i, w in enumerate(text.split(" ")):
        if not w:
            out.append(w)
            continue
        if w.isupper() and len(w) > 1:   # siglas: FANIA, NG, DJ
            out.append(w)
            continue
        base = w.lower()
        if i > 0 and base in LOWER_EXCEPTIONS:
            out.append(base)
        else:
            out.append(_cap_first_letter(w))
    return " ".join(out)


# ── Extracción de cantidad ─────────────────────────────────────────────────────

def _word_to_num_es(token: str) -> Optional[int]:
    return _NUM_WORDS_ES.get(strip_accents(token.lower()))


def extract_count(user_text: str) -> Optional[int]:
    """
    Extrae un número de un texto en español/inglés.
    Entiende: '2', 'dos', 'unas 5', 'entre 5 y 8', 'al menos 8', etc.
    """
    t = user_text.strip()
    t_norm = strip_accents(t.lower())

    for pat in [
        r"\bentre\s+(\d{1,2})\s+y\s+(\d{1,2})\b",
        r"\bde\s+(\d{1,2})\s+a\s+(\d{1,2})\b",
        r"\b(\d{1,2})\s*-\s*(\d{1,2})\b",
    ]:
        m = re.search(pat, t_norm)
        if m:
            n = max(int(m.group(1)), int(m.group(2)))
            if 1 <= n <= 50:
                return n

    for pat in [
        r"\b(al\s+menos|por\s+lo\s+menos|minimo|mínimo)\s+(\d{1,2})\b",
        r"\b(hasta|maximo|máximo)\s+(\d{1,2})\b",
        r"\b(unas|unos|como|cerca\s+de|aprox(?:imadamente)?)\s+(\d{1,2})\b",
    ]:
        m = re.search(pat, t_norm)
        if m:
            n = int(m.group(2))
            if 1 <= n <= 50:
                return n

    m = re.search(r"\b(\d{1,2})\b", t_norm)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 50:
            return n

    for tok in re.findall(r"[a-záéíóúñ]+", t_norm):
        n = _word_to_num_es(tok)
        if n and 1 <= n <= 50:
            return n

    return None

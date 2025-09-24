#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import os
import sys
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(PROJECT_DIR, ".env"))
except Exception:
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_MANIFESTS = [
    os.getenv("MANIFEST_FILE", os.path.join(
        PROJECT_DIR, "cache/manifest.csv")),
    os.path.join(PROJECT_DIR, "cache/manifest.csv"),
    os.path.expanduser("~/.mala_pata/manifest.csv"),
    os.path.expanduser("~/.mala_pata/manifest"),
]

DEFAULT_MUSIC_ROOT = os.getenv(
    "LIB_BASE_DIR", os.path.expanduser("~/Music/mala_pata_come_candela"))

# ---------- utilidades de paths/normalización ----------


def expand(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p)) if p else p


def simplify(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = "".join(c for c in unicodedata.normalize(
        "NFD", s) if unicodedata.category(c) != "Mn")
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s, flags=re.UNICODE)
    return s


def basename_simplified(path: str) -> str:
    return simplify(os.path.basename(path or ""))


def autodetect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", "\t", ";", "|"])
        return dialect.delimiter
    except Exception:
        return "\t"

# ---------- localizar manifest ----------


def find_manifest(path_arg: Optional[str]) -> str:
    if path_arg:
        p = expand(path_arg)
        if os.path.exists(p):
            return p
        print(f"❌ No se encontró el manifest en: {p}")
        sys.exit(1)
    for p in DEFAULT_MANIFESTS:
        if os.path.exists(p):
            return p
    print("❌ No se encontró manifest en rutas por defecto:")
    for p in DEFAULT_MANIFESTS:
        print("   -", p)
    sys.exit(1)

# ---------- leer/escribir manifest ----------


def read_rows(path: str) -> Tuple[List[Dict], List[str], str]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delim = autodetect_delimiter(sample)
        reader = csv.DictReader(f, delimiter=delim)
        rows = list(reader)
        headers = reader.fieldnames or []
    if rows is None:
        rows = []
    return rows, headers, delim


def write_rows(path: str, headers: List[str], rows: List[Dict], delim: str):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=delim)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def resolve_columns(headers: List[str]) -> Dict[str, Optional[str]]:
    norm = {h: simplify(h) for h in headers}

    def find_one(candidates):
        for h, nh in norm.items():
            for cand in candidates:
                if cand in nh:
                    return h
        return None
    artist_col = find_one(["artist"])
    title_col = find_one(["title", "track", "song"])
    genre_col = find_one(["genre", "genero", "genre_slug"])
    filepath_col = find_one(
        ["filepath", "fullpath", "file_path", "full_path", "path", "location"])
    return {"artist": artist_col, "title": title_col, "genre": genre_col, "filepath": filepath_col}

# ---------- búsqueda en disco ----------


def find_files_by_filename(root: str, filename: str, debug: bool = False) -> List[str]:
    """
    Busca en el árbol 'root' cualquier archivo cuyo basename normalizado
    coincida con 'filename' normalizado.
    """
    target = simplify(filename)
    found = []
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if simplify(fn) == target:
                full = os.path.join(dirpath, fn)
                found.append(full)
                if debug:
                    print("   🔎 match FS:", full)
    return found


def parse_artist_title_from_filename(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Intenta parsear 'Artista - Título.ext' → (Artista, Título)
    Usa la ÚLTIMA ocurrencia de ' - ' para tolerar 'A - B - C'.
    """
    base = os.path.splitext(os.path.basename(filename))[0]
    if " - " in base:
        artist, title = base.rsplit(" - ", 1)
        return artist.strip(), title.strip()
    return None, None

# ---------- matching de filas ----------


def match_row_by_fields(row: Dict, cols: Dict[str, Optional[str]],
                        artist_s: Optional[str], title_s: Optional[str],
                        genre_s: Optional[str], filename_s: Optional[str],
                        filepath_s: Optional[str]) -> bool:
    a = simplify(row.get(cols["artist"] or "", "")) if cols["artist"] else ""
    t = simplify(row.get(cols["title"] or "", "")) if cols["title"] else ""
    g = simplify(row.get(cols["genre"] or "", "")) if cols["genre"] else ""
    fp_raw = row.get(cols["filepath"] or "", "") if cols["filepath"] else ""
    fp = simplify(fp_raw)
    fn = basename_simplified(fp_raw)

    ok = True
    if artist_s is not None:
        ok = ok and (a == artist_s)
    if title_s is not None:
        ok = ok and (t == title_s)
    if genre_s is not None:
        ok = ok and (g == genre_s)
    if filename_s is not None:
        ok = ok and (fn == filename_s)
    if filepath_s is not None:
        ok = ok and (fp == filepath_s)
    return ok


def match_row_by_filename_only(row: Dict, cols: Dict[str, Optional[str]], filename: str) -> bool:
    fp_col = cols["filepath"]
    if not fp_col:
        return False
    fp_raw = row.get(fp_col, "") or ""
    return basename_simplified(fp_raw) == basename_simplified(filename)


def match_row_by_artist_title_guess(row: Dict, cols: Dict[str, Optional[str]],
                                    artist_guess: Optional[str], title_guess: Optional[str]) -> bool:
    a = simplify(row.get(cols["artist"] or "", "")) if cols["artist"] else ""
    t = simplify(row.get(cols["title"] or "", "")) if cols["title"] else ""
    return (artist_guess is not None and simplify(artist_guess) == a) and \
           (title_guess is not None and simplify(title_guess) == t)

# ---------- main ----------


def main():
    ap = argparse.ArgumentParser(
        description="Borra una canción (archivo + fila) del manifest, buscando también en disco por filename.")
    ap.add_argument("--manifest", "-m",
                    help="Ruta al manifest (default: <proyecto>/cache/manifest.csv o MANIFEST_FILE en .env)")
    ap.add_argument("--music-root", default=DEFAULT_MUSIC_ROOT,
                    help=f"Raíz de tu librería (default: {DEFAULT_MUSIC_ROOT})")

    # modos de selección
    ap.add_argument("--artist", help="Nombre del artista")
    ap.add_argument("--title", help="Título de la canción")
    ap.add_argument("--genre", help="Género (opcional)")
    ap.add_argument(
        "--filename", help="Nombre de archivo (sin ruta), p.ej. 'NG La Banda - Santa Palabra.mp3'")
    ap.add_argument(
        "--filepath", help="Ruta completa del archivo a borrar (coincidencia exacta)")

    ap.add_argument("--all", action="store_true",
                    help="Borrar todas las coincidencias (default: solo la primera)")
    ap.add_argument("--debug", action="store_true",
                    help="Mostrar detalles de matching")

    args = ap.parse_args()

    manifest_path = find_manifest(args.manifest)
    rows, headers, delim = read_rows(manifest_path)
    cols = resolve_columns(headers)

    if args.debug:
        print("🧭 Manifest:", manifest_path)
        print("🧩 Delimiter detectado:", repr(delim))
        print("🗂️ Headers:", headers)
        print("🔗 Columnas resueltas:", cols)

    # Normalización de criterios
    artist_s = simplify(args.artist) if args.artist else None
    title_s = simplify(args.title) if args.title else None
    genre_s = simplify(args.genre) if args.genre else None
    filename_s = simplify(args.filename) if args.filename else None
    filepath_s = simplify(args.filepath) if args.filepath else None

    if not any([args.artist and args.title, args.filepath, args.filename]):
        print("❌ Debes indicar (artist + title) o bien --filepath o bien --filename")
        ap.print_help()
        sys.exit(1)

    # 1) Resolver archivos a borrar (filesystem-first si viene filename)
    files_to_delete: List[str] = []
    if args.filepath:
        files_to_delete.append(expand(args.filepath))
    elif args.filename:
        # Buscar en disco primero
        root = expand(args.music_root)
        if args.debug:
            print("📚 Buscando en disco bajo:", root)
        candidates = find_files_by_filename(
            root, args.filename, debug=args.debug)
        if not candidates:
            if args.debug:
                print(
                    "   ⚠️ No se halló el filename en disco. Intento matchear por manifest igual…")
        files_to_delete.extend(candidates)

    # 2) Seleccionar filas a eliminar en el manifest
    kept: List[Dict] = []
    removed: List[Dict] = []
    filepaths_from_manifest: List[str] = []

    # Si ya descubrimos archivos exactos en el FS, usarlos para decidir filas;
    # si no, intentar matching por criteria (artist/title/filename/genre).
    target_filenames_norm = set(basename_simplified(p)
                                for p in files_to_delete)

    # Si no encontramos en FS pero recibimos filename, aún podemos borrar la fila por artist/title guess
    artist_guess, title_guess = (None, None)
    if args.filename:
        artist_guess, title_guess = parse_artist_title_from_filename(
            args.filename)

    for i, row in enumerate(rows):
        match = False

        # (a) si hay filepath exacto
        if filepath_s is not None:
            match = match_row_by_fields(
                row, cols, None, None, None, None, filepath_s)

        # (b) si hay filename y ya encontramos archivos: comparamos basenames
        elif target_filenames_norm:
            fp_col = cols["filepath"]
            fp_raw = row.get(fp_col, "") if fp_col else ""
            if basename_simplified(fp_raw) in target_filenames_norm:
                match = True

        # (c) si hay filename pero NO encontramos en FS: intenta por artist/title parseados del filename
        elif args.filename and (artist_guess or title_guess):
            if match_row_by_artist_title_guess(row, cols, artist_guess, title_guess):
                match = True

        # (d) else: usa matching por artist/title/genre/filename normal (manifest)
        elif any([artist_s, title_s, genre_s, filename_s]):
            match = match_row_by_fields(
                row, cols, artist_s, title_s, genre_s, filename_s, None)

        if match:
            if not args.all and removed:
                kept.append(row)
                continue
            removed.append(row)
            fp_col = cols["filepath"]
            if fp_col and row.get(fp_col):
                filepaths_from_manifest.append(row.get(fp_col))
            if args.debug:
                a = row.get(cols["artist"] or "",
                            "?") if cols["artist"] else "?"
                t = row.get(cols["title"] or "", "?") if cols["title"] else "?"
                print(
                    f"✓ MATCH fila {i+1}: {a} — {t} | {row.get(cols['filepath'] or '', '')}")
        else:
            kept.append(row)

    # 3) Unir rutas finales a borrar: FS encontrados + los del manifest
    for fp in filepaths_from_manifest:
        if fp and fp not in files_to_delete:
            files_to_delete.append(fp)

    # Si no tenemos nada que borrar ni filas que remover → informar
    if not removed and not files_to_delete:
        print("⚠️ No se encontró ninguna coincidencia.")
        if args.debug:
            if args.filename:
                print("   filename(norm):", filename_s or simplify(args.filename))
            if cols["filepath"]:
                print(
                    "   (nota) muchas filas antiguas pueden tener filepath vacío en el manifest.")
        sys.exit(1)

    # 4) Borrar archivos físicos (si existen)
    deleted_files = 0
    for fp in files_to_delete:
        try:
            real_fp = expand(fp)
            if os.path.exists(real_fp):
                os.remove(real_fp)
                deleted_files += 1
                print(f"🗑️ Archivo eliminado: {real_fp}")
            else:
                print(f"ℹ️ Archivo no existe (ya borrado?): {real_fp}")
        except Exception as e:
            print(f"⚠️ No se pudo eliminar {fp}: {e}")

    # 5) Reescribir manifest sin las filas borradas (si hubo)
    if removed:
        write_rows(manifest_path, headers, kept, delim)
        print(f"✅ {len(removed)} fila(s) eliminada(s) de {manifest_path}")
        for r in removed:
            a = r.get(cols["artist"] or "", "?") if cols["artist"] else "?"
            t = r.get(cols["title"] or "", "?") if cols["title"] else "?"
            g = r.get(cols["genre"] or "", "?") if cols["genre"] else "?"
            print(f"   - {a} — {t}  [{g}]")
    else:
        print("ℹ️ No se eliminó ninguna fila del manifest (no hubo match), pero sí archivos." if deleted_files else
              "ℹ️ No se eliminó ninguna fila ni archivos.")


if __name__ == "__main__":
    main()

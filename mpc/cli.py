# mpc/cli.py
# -*- coding: utf-8 -*-
"""
CLI unificado de Mala Pata Come Candela.
Punto de entrada: mala_pata.py

Subcomandos:
  create   — genera canciones.csv desde lenguaje natural, Spotify o género directo
  download — ejecuta el pipeline (come-candela)
  delete   — elimina una canción del manifest y disco
  list     — muestra canciones.csv actual
  genres   — lista los géneros disponibles

Backwards compat: si el primer argumento no es un subcomando conocido,
se asume 'create'.
"""

import argparse
import logging
import os
import subprocess
import sys
from typing import List, Optional

from mpc.config import get_config, setup_logging, PROJECT_DIR
from mpc.catalog.genres import ALL_SLUGS, DIRECT_GENRES, AFROLATINO_SLUGS, GENRE_COMMAND

logger = logging.getLogger("mpc.cli")

KNOWN_SUBCOMMANDS = {"create", "download", "delete", "list", "genres"}


# ─────────────────────────────────────────────────────────────────────────────
# SUBCOMANDO: create
# ─────────────────────────────────────────────────────────────────────────────

def cmd_create(args: argparse.Namespace):
    """Genera canciones.csv desde una fuente (NL, Spotify, artista o álbum)."""
    cfg = get_config()

    # ── Importaciones lazy (solo cuando se ejecuta create) ────────────────────
    from mpc.planner.intent import (
        classify_request, is_blocked, blocked_message, detect_direct_genre
    )
    from mpc.planner.llm import llm_plan
    from mpc.sources.openai_source import get_openai_client, find_real_songs
    from mpc.sources.discogs import get_discogs_client
    from mpc.sources.spotify_client import (
        get_spotify_client_oauth, get_spotify_client_credentials,
        fetch_playlist_tracks, fetch_album_tracks, search_artist_tracks,
        detect_source_type, parse_playlist_id, parse_album_id,
    )
    from mpc.builders.playlist import pick_playlist, pick_artist_playlist
    from mpc.builders.album import build_album_csv
    from mpc.utils.csv_io import write_csv, append_csv
    from mpc.utils.text import key_pair, title_case_keep_caps

    out_path = args.out or cfg.default_csv
    if not os.path.isabs(out_path):
        out_path = os.path.join(str(PROJECT_DIR), out_path)

    # ── Inicializar clientes ──────────────────────────────────────────────────
    openai_client, openai_model = get_openai_client(cfg.openai_api_key, cfg.openai_model)
    discogs_client = get_discogs_client(cfg.discogs_token)
    sp_creds = get_spotify_client_credentials(cfg.spotify_client_id, cfg.spotify_client_secret)

    # ── Modo Spotify ──────────────────────────────────────────────────────────
    if args.spotify:
        _create_from_spotify(args, cfg, out_path, title_case_keep_caps, key_pair,
                             write_csv, append_csv)
        return

    # ── Determinar query / género directo ─────────────────────────────────────
    query = args.query or ""
    genre_arg = args.genre

    # Detectar si el género es "directo" (no afrolatino, no necesita clasificador)
    _, direct_genre = detect_direct_genre(query, genre_arg)
    forced_genre = genre_arg  # cualquier género (afrolatino o directo) forzado por CLI

    # ── Dry run ───────────────────────────────────────────────────────────────
    if args.dry_run:
        intent = classify_request(query)
        plan = llm_plan(openai_client, openai_model, query,
                        direct_genre=forced_genre,
                        force_curator=(intent["mode"] == "complex"))
        if args.count:
            plan["count"] = args.count
        if args.artist:
            plan["artist"] = args.artist
        if args.album:
            plan["album"] = args.album
        print("\nPlan detectado:")
        print(f"  task:    {plan.get('task')}")
        print(f"  genre:   {plan.get('genre') or '—'}")
        print(f"  count:   {plan.get('count')}")
        print(f"  artist:  {plan.get('artist') or '—'}")
        print(f"  album:   {plan.get('album') or '—'}")
        print(f"  substyle:{plan.get('substyle') or '—'}")
        print(f"  mode:    {intent['mode']}")
        print("\n[DRY RUN] Nada fue escrito.\n")
        return

    # ── Clasificar intención ──────────────────────────────────────────────────
    print("🔎 Analizando intención…")
    intent = classify_request(query)
    force_llm = (intent["mode"] == "complex")

    print(f"   → modo={intent['mode']} | kind={intent['kind']} | "
          f"count={intent['count'] or '—'} | artist_hint={intent['artist_hint'] or '—'}")

    print("🔮 Los oráculos interpretan tu pedido…")
    plan = llm_plan(
        openai_client, openai_model, query,
        direct_genre=forced_genre or direct_genre,
        force_curator=force_llm,
    )

    # Ajustes CLI override > LLM
    if args.count:
        plan["count"] = args.count
    if args.artist:
        plan["artist"] = args.artist
    if args.album:
        plan["album"] = args.album
    if forced_genre:
        plan["genre"] = forced_genre
    if args.style:
        plan["substyle"] = args.style

    if intent["kind"] == "single" and plan.get("task") != "single":
        plan["task"] = "single"
        plan["count"] = 1
    if intent["artist_hint"] and not plan.get("artist"):
        plan["artist"] = intent["artist_hint"]

    # Default substyle para salsa dura
    if plan.get("task") == "playlist" and not plan.get("substyle"):
        g = (plan.get("genre") or "").lower()
        plan["substyle"] = "underground" if "salsa_dura_clasica" in g else None

    print(f"🧠 Plan: task={plan.get('task')} | genre={plan.get('genre') or '—'} | "
          f"count={plan.get('count')} | artist={plan.get('artist') or '—'} | "
          f"substyle={plan.get('substyle') or '—'}")

    # ── Blocklist ─────────────────────────────────────────────────────────────
    if plan.get("artist") and is_blocked(plan["artist"]):
        print(blocked_message(plan["artist"]))
        return

    # ── Construir lista ────────────────────────────────────────────────────────
    import time as _time
    rows: List = []
    _t_build = _time.time()

    if plan["task"] == "album" and plan.get("artist") and plan.get("album"):
        print(f"📜 Buscando: {plan['artist']} — {plan['album']}")
        rows = build_album_csv(plan["artist"], plan["album"])
        if not rows:
            print("   ⚠️ El pergamino está vacío (álbum no encontrado en MusicBrainz)")

    else:
        count = int(plan.get("count") or 10)
        artist = (plan.get("artist") or "").strip() or None
        genre = plan.get("genre") or None

        if artist and not plan.get("album"):
            print(f"🎭 Playlist del artista: {artist}  ({count} temas)")
            rows = pick_artist_playlist(discogs_client, artist, count, genre=genre)
        else:
            g = (genre or "salsa_dura_clasica").lower()
            substyle = plan.get("substyle")
            print(f"🎶 Playlist de género: {g}  ({count} temas, {substyle or 'aleatorio'})")
            rows = pick_playlist(discogs_client, g, substyle, count)

    _build_secs = _time.time() - _t_build

    # ── Fallback si no hay resultados ─────────────────────────────────────────
    if not rows and plan.get("artist"):
        print("🔍 No encontrado en MB/Discogs, buscando en Spotify…")
        rows = search_artist_tracks(sp_creds, plan["artist"],
                                    int(plan.get("count") or 10), plan.get("genre"))

    if not rows and plan.get("artist"):
        print("🤖 Spotify vacío, consultando OpenAI por canciones reales…")
        rows = find_real_songs(
            openai_client, openai_model,
            plan["artist"], int(plan.get("count") or 10),
            plan.get("genre"), query,
        )

    if not rows:
        print("❌ No se pudo generar el CSV. Intenta con otro pedido o verifica las APIs.")
        sys.exit(1)

    # ── Dedupe final ──────────────────────────────────────────────────────────
    target = int(plan.get("count") or len(rows))
    final: List = []
    seen: set = set()
    for r in rows:
        k = key_pair(r["artist"], r["title"])
        if k in seen:
            continue
        seen.add(k)
        final.append(r)
        if len(final) >= target:
            break

    # ── Escribir CSV ──────────────────────────────────────────────────────────
    genre_for_csv = forced_genre if forced_genre else None
    if args.append:
        append_csv(final, out_path, genre=genre_for_csv)
        mode_str = "añadido a"
    else:
        write_csv(final, out_path, genre=genre_for_csv)
        mode_str = "grabado en"

    n = len(final)
    print(f"\n📜 El grimorio quedó {mode_str}: {os.path.basename(out_path)}  "
          f"({n} sello{'s' if n != 1 else ''} inscrito{'s' if n != 1 else ''})")
    print(f"   Tiempo de búsqueda: {_build_secs:.1f}s")
    print("🔥 Para desatar la llama: mala-pata download\n")

    # Resumen de fuentes
    from collections import Counter
    sources = Counter(r.get("source", "?") for r in final)
    print("   Fuentes:")
    for src, cnt_src in sorted(sources.items(), key=lambda x: -x[1]):
        bar = "█" * min(cnt_src, 20)
        print(f"     {src:<15} {cnt_src:>3}  {bar}")
    print()


def _create_from_spotify(args, cfg, out_path, title_case_keep_caps, key_pair,
                         write_csv, append_csv):
    """Flujo de create con --spotify URL."""
    from mpc.sources.spotify_client import (
        get_spotify_client_oauth,
        fetch_playlist_tracks, fetch_album_tracks,
        detect_source_type, parse_playlist_id, parse_album_id,
    )

    sp = get_spotify_client_oauth(
        cfg.spotify_client_id, cfg.spotify_client_secret,
        cfg.spotify_redirect_uri, cfg.spotify_token_cache,
    )
    if not sp:
        print("❌ Spotify no está configurado. Revisa SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en .env")
        sys.exit(1)

    source_type = args.type or detect_source_type(args.spotify)

    if source_type == "album":
        aid = parse_album_id(args.spotify)
        print("💿 Leyendo álbum de Spotify…")
        tracks = fetch_album_tracks(sp, aid, limit_count=args.count)
    else:
        pid = parse_playlist_id(args.spotify)
        print("🎧 Leyendo playlist de Spotify…")
        tracks = fetch_playlist_tracks(sp, pid, limit_count=args.count)

    # Dedupe
    seen: set = set()
    rows = []
    for t in tracks:
        k = key_pair(t["artist"], t["title"])
        if k in seen:
            continue
        seen.add(k)
        rows.append(t)

    # Formatear
    formatted = []
    for r in rows:
        artist_fmt = title_case_keep_caps(r["artist"])
        title_fmt = title_case_keep_caps(r["title"])
        album = r.get("album") or ""
        qov = f"{artist_fmt} {title_fmt} {album}".strip()
        formatted.append({
            "artist": artist_fmt,
            "title": title_fmt,
            "query_override": qov,
            "source": "spotify",
            "genre": args.genre or "",
        })

    if args.append:
        append_csv(formatted, out_path, genre=args.genre)
        mode_str = "añadido a"
    else:
        write_csv(formatted, out_path, genre=args.genre)
        mode_str = "grabado en"

    src_str = "álbum" if source_type == "album" else "playlist"
    n = len(formatted)
    print(f"✅ CSV {mode_str}: {out_path}  ({n} temas desde {src_str} Spotify)")
    if args.genre:
        print(f"   Género asignado: {args.genre}")
    print("🔥 Para descargar: mala-pata download\n")


# ─────────────────────────────────────────────────────────────────────────────
# SUBCOMANDO: download
# ─────────────────────────────────────────────────────────────────────────────

def cmd_download(args: argparse.Namespace):
    """Ejecuta el pipeline: CSV → YouTube → Clasifica → Descarga."""
    cfg = get_config()

    try:
        cfg.validate_for_download()
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    input_csv = args.input or cfg.default_csv
    output_csv = args.output or os.path.join(str(PROJECT_DIR), "out/log_descargas.csv")

    os.makedirs(os.path.dirname(output_csv), exist_ok=True)

    print(f"🔥 Iniciando pipeline…")
    print(f"   Input:  {input_csv}")
    print(f"   Output: {output_csv}")

    py = sys.executable
    pipeline_script = str(PROJECT_DIR / "scripts" / "pipeline_music.py")

    cmd = [py, pipeline_script, "--input", input_csv, "--output", output_csv]
    if args.dry_run:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n⚠️ Pipeline interrumpido.")
        sys.exit(130)


# ─────────────────────────────────────────────────────────────────────────────
# SUBCOMANDO: delete
# ─────────────────────────────────────────────────────────────────────────────

def cmd_delete(args: argparse.Namespace):
    """Elimina una canción del manifest y del disco."""
    py = sys.executable
    delete_script = str(PROJECT_DIR / "scripts" / "delete_song.py")
    cmd = [py, delete_script]
    if args.filename:
        cmd += ["--filename", args.filename]
    if args.artist:
        cmd += ["--artist", args.artist]
    if args.title:
        cmd += ["--title", args.title]
    if args.genre:
        cmd += ["--genre", args.genre]
    if getattr(args, "all", False):
        cmd += ["--all"]
    if getattr(args, "debug", False):
        cmd += ["--debug"]

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


# ─────────────────────────────────────────────────────────────────────────────
# SUBCOMANDO: list
# ─────────────────────────────────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace):
    """Muestra el contenido de canciones.csv."""
    from mpc.utils.csv_io import read_csv
    cfg = get_config()
    path = args.file or cfg.default_csv

    rows = read_csv(path)
    if not rows:
        print(f"📭 {path} está vacío o no existe.")
        return

    print(f"\n📋 {path}  ({len(rows)} canciones)\n")
    for i, r in enumerate(rows, 1):
        artist = r.get("artist", "?")
        title = r.get("title", "?")
        genre = r.get("genre", "")
        src = r.get("source", "")
        genre_str = f"  [{genre}]" if genre else ""
        src_str = f"  ({src})" if src else ""
        print(f"  {i:3}. {artist} — {title}{genre_str}{src_str}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# SUBCOMANDO: genres
# ─────────────────────────────────────────────────────────────────────────────

def cmd_genres(args: argparse.Namespace):
    """Lista los géneros disponibles."""
    print("\n🎵 Géneros afrolatinos (16):")
    for slug in AFROLATINO_SLUGS:
        cmd = GENRE_COMMAND[slug]
        print(f"   {slug:<30}  →  {cmd}")

    print("\n🎧 Géneros directos:")
    for slug in DIRECT_GENRES:
        cmd = GENRE_COMMAND[slug]
        print(f"   {slug:<30}  →  {cmd}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# PARSER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mala-pata",
        description="🔥 Mala Pata Come Candela — Sistema de música afrolatina",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  mala-pata create \"10 canciones de salsa dura underground\"\n"
            "  mala-pata create \"5 de Héctor Lavoe\" --style underground\n"
            "  mala-pata create --spotify https://open.spotify.com/playlist/XXX\n"
            "  mala-pata create --artist \"Ray Barretto\" --count 8\n"
            "  mala-pata create \"silvio rodriguez\" --genre nueva_trova\n"
            "  mala-pata create --dry-run \"algo complejo\"\n"
            "  mala-pata download\n"
            "  mala-pata list\n"
            "  mala-pata genres\n"
            "  mala-pata delete --filename \"Héctor Lavoe - El Cantante.mp3\"\n"
        ),
    )

    # Flags globales
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="-v = INFO, -vv = DEBUG")

    subparsers = parser.add_subparsers(dest="subcommand", metavar="SUBCOMANDO")

    # ── create ────────────────────────────────────────────────────────────────
    p_create = subparsers.add_parser(
        "create", help="Genera canciones.csv",
        description="Genera canciones.csv desde lenguaje natural, Spotify, artista o álbum.",
    )
    p_create.add_argument("query", nargs="?", default="",
                          help="Pedido en lenguaje natural, ej: '10 canciones de mambo'")
    p_create.add_argument("--spotify", metavar="URL",
                          help="Importar desde playlist/álbum de Spotify")
    p_create.add_argument("--type", choices=["playlist", "album"],
                          help="[Spotify] Forzar tipo de fuente")
    p_create.add_argument("-n", "--count", type=int,
                          help="Número de canciones [default: 10]")
    p_create.add_argument("-g", "--genre",
                          help=f"Forzar género (cualquiera de: {', '.join(ALL_SLUGS)})")
    p_create.add_argument("-a", "--artist",
                          help="Focalizar en un artista específico")
    p_create.add_argument("--album",
                          help="Obtener tracks de un álbum (requiere --artist)")
    p_create.add_argument("--style", choices=["underground", "comercial"],
                          help="Sesgo de selección")
    p_create.add_argument("--append", action="store_true",
                          help="Añadir al CSV existente en vez de sobreescribir")
    p_create.add_argument("--out", metavar="FILE",
                          help="CSV de salida [default: canciones.csv]")
    p_create.add_argument("--dry-run", action="store_true",
                          help="Mostrar el plan sin escribir nada")

    # ── download ──────────────────────────────────────────────────────────────
    p_dl = subparsers.add_parser(
        "download", help="Ejecuta el pipeline de descarga (≡ come-candela)",
        description="Procesa canciones.csv → busca YouTube → clasifica → descarga.",
    )
    p_dl.add_argument("--input", metavar="CSV",
                      help="CSV de entrada [default: canciones.csv]")
    p_dl.add_argument("--output", metavar="CSV",
                      help="Log de salida [default: out/log_descargas.csv]")
    p_dl.add_argument("--dry-run", action="store_true",
                      help="Mostrar qué se descargaría sin descargar")

    # ── delete ────────────────────────────────────────────────────────────────
    p_del = subparsers.add_parser(
        "delete", help="Elimina una canción del manifest y disco",
        description="Borra archivo físico y fila del manifest.",
    )
    p_del.add_argument("--filename",
                       help="Nombre de archivo, ej: 'Artista - Titulo.mp3'")
    p_del.add_argument("--artist", help="Nombre del artista")
    p_del.add_argument("--title", help="Título de la canción")
    p_del.add_argument("--genre", help="Género (opcional, para afinar búsqueda)")
    p_del.add_argument("--all", action="store_true",
                       help="Borrar todas las coincidencias")
    p_del.add_argument("--debug", action="store_true")

    # ── list ──────────────────────────────────────────────────────────────────
    p_list = subparsers.add_parser("list", help="Muestra canciones.csv")
    p_list.add_argument("file", nargs="?", help="CSV a listar [default: canciones.csv]")

    # ── genres ────────────────────────────────────────────────────────────────
    subparsers.add_parser("genres", help="Lista géneros disponibles")

    return parser


def main(argv: Optional[List[str]] = None):
    """Entry point principal."""
    if argv is None:
        argv = sys.argv[1:]

    # ── Backwards compat: si el primer arg no es subcomando conocido, es 'create' ──
    if argv and argv[0] not in KNOWN_SUBCOMMANDS and not argv[0].startswith("-"):
        argv = ["create"] + argv

    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    if not args.subcommand:
        parser.print_help()
        return

    dispatch = {
        "create": cmd_create,
        "download": cmd_download,
        "delete": cmd_delete,
        "list": cmd_list,
        "genres": cmd_genres,
    }
    dispatch[args.subcommand](args)


if __name__ == "__main__":
    main()

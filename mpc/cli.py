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

KNOWN_SUBCOMMANDS = {"create", "download", "audios", "videos", "delete", "list", "genres", "curator", "classifier-stats", "review-ambiguous", "replace-audio", "replace-video", "replace-thumbnail"}


# ─────────────────────────────────────────────────────────────────────────────
# SUBCOMANDO: create
# ─────────────────────────────────────────────────────────────────────────────


def cmd_create(args: argparse.Namespace):
    """Genera canciones.csv desde una fuente (NL, Spotify, artista o álbum)."""
    cfg = get_config()

    # ── Importaciones lazy (solo cuando se ejecuta create) ────────────────────
    from mpc.discovery.planner import (
        classify_request,
        is_blocked,
        blocked_message,
        detect_direct_genre,
    )
    from mpc.discovery.llm_planner import llm_plan
    from mpc.sources.openai_source import get_openai_client, find_real_songs
    from mpc.sources.discogs import get_discogs_client
    from mpc.sources.spotify_client import (
        get_spotify_client_oauth,
        get_spotify_client_credentials,
        fetch_playlist_tracks,
        fetch_album_tracks,
        search_artist_tracks,
        detect_source_type,
        parse_playlist_id,
        parse_album_id,
    )
    from mpc.discovery.assembler import (
        pick_playlist,
        pick_artist_playlist,
        build_album_csv,
    )
    from mpc.utils.csv_io import write_csv, append_csv
    from mpc.utils.text import key_pair, title_case_keep_caps

    out_path = args.out or cfg.default_csv
    if not os.path.isabs(out_path):
        out_path = os.path.join(str(PROJECT_DIR), out_path)

    # ── Inicializar clientes ──────────────────────────────────────────────────
    openai_client, openai_model = get_openai_client(
        cfg.openai_api_key, cfg.openai_model
    )
    discogs_client = get_discogs_client(cfg.discogs_token)
    sp_creds = get_spotify_client_credentials(
        cfg.spotify_client_id, cfg.spotify_client_secret
    )

    # ── Modo Spotify ──────────────────────────────────────────────────────────
    if args.spotify:
        _create_from_spotify(
            args, cfg, out_path, title_case_keep_caps, key_pair, write_csv, append_csv
        )
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
        plan = llm_plan(
            openai_client,
            openai_model,
            query,
            direct_genre=forced_genre,
            force_curator=(intent["mode"] == "complex"),
        )
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
    force_llm = intent["mode"] == "complex"

    print(
        f"   → modo={intent['mode']} | kind={intent['kind']} | "
        f"count={intent['count'] or '—'} | artist_hint={intent['artist_hint'] or '—'}"
    )

    print("🔮 Los oráculos interpretan tu pedido…")
    plan = llm_plan(
        openai_client,
        openai_model,
        query,
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

    print(
        f"🧠 Plan: task={plan.get('task')} | genre={plan.get('genre') or '—'} | "
        f"count={plan.get('count')} | artist={plan.get('artist') or '—'} | "
        f"substyle={plan.get('substyle') or '—'}"
    )

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
            print(
                f"🎶 Playlist de género: {g}  ({count} temas, {substyle or 'aleatorio'})"
            )
            rows = pick_playlist(discogs_client, g, substyle, count)

    _build_secs = _time.time() - _t_build

    # ── Fallback si no hay resultados ─────────────────────────────────────────
    if not rows and plan.get("artist"):
        print("🔍 No encontrado en MB/Discogs, buscando en Spotify…")
        rows = search_artist_tracks(
            sp_creds, plan["artist"], int(plan.get("count") or 10), plan.get("genre")
        )

    if not rows and plan.get("artist"):
        print("🤖 Spotify vacío, consultando OpenAI por canciones reales…")
        rows = find_real_songs(
            openai_client,
            openai_model,
            plan["artist"],
            int(plan.get("count") or 10),
            plan.get("genre"),
            query,
        )

    if not rows:
        print(
            "❌ No se pudo generar el CSV. Intenta con otro pedido o verifica las APIs."
        )
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
    print(
        f"\n📜 El grimorio quedó {mode_str}: {os.path.basename(out_path)}  "
        f"({n} sello{'s' if n != 1 else ''} inscrito{'s' if n != 1 else ''})"
    )
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


def _create_from_spotify(
    args, cfg, out_path, title_case_keep_caps, key_pair, write_csv, append_csv
):
    """Flujo de create con --spotify URL."""
    from mpc.sources.spotify_client import (
        get_spotify_client_oauth,
        fetch_playlist_tracks,
        fetch_album_tracks,
        detect_source_type,
        parse_playlist_id,
        parse_album_id,
    )

    sp = get_spotify_client_oauth(
        cfg.spotify_client_id,
        cfg.spotify_client_secret,
        cfg.spotify_redirect_uri,
        cfg.spotify_token_cache,
    )
    if not sp:
        print(
            "❌ Spotify no está configurado. Revisa SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en .env"
        )
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
        formatted.append(
            {
                "artist": artist_fmt,
                "title": title_fmt,
                "query_override": qov,
                "source": "spotify",
                "genre": args.genre or "",
            }
        )

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


def cmd_audios(args: argparse.Namespace):
    """Descarga archivos de audio (MP3) desde CSV o BD."""
    cfg = get_config()

    try:
        cfg.validate_for_download()
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Handle --curator: read from DB instead of CSV
    if args.curator:
        from mpc.library.repository import TrackRepository
        from mpc.curator.status import CuratorStatus

        db_path = str(PROJECT_DIR / "cache" / "library.db")
        repo = TrackRepository(db_path)

        tracks = (
            repo.by_curator_status(CuratorStatus.MISSING)
            + repo.by_curator_status(CuratorStatus.NEEDS_METADATA)
            + repo.by_curator_status(CuratorStatus.NEEDS_THUMBNAIL)
            + repo.by_curator_status(CuratorStatus.NEEDS_TAGS)
        )
        if not tracks:
            print("✅ No hay tracks marcadas por curator para procesar.")
            return

        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("artist,title\n")
            for t in tracks:
                f.write(f"{t['artist']},{t['title']}\n")
            input_csv = f.name

        print(f"📋 Procesando {len(tracks)} tracks de la BD (curator)...")
    elif getattr(args, "quality", False):
        # Re-descarga tracks con calidad bajo el umbral
        from mpc.library.repository import TrackRepository
        db_path = str(PROJECT_DIR / "cache" / "library.db")
        repo = TrackRepository(db_path)

        min_bitrate = getattr(args, "min_bitrate", 192)
        min_score = getattr(args, "min_score", 60)
        tracks = repo.low_quality_candidates(
            min_bitrate=min_bitrate, min_score=min_score,
        )
        if getattr(args, "limit", None):
            tracks = tracks[:args.limit]

        if not tracks:
            print(f"✅ No hay tracks bajo umbral (bitrate<{min_bitrate} o score<{min_score}).")
            return

        print(f"📋 {len(tracks)} tracks bajo umbral (bitrate<{min_bitrate} o score<{min_score})")

        if args.dry_run:
            for t in tracks:
                print(f"   [DRY-RUN] {t['artist']} - {t['title']} "
                      f"(br={t.get('bitrate_kbps','?')}k, score={t.get('audio_quality_score','?')})")
            print(f"\n[DRY-RUN] nada se borra. Usá --apply para ejecutar.")
            return

        # Backup de quality para comparar después
        backup = {
            t["track_id"]: {
                "score": t.get("audio_quality_score"),
                "bitrate": t.get("bitrate_kbps"),
                "filepath": t.get("filepath"),
            } for t in tracks
        }

        # Borrar MP3 y resetear BD para que el pipeline los trate como missing
        for t in tracks:
            fp = t.get("filepath") or ""
            if fp and os.path.isfile(fp):
                try:
                    os.remove(fp)
                except OSError as e:
                    print(f"   ⚠️  no se pudo borrar {fp}: {e}")
            from mpc.curator.status import CuratorStatus as _CS
            repo.update_curator_flags(
                t["track_id"],
                filepath="",
                curator_status=_CS.MISSING,
                status="pending",
            )

        # Escribir CSV temporal y disparar pipeline
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("artist,title\n")
            for t in tracks:
                f.write(f"{t['artist']},{t['title']}\n")
            input_csv = f.name
        print(f"🎵 Re-bajando {len(tracks)} tracks con nuevo scoring de calidad...")

        # Guardar backup para post-comparación (se lee al final)
        import json as _json
        backup_path = os.path.join(str(PROJECT_DIR), "cache", "quality_rebuild_backup.json")
        with open(backup_path, "w") as bf:
            _json.dump(backup, bf)
    else:
        input_csv = args.input or cfg.default_csv
    
    output_csv = args.output or os.path.join(str(PROJECT_DIR), "out/log_descargas.csv")
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)

    print(f"🎵 Iniciando descarga de audio...")
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
# SUBCOMANDO: videos (INTERACTIVE)
# ─────────────────────────────────────────────────────────────────────────────


def cmd_videos(args: argparse.Namespace):
    """Descarga videos (MP4) con confirmación interactiva."""
    import subprocess
    import time
    from mpc.config import get_config, PROJECT_DIR
    from mpc.library.repository import TrackRepository
    from mpc.acquisition.steps.downloader import (
        is_preferred_video, is_bad_video, should_ask_user, classify_video,
        YtDlpDownloader,
    )

    cfg = get_config()

    # Load tracks from CSV or DB
    if args.curator:
        from mpc.curator.status import VideoStatus

        db_path = str(PROJECT_DIR / "cache" / "library.db")
        repo = TrackRepository(db_path)
        tracks = repo.by_video_status(VideoStatus.NEEDS_VIDEO)
        if not tracks:
            print("✅ No hay tracks con video_status='needs_video'. Corré `mala-pata curator audit` primero.")
            return
        print(f"📋 Cargando {len(tracks)} tracks de la BD (video_status=needs_video)...")
    else:
        # Load from CSV
        input_csv = args.input or cfg.default_csv
        if not os.path.exists(input_csv):
            print(f"❌ No encontrado: {input_csv}")
            return
        
        import csv
        tracks = []
        with open(input_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("artist") and row.get("title"):
                    tracks.append({
                        "artist": row["artist"],
                        "title": row["title"],
                        "genre_slug": row.get("genre", ""),
                    })
        print(f"📋 Cargando {len(tracks)} tracks de {input_csv}")

    # Initialize downloader
    downloader = YtDlpDownloader(cfg.lib_base_dir, cfg.ytdlp_bin)
    err = downloader.check_tools()
    if err:
        print(f"❌ Error: yt-dlp no disponible ({err})")
        return

    # Process each track
    accepted = 0
    rejected = 0
    skipped = 0
    unavailable = 0
    
    import re as _re

    def _extract_youtube_id(text: str) -> str:
        """Extrae video_id de una URL YouTube o devuelve el texto si parece ID."""
        text = (text or "").strip()
        if not text:
            return ""
        # URLs comunes: youtube.com/watch?v=ID, youtu.be/ID, embed/ID, shorts/ID
        patterns = [
            r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
            r"^([A-Za-z0-9_-]{11})$",  # ID pelado (exactamente 11 chars)
        ]
        for p in patterns:
            m = _re.search(p, text)
            if m:
                return m.group(1)
        return ""

    def _fetch_yt_info(video_id: str) -> tuple:
        """Corre yt-dlp --dump-json. Retorna (title, channel, available)."""
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            cmd = [cfg.ytdlp_bin, "--dump-json", "--no-download", url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                return (
                    data.get("title", ""),
                    data.get("channel", "") or data.get("uploader", ""),
                    True,
                )
        except Exception:
            pass
        return "", "", False

    def _analyze_quality_auto(filepath: str, tid: str) -> None:
        """Corre análisis de calidad tier máximo disponible y persiste."""
        try:
            from mpc.curator.quality import ffprobe, loudness, fingerprint, score
        except Exception:
            return
        if not filepath or not os.path.isfile(filepath):
            return
        m = {}
        if ffprobe.is_available():
            m.update(ffprobe.analyze(filepath))
        if loudness.is_available():
            m.update(loudness.analyze(filepath))
        if fingerprint.is_available():
            ak = os.getenv("ACOUSTID_API_KEY", "")
            m.update(fingerprint.analyze(filepath, ak))
        if not m:
            return
        m["audio_quality_score"] = score.compute(m)
        try:
            repo.update_quality(tid, m)
        except Exception:
            pass

    def _download_video(artist: str, title: str, genre_slug: str, video_id: str) -> tuple:
        """Descarga el MP4 y actualiza BD. Retorna (ok, filepath_or_error).
        Al fallar marca video_status='video_unavailable' para evitar reintentos
        en siguientes runs."""
        from mpc.acquisition.track_ref import TrackRef
        url = f"https://www.youtube.com/watch?v={video_id}"
        track_ref = TrackRef(
            platform="youtube",
            url=url,
            display_id=video_id,
            thumbnail_url=f"https://i3.ytimg.com/vi/{video_id}/hqdefault.jpg",
        )
        gs = genre_slug or "salsa_dura_clasica"
        status, filepath, error, detail = downloader.download_with_video(
            track_ref, artist, title, gs
        )
        if status.value == "downloaded" and filepath:
            # mark_video_accepted guarda video_filepath + video_status=video_ok
            repo.mark_video_accepted(artist, title, filepath)
            # Actualizar también video_source_id (para audits futuros)
            trk = repo.get(artist, title)
            tid = trk["track_id"] if trk else None
            if tid:
                repo.update_curator_flags(tid, video_source_id=video_id)
                # Análisis de calidad automático (tier máx disponible) sobre el MP4
                _analyze_quality_auto(filepath, tid)
            return True, filepath

        # Falló: marcar unavailable para evitar reintentos ciegos
        try:
            repo.mark_video_unavailable(artist, title)
        except Exception:
            pass
        return False, (detail or str(error))

    for i, t in enumerate(tracks, 1):
        artist = t["artist"]
        title = t["title"]
        db_path = str(PROJECT_DIR / "cache" / "library.db")
        repo = TrackRepository(db_path)

        print(f"\n▶ [{i}/{len(tracks)}] {artist} - {title}")

        # video_source_id sugerido (de BD) — puede estar vacío
        track = repo.get(artist, title)
        video_id = (track.get("video_source_id") if track else "") or ""

        video_title = channel = ""
        if video_id:
            video_title, channel, _ = _fetch_yt_info(video_id)
            url = f"https://www.youtube.com/watch?v={video_id}"
            classification = classify_video(video_title, channel)
            print(f"   YouTube: {url}")
            print(f"   Title: {video_title}")
            print(f"   Channel: {channel}")
            print(f"   Quality: {classification}")
        else:
            print("   ⚠️  Sin video_source_id sugerido en BD")

        if args.all:
            if not video_id:
                print("   ⏭️  Batch mode sin ID → skip")
                skipped += 1
                time.sleep(1)
                continue
            print("   ⏭️  Batch mode, descargando...")
            ok, result_info = _download_video(artist, title, t.get("genre_slug", ""), video_id)
            if ok:
                print(f"   ✅ Video guardado: {result_info}")
                accepted += 1
            else:
                print(f"   ❌ Error: {result_info}")
                rejected += 1
            time.sleep(1)
            continue

        # Interactive — loop para permitir reintentos con manual
        while True:
            prompt = "   [y] Accept  [n] Reject  [u] No video  [s] Skip  [m] Manual (URL/ID)? " if video_id \
                     else "   [m] Manual (URL/ID)  [n] Reject  [u] No video  [s] Skip? "
            print(prompt, end="")
            try:
                response = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n⚠️ Interrumpido.")
                response = "q"
                break

            if response == "y" and video_id:
                print("   ⬇️  Descargando...")
                ok, info = _download_video(artist, title, t.get("genre_slug", ""), video_id)
                if ok:
                    print(f"   ✅ Video guardado: {info}")
                    accepted += 1
                else:
                    print(f"   ❌ Error: {info}")
                    rejected += 1
                break
            elif response == "n":
                repo.mark_video_rejected(artist, title)
                rejected += 1
                break
            elif response == "u":
                repo.mark_video_unavailable(artist, title)
                unavailable += 1
                break
            elif response == "s":
                skipped += 1
                break
            elif response == "m":
                try:
                    raw = input("   🔗 Pegá URL o ID de YouTube: ")
                except (EOFError, KeyboardInterrupt):
                    print("\n⚠️ Cancelado.")
                    continue
                manual_id = _extract_youtube_id(raw)
                if not manual_id:
                    print("   ❌ URL/ID inválido. Reintentá.")
                    continue
                m_title, m_channel, ok = _fetch_yt_info(manual_id)
                if not ok:
                    print(f"   ❌ No se pudo leer el video {manual_id} (privado/borrado?). Reintentá.")
                    continue
                print(f"   ✅ Video manual encontrado:")
                print(f"      YouTube: https://youtube.com/watch?v={manual_id}")
                print(f"      Title:   {m_title}")
                print(f"      Channel: {m_channel}")
                print("   ⬇️  Descargando...")
                ok, info = _download_video(artist, title, t.get("genre_slug", ""), manual_id)
                if ok:
                    print(f"   ✅ Video guardado: {info}")
                    accepted += 1
                else:
                    print(f"   ❌ Error: {info}")
                    rejected += 1
                break
            else:
                print(f"   ⚠️  Opción inválida: {response!r}")
                continue

        if response == "q":
            break
        time.sleep(1)

    print(f"\n✨ Videos completado:")
    print(f"   ✅ Aceptados: {accepted}")
    print(f"   ❌ Rechazados: {rejected}")
    print(f"   🚫 Sin video disponible: {unavailable}")
    print(f"   ⏭️  Saltados: {skipped}")


# ─────────────────────────────────────────────────────────────────────────────
# SUBCOMANDO: delete
# ─────────────────────────────────────────────────────────────────────────────


def cmd_delete(args: argparse.Namespace):
    """Elimina una canción del BD y del disco (MP3 y MP4 si existen)."""
    from mpc.library.repository import TrackRepository

    repo = TrackRepository(str(PROJECT_DIR / "cache" / "library.db"))

    candidates: list = []
    if args.filename:
        # Buscar por nombre de archivo en filepath
        fn = args.filename
        for t in repo.get_all():
            fp = t.get("filepath") or ""
            vfp = t.get("video_filepath") or ""
            if os.path.basename(fp) == fn or os.path.basename(vfp) == fn:
                candidates.append(t)
    elif args.artist and args.title:
        t = repo.get(args.artist, args.title)
        if t:
            candidates.append(t)
    elif args.artist:
        candidates = repo.by_artist(args.artist)
        if args.genre:
            candidates = [c for c in candidates if c.get("genre_slug") == args.genre]
    else:
        print("❌ Debés pasar --filename o --artist (+opcional --title/--genre)")
        sys.exit(2)

    if not candidates:
        print("❌ Sin coincidencias.")
        sys.exit(1)

    if len(candidates) > 1 and not getattr(args, "all", False):
        print(f"⚠️  {len(candidates)} coincidencias. Usá --all o afiná la búsqueda:")
        for t in candidates[:10]:
            print(f"   • {t['artist']} — {t['title']} [{t.get('genre_slug') or '—'}]")
        sys.exit(1)

    deleted_files = 0
    for t in candidates:
        for fp in (t.get("filepath"), t.get("video_filepath")):
            if fp and os.path.isfile(fp):
                try:
                    os.remove(fp)
                    deleted_files += 1
                except OSError as e:
                    print(f"   ⚠️  no se pudo borrar {fp}: {e}")
        repo.delete_track(t["track_id"])
        print(f"🗑  {t['artist']} — {t['title']}")

    print(f"\n✅ {len(candidates)} filas BD eliminadas, {deleted_files} archivos borrados.")


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
# SUBCOMANDOS: classifier-stats / review-ambiguous
# ─────────────────────────────────────────────────────────────────────────────


def cmd_classifier_stats(args: argparse.Namespace):
    """D2: distribución de géneros y confidence promedio en library.db."""
    from mpc.config import get_config, PROJECT_DIR
    from mpc.library.repository import TrackRepository

    cfg = get_config()
    db_path = str(PROJECT_DIR / "cache" / "library.db")
    repo = TrackRepository(db_path)
    summary = repo.classifier_summary()

    print(f"\n📊 Classifier Stats — total tracks: {summary['total']}\n")
    print(f"{'Género':<28} {'Tracks':>7} {'Avg conf':>10}")
    print("─" * 48)
    for row in summary["by_genre"]:
        print(f"{row['slug']:<28} {row['n']:>7} {row['avg_conf']:>10.3f}")

    if summary["low_conf"]:
        print(f"\n⚠️  Tracks con confidence <0.5 (top {len(summary['low_conf'])}):")
        for r in summary["low_conf"]:
            print(f"   {r['confidence']:.2f}  {r['artist']:<30} — {r['title'][:40]:<40} [{r['genre_slug']}]")


def cmd_review_ambiguous(args: argparse.Namespace):
    """C5: lista tracks marcados ambiguos en cache/classifier_log.jsonl."""
    import json
    from mpc.config import PROJECT_DIR

    log_path = PROJECT_DIR / "cache" / "classifier_log.jsonl"
    if not log_path.exists():
        print(f"❌ No existe {log_path}. Clasifica algún track primero.")
        return

    ambiguous = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("ambiguous"):
                ambiguous.append(row)

    if not ambiguous:
        print("✅ No hay tracks ambiguos en el log.")
        return

    ambiguous = ambiguous[-args.limit:]
    print(f"\n🔍 {len(ambiguous)} tracks ambiguos (más recientes):\n")
    print(f"{'Artista':<28} {'Título':<40} {'Top-1':<20} {'Top-2':<20} {'conf':>5}")
    print("─" * 118)
    for r in ambiguous:
        print(
            f"{(r.get('artist') or '')[:27]:<28} "
            f"{(r.get('title') or '')[:39]:<40} "
            f"{(r.get('final_slug') or '')[:19]:<20} "
            f"{(r.get('slug_2') or '')[:19]:<20} "
            f"{(r.get('final_confidence') or 0):>5.2f}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# SUBCOMANDOS: replace-audio / replace-video / replace-thumbnail
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_track(args: argparse.Namespace):
    """Devuelve (repo, track_dict) o (repo, None) si cancelado/no encontrado."""
    from mpc.library.repository import TrackRepository
    from mpc.curator.replace import fuzzy_find, interactive_pick

    cfg = get_config()
    repo = TrackRepository(cfg.library_db)

    if args.track_id:
        with repo._conn() as con:
            row = con.execute(
                "SELECT * FROM tracks WHERE track_id=?", (args.track_id,)
            ).fetchone()
        if not row:
            print(f"❌ track_id {args.track_id} no encontrado")
            return repo, None
        return repo, dict(row)

    if not args.like:
        print("❌ Usa --like \"query\" o --track-id ID")
        return repo, None

    print(f"🔍 Buscando \"{args.like}\"...")
    candidates = fuzzy_find(repo, args.like, limit=args.limit)
    auto = not getattr(args, "no_auto", False)
    if getattr(args, "yes", False):
        if candidates:
            return repo, candidates[0][1]
        print("❌ Sin matches")
        return repo, None
    track = interactive_pick(candidates, auto_if_clear=auto)
    return repo, track


def cmd_replace_audio(args: argparse.Namespace):
    from mpc.curator.replace import replace_audio
    repo, track = _resolve_track(args)
    if not track:
        return
    print(f"✅ Track: {track['artist']} - {track['title']} "
          f"[{track.get('genre_slug') or '?'}]")
    print(f"   Album: {track.get('album') or '—'!r} | "
          f"Year: {track.get('year') or '—'}")
    replace_audio(repo, track, args.youtube_id)


def cmd_replace_video(args: argparse.Namespace):
    from mpc.curator.replace import replace_video
    repo, track = _resolve_track(args)
    if not track:
        return
    print(f"✅ Track: {track['artist']} - {track['title']} "
          f"[{track.get('genre_slug') or '?'}]")
    replace_video(repo, track, args.youtube_id)


def cmd_replace_thumbnail(args: argparse.Namespace):
    from mpc.curator.replace import replace_thumbnail
    repo, track = _resolve_track(args)
    if not track:
        return
    print(f"✅ Track: {track['artist']} - {track['title']}")
    replace_thumbnail(repo, track, args.youtube_id)


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
            '  mala-pata create "10 canciones de salsa dura underground"\n'
            '  mala-pata create "5 de Héctor Lavoe" --style underground\n'
            "  mala-pata create --spotify https://open.spotify.com/playlist/XXX\n"
            '  mala-pata create --artist "Ray Barretto" --count 8\n'
            '  mala-pata create "silvio rodriguez" --genre nueva_trova\n'
            '  mala-pata create --dry-run "algo complejo"\n'
            "  mala-pata download\n"
            "  mala-pata list\n"
            "  mala-pata genres\n"
            '  mala-pata delete --filename "Héctor Lavoe - El Cantante.mp3"\n'
        ),
    )

    # Flags globales
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="-v = INFO, -vv = DEBUG"
    )

    subparsers = parser.add_subparsers(dest="subcommand", metavar="SUBCOMANDO")

    # ── create ────────────────────────────────────────────────────────────────
    p_create = subparsers.add_parser(
        "create",
        help="Genera canciones.csv",
        description="Genera canciones.csv desde lenguaje natural, Spotify, artista o álbum.",
    )
    p_create.add_argument(
        "query",
        nargs="?",
        default="",
        help="Pedido en lenguaje natural, ej: '10 canciones de mambo'",
    )
    p_create.add_argument(
        "--spotify", metavar="URL", help="Importar desde playlist/álbum de Spotify"
    )
    p_create.add_argument(
        "--type", choices=["playlist", "album"], help="[Spotify] Forzar tipo de fuente"
    )
    p_create.add_argument(
        "-n", "--count", type=int, help="Número de canciones [default: 10]"
    )
    p_create.add_argument(
        "-g", "--genre", help=f"Forzar género (cualquiera de: {', '.join(ALL_SLUGS)})"
    )
    p_create.add_argument("-a", "--artist", help="Focalizar en un artista específico")
    p_create.add_argument(
        "--album", help="Obtener tracks de un álbum (requiere --artist)"
    )
    p_create.add_argument(
        "--style", choices=["underground", "comercial"], help="Sesgo de selección"
    )
    p_create.add_argument(
        "--append",
        action="store_true",
        help="Añadir al CSV existente en vez de sobreescribir",
    )
    p_create.add_argument(
        "--out", metavar="FILE", help="CSV de salida [default: canciones.csv]"
    )
    p_create.add_argument(
        "--dry-run", action="store_true", help="Mostrar el plan sin escribir nada"
    )

    # ── audios ──────────────────────────────────────────────────────────────
    p_audios = subparsers.add_parser(
        "audios",
        help="Descarga archivos de audio (MP3)",
        description="Procesa canciones.csv → busca YouTube → clasifica → descarga audio.",
    )
    p_audios.add_argument(
        "--input", metavar="CSV", help="CSV de entrada [default: data/canciones.csv]"
    )
    p_audios.add_argument(
        "--output", metavar="CSV", help="Log de salida [default: out/log_descargas.csv]"
    )
    p_audios.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar qué se descargaría sin descargar",
    )
    p_audios.add_argument(
        "--curator",
        action="store_true",
        help="Procesar tracks marcados por curator (missing / needs_metadata / needs_thumbnail / needs_tags)",
    )
    p_audios.add_argument(
        "--quality",
        action="store_true",
        help="Re-descarga tracks con bitrate o score bajo umbral (requiere audit-quality previo)",
    )
    p_audios.add_argument(
        "--min-bitrate", type=int, default=192,
        help="Umbral de bitrate para --quality (default: 192)",
    )
    p_audios.add_argument(
        "--min-score", type=int, default=60,
        help="Umbral de score para --quality (default: 60)",
    )
    p_audios.add_argument(
        "--limit", type=int,
        help="Limita N tracks procesados (útil con --quality)",
    )

    # ── videos ──────────────────────────────────────────────────────────────
    p_videos = subparsers.add_parser(
        "videos",
        help="Descarga videos (MP4) con confirmación interactiva",
        description="Descarga videos uno por uno, esperando confirmación del usuario.",
    )
    p_videos.add_argument(
        "--input", metavar="CSV", help="CSV de entrada [default: data/canciones.csv]"
    )
    p_videos.add_argument(
        "--curator",
        action="store_true",
        help="Procesar tracks con video_status='needs_video' (audio curado, sin video)",
    )
    p_videos.add_argument(
        "--all",
        action="store_true",
        help="Descargar todos sin preguntar (batch mode)",
    )

    # ── delete ────────────────────────────────────────────────────────────────
    p_del = subparsers.add_parser(
        "delete",
        help="Elimina una canción del manifest y disco",
        description="Borra archivo físico y fila del manifest.",
    )
    p_del.add_argument(
        "--filename", help="Nombre de archivo, ej: 'Artista - Titulo.mp3'"
    )
    p_del.add_argument("--artist", help="Nombre del artista")
    p_del.add_argument("--title", help="Título de la canción")
    p_del.add_argument("--genre", help="Género (opcional, para afinar búsqueda)")
    p_del.add_argument(
        "--all", action="store_true", help="Borrar todas las coincidencias"
    )
    p_del.add_argument("--debug", action="store_true")

    # ── list ──────────────────────────────────────────────────────────────────
    p_list = subparsers.add_parser("list", help="Muestra canciones.csv")
    p_list.add_argument("file", nargs="?", help="CSV a listar [default: canciones.csv]")

    # ── genres ────────────────────────────────────────────────────────────────
    subparsers.add_parser("genres", help="Lista géneros disponibles")

    # ── curator ───────────────────────────────────────────────────────────────
    p_curator = subparsers.add_parser(
        "curator",
        help="Auditoría y reparación BD↔disco",
        description="Sistema de curaduría: audit, status, fix-metadata, "
                    "fix-duplicates, fix-genres, fix-thumbnails, fix-video-thumbnails, "
                    "fix-tags, backfill-mbid, backfill-audio-source-id, reconcile.",
    )
    curator_sub = p_curator.add_subparsers(dest="curator_cmd", metavar="ACCION")

    curator_sub.add_parser("audit",  help="Escanea disco+BD y actualiza flags")
    curator_sub.add_parser("status", help="Conteo por curator_status")

    p_fix_thumb = curator_sub.add_parser(
        "fix-thumbnails", help="Descarga e inyecta thumbnails (YouTube → APIC)"
    )
    p_fix_thumb.add_argument("--dry-run", action="store_true")
    p_fix_thumb.add_argument("--limit", type=int, help="Limitar N tracks")

    p_fix_tags = curator_sub.add_parser(
        "fix-tags", help="Completa tags ID3 desde BD + MusicBrainz"
    )
    p_fix_tags.add_argument("--dry-run", action="store_true")
    p_fix_tags.add_argument("--limit", type=int)
    p_fix_tags.add_argument("--no-mb", action="store_true", help="No consultar MusicBrainz")

    p_fix_dup = curator_sub.add_parser(
        "fix-duplicates", help="Borra duplicados conservando el mejor candidato"
    )
    p_fix_dup.add_argument("--dry-run", action="store_true")
    p_fix_dup.add_argument("--auto", action="store_true", help="Borrar sin preguntar")
    p_fix_dup.add_argument("--by-fingerprint", action="store_true",
                           help="Agrupa por audio fingerprint (requiere audit-quality --tier 3 previo)")

    p_fix_gen = curator_sub.add_parser(
        "fix-genres", help="Mueve archivos a carpeta correcta y renombra al formato canónico"
    )
    p_fix_gen.add_argument("--dry-run", action="store_true")
    p_fix_gen.add_argument("--auto", action="store_true", default=True)

    p_rec = curator_sub.add_parser(
        "reconcile", help="Resuelve huérfanos y fantasmas (interactivo)"
    )
    p_rec.add_argument("--dry-run", action="store_true")
    p_rec.add_argument("--auto", action="store_true", help="Aceptar defaults sin preguntar")

    p_bfa = curator_sub.add_parser(
        "backfill-audio-source-id",
        help="Busca en YouTube los audio_source_id faltantes",
    )
    p_bfa.add_argument("--dry-run", action="store_true")
    p_bfa.add_argument("--limit", type=int)
    p_bfa.add_argument("--sleep", type=float, default=2.0, help="Segundos entre búsquedas")

    p_bfm = curator_sub.add_parser(
        "backfill-mbid",
        help="Consulta MusicBrainz para rellenar mbid faltantes",
    )
    p_bfm.add_argument("--dry-run", action="store_true")
    p_bfm.add_argument("--limit", type=int)
    p_bfm.add_argument("--min-score", type=int, default=90, help="Score mínimo MB (default 90)")

    p_meta = curator_sub.add_parser(
        "fix-metadata",
        help="Sincroniza filename + tags ID3/MP4 con BD (artist/title/album=genre_slug)",
    )
    p_meta.add_argument("--dry-run", action="store_true", default=True,
                        help="Dry-run (default)")
    p_meta.add_argument("--apply", dest="dry_run", action="store_false",
                        help="Ejecutar cambios")
    p_meta.add_argument("--limit", type=int)

    p_vthumb = curator_sub.add_parser(
        "fix-video-thumbnails",
        help="Embebe thumbnail de YouTube como covr atom en archivos MP4",
    )
    p_vthumb.add_argument("--dry-run", action="store_true")
    p_vthumb.add_argument("--limit", type=int)

    p_aq = curator_sub.add_parser(
        "audit-quality",
        help="Analiza calidad de audio (tier 1=ffprobe, 2=LUFS, 3=fingerprint)",
    )
    p_aq.add_argument("--tier", type=int, choices=[1, 2, 3], default=None,
                      help="Nivel de análisis (default: máximo disponible)")
    p_aq.add_argument("--limit", type=int)
    p_aq.add_argument("--dry-run", action="store_true")
    p_aq.add_argument("--force", action="store_true",
                      help="Re-analiza tracks ya analizados")

    # ── classifier-stats ──────────────────────────────────────────────────────
    subparsers.add_parser(
        "classifier-stats",
        help="Distribución de géneros + confidence promedio (D2)",
    )

    # ── review-ambiguous ──────────────────────────────────────────────────────
    p_rev = subparsers.add_parser(
        "review-ambiguous",
        help="Muestra tracks ambiguos (top-1 vs top-2 cerca) para corrección manual",
    )
    p_rev.add_argument("--limit", type=int, default=30, help="Tracks a mostrar (default 30)")

    # ── replace-audio / replace-video / replace-thumbnail ────────────────────
    def _add_replace_common(p):
        p.add_argument("--like", help='Búsqueda fuzzy: "asi vivo yo alberto barros"')
        p.add_argument("--track-id", help="Track ID exacto de BD")
        p.add_argument("--youtube-id", required=True, help="YouTube video ID")
        p.add_argument("--limit", type=int, default=5, help="Candidatos a mostrar (default 5)")
        p.add_argument("--yes", action="store_true", help="Usar primer match sin preguntar")
        p.add_argument("--no-auto", action="store_true", help="No auto-seleccionar incluso si hay match claro")

    p_ra = subparsers.add_parser(
        "replace-audio",
        help="Re-descarga MP3 desde YouTube ID, preserva metadata BD",
    )
    _add_replace_common(p_ra)

    p_rv = subparsers.add_parser(
        "replace-video",
        help="Re-descarga MP4 desde YouTube ID, preserva metadata BD",
    )
    _add_replace_common(p_rv)

    p_rt = subparsers.add_parser(
        "replace-thumbnail",
        help="Reemplaza solo thumbnail (APIC/covr) desde YouTube ID, NO toca otros tags",
    )
    _add_replace_common(p_rt)

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
        "download": cmd_audios,  # alias for backwards compat
        "audios": cmd_audios,
        "videos": cmd_videos,
        "delete": cmd_delete,
        "list": cmd_list,
        "genres": cmd_genres,
        "classifier-stats": cmd_classifier_stats,
        "review-ambiguous": cmd_review_ambiguous,
        "replace-audio": cmd_replace_audio,
        "replace-video": cmd_replace_video,
        "replace-thumbnail": cmd_replace_thumbnail,
    }

    # Auto-update yt-dlp (cache 24h) — solo si el comando lo usa
    _uses_ytdlp = {"audios", "videos", "download", "curator", "replace-audio", "replace-video"}
    if args.subcommand in _uses_ytdlp:
        try:
            from mpc.utils.ytdlp_updater import ensure_fresh_ytdlp
            ensure_fresh_ytdlp()
        except Exception:
            pass  # never block the command if updater fails

    if args.subcommand == "curator":
        from mpc.curator.cli import dispatch as curator_dispatch
        curator_dispatch(args)
        return
    dispatch[args.subcommand](args)


if __name__ == "__main__":
    main()

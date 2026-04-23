# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## IMPORTANT DEFAULTS (must know)

| Item | Default | Notes |
|------|---------|-------|
| CSV input | `data/canciones.csv` | NOT raiz! |
| SQLite DB | `cache/library.db` | fuente de verdad única (manifest.csv borrado) |
| Music dir | `~/Music/mala_pata_come_candela` | |

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env   # configure paths and API keys

# Run the CLI
python mala_pata.py create "10 canciones de salsa dura"
python mala_pata.py create --spotify https://open.spotify.com/playlist/XXXX
python mala_pata.py audios                   # descarga MP3 desde CSV
python mala_pata.py videos                   # descarga MP4 interactivo (y/n/s)
python mala_pata.py delete --filename "NG La Banda - Santa Palabra.mp3"
python mala_pata.py list
python mala_pata.py genres

# Curator (auditoría + reparación BD↔disco, reemplaza al antiguo `doctor`)
python mala_pata.py curator audit            # escanea disco y pobla curator_status
python mala_pata.py curator status           # conteo por curator_status
python mala_pata.py curator fix-thumbnails   # baja y embebe APIC desde YouTube
python mala_pata.py curator fix-tags         # completa tags ID3 desde MusicBrainz
python mala_pata.py curator fix-duplicates   # interactivo, borra el peor del par
python mala_pata.py curator fix-genres       # mueve archivos a carpeta correcta + rename
python mala_pata.py curator reconcile        # resuelve huérfanos / fantasmas
python mala_pata.py curator backfill-mbid    # rellena mbid faltantes (MusicBrainz)
python mala_pata.py curator backfill-audio-source-id  # busca audio_source_id en YouTube
python mala_pata.py curator fix-metadata --apply  # sincroniza filename+tags+BD (dry-run por default)
python mala_pata.py curator fix-video-thumbnails  # embebe covr atom en MP4 desde YouTube
python mala_pata.py curator audit-quality --tier 1  # bitrate/sample_rate/codec (ffprobe, ~30s)
python mala_pata.py curator audit-quality --tier 2  # + LUFS/peak (requiere pyloudnorm)
python mala_pata.py curator audit-quality --tier 3  # + fingerprint (requiere chromaprint)
python mala_pata.py curator fix-duplicates --by-fingerprint  # dedup cross-encoding (requiere tier 3)
python mala_pata.py audios --curator         # descarga audios de tracks marcados missing/needs_*
python mala_pata.py videos --curator         # revisa videos con video_status='needs_video'

# Dry-run pipeline (no actual downloads)
python scripts/pipeline_music.py --input data/canciones.csv --output /tmp/test_log.csv --dry-run

# Verify imports after structural changes
python -c "from mpc.catalog.genre import Genre; print(Genre('salsa_dura_clasica'))"
python -c "from mpc.discovery import SearchEngine, DiscoverTracksUseCase; print('discovery OK')"
python -c "from mpc.acquisition import DownloadEngine, DownloadTrackUseCase; print('acquisition OK')"
python -c "from mpc.library import TrackRepository, LibraryIndex; print('library OK')"
python -c "from mpc.curator import Auditor, CuratorStatus; print('curator OK')"
```

There is no automated test suite. Validation is done via dry-run and import checks above.

## Architecture

The system is a music pipeline: generate a CSV of songs from natural language or Spotify, search YouTube/SoundCloud, classify by genre, download audio with metadata.

### Three Bounded Contexts (DDD + Hexagonal)

Dependency rule: **Infrastructure → Application → Domain** (domain imports nothing from infra).

**BC1 — Discovery** (`mpc/discovery/`): Interprets user requests, queries Discogs/MusicBrainz/Spotify/OpenAI, returns ranked `CandidateSet` → writes `canciones.csv`.  
Entry: `DiscoverTracksUseCase` → `SearchEngine` → strategies → `assembler.pick_playlist()`

**BC2 — Acquisition** (`mpc/acquisition/`): Downloads tracks via a sequential step pipeline.  
Entry: `DownloadBatchUseCase` → `DownloadEngine` → steps: `IdempotencyStep` → `NoApiSearchStep` → `CandidateScorerStep` → `GenreClassifierStep` → `DownloaderStep` → `TaggerStep`

**BC3 — Library** (`mpc/library/`): SQLite persistence for download history.  
`TrackRepository` (UPSERT by `track_id`) + `LibraryIndex` (read model: `failed()`, `to_retry()`, `summary()`).

**Curator** (`mpc/curator/`): Auditoría y reparación quirúrgica BD↔disco. Reemplaza al antiguo `doctor`.  
Entry: `Auditor.run()` pobla `curator_status` por track. Fixers (`fixers/*.py`): `ThumbnailFixer` (cadena CAA→audio_source_id→video_source_id), `TagFixer` (MB→ID3), `DuplicateFixer` (interactivo), `GenreFixer` (move+rename), `ReconcileFixer` (huérfanos/fantasmas), `AudioSourceBackfiller`/`MbidBackfiller` (rellenan fuentes faltantes). Flag `--curator` en `audios`/`videos` lee de `curator_status`.

### Fuentes de audio y video (separadas)

| Campo | Qué guarda | Poblado por |
|---|---|---|
| `audio_source_id` | YouTube ID donde se sacó el MP3 (audio-oriented) | `audios` pipeline / `backfill-audio-source-id` |
| `video_source_id` | YouTube ID del MP4 visual (puede ser concert) | `videos` pipeline |
| `mbid` | MusicBrainz recording ID (para Cover Art Archive) | `backfill-mbid` / pipeline |

Cadena de thumbnail (prioridad): `mbid→CAA` → `audio_source_id→YT` → `video_source_id→YT` (última opción, warning).

### Audio y Video: métricas separadas

La BD tiene DOS columnas de estado independientes:
- `curator_status` (AUDIO): ok / needs_thumbnail / needs_tags / needs_metadata / needs_rename / needs_move / duplicate / orphan / missing
- `video_status` (VIDEO): not_ready / needs_video / video_ok / video_unavailable / video_rejected

La curación de audio no se contamina con el estado de video. Un track puede estar `ok` de audio y `needs_video` al mismo tiempo. `mala-pata videos --curator` filtra por `video_status='needs_video'`.

### Regla de diseño: `album` = **nombre real del álbum** (NO genre_slug)

`TALB` (MP3) / `©alb` (MP4) guarda el álbum real resuelto vía `AlbumResolver`:
1. MusicBrainz (mbid o search)
2. Discogs
3. OpenAI LLM (confidence ≥ 0.7)
4. Vacío si todo falla

`TCON` / `©gen` guarda el nombre legible del género (función `genre_name(slug)` en `mpc/catalog/genres.py`).

**Reemplaza regla obsoleta `album == genre_slug`**. La regla vieja ponía `genre_slug` en TALB porque el usuario no sabía que ID3 tiene campo genre separado. Ahora están en sus campos correctos.

### Audio quality analyzer (`mpc/curator/quality/`)

Análisis en 3 tiers incrementales (opt-in por deps):
- **Tier 1** (ffprobe): bitrate_kbps, sample_rate, codec, channels, duration_sec
- **Tier 2** (pyloudnorm + soundfile): lufs_integrated, true_peak_db, dynamic_range
- **Tier 3** (chromaprint + pyacoustid): audio_fingerprint, acoustid_mbid (opcional con `ACOUSTID_API_KEY`)

Compone `audio_quality_score` (0-100) automático. `fix-duplicates --by-fingerprint` detecta duplicados cross-encoding (requiere tier 3 corrido previamente).

### Single sanitizer (`mpc/utils/text.sanitize_filename_component`)

Fuente única de verdad para strings usados en BD.artist/title, tags ID3/MP4 y filename. Aplica title-case + NFC Unicode + reemplaza caracteres reservados por filesystem (`/ \ : * < > |`) con ` - `. Preserva acentos, signos (¿ ¡ ? "). Garantiza que BD, tag y filename sean **literalmente el mismo string**.

**`track_id()`** usa normalización aún más estricta (en `mpc/library/identity.py::_key`): ignora TODA puntuación (incluye `-`, `/`, `?`, `¿`, `()`) para que el mismo track con distintas sanitizaciones genere siempre el mismo fingerprint.

**Shared kernel** (`mpc/catalog/`): `genres.py` (ALL_SLUGS, GENRE_DB, GENRE_COMMAND) and `genre.py` (`Genre` value object — frozen dataclass, validated against `ALL_SLUGS`).

**External adapters** (`mpc/sources/`): `musicbrainz.py`, `discogs.py`, `spotify_client.py`, `openai_source.py`.

**Config** (`mpc/config.py`): `get_config()` singleton — loads `.env` once via `Config.from_env()`. All modules must import from here, never call `os.getenv` directly.

### Compat shims — do not use in new code

| Shim path | Real location |
|---|---|
| `mpc/search/` | `mpc.discovery.*` |
| `mpc/planner/` | `mpc.discovery.planner`, `mpc.discovery.llm_planner` |
| `mpc/builders/` | `mpc.discovery.assembler` |
| `mpc/download/` | `mpc.acquisition.*` |

These exist only for backwards compatibility with external scripts.

## Critical rules

### Adding a new genre — only 2 files
1. `mpc/catalog/genres.py`: add to `GENRE_COMMAND`, classify in `AFROLATINO_SLUGS` or `DIRECT_GENRES`, add entry in `GENRE_DB` if afrolatino (include `negative` field to prevent false positives).
2. `scripts/dl-music-system.sh`: add `"dl-nombre") GENRE_DIR="nombre" ;;` in the `case` block.

Verify: `python mala_pata.py genres` should list the new genre.

### Genre classifier (`mpc/acquisition/steps/classifier.py`)
The most critical step. Do not modify without running dry-run tests against a salsa-heavy CSV. Modes controlled by `CLASSIFIER_MODE` in `.env`: `LLM_FALLBACK` (default), `HEURISTIC_ONLY`, `LLM_ONLY`.

### `query_override` column in CSV
Accepts a YouTube ID/URL, SoundCloud URL, `spotify:track:ID`, or Spotify URL — bypasses the search step entirely and routes directly to the appropriate downloader.

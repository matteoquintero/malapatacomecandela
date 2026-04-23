# Mala Pata Come Candela – Sistema de música

Pipeline completo: genera `canciones.csv` desde pedidos naturales o Spotify, busca en YouTube, clasifica en 21 géneros afrolatinos, descarga audio con metadatos, y ofrece curación quirúrgica BD↔disco (auditoría, duplicados, thumbnails, tags, renames, reconciliación).

## Arquitectura

```
mpc/
  catalog/        # Géneros (ALL_SLUGS, GENRE_DB, Genre value object)
  discovery/     # BC1: interpreta pedido → canciones.csv
  acquisition/   # BC2: pipeline de descarga (yt-dlp + tags + classifier)
  library/       # BC3: SQLite (TrackRepository, LibraryIndex)
  curator/       # Auditoría + reparación (reemplaza al antiguo `doctor`)
  sources/       # Clientes: Discogs, MusicBrainz, Spotify, OpenAI
  utils/         # text.py (SSOT sanitizer), csv_io.py
  config.py      # Config desde .env
  cli.py         # CLI unificado

mala_pata.py     # Entry point
scripts/         # pipeline_music.py, audit_library.py, dl-music-system.sh
cache/library.db # Fuente única de verdad (SQLite)
```

## Requisitos

- Python 3.10+
- `ffmpeg` y `yt-dlp` en PATH
- (Opcional) API keys: OpenAI; token Discogs; credenciales Spotify
- (Opcional) `mutagen` para tags/thumbnails

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env        # editar rutas y API keys
chmod +x scripts/dl-music-system.sh
```

## Uso rápido

### Generar CSV de tracks a descargar

```bash
# Lenguaje natural
mala-pata create "10 canciones de salsa dura underground"
mala-pata create "5 de Héctor Lavoe"
mala-pata create --artist "Ray Barretto" -n 8

# Desde Spotify
mala-pata create --spotify https://open.spotify.com/playlist/XXXX

# Ver el plan sin ejecutar
mala-pata create "10 mambos comerciales" --dry-run
```

### Descargar audio y video

```bash
mala-pata audios                    # procesa data/canciones.csv, baja MP3
mala-pata audios --input lista.csv  # otro CSV
mala-pata audios --curator          # baja solo tracks marcados en BD

mala-pata videos                    # descarga MP4 interactivo (y/n/s)
mala-pata videos --all              # sin preguntar
mala-pata videos --curator          # video_status='needs_video' en BD
```

### Curator — auditoría + reparación

```bash
mala-pata curator audit                # escanea disco + BD, pobla flags
mala-pata curator status               # dashboard AUDIO + VIDEO separados
mala-pata curator fix-duplicates       # borra duplicados (interactivo)
mala-pata curator fix-metadata --apply # sincroniza filename + tags + BD
mala-pata curator fix-genres           # mueve a carpeta correcta
mala-pata curator fix-thumbnails       # cadena CAA → audio_source → video_source
mala-pata curator fix-video-thumbnails # covr atom en MP4 desde YouTube
mala-pata curator fix-tags             # completa tags ID3 faltantes
mala-pata curator backfill-mbid        # rellena MusicBrainz IDs
mala-pata curator backfill-audio-source-id  # busca audio_source_id en YouTube
mala-pata curator reconcile            # huérfanos / fantasmas (audio + video)
```

### Otros

```bash
mala-pata delete --filename "NG La Banda - Santa Palabra.mp3"
mala-pata list                         # muestra canciones.csv
mala-pata genres                       # lista géneros disponibles
mala-pata classifier-stats             # distribución + confidence
```

## Configuración (.env)

| Variable | Descripción |
|---|---|
| `LIB_BASE_DIR` | Base de la librería de música |
| `LIBRARY_DB` | SQLite path (default `cache/library.db`) |
| `DL_MUSIC_SCRIPT` | Ruta a `scripts/dl-music-system.sh` |
| `CLASSIFIER_MODE` | `LLM_FALLBACK` \| `HEURISTIC_ONLY` \| `LLM_ONLY` |
| `OPENAI_API_KEY` | Opcional — planner + clasificador LLM |
| `DISCOGS_TOKEN` | Opcional — mejores resultados en create |
| `SPOTIFY_CLIENT_ID/SECRET` | Opcional — importar playlists |

Sin `OPENAI_API_KEY`, el sistema usa planner heurístico y `CLASSIFIER_MODE=HEURISTIC_ONLY`.

## Flujo típico completo

```bash
# 1. Generar lista
mala-pata create "20 canciones de timba"

# 2. Descargar audio
mala-pata audios

# 3. Auditar estado
mala-pata curator audit
mala-pata curator status

# 4. Reparar lo que haga falta (en orden sugerido)
mala-pata curator fix-duplicates
mala-pata curator fix-metadata --apply
mala-pata curator backfill-mbid
mala-pata curator fix-thumbnails
mala-pata curator reconcile

# 5. Si querés videos
mala-pata videos --curator
mala-pata curator fix-video-thumbnails
```

## Reglas de diseño

- **BD es fuente de verdad única**. Disco y tags se sincronizan contra BD.
- **Single sanitizer** (`sanitize_filename_component`): BD.artist/title, tag y filename son **literalmente el mismo string** (title-case, NFC, sin `/\\:*<>|`).
- **TALB (álbum) = nombre real del álbum** (resuelto vía MusicBrainz → Discogs → LLM → vacío). **TCON (género) = nombre legible del género** (desde `GENRE_DB`).
- **Audio y video separados**: `curator_status` (audio) y `video_status` (video) son columnas independientes.
- **Fuentes separadas**: `audio_source_id` ≠ `video_source_id` (distintos videos YouTube para MP3 vs MP4).

## Documentación extendida

Ver `documentation/` para referencia completa.

## Licencia

Uso personal/experimental.

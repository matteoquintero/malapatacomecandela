# Pipeline Basics — Mala Pata Come Candela

## Estructura de datos

### 1. CSV (`data/canciones.csv`)
- **Qué es**: Lista de canciones **a procesar** (input del pipeline de descarga)
- **Contenido**: `artist, title, query_override, source, genre`
- **No es**: La base de datos de lo ya descargado

### 2. Base de datos (`cache/library.db`)
- **Qué es**: Fuente única de verdad — qué está descargado, en qué estado, metadata
- **Tabla**: `tracks` con ~40 columnas agrupadas en bloques:
  - **Identidad**: `track_id`, `artist`, `title`, `mbid`
  - **Fuentes**: `audio_source_id`, `video_source_id` (independientes, distintos videos YouTube)
  - **Archivos**: `filepath` (MP3), `video_filepath` (MP4)
  - **Curator audio**: `curator_status`, `has_thumbnail`, `has_valid_tags`, `filename_ok`, `genre_folder_ok`, `metadata_consistent`
  - **Curator video**: `video_status`, `has_video_thumbnail`
  - **Metadata enriquecida**: `album`, `year`, `mbid_score`, título/canal/duración de fuentes YouTube
  - **Timestamps**: `created_at`, `updated_at`, `curator_checked_at`, etc.

## Flujo de descarga

```
data/canciones.csv
       │
       ▼
┌──────────────────┐
│  audios CLI      │ ← lee CSV o BD (--curator)
└──────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│  IdempotencyStep                │ ← valida BD + archivo existe en disco
└──────────────────────────────────┘
       │
       ├──archivo OK──► SKIP
       ├──fantasma (BD dice downloaded pero no existe)──► re-descarga
       └──no registrado──► continúa
              │
              ▼
┌──────────────────────────────────┐
│  Search + Score + Classify     │ ← yt-dlp + scorer + classifier
└──────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────┐
│  Downloader + Tagger           │ ← MP3 + tags + thumbnail
└──────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────┐
│  BD update                     │ ← status=downloaded, metadata_consistent=1
└──────────────────────────────────┘
```

## Comandos por categoría

### Generación de lista
| Comando | Qué hace |
|---|---|
| `mala-pata create "..."` | Lenguaje natural → CSV |
| `mala-pata create --spotify URL` | Playlist/álbum Spotify → CSV |
| `mala-pata list` | Muestra el CSV actual |

### Descarga
| Comando | Lee de | Output |
|---|---|---|
| `mala-pata audios` | CSV | MP3 en disco + BD |
| `mala-pata audios --curator` | BD (missing/needs_metadata/needs_thumbnail/needs_tags) | MP3 |
| `mala-pata videos` | CSV | MP4 interactivo |
| `mala-pata videos --curator` | BD (video_status='needs_video') | MP4 |

### Curator
| Comando | Scope |
|---|---|
| `curator audit` | Lee disco + BD, pobla flags |
| `curator status` | Dashboard AUDIO + VIDEO (2 bloques) |
| `curator fix-metadata --apply` | Sincroniza filename + tags MP3/MP4 + BD |
| `curator fix-duplicates` | Borra duplicados audio/video (interactivo) |
| `curator fix-genres` | Mueve MP3+MP4 a carpeta correcta |
| `curator fix-thumbnails` | APIC (MP3): CAA → audio_source → video_source |
| `curator fix-video-thumbnails` | covr atom (MP4) desde YouTube |
| `curator fix-tags` | Completa tags ID3/MP4 faltantes |
| `curator backfill-mbid` | MusicBrainz IDs (~17 min) |
| `curator backfill-audio-source-id` | YouTube audio IDs (~32 min) |
| `curator reconcile` | Huérfanos + fantasmas (audio + video) |

## Estados

### `curator_status` (AUDIO)

```
missing → orphan → duplicate → needs_move → needs_rename →
  needs_metadata → needs_thumbnail → needs_tags → ok
```

Prioridad descendente. Si un track califica a varios, se asigna el de mayor prioridad.

### `video_status` (VIDEO)

```
not_ready         → audio no está ok aún, no evaluar video
needs_video       → audio ok, sin video en disco
video_ok          → tiene video_filepath válido
video_unavailable → usuario intentó y YouTube no tiene match (terminal)
video_rejected    → usuario rechazó explícitamente (terminal)
```

Los estados terminales (`video_unavailable`, `video_rejected`) se preservan entre audits.

## Reglas de diseño

### Single sanitizer
`mpc/utils/text.py::sanitize_filename_component()` es la única función que normaliza strings. Aplica:
- Title-case (con excepciones: `de`, `la`, `el`, `y`, etc. en minúscula)
- NFC Unicode (precompuesto)
- Reemplaza `/\\:*<>|` con ` - `
- Preserva acentos, `?`, `"`, `¿`, `¡`, paréntesis

BD, tag y filename resultantes son **literalmente el mismo string**.

### `track_id()` normalización estricta
`mpc/library/identity.py::_key()` usa normalización aún más fuerte: **ignora toda puntuación** (incluye `-`, `/`, `?`). Por eso `"A la Memoria del Muerto / Merecumbe"` y `"A la Memoria del Muerto - Merecumbe"` generan el mismo track_id → no se crean filas duplicadas.

### `album` (TALB) = nombre real del álbum
`TALB` guarda el **álbum real** resuelto vía cadena MusicBrainz (MBID) → MusicBrainz (search) → Discogs → OpenAI LLM (confidence ≥ 0.7) → vacío. El género legible se guarda en `TCON` (ej. `"Son Cubano"`, desde `GENRE_DB`). `fix-metadata` y `fix-tags` usan `mpc/curator/album_resolver.py::AlbumResolver`. Reemplaza la regla anterior `TALB == genre_slug`.

### Fuentes separadas audio/video
`audio_source_id` (de dónde salió el MP3, optimizado por calidad audio) y `video_source_id` (de dónde salió el MP4, optimizado visual — puede ser concert). Son YouTube IDs **distintos**.

## Reset / operaciones manuales

### Re-descargar un track
```bash
sqlite3 cache/library.db "UPDATE tracks SET status='pending', curator_status='missing', filepath='' WHERE artist='X' AND title='Y';"
mala-pata audios --curator
```

### Limpiar duplicados huérfanos (tras borrar archivos a mano)
```bash
mala-pata curator audit       # detecta
mala-pata curator reconcile   # decide uno por uno
```

### Forzar re-sync de un track con BD
```bash
sqlite3 cache/library.db "UPDATE tracks SET metadata_consistent=0 WHERE artist='X';"
mala-pata curator fix-metadata --apply
```

## Troubleshooting

### "Ya bendecido (repositorio) → skip"
- **Significado**: BD dice `status=downloaded` Y archivo existe en disco
- **Si el archivo no existe** (fantasma): idempotency re-baja automáticamente

### Audit marca `duplicate` pero fix-duplicates dice 0
- No debería pasar desde el fix de inconsistencia `simp_pipeline`. Si ocurre, correr `curator audit` y después `fix-duplicates`.

### Filename no coincide con BD pese a fix-metadata --apply
- Probablemente APFS case-insensitive: el fixer ya usa 2-step rename. Si persiste, verificar Unicode NFC vs NFD con `unicodedata.normalize("NFC", filename)`.

## Tablas y scripts

| Archivo | Propósito |
|---|---|
| `data/canciones.csv` | Input — canciones a descargar |
| `cache/library.db` | Estado — fuente única de verdad |
| `scripts/pipeline_music.py` | Wrapper de descarga (delega al engine) |
| `scripts/audit_library.py` | Wrapper del audit (delega al Auditor) |
| `mpc/cli.py` | Dispatch de subcomandos |
| `mpc/curator/` | Auditoría + fixers |
| `out/log_descargas.csv` | Log por descarga del pipeline |

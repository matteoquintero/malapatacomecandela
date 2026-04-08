# Arquitectura DDD + Hexagonal — Mala Pata Come Candela

Sistema de música afrolatina organizado en tres Bounded Contexts con
Clean Architecture y Arquitectura Hexagonal.

---

## Regla de dependencia (Clean Architecture)

```
Infraestructura → Aplicación → Dominio
  (sources/)      (use_cases)   (domain types)
```

**Las dependencias apuntan hacia adentro. El dominio no importa nada de infraestructura.**

---

## Estructura de módulos

```
mpc/
  catalog/            # Dominio compartido (shared kernel)
    genres.py           — ALL_SLUGS, GENRE_DB, GENRE_COMMAND, backfill
    genre.py            — Genre: Value Object validado (frozen dataclass)

  utils/              # Infraestructura compartida
    text.py             — simp_pipeline, strip_accents, key_pair
    csv_io.py           — read_csv, write_csv, append_csv
    cache.py            — caché en disco (TTL)

  sources/            # Adaptadores de APIs externas (Infraestructura)
    musicbrainz.py      — mb_search_artists, mb_get_artist_recordings, …
    discogs.py          — get_discogs_client
    spotify_client.py   — fetch_playlist_tracks, fetch_album_tracks, …
    openai_source.py    — get_openai_client, find_real_songs
    lastfm.py           — (reservado)

  discovery/          # BC1 — Descubrimiento
    intent.py           — QueryIntent, SearchRequest (comandos de entrada)
    candidate.py        — Candidate, CandidateSet (salida estándar)
    engine.py           — SearchEngine, SearchPlan (orquestador)
    planner.py          — classify_request, detect_direct_genre, is_blocked
    llm_planner.py      — llm_plan (OpenAI)
    ranker.py           — rank(candidates, request) → List[Candidate]
    dedup.py            — dedup(candidates) → List[Candidate]
    normalizer.py       — mb_tags_query, discogs_styles, era, scenes
    assembler.py        — pick_playlist, pick_artist_playlist, build_album_csv
    ports.py            — IMusicCatalogPort, IStyleCatalogPort (puertos de salida)
    events.py           — CandidatesDiscovered (evento de dominio)
    use_cases.py        — DiscoverTracksUseCase (capa Application)
    strategies/
      base.py
      mb_recording_tags.py
      mb_artist_expand.py
      mb_artist_recordings.py
      mb_release_tracklist.py
      discogs_style.py

  acquisition/        # BC2 — Adquisición
    engine.py           — DownloadEngine, DownloadConfig (orquestador)
    request.py          — DownloadRequest (comando de entrada)
    result.py           — DownloadResult, DownloadStatus, DownloadError
    track_ref.py        — TrackRef, infer_platform, youtube_ref (YOUTUBE/SOUNDCLOUD/SPOTIFY)
    events.py           — TrackDownloaded, TrackSkipped (eventos de dominio)
    use_cases.py        — DownloadTrackUseCase, DownloadBatchUseCase (capa Application)
    steps/
      base.py             — BaseStep (contrato)
      idempotency.py      — IdempotencyStep (usa TrackRepository)
      search_noapi.py     — NoApiSearchStep (yt-dlp search)
      scorer.py           — CandidateScorerStep
      classifier.py       — GenreClassifierStep (heurística + LLM)
      downloader.py       — DownloaderStep, YtDlpDownloader, SpotdlDownloader
      tagger.py           — TaggerStep (metadatos ID3)

  library/            # BC3 — Biblioteca
    identity.py         — track_id(artist, title) → str, TrackIdentity
    repository.py       — TrackRepository (SQLite, UPSERT, migra CSV legado)
    index.py            — LibraryIndex: failed, to_retry, by_artist, by_genre, summary

  config.py           — AppConfig, get_config(), PROJECT_DIR
  cli.py              — CLI unificado (entry point)
```

---

## Compat shims (backward compatibility)

Los siguientes módulos son shims de compatibilidad que re-exportan desde los BCs.
**No deben usarse en código nuevo.** Se mantienen solo para scripts externos.

| Shim (ruta antigua)         | Re-exporta desde             |
|-----------------------------|------------------------------|
| `mpc/search/__init__.py`    | `mpc.discovery.*`            |
| `mpc/planner/__init__.py`   | `mpc.discovery.planner`, `mpc.discovery.llm_planner` |
| `mpc/builders/__init__.py`  | `mpc.discovery.assembler`    |
| `mpc/download/__init__.py`  | `mpc.acquisition.*`          |

---

## Patrones DDD aplicados

### Value Objects

| Clase | Módulo | Invariantes |
|-------|--------|-------------|
| `Genre` | `mpc.catalog.genre` | `slug ∈ ALL_SLUGS`; inmutable; igualdad por slug |
| `TrackRef` | `mpc.acquisition.track_ref` | `platform ∈ {YOUTUBE, SOUNDCLOUD, SPOTIFY, DIRECT}` |
| `Candidate` | `mpc.discovery.candidate` | `confidence ∈ [0.0, 1.0]` |

### Repositorios

| Clase | Módulo | Descripción |
|-------|--------|-------------|
| `TrackRepository` | `mpc.library.repository` | SQLite UPSERT por `track_id`; migra CSV legado automáticamente |
| `LibraryIndex` | `mpc.library.index` | Read model: `failed()`, `to_retry()`, `by_artist()`, `summary()` |

### Eventos de dominio

| Evento | Módulo | Cuándo se emite |
|--------|--------|-----------------|
| `CandidatesDiscovered` | `mpc.discovery.events` | Al terminar `SearchEngine.execute()` |
| `TrackDownloaded` | `mpc.acquisition.events` | Al completar descarga exitosa |
| `TrackSkipped` | `mpc.acquisition.events` | Al omitir por idempotencia o no encontrar |

### Puertos (Hexagonal)

| Puerto | Módulo | Propósito |
|--------|--------|-----------|
| `IMusicCatalogPort` | `mpc.discovery.ports` | Abstrae fuentes de grabaciones (MusicBrainz) |
| `IStyleCatalogPort` | `mpc.discovery.ports` | Abstrae fuentes de estilos (Discogs) |

Los adaptadores concretos viven en `mpc/sources/`.

### Casos de uso (Application Services)

| Use Case | Módulo | Delega a |
|----------|--------|----------|
| `DiscoverTracksUseCase` | `mpc.discovery.use_cases` | `SearchEngine` + emite `CandidatesDiscovered` |
| `DownloadTrackUseCase` | `mpc.acquisition.use_cases` | `DownloadEngine.process()` + emite eventos |
| `DownloadBatchUseCase` | `mpc.acquisition.use_cases` | `DownloadEngine.process_csv()` |

---

## Flujo de datos completo

```
CLI / scripts/pipeline_music.py
      │
      ▼
  DownloadBatchUseCase
  DownloadTrackUseCase
      │
      ▼
  DownloadEngine.process()
      │
      ├── IdempotencyStep   ──→  TrackRepository (Library BC)
      ├── NoApiSearchStep   ──→  yt-dlp (sin API key)
      ├── CandidateScorerStep
      ├── GenreClassifierStep ──→  OpenAI (opcional)
      └── DownloaderStep    ──→  YtDlpDownloader | SpotdlDownloader
                                 │
                                 ▼
                           TrackRepository.record() → library.db (SQLite)
                           LibraryIndex.summary()
```

```
CLI → cmd_create
      │
      ▼
  DiscoverTracksUseCase
  SearchEngine.execute()
      │
      ├── MBRecordingTagStrategy  ──→  mpc.sources.musicbrainz
      ├── MBArtistExpandStrategy  ──→  mpc.sources.musicbrainz
      ├── MBReleaseTracklistStrategy ─→ mpc.sources.musicbrainz
      └── DiscogsStyleStrategy    ──→  mpc.sources.discogs
      │
      ▼
  CandidateSet → assembler.pick_playlist() → canciones.csv
```

---

## Verificación de imports

```bash
python -c "from mpc.catalog.genre import Genre; print(Genre('salsa_dura_clasica'))"
python -c "from mpc.discovery import SearchEngine, DiscoverTracksUseCase; print('discovery OK')"
python -c "from mpc.acquisition import DownloadEngine, DownloadTrackUseCase; print('acquisition OK')"
python -c "from mpc.library import TrackRepository, LibraryIndex; print('library OK')"
python -c "from mpc.discovery.ports import IMusicCatalogPort, IStyleCatalogPort; print('ports OK')"

# Dry-run pipeline
python scripts/pipeline_music.py \
  --input .claude/skills/music-downloader/test_all_cases.csv \
  --output /tmp/test_log.csv --dry-run
```

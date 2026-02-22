# Flujos y Procesos

## Flujo completo

```
mala-pata create "pedido"
        │
        ├── [PLAN]     intent.py → classify_request()
        │              llm.py    → llm_plan()  (OpenAI o heurística)
        │
        ├── [RESOLVE]  sources/discogs.py
        │              sources/musicbrainz.py
        │              sources/spotify_client.py  (fallback artista)
        │              sources/openai_source.py   (último recurso, solo reales)
        │
        └── canciones.csv

mala-pata download
        │
        ├── [SEARCH]   pipeline_music.py
        │              query_override → YouTube ID directo
        │              yt-dlp ytsearch / YouTube API → ID
        │
        ├── [CLASSIFY] heuristic_scores() → softmax
        │              llm_call() si heurística < umbral  (CLASSIFIER_MODE)
        │
        └── [DOWNLOAD] dl-music-system.sh dl_music()
                       audio mp3 + thumbnail + ID3 tags
```

---

## Subcomandos de la CLI

| Comando | Descripción |
|---|---|
| `mala-pata create "pedido"` | Genera `canciones.csv` desde NL |
| `mala-pata create --spotify URL` | Importa desde playlist/álbum Spotify |
| `mala-pata create --artist "X" -n 10` | Playlist de un artista |
| `mala-pata create --artist "X" --album "Y"` | Tracks de un álbum |
| `mala-pata download` | Ejecuta el pipeline de descarga |
| `mala-pata delete --filename "..."` | Borra archivo + entrada del manifest |
| `mala-pata list` | Muestra `canciones.csv` |
| `mala-pata genres` | Lista los 21 géneros disponibles |

Backwards compat: `mala-pata "pedido"` (sin subcomando) → trata como `create`.

---

## Fuentes por orden de prioridad (create)

```
1. Discogs (reglas de género + anchors)
2. MusicBrainz (reglas de género + anchors)
3. Backfill canónico (BACKFILL en mpc/catalog/genres.py)
4. Spotify credentials (fallback artista)
5. OpenAI (last resort — solo canciones reales, falla explícita si artista desconocido)
```

---

## Modos de búsqueda YouTube (download)

Controlado por `SEARCH_MODE` en `.env`:

| Valor | Comportamiento |
|---|---|
| `no_api_first` | yt-dlp primero, API YouTube si falla |
| `api_first` | YouTube API primero, yt-dlp si falla |
| `no_api_only` | Solo yt-dlp (sin gastar cuota) |
| `api_only` | Solo YouTube API |

---

## Clasificador de géneros (CLASSIFY)

El paso más crítico del pipeline. **No se debe modificar sin pruebas exhaustivas con salsa.**

```
artist + title
    │
    ├── heuristic_scores()   # keywords, artists_hint, negative_rules
    │   softmax sobre 16 géneros
    │
    └── si score < umbral y CLASSIFIER_MODE != HEURISTIC_ONLY:
        llm_call()           # OpenAI con GENRE_DB como contexto
```

Modos (`CLASSIFIER_MODE`):
- `LLM_FALLBACK` (default): heurística + LLM cuando la confianza es baja
- `HEURISTIC_ONLY`: sin LLM, más rápido
- `LLM_ONLY`: siempre LLM

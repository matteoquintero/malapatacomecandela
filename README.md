# Mala Pata Come Candela – Sistema de música

Genera `canciones.csv` a partir de pedidos en lenguaje natural o playlists de Spotify, busca ID en YouTube, clasifica en 16 géneros afrolatinos y descarga el audio con metadatos.

## Estructura

```
mpc/                     # Paquete principal
  catalog/genres.py      # Única fuente de verdad de géneros
  planner/               # Interpretación de pedidos (intent + LLM)
  sources/               # Clientes API: Discogs, MusicBrainz, Spotify, OpenAI
  builders/              # Construcción de playlists y álbumes
  utils/                 # text.py, csv_io.py
  config.py              # Config desde .env
  cli.py                 # CLI unificado (subcomandos)

mala_pata.py             # Entry point: mala-pata create/download/delete/list/genres
pipeline_music.py        # Pipeline de descarga (YouTube → CLASSIFY → dl)
dl-music-system.sh       # Descarga por género con metadatos/thumbnail
delete_song.py           # Elimina canción del manifest y disco
```

## Requisitos

- Python 3.10+
- `ffmpeg` y `yt-dlp` en PATH
- (Opcional) API keys: YouTube Data v3, OpenAI; token Discogs; credenciales Spotify

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env        # editar rutas y API keys
chmod +x dl-music-system.sh
source shell_setup.zsh     # cargar aliases (en .zshrc o a mano)
```

## Uso rápido

```bash
# Generar lista desde lenguaje natural
mala-pata create "10 canciones de salsa dura underground"
mala-pata create "5 de Héctor Lavoe"
mala-pata create --artist "Ray Barretto" -n 8

# Desde Spotify
mala-pata create --spotify https://open.spotify.com/playlist/XXXX

# Ver el plan sin ejecutar
mala-pata create "10 mambos comerciales" --dry-run

# Descargar
mala-pata download          # ≡ come-candela

# Borrar una canción
mala-pata delete --filename "NG La Banda - Santa Palabra.mp3"

# Utilidades
mala-pata list
mala-pata genres
```

## Configuración (.env)

| Variable | Descripción |
|---|---|
| `LIB_BASE_DIR` | Base de tu librería de música |
| `DL_MUSIC_SCRIPT` | Ruta a `dl-music-system.sh` |
| `MANIFEST_FILE` | Registro de descargas |
| `SEARCH_MODE` | `no_api_first` \| `api_first` \| `no_api_only` \| `api_only` |
| `CLASSIFIER_MODE` | `LLM_FALLBACK` \| `HEURISTIC_ONLY` \| `LLM_ONLY` |
| `OPENAI_API_KEY` | Opcional — mejora planner y clasificador |
| `YOUTUBE_API_KEY` | Opcional — búsquedas más precisas |
| `DISCOGS_TOKEN` | Opcional — mejores resultados en create |
| `SPOTIFY_*` | Opcional — importar playlists/álbumes |

Sin `YOUTUBE_API_KEY` el sistema usa yt-dlp (`SEARCH_MODE=no_api_first`).
Sin `OPENAI_API_KEY` usa el planner heurístico y `CLASSIFIER_MODE=HEURISTIC_ONLY`.

## Aliases disponibles (shell_setup.zsh)

| Alias | Comando |
|---|---|
| `mala-pata` | `mala_pata.py` |
| `come-candela` | `mala-pata download` |
| `mala-candela` | `mala-pata delete --filename` |
| `mala-pata-spotify` | `mala-pata create --spotify` |

## Problemas comunes

**Errores SABR / "format not available":**
```bash
./test_sabr_streaming.sh VIDEO_ID
pip install --upgrade yt-dlp
```

**Sin cuota YouTube:**
```bash
./configure_no_api.sh
# o manualmente: SEARCH_MODE=no_api_only en .env
```

## Documentación

Ver `documentation/` para referencia completa de APIs, flujos y ejemplos.

## Licencia

Uso personal/experimental.

# Mala Pata Come Candela – Sistema de música

Genera `canciones.csv` a partir de pedidos en lenguaje natural o playlists de Spotify, y luego resuelve video/ID en YouTube, clasifica en 16 géneros afrolatinos y descarga el audio con metadatos.

## Estructura

- `request_to_csv.py`: genera `canciones.csv` desde un pedido natural (Discogs + MusicBrainz + opcional OpenAI).
- `spotify_to_csv.py`: exporta una playlist de Spotify a `canciones.csv`.
- `pipeline_music.py`: procesa el CSV → busca ID YouTube (API o yt-dlp) → clasifica → descarga con `dl-music-system.sh`.
- `delete_song.py`: elimina canción y fila asociada del manifest, con búsqueda por nombre de archivo.
- `dl-music-system.sh`: funciones de descarga por género y agregado de metadatos/thumbnail.

## Requisitos

- Python 3.10+ recomendado
- `ffmpeg` y `yt-dlp` instalados en el sistema
- (Opcional) API keys: YouTube Data API v3, OpenAI; token Discogs; credenciales Spotify

## Instalación

1. Crear entorno y instalar dependencias:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

1. Copiar variables de entorno y editar rutas/API keys:

```bash
cp env.example .env
```

1. Ajustar permisos del script de descarga:

```bash
chmod +x dl-music-system.sh
```

## Configuración (.env)

Variables principales:

- `DL_MUSIC_SCRIPT`: ruta al `dl-music-system.sh`.
- `LIB_BASE_DIR`: base de tu librería de música.
- `MANIFEST_FILE`: ruta del manifest (por defecto dentro del proyecto).
- `SEARCH_MODE`: `no_api_first` | `api_first` | `no_api_only` | `api_only`.
- `NOAPI_SOURCES`: `ytsearch,ytmusicsearch,scsearch`.
- `YOUTUBE_API_KEY` (opcional): activa búsquedas vía API.
- `OPENAI_API_KEY` (opcional) y `OPENAI_MODEL`.
- `DISCOGS_TOKEN` (opcional): mejora resultados.
- `SPOTIFY_*` (para `spotify_to_csv.py`).

Cachés por defecto (locales al proyecto):

- `CHANNEL_CACHE_FILE`: `.cache/yt_channel_cache.json`
- `SEARCH_CACHE_FILE`: `.cache/yt_search_cache.json`

## Uso rápido

- Generar CSV desde pedido natural:

```bash
source .venv/bin/activate
python request_to_csv.py "10 canciones de salsa dura clasica underground"
```

- Generar CSV desde playlist de Spotify:

```bash
python spotify_to_csv.py https://open.spotify.com/playlist/XXXXXXXX --count 20
```

- Ejecutar pipeline (descarga):

```bash
python pipeline_music.py --input canciones.csv --output out/log_descargas.csv
```

- Borrar una canción por filename o por artist/title:

```bash
python delete_song.py --filename "NG La Banda - Santa Palabra.mp3" --all
# o
python delete_song.py --artist "NG La Banda" --title "Santa Palabra"
```

## Notas de clasificación

- Modo `LLM_FALLBACK`: usa heurística y recurre a LLM si hace falta.
- Para forzar solo heurística: `CLASSIFIER_MODE=HEURISTIC_ONLY`.
- Para solo LLM: `CLASSIFIER_MODE=LLM_ONLY` (requiere `OPENAI_API_KEY`).

## Consejos y solución de problemas

- Si no tienes `YOUTUBE_API_KEY`, el sistema usa `yt-dlp` (`SEARCH_MODE=no_api_first`).
- Asegúrate de tener `ffmpeg` y `yt-dlp` en PATH.
- Si no descarga la miniatura, el MP3 se guarda igual con metadatos básicos.
- Si el manifest no existe, se crea automáticamente en `<proyecto>/manifest.csv` (puedes cambiarlo con `MANIFEST_FILE`).
- Discogs y MusicBrainz tienen límites; el código respeta pausas para ser amable.

## Desarrollo

- Formato CSV esperado por el pipeline: columnas `artist,title,query_override,source`.
- `query_override` puede incluir un `VIDEO_ID` o URL de YouTube; si contiene ID válido, se usa directo.

## Licencia

Uso personal/experimental.

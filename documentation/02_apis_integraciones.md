# APIs e Integraciones - Mala Pata Come Candela

## Resumen de Integraciones

El sistema integra múltiples APIs externas para proporcionar funcionalidades completas de búsqueda, clasificación y descarga de música. Cada API tiene un propósito específico y se utiliza de manera optimizada para minimizar costos y maximizar la calidad de los resultados.

## 1. YouTube Data API v3

### Propósito

- Búsqueda de videos musicales
- Obtención de metadatos de videos
- Información de canales y estadísticas

### Configuración

```bash
YOUTUBE_API_KEY=tu_api_key_aqui
YOUTUBE_MAX_RESULTS=5
YOUTUBE_CALL_BUDGET=4000000
```

### Endpoints Utilizados

#### `search.list`

- **Costo**: 100 unidades de cuota
- **Uso**: Búsqueda de videos y canales
- **Parámetros**:
  - `q`: Query de búsqueda
  - `type`: "video" o "channel"
  - `maxResults`: Número de resultados
  - `order`: "relevance"
  - `videoEmbeddable`: "true"

#### `videos.list`

- **Costo**: 1 unidad de cuota
- **Uso**: Metadatos detallados de videos
- **Parámetros**:
  - `id`: IDs de videos separados por comas
  - `part`: "contentDetails,statistics"

#### `channels.list`

- **Costo**: 1 unidad de cuota
- **Uso**: Información de canales
- **Parámetros**:
  - `id`: IDs de canales
  - `part`: "statistics,snippet"

### Estrategia de Búsqueda

#### 1. Búsqueda por Canal Oficial

```python
# Prioriza canales oficiales del artista
channels = search_official_channels(artist, per_track)
for channel in channels:
    videos = search_videos_in_channel(title, channel_id)
```

#### 2. Búsqueda General con Filtros

```python
# Filtros negativos para evitar contenido no deseado
negatives = [
    '-live', '-"en vivo"', '-"en directo"', '-concert',
    '-session', '-karaoke', '-cover', '-"full album"',
    '-lyrics', '-letra', '-subtitles', '-mix'
]
```

### Sistema de Caché

- **Archivo**: `cache/yt_search_cache.json`
- **TTL**: 45 días por defecto
- **Clave**: `{artist_normalized}|{title_normalized}`

## 2. OpenAI API

### Propósito

- Clasificación inteligente de géneros musicales
- Interpretación de solicitudes en lenguaje natural
- Análisis contextual de metadatos

### Configuración

```bash
OPENAI_API_KEY=tu_api_key_aqui
OPENAI_MODEL=gpt-4o-mini
CLASSIFIER_MODE=LLM_FALLBACK
```

### Modelos Utilizados

#### GPT-4o-mini (Recomendado)

- **Costo**: $0.15/1M tokens entrada, $0.60/1M tokens salida
- **Uso**: Clasificación de géneros, interpretación de solicitudes
- **Ventajas**: Balance costo-rendimiento

#### GPT-4 (Opcional)

- **Costo**: Mayor pero mayor precisión
- **Uso**: Para casos complejos de clasificación

### Prompts Especializados

#### Clasificación de Géneros

```python
SYSTEM_PROMPT = """
Eres musicólogo experto en salsa y géneros afrolatinos.
Clasifica EXACTAMENTE en uno de estos 16 slugs: {genres}.

Evalúa con 4 ejes:
1) Ritmo e instrumentación
2) Estilo vocal y lírica
3) Estructura musical
4) Contexto histórico/estético

Formato de salida (JSON estricto):
{
  "slug": "<género>",
  "confidence": 0.0-1.0,
  "rationale": "explicación",
  "checks": {...},
  "disqualified_genres": [...]
}
"""
```

#### Interpretación de Solicitudes

```python
PLANNER_PROMPT = """
Eres un planificador musical experto en música afrolatina.
Lee la instrucción del usuario y devuelve SOLO JSON:

{
  "task": "album" | "playlist",
  "count": <int>,
  "genre": <string>,
  "substyle": "underground" | "comercial",
  "artist": <string>,
  "album": <string>
}
"""
```

### Modos de Clasificación

#### LLM_FALLBACK (Recomendado)

1. Intenta clasificación heurística
2. Si confianza < 0.80, usa LLM
3. Combina resultados para decisión final

#### LLM_ONLY

- Usa únicamente OpenAI para clasificación
- Mayor precisión pero mayor costo

#### HEURISTIC_ONLY

- Solo clasificación basada en reglas
- Sin costo de API pero menor precisión

## 3. Discogs API

### Propósito

- Base de datos musical especializada
- Metadatos detallados de releases
- Información de artistas y géneros

### Configuración

```bash
DISCOGS_TOKEN=tu_token_aqui
```

### Funcionalidades

#### Búsqueda por Género

```python
def discogs_search_rule(genre_key, rule, limit=100):
    styles = DISCOGS_STYLE_MAP.get(genre_key, [])
    for style in styles:
        results = discogs.search(
            type="release",
            genre="Latin",
            style=style
        )
```

#### Búsqueda por Artista

```python
def discogs_search_by_artist(artist, limit=120):
    results = discogs.search(
        type="release",
        artist=artist,
        genre="Latin"
    )
```

### Mapeo de Géneros

```python
DISCOGS_STYLE_MAP = {
    "salsa_dura_clasica": ["Salsa"],
    "boogaloo": ["Boogaloo"],
    "mambo": ["Mambo"],
    "latin_soul": ["Latin Soul", "Soul", "Funk"],
    "son_cubano": ["Son", "Son Montuno"],
    # ... más mapeos
}
```

## 4. MusicBrainz API

### Propósito

- Base de datos musical libre
- Metadatos de grabaciones y releases
- Información de artistas y álbumes

### Endpoints Utilizados

#### Búsqueda de Grabaciones

```python
def mb_search_recordings(query, limit=100):
    data = mb_get("recording", {
        "query": query,
        "limit": limit,
        "offset": 0
    })
```

#### Búsqueda de Release Groups

```python
def mb_search_release(artist, album):
    query = f'artist:"{artist}" AND releasegroup:"{album}"'
    data = mb_get("release-group", {
        "query": query,
        "limit": 5
    })
```

### Rate Limiting

- **Pausa**: 1 segundo entre llamadas
- **User-Agent**: "mala-pata-come-candela/1.0 (mateoquintero)"
- **Formato**: JSON por defecto

## 5. Spotify Web API

### Propósito

- Integración con playlists y álbumes de Spotify
- Extracción de metadatos de tracks
- Autenticación OAuth2

### Configuración

```bash
SPOTIFY_CLIENT_ID=tu_client_id
SPOTIFY_CLIENT_SECRET=tu_client_secret
SPOTIFY_REDIRECT_URI=https://localhost:8080/callback
```

### Flujo de Autenticación

#### 1. OAuth2 Authorization Code

```python
scope = "playlist-read-private playlist-read-collaborative"
auth = SpotifyOAuth(
    client_id=cid,
    client_secret=secret,
    redirect_uri=redirect,
    scope=scope,
    cache_path=cache_path
)
```

#### 2. Obtención de Tracks

##### Playlists

```python
def fetch_playlist_tracks(sp, playlist_id, limit_count=None):
    results = sp.playlist_items(
        playlist_id,
        fields="items(track(name,artists(name),album(name))),next",
        additional_types=["track"]
    )
```

##### Álbumes

```python
def fetch_album_tracks(sp, album_id, limit_count=None):
    album = sp.album(album_id)
    album_name = album.get("name", "")
    results = sp.album_tracks(album_id, limit=50, offset=0)
```

### Parsing de URLs

```python
def parse_playlist_id(s):
    if "open.spotify.com/playlist/" in s:
        part = s.split("open.spotify.com/playlist/")[1]
        return part.split("?")[0].split("/")[0]
    return s

def parse_album_id(s):
    if "open.spotify.com/album/" in s:
        part = s.split("open.spotify.com/album/")[1]
        return part.split("?")[0].split("/")[0]
    return s
```

### Detección Automática (No Requiere --type)

El sistema detecta automáticamente si una URL es de playlist o álbum **sin necesidad de especificar parámetros adicionales**:

```python
# Detección automática por presencia de "album" en la URL
source_type = args.type  # Solo si el usuario lo especificó (opcional)
if not source_type:
    # Detección automática
    if "album" in args.source or ":album:" in args.source:
        source_type = "album"
    else:
        source_type = "playlist"
```

**Ejemplos:**

```bash
# Detecta automáticamente el tipo
mala-pata create --spotify https://open.spotify.com/playlist/37i9dQZF1DX8S0uQvJ4gaa
mala-pata create --spotify https://open.spotify.com/album/6s84u2TUpR3wdUv4NgKA2j

# Forzar tipo y limitar canciones
mala-pata create --spotify URL --type album --count 10 --genre mambo
```

## 6. yt-dlp (Sin API)

### Propósito

- Búsqueda de videos sin usar YouTube API
- Alternativa cuando se agota la cuota
- Múltiples fuentes de búsqueda

### Configuración

```bash
SEARCH_MODE=no_api_first
NOAPI_SOURCES=ytsearch,scsearch
YTDLP_BIN=yt-dlp
```

### Fuentes de Búsqueda

#### ytsearch

- Búsqueda estándar de YouTube
- Sin costo de API
- Resultados limitados

#### scsearch

- Búsqueda en SoundCloud
- Contenido alternativo
- Diferentes metadatos

### Implementación

```python
def yt_dlp_search(query, max_results=5, source="ytsearch"):
    cmd = [
        YTDLP_BIN, f"{source}{max_results}:{query}",
        "--skip-download",
        "--print", "%(id)s|||%(title)s|||%(uploader)s"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
```

## Estrategias de Optimización

### 1. Sistema de Caché Inteligente

- **Búsquedas**: TTL de 45 días
- **Canales**: TTL de 30 días
- **Deduplicación**: Por clave normalizada

### 2. Fallback Automático

```python
if SEARCH_MODE == "no_api_first":
    results = try_noapi_search()
    if not results and budget_left() > 0:
        results = try_api_search()
```

### 3. Gestión de Cuotas

- **Presupuesto**: 4M unidades YouTube por defecto
- **Monitoreo**: Seguimiento en tiempo real
- **Alertas**: Notificación cuando se agota

### 4. Rate Limiting

- **MusicBrainz**: 1 segundo entre llamadas
- **Discogs**: Respeta límites de la API
- **OpenAI**: Sin límites adicionales

## Manejo de Errores

### Tipos de Errores

1. **API Rate Limits**: Pausa y reintento
2. **Cuota Agotada**: Cambio a modo sin API
3. **Errores de Red**: Reintento con backoff
4. **Datos Inválidos**: Fallback a valores por defecto

### Estrategias de Recuperación

```python
try:
    result = api_call()
except RateLimitError:
    time.sleep(backoff_time)
    result = api_call()
except QuotaExceededError:
    result = fallback_noapi_search()
```

## Monitoreo y Métricas

### Métricas de API

- **Cuota Utilizada**: Por endpoint y total
- **Tasa de Éxito**: Porcentaje de llamadas exitosas
- **Tiempo de Respuesta**: Latencia promedio
- **Errores**: Tipos y frecuencias

### Logs Estructurados

```json
{
	"timestamp": "2024-01-01T12:00:00Z",
	"api": "youtube",
	"endpoint": "search.list",
	"quota_used": 100,
	"success": true,
	"response_time_ms": 250
}
```

## Consideraciones de Costo

### YouTube API

- **Búsqueda**: $0.00 (gratis hasta 10,000 unidades/día)
- **Videos**: $0.00 (gratis)
- **Canales**: $0.00 (gratis)

### OpenAI

- **GPT-4o-mini**: ~$0.001 por clasificación
- **GPT-4**: ~$0.01 por clasificación

### Discogs

- **Gratuito**: Hasta 60 requests/minuto
- **Pro**: $20/mes para límites mayores

### MusicBrainz

- **Completamente Gratuito**: Sin límites de costo

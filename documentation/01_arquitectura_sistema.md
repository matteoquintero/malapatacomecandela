# Arquitectura del Sistema Mala Pata Come Candela

## Visión General

El sistema **Mala Pata Come Candela** es una plataforma automatizada para la descarga y organización de música afrolatina. El sistema procesa solicitudes en lenguaje natural, busca contenido en YouTube, clasifica automáticamente en 16 géneros específicos y descarga audio con metadatos completos.

## Componentes Principales

### 1. Módulos de Entrada de Datos

#### `request_to_csv.py`

- **Propósito**: Convierte solicitudes en lenguaje natural a listas de canciones
- **Tecnologías**: OpenAI GPT, Discogs API, MusicBrainz API
- **Funcionalidades**:
  - Interpretación de solicitudes naturales
  - Búsqueda en bases de datos musicales
  - Generación de CSV con metadatos

#### `spotify_to_csv.py`

- **Propósito**: Exporta playlists de Spotify a formato CSV
- **Tecnologías**: Spotify Web API, OAuth2
- **Funcionalidades**:
  - Autenticación con Spotify
  - Extracción de tracks de playlists
  - Formateo de datos para el pipeline

### 2. Motor de Procesamiento

#### `pipeline_music.py`

- **Propósito**: Motor principal de procesamiento y descarga
- **Tecnologías**: YouTube Data API, yt-dlp, OpenAI, ffmpeg
- **Funcionalidades**:
  - Búsqueda de videos en YouTube
  - Clasificación automática de géneros
  - Descarga y procesamiento de audio
  - Gestión de metadatos y thumbnails

### 3. Sistema de Descarga

#### `dl-music-system.sh`

- **Propósito**: Script de descarga con funciones especializadas por género
- **Tecnologías**: yt-dlp, ffmpeg, curl
- **Funcionalidades**:
  - 16 funciones específicas por género musical
  - Descarga de audio en formato MP3
  - Inserción de metadatos y artwork
  - Organización por directorios de género

### 4. Utilidades

#### `delete_song.py`

- **Propósito**: Gestión de eliminación de canciones
- **Funcionalidades**:
  - Búsqueda por múltiples criterios
  - Eliminación de archivos y registros
  - Mantenimiento de consistencia

## Arquitectura de Datos

### Flujo de Información

```
Solicitud Natural/Spotify → CSV → YouTube Search → Clasificación → Descarga → Organización
```

### Estructura de Archivos

```
malapatacomecandela_system/
├── cache/                    # Cachés del sistema
│   ├── manifest.csv         # Registro de descargas
│   ├── yt_channel_cache.json
│   ├── yt_search_cache.json
│   └── genres_ref.json
├── out/                     # Logs de procesamiento
│   └── log_descargas.csv
├── documentation/           # Documentación técnica
└── [archivos Python]       # Módulos principales
```

### Base de Datos de Géneros

El sistema maneja 16 géneros específicos de música afrolatina:

1. **Son Cubano** - `son_cubano`
2. **Guajira Moderna** - `guajira_moderna`
3. **Guaracha** - `guaracha`
4. **Rumba Guaguancó** - `rumba_guaguanco`
5. **Afro Cuban Jazz Descarga** - `afro_cuban_jazz_descarga`
6. **Mambo** - `mambo`
7. **Cha Cha Cha** - `cha_cha_cha`
8. **Boogaloo** - `boogaloo`
9. **Salsa Dura Clásica** - `salsa_dura_clasica`
10. **Guaguancó Fusionado** - `guaguanco_fusionado`
11. **Exotica** - `exotica`
12. **Latin Soul** - `latin_soul`
13. **Plena Bomba** - `plena_bomba`
14. **Salsa Romántica** - `salsa_romantica`
15. **Timba** - `timba`
16. **Salsa Dura Revival** - `salsa_dura_revival`

## Tecnologías y Dependencias

### APIs Externas

- **YouTube Data API v3**: Búsqueda de videos
- **OpenAI API**: Clasificación inteligente de géneros
- **Discogs API**: Base de datos musical
- **MusicBrainz API**: Metadatos musicales
- **Spotify Web API**: Integración con playlists

### Herramientas de Sistema

- **yt-dlp**: Descarga de contenido multimedia
- **ffmpeg**: Procesamiento de audio
- **curl**: Descarga de thumbnails

### Librerías Python

- `google-api-python-client`: Integración YouTube
- `openai`: Clasificación con IA
- `discogs-client`: Acceso a Discogs
- `spotipy`: Integración Spotify
- `requests`: Comunicación HTTP

## Patrones de Diseño

### 1. Pipeline de Procesamiento

- **Patrón**: Pipeline/Chain of Responsibility
- **Implementación**: Flujo secuencial de transformaciones
- **Beneficios**: Modularidad, extensibilidad, mantenibilidad

### 2. Sistema de Caché

- **Patrón**: Cache-Aside
- **Implementación**: Cachés JSON para YouTube y búsquedas
- **Beneficios**: Reducción de llamadas API, mejora de rendimiento

### 3. Clasificación Híbrida

- **Patrón**: Strategy + Fallback
- **Implementación**: Heurística + LLM como respaldo
- **Beneficios**: Eficiencia y precisión balanceadas

### 4. Gestión de Estado

- **Patrón**: Manifest/Registry
- **Implementación**: CSV como base de datos de estado
- **Beneficios**: Persistencia, trazabilidad, recuperación

## Consideraciones de Rendimiento

### Optimizaciones Implementadas

1. **Caché de Búsquedas**: TTL configurable para resultados
2. **Búsqueda Sin API**: yt-dlp como alternativa a YouTube API
3. **Procesamiento por Lotes**: Manejo eficiente de múltiples tracks
4. **Deduplicación**: Prevención de descargas duplicadas

### Límites y Cuotas

- **YouTube API**: 4M unidades de cuota por defecto
- **OpenAI**: Límites por modelo y uso
- **Rate Limiting**: Pausas entre llamadas a APIs externas

## Seguridad y Privacidad

### Manejo de Credenciales

- Variables de entorno para API keys
- Archivo `.env` excluido del control de versiones
- Tokens de acceso con expiración

### Datos Sensibles

- No almacenamiento de contenido protegido por derechos
- Uso solo para fines personales/educativos
- Respeto a términos de servicio de APIs

## Escalabilidad

### Puntos de Extensión

1. **Nuevos Géneros**: Adición fácil de categorías musicales
2. **Fuentes de Datos**: Integración con nuevas APIs
3. **Formatos de Salida**: Soporte para diferentes formatos de audio
4. **Clasificadores**: Implementación de nuevos algoritmos de IA

### Limitaciones Actuales

- Procesamiento secuencial (no paralelo)
- Dependencia de APIs externas
- Almacenamiento local únicamente

## Monitoreo y Logging

### Sistema de Logs

- **CSV de Procesamiento**: Registro detallado de cada operación
- **Logs de Error**: Captura de excepciones y fallos
- **Métricas de API**: Seguimiento de uso de cuotas

### Indicadores de Salud

- Tasa de éxito de descargas
- Uso de cuotas de API
- Tiempo de procesamiento por track
- Calidad de clasificación de géneros

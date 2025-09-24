# Uso y Ejemplos - Mala Pata Come Candela

## Guía de Uso Rápido

### Comandos Básicos

#### 1. Generar Lista desde Solicitud Natural

```bash
# Activar entorno virtual
source .venv/bin/activate

# Solicitud básica
python request_to_csv.py "10 canciones de salsa dura clasica"

# Con especificaciones
python request_to_csv.py "15 boogaloos underground de los 60s"

# Por artista específico
python request_to_csv.py "8 canciones de Willie Colón"
```

#### 2. Generar Lista desde Spotify

```bash
# Playlist completa
python spotify_to_csv.py https://open.spotify.com/playlist/37i9dQZF1DX8S0uQvJ4gaa

# Con límite de canciones
python spotify_to_csv.py https://open.spotify.com/playlist/37i9dQZF1DX8S0uQvJ4gaa --count 20
```

#### 3. Ejecutar Pipeline de Descarga

```bash
# Descarga completa
python pipeline_music.py --input canciones.csv --output out/log_descargas.csv

# Modo dry-run (solo búsqueda y clasificación)
python pipeline_music.py --input canciones.csv --output out/log_descargas.csv --dry-run

# Con tipo de imagen específico
python pipeline_music.py --input canciones.csv --output out/log_descargas.csv --image-type max
```

#### 4. Eliminar Canciones

```bash
# Por nombre de archivo
python delete_song.py --filename "Willie Colón - Aguanilé.mp3"

# Por artista y título
python delete_song.py --artist "Willie Colón" --title "Aguanilé"

# Eliminar todas las coincidencias
python delete_song.py --artist "Willie Colón" --all
```

## Ejemplos Detallados

### Ejemplo 1: Playlist de Salsa Dura Clásica

#### Solicitud

```bash
python request_to_csv.py "20 canciones de salsa dura clasica de los 70s"
```

#### Proceso Interno

1. **Interpretación**: Sistema detecta género "salsa_dura_clasica", época "70s", cantidad "20"
2. **Búsqueda**: Consulta Discogs y MusicBrainz por releases de salsa de los 70s
3. **Filtrado**: Prioriza artistas como Willie Colón, Héctor Lavoe, Fania All Stars
4. **Generación**: Crea `canciones.csv` con 20 tracks

#### Resultado Esperado

```csv
artist,title,query_override,source
Willie Colón & Héctor Lavoe,Aguanilé,Willie Colón & Héctor Lavoe Aguanilé,discogs
Rubén Blades & Willie Colón,Plástico,Rubén Blades & Willie Colón Plástico,discogs
Ray Barretto,Indestructible,Ray Barretto Indestructible,musicbrainz
...
```

### Ejemplo 2: Playlist de Boogaloo Underground

#### Solicitud

```bash
python request_to_csv.py "12 boogaloos underground de Nueva York"
```

#### Proceso Interno

1. **Interpretación**: Género "boogaloo", substyle "underground", ubicación "Nueva York"
2. **Búsqueda**: Enfoca en artistas menos conocidos del boogaloo
3. **Filtrado**: Evita hits comerciales, prioriza rarezas
4. **Generación**: Lista curatorial de 12 tracks

### Ejemplo 3: Álbum Específico

#### Solicitud

```bash
python request_to_csv.py "álbum 'Siembra' de Rubén Blades y Willie Colón"
```

#### Proceso Interno

1. **Interpretación**: task="album", artist="Rubén Blades", album="Siembra"
2. **Búsqueda**: MusicBrainz busca el release group específico
3. **Extracción**: Obtiene tracklist completo del álbum
4. **Generación**: CSV con todas las canciones del álbum

### Ejemplo 4: Integración con Spotify

#### Playlist de Usuario

```bash
python spotify_to_csv.py https://open.spotify.com/playlist/37i9dQZF1DX8S0uQvJ4gaa --count 15
```

#### Proceso Interno

1. **Autenticación**: OAuth2 con Spotify
2. **Extracción**: Obtiene tracks de la playlist
3. **Formateo**: Convierte a formato CSV del sistema
4. **Deduplicación**: Elimina duplicados por artista-título

## Casos de Uso Avanzados

### Caso 1: Descarga Masiva con Control de Calidad

#### Configuración

```bash
# .env
SEARCH_MODE=api_first
YOUTUBE_CALL_BUDGET=1000000
CLASSIFIER_MODE=LLM_ONLY
```

#### Ejecución

```bash
# Generar lista grande
python request_to_csv.py "50 canciones de timba cubana"

# Procesar con alta calidad
python pipeline_music.py --input canciones.csv --output out/log_descargas.csv --image-type max
```

#### Resultado

- Búsquedas prioritarias con YouTube API
- Clasificación con IA para máxima precisión
- Thumbnails en máxima resolución
- Log detallado de cada operación

### Caso 2: Modo Económico (Sin APIs)

#### Configuración

```bash
# .env
SEARCH_MODE=no_api_only
CLASSIFIER_MODE=HEURISTIC_ONLY
```

#### Ejecución

```bash
# Procesar sin costo de APIs
python pipeline_music.py --input canciones.csv --output out/log_descargas.csv
```

#### Resultado

- Búsquedas solo con yt-dlp
- Clasificación basada en reglas
- Sin costos de API
- Procesamiento más lento pero gratuito

### Caso 3: Recuperación de Errores

#### Problema: Cuota de API Agotada

```bash
# El sistema automáticamente cambia a modo sin API
python pipeline_music.py --input canciones.csv --output out/log_descargas.csv
```

#### Log de Recuperación

```
⚠️ Presupuesto API agotado, cambiando a modo sin API...
🌐 Modo búsqueda: NO_API_ONLY
🔍 ytsearch resultados (no API): 3
✅ Candidato elegido: [título] ([video_id])
```

### Caso 4: Gestión de Librería

#### Verificar Estado

```bash
# Ver manifest actual
head -10 cache/manifest.csv

# Ver estadísticas
wc -l cache/manifest.csv
```

#### Limpiar Duplicados

```bash
# Buscar archivos duplicados
find "$LIB_BASE_DIR" -name "*.mp3" | sort | uniq -d

# Eliminar duplicados específicos
python delete_song.py --filename "Artista - Título.mp3" --all
```

#### Reorganizar por Género

```bash
# El sistema ya organiza automáticamente, pero puedes verificar
ls -la "$LIB_BASE_DIR"/
```

## Mejores Prácticas

### 1. Gestión de APIs

#### Optimizar Uso de YouTube API

```bash
# Configuración eficiente
YOUTUBE_CALL_BUDGET=2000000  # 2M unidades
SEARCH_MODE=no_api_first     # Priorizar yt-dlp
YOUTUBE_MAX_RESULTS=3        # Menos resultados por búsqueda
```

#### Monitorear Cuotas

```bash
# Verificar uso actual
grep "Unidades gastadas" out/log_descargas.csv | tail -1
```

### 2. Calidad de Resultados

#### Configuración de Alta Precisión

```bash
# .env
CLASSIFIER_MODE=LLM_ONLY
OPENAI_MODEL=gpt-4o-mini
PASS_HEURISTIC_TO_LLM=true
```

#### Validación Manual

```bash
# Revisar clasificaciones
grep "predicted_genre" out/log_descargas.csv | sort | uniq -c
```

### 3. Organización de Archivos

#### Estructura Recomendada

```
~/Music/mala_pata_come_candela/
├── salsa_dura_clasica/
├── salsa_romantica/
├── boogaloo/
├── mambo/
├── son_cubano/
├── timba/
└── [otros géneros]/
```

#### Nomenclatura de Archivos

```
Artista - Título.mp3
```

### 4. Mantenimiento del Sistema

#### Limpieza Regular

```bash
# Limpiar cachés expirados (automático)
# Limpiar archivos temporales
rm -f /tmp/thumbnail_*.jpg

# Verificar espacio en disco
df -h "$LIB_BASE_DIR"
```

#### Backup de Configuración

```bash
# Backup de manifest
cp cache/manifest.csv cache/manifest_$(date +%Y%m%d).csv

# Backup de configuración
cp .env .env.backup
```

## Solución de Problemas Comunes

### Problema 1: "No se encontraron resultados"

#### Causas Posibles

- Género muy específico o poco común
- Artista con nombre poco común
- Filtros muy restrictivos

#### Soluciones

```bash
# Ampliar búsqueda
python request_to_csv.py "salsa en general"  # En lugar de género específico

# Usar backfill
# El sistema automáticamente usa canciones canónicas si no encuentra suficientes
```

### Problema 2: "Error de descarga"

#### Verificar Dependencias

```bash
# Verificar yt-dlp
yt-dlp --version

# Verificar ffmpeg
ffmpeg -version

# Verificar permisos
ls -la dl-music-system.sh
```

#### Logs de Debug

```bash
# Ver errores específicos
tail -20 out/log_descargas.csv | grep "error"
```

### Problema 3: "Clasificación incorrecta"

#### Ajustar Configuración

```bash
# Usar solo LLM para mayor precisión
CLASSIFIER_MODE=LLM_ONLY

# O solo heurística para consistencia
CLASSIFIER_MODE=HEURISTIC_ONLY
```

#### Validar Géneros

```bash
# Ver géneros disponibles
python -c "from pipeline_music import GENRE_COMMAND; print(list(GENRE_COMMAND.keys()))"
```

### Problema 4: "Cuota de API agotada"

#### Configuración de Emergencia

```bash
# Cambiar a modo sin API
SEARCH_MODE=no_api_only
CLASSIFIER_MODE=HEURISTIC_ONLY
```

#### Recuperar Presupuesto

```bash
# YouTube API se renueva diariamente
# OpenAI tiene límites mensuales
```

## Scripts de Automatización

### Script de Descarga Diaria

```bash
#!/bin/bash
# daily_download.sh

# Activar entorno
source .venv/bin/activate

# Generar lista del día
python request_to_csv.py "10 canciones de salsa dura clasica"

# Procesar
python pipeline_music.py --input canciones.csv --output out/log_$(date +%Y%m%d).csv

# Limpiar
rm canciones.csv

echo "Descarga diaria completada: $(date)"
```

### Script de Monitoreo

```bash
#!/bin/bash
# monitor_system.sh

echo "=== Estado del Sistema ==="
echo "Fecha: $(date)"
echo "Espacio en disco: $(df -h . | tail -1 | awk '{print $4}')"
echo "Archivos en librería: $(find "$LIB_BASE_DIR" -name "*.mp3" | wc -l)"
echo "Entradas en manifest: $(wc -l < cache/manifest.csv)"
echo "Última descarga: $(tail -1 cache/manifest.csv | cut -d',' -f1)"
```

### Script de Limpieza

```bash
#!/bin/bash
# cleanup_system.sh

# Limpiar archivos temporales
rm -f /tmp/thumbnail_*.jpg

# Limpiar logs antiguos (más de 30 días)
find out/ -name "*.csv" -mtime +30 -delete

# Limpiar cachés expirados
python -c "
import os, json, datetime
from datetime import timedelta

# Limpiar caché de búsquedas
cache_file = 'cache/yt_search_cache.json'
if os.path.exists(cache_file):
    with open(cache_file, 'r') as f:
        cache = json.load(f)

    cutoff = datetime.datetime.now() - timedelta(days=45)
    expired = [k for k, v in cache.items()
               if datetime.datetime.fromisoformat(v['ts']) < cutoff]

    for k in expired:
        del cache[k]

    with open(cache_file, 'w') as f:
        json.dump(cache, f, indent=2)

    print(f'Limpiados {len(expired)} elementos expirados')
"

echo "Limpieza completada"
```

## Integración con Otros Sistemas

### Integración con Music Players

#### MPD (Music Player Daemon)

```bash
# Actualizar base de datos MPD
mpc update

# Agregar directorio específico
mpc add "$LIB_BASE_DIR/salsa_dura_clasica"
```

#### iTunes/music

```bash
# En macOS, el directorio se sincroniza automáticamente
# Verificar en Music.app
```

### Integración con Sistemas de Backup

#### rsync

```bash
# Backup a servidor remoto
rsync -av "$LIB_BASE_DIR/" user@server:/backup/music/
```

#### Time Machine (macOS)

```bash
# El directorio se incluye automáticamente en Time Machine
# Verificar en Preferencias del Sistema > Time Machine
```

## Métricas y Análisis

### Estadísticas de Uso

```bash
# Canciones por género
cut -d',' -f6 cache/manifest.csv | sort | uniq -c | sort -nr

# Artistas más descargados
cut -d',' -f2 cache/manifest.csv | sort | uniq -c | sort -nr | head -10

# Fechas de descarga
cut -d',' -f1 cache/manifest.csv | cut -d'T' -f1 | sort | uniq -c
```

### Análisis de Calidad

```bash
# Tasa de éxito de descargas
grep -c "downloaded" out/log_descargas.csv
grep -c "error" out/log_descargas.csv

# Distribución de confianza en clasificación
cut -d',' -f6 out/log_descargas.csv | sort -n | tail -10
```

## Personalización Avanzada

### Agregar Nuevos Géneros

```python
# En pipeline_music.py
GENRE_COMMAND["bachata"] = "dl-bachata"

# En dl-music-system.sh
dl-bachata() { dl_music "dl-bachata" "$@"; }

# Mapeo de directorio
case $GENERO in
    "dl-bachata") GENRE_DIR="bachata" ;;
esac
```

### Personalizar Clasificación

```python
# Agregar reglas específicas
GENRE_RULES["bachata"] = {
    "query_hint": ["bachata", "guitarra", "bongó"],
    "negative_hint": ["salsa", "merengue"],
    "mb_tags": ["bachata", "dominican"]
}
```

### Configurar Fuentes Personalizadas

```python
# Agregar nueva fuente de búsqueda
def custom_search_source(query, limit=5):
    # Implementar búsqueda personalizada
    return results
```

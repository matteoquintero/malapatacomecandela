# Instalación y Configuración - Mala Pata Come Candela

## Requisitos del Sistema

### Requisitos Mínimos

- **Sistema Operativo**: macOS, Linux, o Windows con WSL
- **Python**: 3.10 o superior (recomendado 3.11+)
- **Memoria RAM**: 4GB mínimo, 8GB recomendado
- **Espacio en Disco**: 2GB para instalación + espacio para música
- **Conexión a Internet**: Requerida para APIs y descargas

### Dependencias del Sistema

#### Herramientas Requeridas

```bash
# macOS (con Homebrew)
brew install ffmpeg yt-dlp

# Ubuntu/Debian
sudo apt update
sudo apt install ffmpeg
pip install yt-dlp

# CentOS/RHEL
sudo yum install ffmpeg
pip install yt-dlp

# Windows (con Chocolatey)
choco install ffmpeg
pip install yt-dlp
```

#### Verificación de Dependencias

```bash
# Verificar instalaciones
ffmpeg -version
yt-dlp --version
python3 --version
```

## Instalación Paso a Paso

### 1. Clonar o Descargar el Proyecto

```bash
# Opción 1: Clonar repositorio (si está en Git)
git clone <repository-url>
cd malapatacomecandela_system

# Opción 2: Descargar y extraer
# Descargar el archivo ZIP y extraer en el directorio deseado
cd malapatacomecandela_system
```

### 2. Crear Entorno Virtual

```bash
# Crear entorno virtual
python3 -m venv .venv

# Activar entorno virtual
# En macOS/Linux:
source .venv/bin/activate

# En Windows:
.venv\Scripts\activate
```

### 3. Instalar Dependencias Python

```bash
# Actualizar pip
pip install --upgrade pip

# Instalar dependencias
pip install -r requirements.txt
```

### 4. Configurar Variables de Entorno

```bash
# Copiar archivo de ejemplo
cp env.example .env

# Editar configuración
nano .env  # o usar tu editor preferido
```

### 5. Configurar Permisos

```bash
# Hacer ejecutable el script de descarga
chmod +x dl-music-system.sh

# Verificar permisos
ls -la dl-music-system.sh
```

## Configuración Detallada

### Archivo .env

#### Configuración Básica

```bash
# Rutas del sistema (AJUSTAR A TU SISTEMA)
DL_MUSIC_SCRIPT=/ruta/completa/al/dl-music-system.sh
LIB_BASE_DIR=/ruta/a/tu/libreria/musica
MANIFEST_FILE=/ruta/al/proyecto/cache/manifest.csv

# Directorio base de música (ejemplo)
LIB_BASE_DIR=/Users/tuusuario/Music/mala_pata_come_candela
```

#### APIs Opcionales

```bash
# OpenAI (para clasificación inteligente)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# YouTube Data API (para búsquedas mejoradas)
YOUTUBE_API_KEY=AIza...

# Discogs (para mejores resultados)
DISCOGS_TOKEN=tu_token_discogs

# Spotify (para integración con playlists)
SPOTIFY_CLIENT_ID=tu_client_id
SPOTIFY_CLIENT_SECRET=tu_client_secret
SPOTIFY_REDIRECT_URI=https://localhost:8080/callback
```

#### Configuración de Búsqueda

```bash
# Modo de búsqueda
SEARCH_MODE=no_api_first  # no_api_first | api_first | no_api_only | api_only

# Fuentes sin API
NOAPI_SOURCES=ytsearch,ytmusicsearch,scsearch

# Presupuesto YouTube API
YOUTUBE_CALL_BUDGET=4000000
YOUTUBE_MAX_RESULTS=5
```

#### Configuración de Clasificación

```bash
# Modo de clasificador
CLASSIFIER_MODE=LLM_FALLBACK  # LLM_ONLY | LLM_FALLBACK | HEURISTIC_ONLY

# Pasar heurística al LLM
PASS_HEURISTIC_TO_LLM=false
```

### Estructura de Directorios

#### Crear Estructura Inicial

```bash
# Crear directorios necesarios
mkdir -p cache
mkdir -p out
mkdir -p "$(dirname "$LIB_BASE_DIR")"

# Crear directorios por género
for genre in salsa_dura_clasica salsa_romantica boogaloo mambo son_cubano; do
    mkdir -p "$LIB_BASE_DIR/$genre"
done
```

#### Estructura Final

```
malapatacomecandela_system/
├── .venv/                    # Entorno virtual
├── cache/                    # Cachés del sistema
│   ├── manifest.csv         # Registro de descargas
│   ├── yt_channel_cache.json
│   ├── yt_search_cache.json
│   └── spotify_token_cache
├── out/                     # Logs de procesamiento
├── documentation/           # Documentación
├── .env                     # Configuración
├── requirements.txt         # Dependencias
└── [archivos Python]       # Código fuente
```

## Configuración de APIs

### 1. YouTube Data API v3

#### Obtener API Key

1. Ir a [Google Cloud Console](https://console.cloud.google.com/)
2. Crear nuevo proyecto o seleccionar existente
3. Habilitar YouTube Data API v3
4. Crear credenciales (API Key)
5. Configurar restricciones (opcional)

#### Configurar en .env

```bash
YOUTUBE_API_KEY=AIzaSyC...tu_api_key_aqui
YOUTUBE_CALL_BUDGET=4000000  # 4M unidades (gratis)
```

### 2. OpenAI API

#### Obtener API Key

1. Ir a [OpenAI Platform](https://platform.openai.com/)
2. Crear cuenta o iniciar sesión
3. Ir a API Keys
4. Crear nueva API key
5. Configurar límites de uso

#### Configurar en .env

```bash
OPENAI_API_KEY=sk-...tu_api_key_aqui
OPENAI_MODEL=gpt-4o-mini  # Modelo recomendado
```

### 3. Discogs API

#### Obtener Token

1. Ir a [Discogs Developers](https://www.discogs.com/settings/developers)
2. Crear nueva aplicación
3. Copiar User Token
4. Configurar User-Agent

#### Configurar en .env

```bash
DISCOGS_TOKEN=tu_token_discogs_aqui
```

### 4. Spotify API

#### Configurar Aplicación

1. Ir a [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Crear nueva aplicación
3. Configurar Redirect URI: `https://localhost:8080/callback`
4. Copiar Client ID y Client Secret

#### Configurar en .env

```bash
SPOTIFY_CLIENT_ID=tu_client_id_aqui
SPOTIFY_CLIENT_SECRET=tu_client_secret_aqui
SPOTIFY_REDIRECT_URI=https://localhost:8080/callback
```

## Verificación de Instalación

### Script de Verificación

```bash
#!/bin/bash
# verify_installation.sh

echo "🔍 Verificando instalación de Mala Pata Come Candela..."

# Verificar Python
if command -v python3 &> /dev/null; then
    echo "✅ Python3: $(python3 --version)"
else
    echo "❌ Python3 no encontrado"
    exit 1
fi

# Verificar ffmpeg
if command -v ffmpeg &> /dev/null; then
    echo "✅ ffmpeg: $(ffmpeg -version | head -n1)"
else
    echo "❌ ffmpeg no encontrado"
    exit 1
fi

# Verificar yt-dlp
if command -v yt-dlp &> /dev/null; then
    echo "✅ yt-dlp: $(yt-dlp --version)"
else
    echo "❌ yt-dlp no encontrado"
    exit 1
fi

# Verificar entorno virtual
if [ -d ".venv" ]; then
    echo "✅ Entorno virtual encontrado"
else
    echo "❌ Entorno virtual no encontrado"
    exit 1
fi

# Verificar archivo .env
if [ -f ".env" ]; then
    echo "✅ Archivo .env encontrado"
else
    echo "❌ Archivo .env no encontrado"
    exit 1
fi

# Verificar script de descarga
if [ -f "dl-music-system.sh" ] && [ -x "dl-music-system.sh" ]; then
    echo "✅ Script de descarga ejecutable"
else
    echo "❌ Script de descarga no encontrado o no ejecutable"
    exit 1
fi

# Verificar dependencias Python
source .venv/bin/activate
if python -c "import requests, openai, spotipy" 2>/dev/null; then
    echo "✅ Dependencias Python instaladas"
else
    echo "❌ Dependencias Python faltantes"
    exit 1
fi

echo "🎉 Instalación verificada correctamente!"
```

### Ejecutar Verificación

```bash
chmod +x verify_installation.sh
./verify_installation.sh
```

## Configuración Avanzada

### Personalización de Géneros

#### Agregar Nuevo Género

```python
# En pipeline_music.py, agregar a GENRE_COMMAND
GENRE_COMMAND["nuevo_genero"] = "dl-nuevo-genero"

# En dl-music-system.sh, agregar función
dl-nuevo-genero() { dl_music "dl-nuevo-genero" "$@"; }

# Agregar mapeo de directorio
case $GENERO in
    "dl-nuevo-genero") GENRE_DIR="nuevo_genero" ;;
    # ... otros géneros
esac
```

### Configuración de Caché

#### Ajustar TTL de Caché

```bash
# En .env
CHANNEL_CACHE_TTL_DAYS=30    # Caché de canales
SEARCH_CACHE_TTL_DAYS=45     # Caché de búsquedas
```

#### Limpiar Caché

```bash
# Limpiar cachés manualmente
rm -f cache/yt_channel_cache.json
rm -f cache/yt_search_cache.json
rm -f cache/spotify_token_cache
```

### Configuración de Logging

#### Nivel de Logging

```bash
# En .env
LOG_LEVEL=INFO  # DEBUG | INFO | WARNING | ERROR
LOG_FILE=out/system.log
```

#### Rotación de Logs

```bash
# Configurar logrotate (Linux/macOS)
sudo nano /etc/logrotate.d/mala-pata-come-candela
```

## Solución de Problemas

### Problemas Comunes

#### 1. Error de Permisos

```bash
# Error: Permission denied
chmod +x dl-music-system.sh
chmod +x *.py
```

#### 2. ffmpeg No Encontrado

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Verificar PATH
which ffmpeg
```

#### 3. yt-dlp No Encontrado

```bash
# Instalar globalmente
pip install yt-dlp

# O en el entorno virtual
source .venv/bin/activate
pip install yt-dlp
```

#### 4. Error de API Keys

```bash
# Verificar .env
cat .env | grep API_KEY

# Verificar variables de entorno
source .env
echo $YOUTUBE_API_KEY
```

#### 5. Error de Espacio en Disco

```bash
# Verificar espacio disponible
df -h

# Limpiar cachés
rm -rf cache/*.json
```

### Logs de Debug

#### Habilitar Debug

```bash
# En .env
DEBUG=true
LOG_LEVEL=DEBUG
```

#### Ver Logs en Tiempo Real

```bash
# Seguir logs de procesamiento
tail -f out/log_descargas.csv

# Ver logs del sistema
tail -f out/system.log
```

### Recuperación de Errores

#### Restaurar Manifest

```bash
# Hacer backup del manifest
cp cache/manifest.csv cache/manifest.csv.backup

# Restaurar desde backup
cp cache/manifest.csv.backup cache/manifest.csv
```

#### Reinstalar Dependencias

```bash
# Recrear entorno virtual
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Mantenimiento

### Actualizaciones

#### Actualizar yt-dlp

```bash
pip install --upgrade yt-dlp
```

#### Actualizar Dependencias

```bash
pip install --upgrade -r requirements.txt
```

### Backup y Restauración

#### Script de Backup

```bash
#!/bin/bash
# backup_system.sh

BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup de configuración
cp .env "$BACKUP_DIR/"
cp cache/manifest.csv "$BACKUP_DIR/"

# Backup de cachés
cp -r cache/ "$BACKUP_DIR/"

echo "Backup creado en: $BACKUP_DIR"
```

#### Script de Restauración

```bash
#!/bin/bash
# restore_system.sh

BACKUP_DIR="$1"
if [ -z "$BACKUP_DIR" ]; then
    echo "Uso: $0 <directorio_backup>"
    exit 1
fi

# Restaurar configuración
cp "$BACKUP_DIR/.env" .
cp "$BACKUP_DIR/manifest.csv" cache/

# Restaurar cachés
cp -r "$BACKUP_DIR/cache/"* cache/

echo "Sistema restaurado desde: $BACKUP_DIR"
```

## Configuración de Producción

### Optimizaciones de Rendimiento

#### Configuración de Memoria

```bash
# En .env
PYTHON_OPTIMIZE=1
PYTHONUNBUFFERED=1
```

#### Configuración de Red

```bash
# Timeouts para APIs
API_TIMEOUT=30
MAX_RETRIES=3
BACKOFF_FACTOR=2
```

### Monitoreo

#### Métricas del Sistema

```bash
# Script de monitoreo
#!/bin/bash
echo "=== Estado del Sistema ==="
echo "Espacio en disco: $(df -h . | tail -1)"
echo "Memoria: $(free -h | grep Mem)"
echo "Procesos Python: $(ps aux | grep python | wc -l)"
echo "Tamaño de caché: $(du -sh cache/)"
```

### Seguridad

#### Configuración de Permisos

```bash
# Restringir acceso a .env
chmod 600 .env

# Restringir acceso a cachés
chmod 700 cache/
```

#### Backup de Seguridad

```bash
# Cifrar backups
tar -czf - cache/ | gpg --symmetric --cipher-algo AES256 -o backup_$(date +%Y%m%d).tar.gz.gpg
```

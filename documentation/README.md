# Documentación Técnica - Mala Pata Come Candela

## Índice de Documentación

Esta carpeta contiene la documentación técnica completa del sistema **Mala Pata Come Candela**, una plataforma automatizada para la descarga y organización de música afrolatina.

### 📋 Documentos Disponibles

#### 1. [Arquitectura del Sistema](01_arquitectura_sistema.md)

- **Visión general** del sistema y sus componentes
- **Arquitectura de datos** y flujo de información
- **Tecnologías y dependencias** utilizadas
- **Patrones de diseño** implementados
- **Consideraciones de rendimiento** y escalabilidad
- **Seguridad y privacidad**

#### 2. [APIs e Integraciones](02_apis_integraciones.md)

- **YouTube Data API v3** - Búsqueda de videos y metadatos
- **OpenAI API** - Clasificación inteligente de géneros
- **Discogs API** - Base de datos musical especializada
- **MusicBrainz API** - Metadatos musicales libres
- **Spotify Web API** - Integración con playlists
- **yt-dlp** - Búsqueda sin API como alternativa
- **Estrategias de optimización** y manejo de errores

#### 3. [Flujos y Procesos](03_flujos_procesos.md)

- **Flujo principal**: Solicitud Natural → Descarga
- **Flujo de pipeline**: CSV → Descarga
- **Flujo de descarga**: Script Bash
- **Flujo de Spotify**: Playlist → CSV
- **Flujo de eliminación**: Gestión de canciones
- **Flujos de caché** y optimización
- **Flujos de error** y recuperación
- **Flujos de monitoreo** y logging

#### 4. [Instalación y Configuración](04_instalacion_configuracion.md)

- **Requisitos del sistema** y dependencias
- **Instalación paso a paso** completa
- **Configuración detallada** de variables de entorno
- **Configuración de APIs** externas
- **Verificación de instalación** y scripts de prueba
- **Configuración avanzada** y personalización
- **Solución de problemas** comunes
- **Mantenimiento** y actualizaciones

#### 5. [Uso y Ejemplos](05_uso_ejemplos.md)

- **Guía de uso rápido** con comandos básicos
- **Ejemplos detallados** de casos de uso
- **Casos de uso avanzados** y configuraciones especiales
- **Mejores prácticas** para optimizar resultados
- **Solución de problemas** comunes
- **Scripts de automatización** y monitoreo
- **Integración con otros sistemas**
- **Métricas y análisis** de uso

## 🚀 Inicio Rápido

### Para Desarrolladores

1. Lee [Arquitectura del Sistema](01_arquitectura_sistema.md) para entender la estructura
2. Consulta [APIs e Integraciones](02_apis_integraciones.md) para configurar servicios externos
3. Revisa [Flujos y Procesos](03_flujos_procesos.md) para entender el funcionamiento interno

### Para Usuarios

1. Sigue [Instalación y Configuración](04_instalacion_configuracion.md) para configurar el sistema
2. Consulta [Uso y Ejemplos](05_uso_ejemplos.md) para aprender a usar el sistema
3. Usa los scripts de automatización para optimizar tu flujo de trabajo

### Para Administradores

1. Revisa [Instalación y Configuración](04_instalacion_configuracion.md) para configuraciones de producción
2. Consulta [Flujos y Procesos](03_flujos_procesos.md) para entender el monitoreo
3. Usa [Uso y Ejemplos](05_uso_ejemplos.md) para scripts de mantenimiento

## 🏗️ Arquitectura del Sistema

### Componentes Principales

- **`request_to_csv.py`**: Convierte solicitudes naturales a listas de canciones
- **`spotify_to_csv.py`**: Exporta playlists de Spotify
- **`pipeline_music.py`**: Motor principal de procesamiento y descarga
- **`dl-music-system.sh`**: Script de descarga especializado por género
- **`delete_song.py`**: Gestión de eliminación de canciones

### Flujo de Datos

```
Solicitud → Interpretación → Búsqueda → CSV → Pipeline → Descarga → Organización
```

### Géneros Soportados

El sistema clasifica automáticamente en 16 géneros específicos de música afrolatina:

- Son Cubano, Guajira Moderna, Guaracha, Rumba Guaguancó
- Afro Cuban Jazz Descarga, Mambo, Cha Cha Cha, Boogaloo
- Salsa Dura Clásica, Guaguancó Fusionado, Exotica, Latin Soul
- Plena Bomba, Salsa Romántica, Timba, Salsa Dura Revival

## 🔧 Tecnologías Utilizadas

### APIs Externas

- **YouTube Data API v3**: Búsqueda de videos
- **OpenAI API**: Clasificación con IA
- **Discogs API**: Base de datos musical
- **MusicBrainz API**: Metadatos libres
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

## 📊 Características del Sistema

### Funcionalidades Principales

- ✅ **Interpretación de lenguaje natural** para solicitudes musicales
- ✅ **Búsqueda inteligente** en múltiples fuentes (YouTube, Discogs, MusicBrainz)
- ✅ **Clasificación automática** en 16 géneros afrolatinos
- ✅ **Descarga automatizada** con metadatos y thumbnails
- ✅ **Organización por géneros** en estructura de directorios
- ✅ **Sistema de caché** para optimizar rendimiento
- ✅ **Gestión de cuotas** de APIs externas
- ✅ **Fallback automático** cuando se agotan las cuotas
- ✅ **Deduplicación** para evitar descargas duplicadas
- ✅ **Logging detallado** de todas las operaciones

### Modos de Operación

- **Modo API**: Usa APIs externas para máxima precisión
- **Modo Sin API**: Usa yt-dlp para búsquedas gratuitas
- **Modo Híbrido**: Combina ambos enfoques automáticamente
- **Modo Económico**: Solo herramientas gratuitas

## 🛠️ Configuración y Personalización

### Variables de Entorno Principales

```bash
# APIs (opcionales)
YOUTUBE_API_KEY=tu_api_key
OPENAI_API_KEY=tu_api_key
DISCOGS_TOKEN=tu_token
SPOTIFY_CLIENT_ID=tu_client_id

# Configuración del sistema
SEARCH_MODE=no_api_first
CLASSIFIER_MODE=LLM_FALLBACK
LIB_BASE_DIR=/ruta/a/tu/libreria
```

### Personalización Avanzada

- **Nuevos géneros**: Agregar categorías musicales personalizadas
- **Fuentes de datos**: Integrar nuevas APIs o bases de datos
- **Clasificadores**: Implementar algoritmos de IA personalizados
- **Formatos de salida**: Soporte para diferentes formatos de audio

## 📈 Rendimiento y Escalabilidad

### Optimizaciones Implementadas

- **Sistema de caché inteligente** con TTL configurable
- **Búsqueda sin API** como alternativa a YouTube API
- **Procesamiento por lotes** para múltiples tracks
- **Deduplicación automática** por artista-título
- **Rate limiting** para respetar límites de APIs

### Límites y Consideraciones

- **YouTube API**: 4M unidades de cuota por defecto
- **OpenAI**: Límites por modelo y uso
- **Procesamiento**: Secuencial (no paralelo actualmente)
- **Almacenamiento**: Solo local (no distribuido)

## 🔒 Seguridad y Privacidad

### Manejo de Credenciales

- Variables de entorno para API keys
- Archivo `.env` excluido del control de versiones
- Tokens de acceso con expiración automática

### Consideraciones Legales

- Uso solo para fines personales/educativos
- Respeto a términos de servicio de APIs
- No almacenamiento de contenido protegido por derechos

## 📝 Logging y Monitoreo

### Sistema de Logs

- **CSV de procesamiento**: Registro detallado de cada operación
- **Logs de error**: Captura de excepciones y fallos
- **Métricas de API**: Seguimiento de uso de cuotas

### Indicadores de Salud

- Tasa de éxito de descargas
- Uso de cuotas de API
- Tiempo de procesamiento por track
- Calidad de clasificación de géneros

## 🤝 Contribución y Desarrollo

### Estructura del Código

- **Módulos separados** por funcionalidad
- **Documentación inline** en español
- **Manejo de errores** robusto
- **Logging estructurado** para debugging

### Puntos de Extensión

1. **Nuevos géneros**: Adición fácil de categorías musicales
2. **Fuentes de datos**: Integración con nuevas APIs
3. **Formatos de salida**: Soporte para diferentes formatos
4. **Clasificadores**: Implementación de nuevos algoritmos

## 📞 Soporte y Recursos

### Documentación Adicional

- **README.md** en la raíz del proyecto para uso básico
- **requirements.txt** para dependencias Python
- **Makefile** para comandos de automatización
- **env.example** para configuración de ejemplo

### Recursos Externos

- [YouTube Data API Documentation](https://developers.google.com/youtube/v3)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Discogs API Documentation](https://www.discogs.com/developers/)
- [MusicBrainz API Documentation](https://musicbrainz.org/doc/Development)
- [Spotify Web API Documentation](https://developer.spotify.com/documentation/web-api/)

## 📄 Licencia y Uso

Este sistema está diseñado para uso personal y educativo. Asegúrate de respetar los términos de servicio de todas las APIs utilizadas y las leyes de derechos de autor aplicables en tu jurisdicción.

---

**Última actualización**: Enero 2025
**Versión del sistema**: 1.0
**Autor**: Mateo Quintero

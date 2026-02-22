#!/bin/bash

# Idempotent guard: evita imprimir/definir todo dos veces si se fuentea de nuevo
# Solo aplicar el guard si no estamos siendo ejecutados desde pipeline_music.py
if [ -n "${__MPCC_DL_MUSIC_LOADED:-}" ] && [ -z "${__MPCC_FROM_PIPELINE:-}" ]; then
  return 0 2>/dev/null || true
fi
export __MPCC_DL_MUSIC_LOADED=1

# ── Verificación única de yt-dlp al cargar el script ─────────────────────────
if command -v yt-dlp >/dev/null 2>&1; then
    _YTDLP_VERSION=$(yt-dlp --version 2>/dev/null)
    if echo "$_YTDLP_VERSION" | grep -q "2024\|2025\|2026"; then
        echo "   ✅ yt-dlp $_YTDLP_VERSION listo"
    else
        echo "   ⚠️  yt-dlp $_YTDLP_VERSION puede estar desactualizado"
        echo "   💡 Actualiza con: pip install --upgrade yt-dlp"
    fi
else
    echo "❌ yt-dlp no está instalado o no está en PATH"
    echo "💡 Instala con: pip install yt-dlp"
fi
unset _YTDLP_VERSION

# Sistema general para descargar música con metadatos
# Función base que reemplaza todos los alias dl-*

# Desactivar alias existentes si existen
unalias dl-salsa-dura-revival 2>/dev/null || true
unalias dl-salsa-dura-clasica 2>/dev/null || true
unalias dl-salsa 2>/dev/null || true
unalias dl-salsa-romantica 2>/dev/null || true
unalias dl-mambo 2>/dev/null || true
unalias dl-son-cubano 2>/dev/null || true
unalias dl-timba 2>/dev/null || true
unalias dl-guaracha 2>/dev/null || true
unalias dl-latin-soul 2>/dev/null || true
unalias dl-boogaloo 2>/dev/null || true
unalias dl-afro-cuban-jazz 2>/dev/null || true
unalias dl-balada 2>/dev/null || true
unalias dl-cha-cha-cha 2>/dev/null || true
unalias dl-exotica 2>/dev/null || true
unalias dl-guaguanco-fusionado 2>/dev/null || true
unalias dl-guajira-moderna 2>/dev/null || true
unalias dl-house 2>/dev/null || true
unalias dl-nueva-trova 2>/dev/null || true
unalias dl-plena-bomba 2>/dev/null || true
unalias dl-rumba-guaguanco 2>/dev/null || true
unalias dl-techno 2>/dev/null || true
unalias dl-cumbia 2>/dev/null || true

dl_music() {
    local GENERO="$1"
    local VIDEO_ID="$2"
    local ARTISTA="$3"
    local TITULO="$4"
    local IMAGEN_TYPE="${5:-hq}"  # Por defecto 'hq'

    # Validar parámetros
    if [ $# -lt 4 ]; then
        echo "❌ Uso: $GENERO \"VIDEO_ID\" \"ARTISTA\" \"TITULO\" [IMAGEN_TYPE]"
        echo "📍 Ejemplo: $GENERO \"atVS36nBgDw\" \"Héctor Lavoe\" \"El Cantante\" hq"
        echo "💡 Solo necesitas el ID del video, no la URL completa"
        echo "🖼️  Tipos de imagen: 'hq' (default) o 'max' (mejor calidad)"
        return 1
    fi

    # Construir URLs
    local URL="https://www.youtube.com/watch?v=$VIDEO_ID"

    # Seleccionar tipo de thumbnail
    local THUMBNAIL_URL
    if [ "$IMAGEN_TYPE" = "hq" ]; then
        THUMBNAIL_URL="https://i3.ytimg.com/vi/$VIDEO_ID/hqdefault.jpg"
        echo "🖼️  Usando imagen HQ (videos viejos)"
    else
        THUMBNAIL_URL="https://img.youtube.com/vi/$VIDEO_ID/maxresdefault.jpg"
        echo "🖼️  Usando imagen MAX (mejor calidad)"
    fi

    # Definir directorio según el género (permitir override por ENV)
    local BASE_DIR="${MUSIC_BASE:-/Users/matteoquintero/Music/mala_pata_come_candela}"
    local GENRE_DIR=""

    case $GENERO in
        "dl-salsa-dura-revival") GENRE_DIR="salsa_dura_revival" ;;
        "dl-salsa-dura-clasica") GENRE_DIR="salsa_dura_clasica" ;;
        "dl-salsa") GENRE_DIR="salsa" ;;
        "dl-salsa-romantica") GENRE_DIR="salsa_romantica" ;;
        "dl-mambo") GENRE_DIR="mambo" ;;
        "dl-son-cubano") GENRE_DIR="son_cubano" ;;
        "dl-timba") GENRE_DIR="timba" ;;
        "dl-guaracha") GENRE_DIR="guaracha" ;;
        "dl-latin-soul") GENRE_DIR="latin_soul" ;;
        "dl-boogaloo") GENRE_DIR="boogaloo" ;;
        "dl-afro-cuban-jazz") GENRE_DIR="afro_cuban_jazz_descarga" ;;
        "dl-balada") GENRE_DIR="balada" ;;
        "dl-cha-cha-cha") GENRE_DIR="cha_cha_cha" ;;
        "dl-exotica") GENRE_DIR="exotica" ;;
        "dl-guaguanco-fusionado") GENRE_DIR="guaguanco_fusionado" ;;
        "dl-guajira-moderna") GENRE_DIR="guajira_moderna" ;;
        "dl-house") GENRE_DIR="house" ;;
        "dl-nueva-trova") GENRE_DIR="nueva_trova" ;;
        "dl-plena-bomba") GENRE_DIR="plena_bomba" ;;
        "dl-rumba-guaguanco") GENRE_DIR="rumba_guaguanco" ;;
        "dl-techno") GENRE_DIR="techno" ;;
        "dl-cumbia") GENRE_DIR="cumbia" ;;
        *)
            echo "❌ Género no reconocido: $GENERO"
            return 1
            ;;
    esac

    local FULL_DIR="$BASE_DIR/$GENRE_DIR"
    mkdir -p "$FULL_DIR"

    local FILENAME="${ARTISTA} - ${TITULO}.mp3"
    local FULL_PATH="$FULL_DIR/$FILENAME"

    echo "🎵 Descargando: $TITULO"
    echo "🎤 Artista: $ARTISTA"
    echo "📁 Destino: $FULL_PATH"

    local THUMBNAIL_FILE=""
    echo "🖼️  Descargando thumbnail de YouTube..."
    THUMBNAIL_FILE="/tmp/thumbnail_${VIDEO_ID}.jpg"

    if curl -s -L "$THUMBNAIL_URL" -o "$THUMBNAIL_FILE"; then
        if file "$THUMBNAIL_FILE" | grep -q "image"; then
            echo "✅ Thumbnail descargada exitosamente"
        else
            echo "⚠️  Thumbnail no disponible, continuando sin artwork"
            rm -f "$THUMBNAIL_FILE"
            THUMBNAIL_FILE=""
        fi
    else
        echo "⚠️  Error al descargar thumbnail, continuando sin artwork"
        THUMBNAIL_FILE=""
    fi

    echo ""

    # Try multiple format strategies to handle SABR streaming and format availability issues
    # Strategy 1: Android client (bypasses 403 errors)
    if yt-dlp -x --audio-format mp3 --audio-quality 0 --extractor-args "youtube:player_client=android" -o "$FULL_PATH" "$URL" 2>/dev/null; then
        echo "✅ Descarga exitosa con cliente Android"
    # Strategy 2: Standard extraction with audio quality 0
    elif yt-dlp -x --audio-format mp3 --audio-quality 0 -o "$FULL_PATH" "$URL" 2>/dev/null; then
        echo "✅ Descarga exitosa con método estándar"
    # Strategy 3: Try with specific audio formats for SABR streaming
    elif yt-dlp -x --audio-format mp3 --audio-quality 0 --format "bestaudio[ext=m4a]/bestaudio/best" -o "$FULL_PATH" "$URL" 2>/dev/null; then
        echo "✅ Descarga exitosa con formato m4a/best"
    # Strategy 4: Try with bestaudio only
    elif yt-dlp -x --audio-format mp3 --audio-quality 0 --format "bestaudio" -o "$FULL_PATH" "$URL" 2>/dev/null; then
        echo "✅ Descarga exitosa con bestaudio"
    # Strategy 5: Android client with bestaudio
    elif yt-dlp -x --audio-format mp3 --audio-quality 0 --extractor-args "youtube:player_client=android" --format "bestaudio" -o "$FULL_PATH" "$URL" 2>/dev/null; then
        echo "✅ Descarga exitosa con cliente Android + bestaudio"
    # Strategy 6: Try with SABR streaming workaround (no format selection)
    elif yt-dlp -x --audio-format mp3 --audio-quality 0 --extractor-args "youtube:formats=missing_pot" -o "$FULL_PATH" "$URL" 2>/dev/null; then
        echo "✅ Descarga exitosa con workaround SABR"
    # Strategy 7: Last resort - try without format restrictions
    elif yt-dlp -x --audio-format mp3 --audio-quality 0 --extractor-args "youtube:formats=missing_pot" --format "best" -o "$FULL_PATH" "$URL" 2>/dev/null; then
        echo "✅ Descarga exitosa con formato best y SABR workaround"
    else
        # All strategies failed
        echo "❌ Todas las estrategias de descarga fallaron"
        false
    fi

    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Descarga completada!"
        echo "📄 Archivo: $FILENAME"
        echo "📂 Ubicación: $FULL_DIR"

        echo "📋 Agregando metadatos..."
        local TEMP_FILE="${FULL_PATH}.temp.mp3"

        if [ -n "$THUMBNAIL_FILE" ] && [ -f "$THUMBNAIL_FILE" ]; then
            echo "🖼️  Agregando thumbnail como artwork..."

            ffmpeg -i "$FULL_PATH" -i "$THUMBNAIL_FILE" -map 0:a -map 1:v \
                -c:a copy -c:v mjpeg -disposition:v attached_pic \
                -metadata title="$TITULO" -metadata artist="$ARTISTA" -metadata album="$GENRE_DIR" \
                -metadata genre="$(echo $GENRE_DIR | sed 's/_/ /g')" -metadata date="$(date +%Y)" \
                "$TEMP_FILE" -y -v quiet

            if [ $? -eq 0 ]; then
                mv "$TEMP_FILE" "$FULL_PATH"
                echo "✅ Metadatos y artwork agregados exitosamente"
            else
                echo "⚠️  Error al agregar artwork, intentando solo metadatos..."
                ffmpeg -i "$FULL_PATH" -c:a copy \
                    -metadata title="$TITULO" -metadata artist="$ARTISTA" -metadata album="$GENRE_DIR" \
                    -metadata genre="$(echo $GENRE_DIR | sed 's/_/ /g')" -metadata date="$(date +%Y)" \
                    "$TEMP_FILE" -y >/dev/null 2>&1

                if [ $? -eq 0 ]; then
                    mv "$TEMP_FILE" "$FULL_PATH"
                    echo "✅ Metadatos agregados exitosamente (sin artwork)"
                else
                    echo "⚠️  Error al agregar metadatos, pero el archivo se descargó correctamente"
                    rm -f "$TEMP_FILE"
                fi
            fi
        else
            echo "📋 Agregando solo metadatos..."
            ffmpeg -i "$FULL_PATH" -c:a copy \
                -metadata title="$TITULO" -metadata artist="$ARTISTA" -metadata album="$GENRE_DIR" \
                -metadata genre="$(echo $GENRE_DIR | sed 's/_/ /g')" -metadata date="$(date +%Y)" \
                "$TEMP_FILE" -y >/dev/null 2>&1

            if [ $? -eq 0 ]; then
                mv "$TEMP_FILE" "$FULL_PATH"
                echo "✅ Metadatos agregados exitosamente"
            else
                echo "⚠️  Error al agregar metadatos, pero el archivo se descargó correctamente"
                rm -f "$TEMP_FILE"
            fi
        fi

        if [ -n "$THUMBNAIL_FILE" ] && [ -f "$THUMBNAIL_FILE" ]; then
            rm -f "$THUMBNAIL_FILE"
        fi

        return 0
    else
        echo "❌ Error en la descarga"
        echo "🔍 Intentando diagnóstico del error..."

        # Check if this is a SABR streaming issue
        echo "🔍 Verificando si es un problema de SABR streaming..."
        if yt-dlp --list-formats "$URL" 2>&1 | grep -q "SABR streaming\|missing_pot\|GVS PO Token"; then
            echo "⚠️  Detectado problema de SABR streaming de YouTube"
            echo "   YouTube ha implementado un nuevo protocolo de streaming que puede causar problemas"
        fi

        # Try to get more information about available formats
        echo "📋 Formatos disponibles para el video:"
        yt-dlp --list-formats "$URL" 2>/dev/null | head -20 || echo "   No se pudieron obtener formatos"

        echo ""
        echo "💡 Sugerencias para resolver el problema:"
        echo "   1. Actualiza yt-dlp a la versión más reciente:"
        echo "      pip install --upgrade yt-dlp"
        echo "      o para nightly: pip install --upgrade yt-dlp-nightly"
        echo ""
        echo "   2. Si es un problema de SABR streaming:"
        echo "      - YouTube ha cambiado su protocolo de streaming"
        echo "      - Algunos videos pueden no estar disponibles temporalmente"
        echo "      - Intenta con otro video ID"
        echo ""
        echo "   3. Verifica que el video sea público y esté disponible"
        echo "   4. Si el problema persiste, puede ser una restricción regional"

        return 1
    fi
}

# Crear funciones para cada género
dl-salsa-dura-revival() { dl_music "dl-salsa-dura-revival" "$@"; }
dl-salsa-dura-clasica() { dl_music "dl-salsa-dura-clasica" "$@"; }
dl-salsa() { dl_music "dl-salsa" "$@"; }
dl-salsa-romantica() { dl_music "dl-salsa-romantica" "$@"; }
dl-mambo() { dl_music "dl-mambo" "$@"; }
dl-son-cubano() { dl_music "dl-son-cubano" "$@"; }
dl-timba() { dl_music "dl-timba" "$@"; }
dl-guaracha() { dl_music "dl-guaracha" "$@"; }
dl-latin-soul() { dl_music "dl-latin-soul" "$@"; }
dl-boogaloo() { dl_music "dl-boogaloo" "$@"; }
dl-afro-cuban-jazz() { dl_music "dl-afro-cuban-jazz" "$@"; }
dl-balada() { dl_music "dl-balada" "$@"; }
dl-cha-cha-cha() { dl_music "dl-cha-cha-cha" "$@"; }
dl-exotica() { dl_music "dl-exotica" "$@"; }
dl-guaguanco-fusionado() { dl_music "dl-guaguanco-fusionado" "$@"; }
dl-guajira-moderna() { dl_music "dl-guajira-moderna" "$@"; }
dl-house() { dl_music "dl-house" "$@"; }
dl-nueva-trova() { dl_music "dl-nueva-trova" "$@"; }
dl-plena-bomba() { dl_music "dl-plena-bomba" "$@"; }
dl-rumba-guaguanco() { dl_music "dl-rumba-guaguanco" "$@"; }
dl-techno() { dl_music "dl-techno" "$@"; }
dl-cumbia() { dl_music "dl-cumbia" "$@"; }

# ===== Mensajes de bienvenida (4 variantes) =====
print_block_1() {
  echo "⚡️ [Mala Pata · Come Candela] invocado."
  echo ""
  echo "✨ Cómo funciona el conjuro:"
  echo "  1) 🔮 Crea el listado:"
  echo "       · mala-pata \"10 de boogaloo underground\""
  echo "       · mala-pata \"3 canciones de Silvio Rodríguez\" \"nueva_trova\""
  echo "       · mala-pata-spotify 'https://open.spotify.com/playlist/XXXX' --genre salsa"
  echo "       · mala-pata-spotify 'https://open.spotify.com/album/XXXX' --genre mambo"
  echo ""
  echo "  2) 🔥 Enciende la llama → come-candela"
  echo "       (descarga todo lo que pediste)"
  echo ""
  echo "  3) ❌ Si algo no vibra contigo:"
  echo "       · mala-candela \"Artista - Título.mp3\""
}

print_block_2() {
  echo "⚡️ [Mala Pata · Come Candela] despierta."
  echo ""
  echo "🔮 El ritual del fuego:"
  echo "  1) ✨ Invoca tu lista:"
  echo "       · mala-pata \"20 guarachas picarescas\""
  echo "       · mala-pata \"2 canciones de Kraftwerk\" \"techno\""
  echo "       · mala-pata-spotify 'https://open.spotify.com/playlist/XXXX' --genre house"
  echo "       · mala-pata-spotify 'https://open.spotify.com/album/XXXX' --genre boogaloo"
  echo ""
  echo "  2) 🔥 Alimenta la llama → come-candela"
  echo "       (la música cruza portales y llega a tu disco)"
  echo ""
  echo "  3) 🕯️ Purga lo indeseado:"
  echo "       · mala-candela \"Artista - Título.mp3\""
}

print_block_3() {
  echo "⚡️ [Mala Pata · Come Candela] online."
  echo ""
  echo "🤖 Protocolo de extracción sonora:"
  echo "  1) 📡 Genera el manifiesto de tracks:"
  echo "       · mala-pata \"15 joyas de salsa dura\""
  echo "       · mala-pata \"4 canciones de Daft Punk\" \"house\""
  echo "       · mala-pata-spotify 'https://open.spotify.com/playlist/XXXX' --genre timba"
  echo "       · mala-pata-spotify 'https://open.spotify.com/album/XXXX' --genre son-cubano"
  echo ""
  echo "  2) ⚙️ Ejecuta el motor → come-candela"
  echo "       (la data cruda se transforma en .mp3)"
  echo ""
  echo "  3) 🗑️ Limpieza de buffer:"
  echo "       · mala-candela \"Artista - Título.mp3\""
}

print_block_4() {
  echo "⚡️ [Mala Pata · Come Candela] conjurado."
  echo ""
  echo "🪄 Hechizo musical en 3 pasos:"
  echo "  1) ✏️ Escribe tu deseo:"
  echo "       · mala-pata \"5 timbas que revienten\""
  echo "       · mala-pata \"1 cancion de Leo Dan\" \"balada\""
  echo "       · mala-pata-spotify 'https://open.spotify.com/playlist/XXXX' --genre balada"
  echo "       · mala-pata-spotify 'https://open.spotify.com/album/XXXX' --genre guaracha"
  echo ""
  echo "  2) 🔥 Prende la candela → come-candela"
  echo "       (los espíritus traen tus canciones)"
  echo ""
  echo "  3) 💨 Borra el maleficio si no gustó:"
  echo "       · mala-candela \"Artista - Título.mp3\""
}

# Seleccionar una variante al azar y evitar imprimir bloques legacy más abajo
# Solo mostrar el mensaje si NO estamos siendo ejecutados desde pipeline
if [ -z "${__MPCC_FROM_PIPELINE:-}" ]; then
  _mpcc_rand=$((RANDOM % 4))
  case $_mpcc_rand in
    0) print_block_1 ;;
    1) print_block_2 ;;
    2) print_block_3 ;;
    3) print_block_4 ;;
  esac
fi

# Evitar imprimir mensajes legacy que siguen en el archivo
# Solo hacer return si NO estamos siendo ejecutados desde pipeline
if [ -z "${__MPCC_FROM_PIPELINE:-}" ]; then
  return 0 2>/dev/null || true
fi

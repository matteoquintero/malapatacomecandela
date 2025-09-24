#!/bin/bash

# Idempotent guard: evita imprimir/definir todo dos veces si se fuentea de nuevo
if [ -n "${__MPCC_DL_MUSIC_LOADED:-}" ]; then
  return 0 2>/dev/null || true
fi
export __MPCC_DL_MUSIC_LOADED=1

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

    if yt-dlp -x --audio-format mp3 -o "$FULL_PATH" "$URL"; then
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

# ===== Mensajes de bienvenida (4 variantes) =====
print_block_1() {
  echo "⚡️ [Mala Pata · Come Candela] invocado."
  echo ""
  echo "✨ Cómo funciona el conjuro:"
  echo "  1) 🔮 Crea el listado:"
  echo "       · mala-pata \"10 de boogaloo underground\""
  echo "       · mala-pata-spotify 'https://open.spotify.com/playlist/XXXX'"
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
  echo "       · mala-pata-spotify 'https://open.spotify.com/playlist/XXXX'"
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
  echo "       · mala-pata-spotify 'https://open.spotify.com/playlist/XXXX'"
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
  echo "       · mala-pata-spotify 'https://open.spotify.com/playlist/XXXX'"
  echo ""
  echo "  2) 🔥 Prende la candela → come-candela"
  echo "       (los espíritus traen tus canciones)"
  echo ""
  echo "  3) 💨 Borra el maleficio si no gustó:"
  echo "       · mala-candela \"Artista - Título.mp3\""
}

# Seleccionar una variante al azar y evitar imprimir bloques legacy más abajo
_mpcc_rand=$((RANDOM % 4))
case $_mpcc_rand in
  0) print_block_1 ;;
  1) print_block_2 ;;
  2) print_block_3 ;;
  3) print_block_4 ;;

esac

# Evitar imprimir mensajes legacy que siguen en el archivo
return 0 2>/dev/null || true

#!/bin/bash

# Script para configurar el sistema para NO usar la API de YouTube
# Esto evita gastar cuota de la API y usa solo yt-dlp

echo "🔧 Configurando sistema para NO usar API de YouTube"
echo ""

# Verificar si existe .env
if [ ! -f ".env" ]; then
    echo "📋 Creando archivo .env desde env.example..."
    cp env.example .env
    echo "✅ Archivo .env creado"
else
    echo "📋 Archivo .env ya existe"
fi

echo ""
echo "🔧 Configurando variables para modo NO_API..."

# Configurar para usar solo métodos sin API
sed -i.bak 's/^SEARCH_MODE=.*/SEARCH_MODE=no_api_only/' .env
sed -i.bak 's/^DISABLE_API_FALLBACK=.*/DISABLE_API_FALLBACK=true/' .env

# Comentar la API key para evitar su uso accidental
sed -i.bak 's/^YOUTUBE_API_KEY=.*/#YOUTUBE_API_KEY=/' .env

echo "✅ Configuración aplicada:"
echo "   - SEARCH_MODE=no_api_only"
echo "   - DISABLE_API_FALLBACK=true"
echo "   - YOUTUBE_API_KEY comentada"
echo ""

# Verificar que yt-dlp esté instalado
if command -v yt-dlp >/dev/null 2>&1; then
    YTDLP_VERSION=$(yt-dlp --version 2>/dev/null)
    echo "✅ yt-dlp disponible: $YTDLP_VERSION"
else
    echo "❌ yt-dlp no está instalado"
    echo "💡 Instala con: pip install yt-dlp"
fi

echo ""
echo "🎯 El sistema ahora usará SOLO métodos sin API:"
echo "   - ytsearch (búsqueda general de YouTube)"
echo "   - scsearch (búsqueda en SoundCloud)"
echo ""
echo "💡 Para volver a usar la API, edita .env y cambia:"
echo "   - SEARCH_MODE=no_api_first (o api_first)"
echo "   - DISABLE_API_FALLBACK=false"
echo "   - Descomenta YOUTUBE_API_KEY"

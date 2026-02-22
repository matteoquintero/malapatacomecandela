#!/bin/bash

# Script para diagnosticar problemas de SABR streaming en YouTube
# Uso: ./test_sabr_streaming.sh VIDEO_ID

VIDEO_ID="$1"

if [ -z "$VIDEO_ID" ]; then
    echo "❌ Uso: $0 VIDEO_ID"
    echo "📍 Ejemplo: $0 e9eWn6ikxuU"
    exit 1
fi

URL="https://www.youtube.com/watch?v=$VIDEO_ID"

echo "🔍 Diagnosticando SABR streaming para video: $VIDEO_ID"
echo "🌐 URL: $URL"
echo ""

# Check yt-dlp version
echo "📋 Información de yt-dlp:"
yt-dlp --version 2>/dev/null || echo "❌ yt-dlp no disponible"
echo ""

# Test 1: List formats
echo "🧪 Test 1: Listando formatos disponibles..."
echo "----------------------------------------"
yt-dlp --list-formats "$URL" 2>&1 | head -30
echo ""

# Test 2: Check for SABR streaming indicators
echo "🧪 Test 2: Verificando indicadores de SABR streaming..."
echo "----------------------------------------------------"
if yt-dlp --list-formats "$URL" 2>&1 | grep -q "SABR streaming\|missing_pot\|GVS PO Token"; then
    echo "⚠️  DETECTADO: Problema de SABR streaming"
    echo "   - YouTube ha implementado un nuevo protocolo de streaming"
    echo "   - Algunos formatos pueden no estar disponibles"
else
    echo "✅ No se detectaron problemas obvios de SABR streaming"
fi
echo ""

# Test 3: Try different extraction strategies
echo "🧪 Test 3: Probando estrategias de extracción..."
echo "----------------------------------------------"

strategies=(
    "yt-dlp -x --audio-format mp3 --audio-quality 0 --dry-run"
    "yt-dlp -x --audio-format mp3 --audio-quality 0 --format 'bestaudio[ext=m4a]/bestaudio/best' --dry-run"
    "yt-dlp -x --audio-format mp3 --audio-quality 0 --format 'bestaudio' --dry-run"
    "yt-dlp -x --audio-format mp3 --audio-quality 0 --format 'worst' --dry-run"
    "yt-dlp -x --audio-format mp3 --audio-quality 0 --extractor-args 'youtube:formats=missing_pot' --dry-run"
)

for i in "${!strategies[@]}"; do
    strategy_num=$((i + 1))
    echo "   Estrategia $strategy_num: ${strategies[$i]}"
    if eval "${strategies[$i]} '$URL'" >/dev/null 2>&1; then
        echo "   ✅ ÉXITO"
    else
        echo "   ❌ FALLO"
    fi
done
echo ""

# Test 4: Verbose output for debugging
echo "🧪 Test 4: Salida verbose para debugging..."
echo "----------------------------------------"
echo "Ejecutando: yt-dlp -vU --dry-run '$URL'"
echo ""
yt-dlp -vU --dry-run "$URL" 2>&1 | head -50
echo ""

# Recommendations
echo "💡 Recomendaciones:"
echo "------------------"
echo "1. Actualiza yt-dlp a la versión más reciente:"
echo "   pip install --upgrade yt-dlp"
echo "   o para nightly: pip install --upgrade yt-dlp-nightly"
echo ""
echo "2. Si el problema persiste:"
echo "   - Es un problema conocido de YouTube/SABR streaming"
echo "   - Algunos videos pueden no estar disponibles temporalmente"
echo "   - Intenta con otro video ID"
echo ""
echo "3. Para más información:"
echo "   - GitHub issue: https://github.com/yt-dlp/yt-dlp/issues/12482"
echo "   - yt-dlp wiki: https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide"

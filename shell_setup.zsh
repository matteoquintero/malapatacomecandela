# Carga utilidades del proyecto para que funcionen al abrir la consola

# Prioriza Homebrew
export PATH="/opt/homebrew/bin:$PATH"

# Base de música
export MUSIC_BASE="${MUSIC_BASE:-$HOME/Music/mala_pata_come_candela}"

# Alias simples (yt-dlp directo)
alias dl-techno="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/techno/%(title)s.%(ext)s\""
alias dl-house="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/house/%(title)s.%(ext)s\""
alias dl-balada="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/balada/%(title)s.%(ext)s\""
alias dl-nueva-trova="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/nueva_trova/%(title)s.%(ext)s\""
alias dl-cumbia="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/cumbia/%(title)s.%(ext)s\""
alias dl-son-cubano="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/son_cubano/%(title)s.%(ext)s\""
alias dl-guajira-moderna="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/guajira_moderna/%(title)s.%(ext)s\""
alias dl-guaracha="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/guaracha/%(title)s.%(ext)s\""
alias dl-rumba-guaguanco="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/rumba_guaguanco/%(title)s.%(ext)s\""
alias dl-afro-cuban-jazz="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/afro_cuban_jazz_descarga/%(title)s.%(ext)s\""
alias dl-mambo="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/mambo/%(title)s.%(ext)s\""
alias dl-cha-cha-cha="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/cha_cha_cha/%(title)s.%(ext)s\""
alias dl-boogaloo="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/boogaloo/%(title)s.%(ext)s\""
alias dl-salsa-dura-clasica="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/salsa_dura_clasica/%(title)s.%(ext)s\""
alias dl-guaguanco-fusionado="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/guaguanco_fusionado/%(title)s.%(ext)s\""
alias dl-exotica="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/exotica/%(title)s.%(ext)s\""
alias dl-latin-soul="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/latin_soul/%(title)s.%(ext)s\""
alias dl-plena-bomba="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/plena_bomba/%(title)s.%(ext)s\""
alias dl-salsa-romantica="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/salsa_romantica/%(title)s.%(ext)s\""
alias dl-timba="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/timba/%(title)s.%(ext)s\""
alias dl-salsa-dura-revival="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/salsa_dura_revival/%(title)s.%(ext)s\""

# Cargar funciones de descarga por género
if [ -f "$HOME/malapatacomecandela_system/dl-music-system.sh" ]; then
  # si el usuario movió el repo a ~
  source "$HOME/malapatacomecandela_system/dl-music-system.sh"
elif [ -f "$(dirname ${BASH_SOURCE[0]:-${(%):-%x}})/dl-music-system.sh" ]; then
  # ruta relativa a este archivo
  source "$(dirname ${BASH_SOURCE[0]:-${(%):-%x}})/dl-music-system.sh"
elif [ -f "/Users/matteoquintero/malapatacomecandela_system/dl-music-system.sh" ]; then
  # fallback a ruta fija provista
  source "/Users/matteoquintero/malapatacomecandela_system/dl-music-system.sh"
fi

# Detectar python del venv del proyecto si existe
export MPCC_DIR="/Users/matteoquintero/malapatacomecandela_system"
if [ -x "$MPCC_DIR/.venv/bin/python" ]; then
  export MPCC_PY="$MPCC_DIR/.venv/bin/python"
else
  export MPCC_PY="python3"
fi

# Aliases de entrada/salida del pipeline usando el python detectado
alias come-candela='$MPCC_PY "$MPCC_DIR/pipeline_music.py" --input "$MPCC_DIR/canciones.csv" --output "$MPCC_DIR/out/log_descargas.csv"'
alias mala-pata='$MPCC_PY "$MPCC_DIR/request_to_csv.py"'
alias mala-candela='$MPCC_PY "$MPCC_DIR/delete_song.py" --filename'
alias mala-pata-spotify='$MPCC_PY "$MPCC_DIR/spotify_to_csv.py"'

# Otros binarios del usuario
export PATH="$HOME/.console-ninja/.bin:$PATH"

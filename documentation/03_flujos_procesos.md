# Flujos y Procesos - Mala Pata Come Candela

## Visión General de Flujos

El sistema implementa varios flujos de trabajo que se ejecutan de manera secuencial y paralela para procesar solicitudes musicales desde diferentes fuentes hasta la descarga final de archivos de audio organizados.

## 1. Flujo Principal: Solicitud Natural → Descarga

### Diagrama de Flujo

```
Solicitud Natural → Interpretación → Búsqueda de Datos → CSV → Pipeline → Descarga
```

### Proceso Detallado

#### Fase 1: Interpretación de Solicitud

```python
# request_to_csv.py
def llm_plan(user_text: str) -> Dict:
    # 1. Análisis con OpenAI (si disponible)
    if _openai:
        response = _openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user_text}]
        )
    else:
        # 2. Heurística de respaldo
        plan = extract_plan_heuristically(user_text)

    return {
        "task": "playlist" | "album",
        "count": int,
        "genre": str,
        "substyle": "underground" | "comercial",
        "artist": str,
        "album": str
    }
```

#### Fase 2: Búsqueda de Contenido

```python
def pick_playlist(genre: str, substyle: str, count: int):
    # 1. Búsqueda en Discogs (prioridad)
    dc_results = discogs_search_rule(genre, rule, limit=180)

    # 2. Búsqueda en MusicBrainz (fallback)
    mb_results = search_by_rule(genre, limit=160)

    # 3. Combinación y deduplicación
    combined = deduplicate_and_merge(dc_results, mb_results)

    # 4. Ordenamiento por substyle
    if substyle == "comercial":
        ordered = prioritize_anchor_artists(combined)
    elif substyle == "underground":
        ordered = deprioritize_anchor_artists(combined)

    return ordered[:count]
```

#### Fase 3: Generación de CSV

```python
def write_csv(rows: List[Dict], path: str):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "artist", "title", "query_override", "source"
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
```

## 2. Flujo de Pipeline: CSV → Descarga

### Diagrama de Flujo

```
CSV → Validación → Búsqueda YouTube → Clasificación → Descarga → Organización
```

### Proceso Detallado

#### Fase 1: Validación y Deduplicación

```python
def process_csv(input_csv: str, out_csv: str):
    # 1. Cargar manifest existente
    manifest_keys = load_manifest_keys(MANIFEST_FILE)

    # 2. Indexar librería existente
    lib_index = build_library_index(LIB_BASE_DIR)

    # 3. Procesar cada fila
    for row in csv.DictReader(input_csv):
        # Verificar duplicados
        if norm_key(artist, title) in manifest_keys:
            skip_row("already_in_manifest")
        elif norm_key(artist, title) in lib_index:
            skip_row("already_downloaded")
```

#### Fase 2: Resolución de Video ID

```python
def resolve_video_id(artist: str, title: str, query_override: str):
    # 1. Verificar override directo
    if query_override:
        video_id = extract_video_id(query_override)
        if video_id:
            return video_id, "direct_override"

    # 2. Búsqueda según modo configurado
    if SEARCH_MODE == "no_api_first":
        candidates = find_candidates_noapi(artist, title)
        if not candidates and budget_left() > 0:
            candidates = search_youtube_id(artist, title)
    elif SEARCH_MODE == "api_first":
        candidates = search_youtube_id(artist, title)
        if not candidates:
            candidates = find_candidates_noapi(artist, title)

    # 3. Selección del mejor candidato
    best = choose_best_candidate(candidates, artist, title)
    return best["video_id"] if best else None
```

#### Fase 3: Clasificación de Género

```python
def classify(meta: Dict) -> Dict:
    # 1. Clasificación heurística
    hres = heuristic_scores(meta)
    best_heuristic = hres[0] if hres else None
    conf_heur = calculate_confidence(best_heuristic)

    # 2. Decisión de usar LLM
    if CLASSIFIER_MODE == "LLM_ONLY" or conf_heur < LOW_CONF_THRESHOLD:
        llm_result = llm_call(meta)
        return combine_results(best_heuristic, llm_result)
    else:
        return {
            "slug": best_heuristic.slug,
            "confidence": conf_heur,
            "rationale": f"Heurística: {best_heuristic.reasons}"
        }
```

#### Fase 4: Descarga y Procesamiento

```python
def run_download(video_id: str, artist: str, title: str, slug: str):
    # 1. Determinar comando por género
    command = GENRE_COMMAND[slug]

    # 2. Ejecutar script de descarga
    cmd = f'source {DL_SCRIPT} && {command} "{video_id}" "{artist}" "{title}"'
    result = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True)

    # 3. Actualizar manifest si exitoso
    if result.returncode == 0:
        append_manifest_row(MANIFEST_FILE, artist, title, video_id, slug, command, "downloaded")

    return result
```

## 3. Flujo de Descarga: Script Bash

### Diagrama de Flujo

```
Video ID → Descarga Audio → Thumbnail → Metadatos → Organización por Género
```

### Proceso Detallado

#### Fase 1: Preparación

```bash
dl_music() {
    local GENERO="$1"
    local VIDEO_ID="$2"
    local ARTISTA="$3"
    local TITULO="$4"
    local IMAGEN_TYPE="${5:-hq}"

    # 1. Construir URLs
    local URL="https://www.youtube.com/watch?v=$VIDEO_ID"
    local THUMBNAIL_URL="https://i3.ytimg.com/vi/$VIDEO_ID/hqdefault.jpg"

    # 2. Determinar directorio por género
    local GENRE_DIR=$(map_genre_to_directory $GENERO)
    local FULL_DIR="$BASE_DIR/$GENRE_DIR"
    mkdir -p "$FULL_DIR"
}
```

#### Fase 2: Descarga de Thumbnail

```bash
# Descargar thumbnail de YouTube
THUMBNAIL_FILE="/tmp/thumbnail_${VIDEO_ID}.jpg"
if curl -s -L "$THUMBNAIL_URL" -o "$THUMBNAIL_FILE"; then
    if file "$THUMBNAIL_FILE" | grep -q "image"; then
        echo "✅ Thumbnail descargada exitosamente"
    else
        rm -f "$THUMBNAIL_FILE"
        THUMBNAIL_FILE=""
    fi
fi
```

#### Fase 3: Descarga de Audio

```bash
# Descargar audio con yt-dlp
if yt-dlp -x --audio-format mp3 -o "$FULL_PATH" "$URL"; then
    echo "✅ Descarga completada!"

    # Agregar metadatos y artwork
    if [ -n "$THUMBNAIL_FILE" ]; then
        ffmpeg -i "$FULL_PATH" -i "$THUMBNAIL_FILE" \
            -map 0:a -map 1:v -c:a copy -c:v mjpeg \
            -disposition:v attached_pic \
            -metadata title="$TITULO" \
            -metadata artist="$ARTISTA" \
            -metadata album="$GENRE_DIR" \
            -metadata genre="$(echo $GENRE_DIR | sed 's/_/ /g')" \
            -metadata date="$(date +%Y)" \
            "$TEMP_FILE" -y -v quiet
    fi
fi
```

## 4. Flujo de Spotify: Playlist → CSV

### Diagrama de Flujo

```
URL Playlist → Autenticación → Extracción → Formateo → CSV
```

### Proceso Detallado

#### Fase 1: Autenticación

```python
def get_spotify_client():
    auth = SpotifyOAuth(
        client_id=cid,
        client_secret=secret,
        redirect_uri=redirect,
        scope="playlist-read-private playlist-read-collaborative",
        cache_path=cache_path,
        open_browser=True
    )
    return spotipy.Spotify(auth_manager=auth)
```

#### Fase 2: Extracción de Tracks

```python
def fetch_playlist_tracks(sp, playlist_id: str, limit_count: int = None):
    items = []
    results = sp.playlist_items(
        playlist_id,
        fields="items(track(name,artists(name),album(name))),next",
        additional_types=["track"]
    )

    while True:
        for item in results.get("items", []):
            track = item.get("track")
            if track:
                artist = track["artists"][0]["name"] if track["artists"] else ""
                title = track.get("name", "")
                album = track.get("album", {}).get("name", "")
                items.append({"artist": artist, "title": title, "album": album})

                if limit_count and len(items) >= limit_count:
                    return items

        if not results.get("next"):
            break
        results = sp.next(results)

    return items
```

## 5. Flujo de Eliminación: Gestión de Canciones

### Diagrama de Flujo

```
Criterios → Búsqueda → Validación → Eliminación Archivo → Actualización Manifest
```

### Proceso Detallado

#### Fase 1: Resolución de Criterios

```python
def main():
    # 1. Determinar criterios de búsqueda
    if args.filepath:
        files_to_delete = [expand(args.filepath)]
    elif args.filename:
        # Buscar en filesystem
        candidates = find_files_by_filename(root, args.filename)
        files_to_delete.extend(candidates)

    # 2. Parsear artist/title si viene filename
    if args.filename:
        artist_guess, title_guess = parse_artist_title_from_filename(args.filename)
```

#### Fase 2: Matching de Filas

```python
for row in rows:
    match = False

    # Matching por filepath exacto
    if filepath_s is not None:
        match = match_row_by_fields(row, cols, None, None, None, None, filepath_s)

    # Matching por filename encontrado en FS
    elif target_filenames_norm:
        if basename_simplified(row[filepath_col]) in target_filenames_norm:
            match = True

    # Matching por artist/title parseado
    elif args.filename and (artist_guess or title_guess):
        match = match_row_by_artist_title_guess(row, cols, artist_guess, title_guess)

    if match:
        removed.append(row)
        if not args.all and removed:
            break
```

#### Fase 3: Eliminación

```python
# Eliminar archivos físicos
for filepath in files_to_delete:
    if os.path.exists(filepath):
        os.remove(filepath)
        print(f"🗑️ Archivo eliminado: {filepath}")

# Actualizar manifest
if removed:
    write_rows(manifest_path, headers, kept, delim)
    print(f"✅ {len(removed)} fila(s) eliminada(s)")
```

## 6. Flujos de Caché y Optimización

### Sistema de Caché de Búsquedas

```python
def _search_cache_get(artist: str, title: str) -> Optional[List[Dict]]:
    cache = _load_json_cache(SEARCH_CACHE_FILE)
    key = f"{_simp_text(artist)}|{_simp_text(title)}"
    rec = cache.get(key)

    if rec:
        ts = datetime.fromisoformat(rec.get("ts"))
        if datetime.now() - ts <= timedelta(days=SEARCH_CACHE_TTL_DAYS):
            return rec.get("items")

    return None

def _search_cache_put(artist: str, title: str, items: List[Dict]):
    cache = _load_json_cache(SEARCH_CACHE_FILE)
    key = f"{_simp_text(artist)}|{_simp_text(title)}"
    cache[key] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "items": items[:YOUTUBE_MAX_RESULTS]
    }
    _save_json_cache(SEARCH_CACHE_FILE, cache)
```

### Sistema de Caché de Canales

```python
def _get_channels_info_batch(channel_ids: List[str], per_track: Dict):
    cache = _load_json_cache(CHANNEL_CACHE_FILE)
    missing = []

    # Verificar caché existente
    for cid in channel_ids:
        rec = _channel_from_cache(cache, cid)
        if rec:
            out[cid] = rec
        else:
            missing.append(cid)

    # Obtener información faltante de API
    if missing and _can_spend(QUOTA_COSTS["channels.list"]):
        resp = _youtube.channels().list(
            id=",".join(missing),
            part="statistics,snippet"
        ).execute()
        _update_channel_cache_batch(extracted_metadata)
```

## 7. Flujos de Error y Recuperación

### Manejo de Errores de API

```python
def safe_api_call(api_function, *args, **kwargs):
    max_retries = 3
    backoff_time = 1

    for attempt in range(max_retries):
        try:
            return api_function(*args, **kwargs)
        except RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(backoff_time * (2 ** attempt))
                continue
            else:
                return fallback_noapi_search(*args, **kwargs)
        except QuotaExceededError:
            return fallback_noapi_search(*args, **kwargs)
        except Exception as e:
            log_error(f"API call failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(backoff_time)
                continue
            else:
                return None
```

### Fallback Automático

```python
def search_with_fallback(artist: str, title: str):
    # 1. Intentar búsqueda preferida
    if SEARCH_MODE == "no_api_first":
        results = find_candidates_noapi(artist, title)
        if not results and _budget_left() > 0:
            results = search_youtube_id(artist, title)
    else:
        results = search_youtube_id(artist, title)
        if not results:
            results = find_candidates_noapi(artist, title)

    # 2. Si no hay resultados, usar backfill
    if not results:
        results = get_backfill_tracks(artist, title)

    return results
```

## 8. Flujos de Monitoreo y Logging

### Logging Estructurado

```python
def log_processing_step(step: str, data: Dict):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "step": step,
        "data": data,
        "quota_used": _total_quota_units,
        "budget_left": _budget_left()
    }

    # Escribir a CSV de log
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=log_entry.keys())
        writer.writerow(log_entry)
```

### Métricas en Tiempo Real

```python
def _print_totals():
    print("\n🧮 Resumen global YouTube:")
    print(f"   Unidades gastadas:   {_total_quota_units}")
    print(f"   Presupuesto restante: {_budget_left()}")
    print("   Llamadas por endpoint:")
    for endpoint, count in _total_api_calls.items():
        print(f"     • {endpoint}: {count}")
```

## 9. Flujos de Configuración y Personalización

### Carga de Configuración

```python
def load_configuration():
    # 1. Cargar variables de entorno
    config = {
        "youtube_api_key": os.getenv("YOUTUBE_API_KEY", ""),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "search_mode": os.getenv("SEARCH_MODE", "no_api_first"),
        "classifier_mode": os.getenv("CLASSIFIER_MODE", "LLM_FALLBACK")
    }

    # 2. Validar configuración
    validate_config(config)

    # 3. Aplicar configuraciones por defecto
    apply_defaults(config)

    return config
```

### Personalización de Géneros

```python
def add_custom_genre(name: str, command: str, rules: Dict):
    # 1. Validar formato
    validate_genre_format(name, command, rules)

    # 2. Agregar a diccionarios
    GENRE_COMMAND[name] = command
    GENRE_RULES[name] = rules
    ANCHOR_ARTISTS[name] = rules.get("artists", [])

    # 3. Actualizar caché
    update_genre_cache()
```

## 10. Flujos de Mantenimiento

### Limpieza de Caché

```python
def cleanup_expired_cache():
    # 1. Limpiar caché de búsquedas
    search_cache = _load_json_cache(SEARCH_CACHE_FILE)
    expired_keys = []

    for key, data in search_cache.items():
        ts = datetime.fromisoformat(data.get("ts"))
        if datetime.now() - ts > timedelta(days=SEARCH_CACHE_TTL_DAYS):
            expired_keys.append(key)

    for key in expired_keys:
        del search_cache[key]

    _save_json_cache(SEARCH_CACHE_FILE, search_cache)

    # 2. Limpiar archivos temporales
    cleanup_temp_files()
```

### Verificación de Integridad

```python
def verify_system_integrity():
    # 1. Verificar archivos de configuración
    check_config_files()

    # 2. Verificar dependencias
    check_dependencies()

    # 3. Verificar permisos
    check_file_permissions()

    # 4. Verificar conectividad de APIs
    test_api_connectivity()

    return integrity_report
```

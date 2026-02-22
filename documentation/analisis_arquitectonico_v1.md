# Análisis Arquitectónico: Mala Pata Come Candela

> Análisis realizado antes de la refactorización 2.0 (febrero 2026).
> Sirve como referencia del estado original y las decisiones tomadas.

---

## 1. Diagnóstico crítico

El sistema **funciona**, pero funciona por inercia. Hay capas de features pegadas con cinta, no integradas. El punto más débil no es solo `request_to_csv.py` como script — es que el sistema no tiene arquitectura: tiene scripts.

**Métricas de deuda técnica detectadas:**
- `request_to_csv.py`: 2037 líneas. No es un script, es un monolito.
- Tres entry points sin coordinación: `request_to_csv.py`, `spotify_to_csv.py`, `pipeline_music.py`.
- Dos sistemas de géneros paralelos que no se hablan.
- Dos funciones `simp()` idénticas duplicadas entre archivos.
- Dos runners (`run_request` / `run_request_with_direct_genre`) con ~80% de código idéntico.
- Un fallback que genera **canciones ficticias** silenciosamente.

---

## 2. Problemas arquitectónicos detectados

### 2.1 — El monolito de `request_to_csv.py`

El archivo mezcla sin separación:
- Definición de datos del dominio (`GENRE_DB`, `ANCHOR_ARTISTS`, `BACKFILL`, ~500 líneas de datos puros)
- Clientes HTTP (Discogs, MusicBrainz, OpenAI, Spotify)
- Lógica de negocio (planificación de intent, construcción de playlists)
- Parsing de NL (regex, LLM call, heurísticas)
- Escritura de CSV
- CLI/argparse

Consecuencia: modificar cualquier cosa requiere leer el archivo entero. No hay unidades testeables.

### 2.2 — Los dos sistemas de géneros (`GENRE_DB` vs `DIRECT_GENRES`)

El sistema original tiene 16 géneros afrolatinos con ANCHOR_ARTISTS, GENRE_RULES, BACKFILL, heurísticas. Los géneros "directos" (`balada`, `house`, `techno`, `nueva_trova`, `cumbia`) se añadieron después con una ruta de código completamente separada (`run_request_with_direct_genre`) que:
- No tiene ANCHOR_ARTISTS propios
- No tiene BACKFILL propio
- Cuando no detecta artista, **ignora el género directo** y usa `pick_playlist("salsa_dura_clasica", None, count)` — línea 1980

```python
# Bug real: si pides "10 canciones de house" sin artista,
# te da salsa dura clásica silenciosamente
rows = pick_playlist("salsa_dura_clasica", None, count)
```

### 2.3 — El fallback de títulos ficticios

Esta es la falla más seria de calidad de datos:

```python
def generate_basic_fictional_titles(...) -> List[str]:
    generic_titles = [
        "La Noche Perfecta",
        "Sueños de Amor",
        ...
    ]
```

Si MusicBrainz, Discogs, Spotify y OpenAI fallan, el sistema **escribe canciones inexistentes al CSV** con `source: "fictional_basic"`. Esas canciones luego entran al pipeline, no se encuentran en YouTube, y el fallo es silencioso. El usuario no sabe que su CSV contiene basura.

### 2.4 — Parsing frágil del input

```python
# Detecta si el input tiene dos tokens para inferir "instrucción + género"
parts = shlex.split(user_input)
if len(parts) == 2:
    instruction, genre = parts
```

Cualquier pedido de dos palabras — `"salsa underground"`, `"10 canciones"`, `"Héctor Lavoe"` — podría ser malinterpretado como `(instrucción, género)`.

### 2.5 — Configuración dispersa

Cada script llama `load_dotenv()` independientemente. No hay validación de configuración al inicio. Si falta `DL_MUSIC_SCRIPT`, el error aparece al descargar la primera canción, no al arrancar.

### 2.6 — Estado global en módulo

```python
_total_quota_units = 0
_total_api_calls: Dict[str, int] = defaultdict(int)
_openai_client = None
_youtube = None
discogs = None
```

Los clientes se inicializan al importar el módulo. No hay inyección de dependencias. No hay manera de testear sin las APIs reales.

### 2.7 — `debug_print` envuelto en try/except en 40+ sitios

```python
try:
    debug_print(f"[DBG] algo {var}")
except Exception:
    pass
```

Esto es el síntoma de que el sistema creció sin un framework de logging. No hay severidad, no hay timestamps, no hay destino configurable.

### 2.8 — yt-dlp version check en cada descarga

```bash
# dl-music-system.sh — se ejecuta POR CADA CANCIÓN
YTDLP_VERSION=$(yt-dlp --version 2>/dev/null)
```

Con un batch de 20 canciones, eso son 20 llamadas a `yt-dlp --version`. Es un antipatrón de performance.

---

## 3. Rediseño del sistema completo

El sistema tiene un flujo lineal claro que debe respetarse:

```
INPUT (NL/Spotify/directo)
    ↓
[PLAN] — interpretar qué se pide
    ↓
[RESOLVE] — encontrar artista+título reales (Discogs/MB/Spotify/OpenAI)
    ↓
[OUTPUT] — escribir canciones.csv
    ↓ (pipeline separado)
[SEARCH] — encontrar YouTube ID por cada fila
    ↓
[CLASSIFY] — asignar género si no viene en el CSV
    ↓
[DOWNLOAD] — descargar con dl-music-system.sh
```

Estos 6 pasos son los módulos del sistema. Cada uno tiene una responsabilidad única y una interfaz clara.

**Principio de diseño:** El CSV es el contrato entre etapas. Producirlo bien es la mitad del trabajo.

---

## 4. Rediseño específico del comando `create`

### 4.1 — Problemas conceptuales actuales

| Problema | Síntoma |
|---|---|
| Input ambiguo | `"10 canciones"` como argumento posicional vs. `-n 10` |
| Género como argumento posicional opcional | Parsing frágil con shlex |
| Sin `--append` | Cada llamada destruye el CSV anterior |
| Sin `--dry-run` | No puedes ver el plan sin escribir |
| Sin `--no-llm` como flag explícito | Solo controlable por env var |
| Sin feedback del plan antes de ejecutar | El usuario no sabe qué va a pasar |
| `--out` no tiene default sensato | Siempre `canciones.csv`, no configurable por defecto |

### 4.2 — Flags que debe aceptar

```
mala-pata create [QUERY] [OPTIONS]

Positional:
  QUERY           Pedido en lenguaje natural (opcional si se usa --spotify)

Fuentes (mutuamente excluyentes):
  --spotify URL           Importar desde playlist/álbum de Spotify
  --artist ARTIST         Modo artista: busca tracks de un artista específico
  --album ALBUM           Modo álbum: requiere --artist

Filtros:
  -n, --count N           Número de canciones [default: 10]
  -g, --genre GENRE       Forzar género (sobrescribe detección NL)
  --style [underground|comercial]

Output:
  --out FILE              CSV de salida [default: canciones.csv]
  --append                Añadir a CSV existente (no sobreescribir)

Comportamiento:
  --dry-run               Mostrar plan sin escribir nada
  --no-llm                Deshabilitar LLM (solo heurística)

Debug:
  -v, --verbose           Log level INFO
  -vv                     Log level DEBUG
```

### 4.3 — Subcomandos

```
mala-pata create "10 canciones de mambo"
mala-pata create --spotify URL
mala-pata download
mala-pata delete --artist "X" --title "Y"
mala-pata list          # muestra canciones.csv
mala-pata genres        # lista géneros disponibles
```

Esto resuelve el problema de los tres entry points sin coordinación. Un binario `mala-pata` como dispatcher unificado. Backwards compat: `mala-pata "pedido"` (sin subcomando) → trata el primer arg como `create`.

### 4.4 — Dry run

```
$ mala-pata create "10 canciones de salsa dura" --dry-run

Plan detectado:
  task:     playlist
  genre:    salsa_dura_clasica
  count:    10
  artist:   —
  style:    underground (inferido)
  sources:  discogs → musicbrainz → backfill

[DRY RUN] Nada fue escrito.
```

---

## 5. Estructura ideal de carpetas

```
mpc/                          # paquete Python instalable
├── __init__.py
├── cli.py                    # entry point, subcomandos, argparse
├── config.py                 # Config dataclass, from_env(), validacion
│
├── catalog/                  # dominio: conocimiento musical
│   ├── __init__.py
│   └── genres.py             # GENRE_DB, ANCHOR_ARTISTS, GENRE_RULES, BACKFILL
│
├── planner/                  # interpretar qué se pide
│   ├── __init__.py
│   ├── intent.py             # classify_request(), extract_count(), _guess_artist()
│   └── llm.py                # llm_plan(), prompts
│
├── sources/                  # obtener artista+título reales
│   ├── __init__.py
│   ├── musicbrainz.py
│   ├── discogs.py
│   ├── spotify_client.py
│   └── openai_source.py      # solo canciones reales, sin ficticias
│
├── builders/                 # construir listas de canciones
│   ├── __init__.py
│   ├── playlist.py           # pick_playlist(), pick_artist_playlist()
│   └── album.py              # build_album_csv()
│
├── pipeline/                 # etapa de descarga (futuro)
│   └── __init__.py
│
└── utils/
    ├── __init__.py
    ├── text.py               # simp(), strip_accents(), key_pair()
    └── csv_io.py             # read_csv(), write_csv(), append_csv()

mala_pata.py                  # thin entry point → mpc.cli.main()
request_to_csv.py             # backwards-compat wrapper
spotify_to_csv.py             # backwards-compat wrapper
pipeline_music.py             # pipeline (clasificador intacto)
dl-music-system.sh            # descarga por género
```

---

## 6. Propuestas de mejora específicas

### Búsqueda (sources)

**Problema:** Las 4 fuentes (Discogs, MB, Spotify, OpenAI) se consultan secuencialmente. Con rate limiting de MB (1s por request) y múltiples queries, construir una playlist puede tomar 30–60 segundos.

**Mejora:** Paralelizar con `concurrent.futures.ThreadPoolExecutor`:
```python
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {
        executor.submit(discogs.search_by_rule, key, rule): "discogs_rule",
        executor.submit(discogs.search_anchors, key, anchors): "discogs_anchor",
        executor.submit(mb.search_by_rule, key): "mb_rule",
        executor.submit(mb.search_anchors, key, anchors): "mb_anchor",
    }
    results = {label: f.result() for f, label in futures.items()}
```

**Mejora 2:** Cache persistente para búsquedas MB/Discogs por (genre, substyle). Una búsqueda de "salsa dura clásica" debería cachearse 7 días, no repetirse cada vez.

### Parsing / NL

**Problema:** Hay tres sistemas de parsing superpuestos:
1. `classify_request()` — intención simple/compleja
2. `llm_plan()` — plan estructurado via LLM
3. `_guess_artist_from_text()` — heurística de regex

Los tres operan sobre el mismo texto y luego hay lógica de merge manual entre sus resultados.

**Mejora:** Hacer del LLM el parser principal cuando está disponible, y del heurístico el fallback completo — no parcheando el resultado del LLM con heurísticas.

### Manejo de errores

**Problema actual:** Los errores de APIs externas se silencian con `except Exception: return []`. El usuario no sabe si Discogs falló o simplemente no tiene datos de ese género.

**Mejora:** Separar "no encontré resultados" de "falló la llamada". Al final del `create`, mostrar summary de fuentes:

```
Fuentes consultadas:
  discogs:        45 resultados
  musicbrainz:    32 resultados
  backfill:        3 completados  ← aviso: pool insuficiente

Total: 10 canciones escritas en canciones.csv
```

### Logs

Reemplazar todos los `print()` + `debug_print()` con `logging` estándar:
```python
import logging
logger = logging.getLogger("mpc.create")
logger.info("Analizando intención...")
logger.debug("Plan: %s", plan)
```

Con `-v` mapea a `INFO`, `-vv` a `DEBUG`. El output normal es solo lo que el usuario necesita saber.

---

## 7. Roadmap evolutivo 2.0

### Fase 0 — Inmediata (sin romper nada) ✅ COMPLETADO
1. **Eliminar `generate_basic_fictional_titles`** → fallo explícito si no hay resultados.
2. **Corregir el bug de géneros directos sin artista** (línea 1980).
3. **Unificar `run_request` y `run_request_with_direct_genre`** en una sola función.
4. **Mover `simp()` y text utils a archivo compartido** (`mpc/utils/text.py`).

### Fase 1 — Refactoring estructural ✅ COMPLETADO
- Extraer `genres.py` con todos los datos del dominio.
- Extraer clients de API a `sources/`.
- Crear `Config` dataclass con validación al arranque.
- Reemplazar `print`/`debug_print` con `logging`.
- Mover version check de yt-dlp al inicio del batch.

### Fase 2 — CLI redesign ✅ COMPLETADO
- Entry point unificado `mala_pata.py` con subcomandos.
- Flags completos: `--dry-run`, `--append`, `--style`, `--spotify`, etc.
- Backwards compat: `mala-pata "pedido"` sigue funcionando.
- Schema CSV con columna `genre`.

### Fase 3 — Performance & calidad (pendiente)
- Paralelizar búsquedas con ThreadPoolExecutor.
- Cache MB con TTL configurable.
- Summary de fuentes al final del create.

### Fase 4 — Extensibilidad (futuro)
- Genre definitions en YAML (no hardcoded en Python).
- Modo interactivo: preview antes de escribir CSV.
- Integración con Last.fm/ListenBrainz.

---

## 8. Riesgos técnicos

| Riesgo | Severidad | Estado | Mitigación |
|---|---|---|---|
| `generate_basic_fictional_titles` contamina el manifest | Alta | ✅ Eliminado | `openai_source.py` falla explícitamente |
| Bug: género directo sin artista da salsa dura | Alta | ✅ Corregido | `pick_playlist` usa el género correcto |
| MB rate limit (1 req/seg) con batches grandes | Media | Pendiente | Token bucket + cache de queries |
| Parsing de dos tokens interpretado como `(instrucción, género)` | Media | ✅ Corregido | Flag `--genre` explícito |
| Sin validación de config al inicio → error tardío | Media | ✅ Corregido | `Config.validate()` al arrancar |
| OpenAI cost sin cap | Baja | Igual | Budget tracking similar al de YouTube API |
| yt-dlp version check por canción | Baja | ✅ Corregido | Check único al cargar `dl-music-system.sh` |

---

## 9. Decisiones estratégicas tomadas

**1. Entry point unificado `mala-pata`.**
Un binario con subcomandos (`create`, `download`, `delete`, `list`, `genres`) resuelve la confusión entre los tres scripts sin romper nada.

**2. Eliminados los títulos ficticios.**
Es la falla de calidad más seria. Cuando no hay resultados, el sistema falla con mensaje claro. Mejor un error ruidoso que un fallo silencioso.

**3. El pipeline no fue refactorizado.**
`pipeline_music.py` funciona bien. El clasificador (heurístico + LLM) es crítico especialmente para la salsa y se mantiene intacto. Solo se extrajeron los datos de dominio (`GENRE_DB`, `GENRE_COMMAND`, `ALL_SLUGS`) a `mpc/catalog/genres.py`.

**4. El CSV como contrato se mantiene — schema ampliado.**
El CSV como interfaz entre etapas es una decisión arquitectónica sólida para un CLI personal. Es auditable, editable, versionable. Se añadió la columna `genre` opcional.

**5. Los géneros directos se integraron al mismo flujo.**
`balada`, `house`, `techno` ya no tienen una ruta de código separada. El flag `--genre` acepta cualquier slug del catálogo unificado.

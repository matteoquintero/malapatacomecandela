# Agregar un Género Nuevo

Con la arquitectura 2.0 solo hay **2 archivos** a modificar (antes eran 5).

---

## 1. `mpc/catalog/genres.py`

Es la única fuente de verdad del catálogo. Hay 3 secciones a editar:

### 1.1 Agregar a `GENRE_COMMAND`

```python
GENRE_COMMAND: Dict[str, str] = {
    ...
    "cumbia": "dl-cumbia",
    "reggae": "dl-reggae",   # ← nuevo
}
```

### 1.2 Clasificar en `AFROLATINO_SLUGS` o `DIRECT_GENRES`

```python
# Géneros afrolatinos (pasan por el clasificador heurístico + LLM):
AFROLATINO_SLUGS = [
    "son_cubano", "guaracha", ...,
    "reggae",  # ← si es un género que el clasificador debe detectar
]

# Géneros directos (bypass del clasificador, --genre explícito):
DIRECT_GENRES = {"balada", "house", "techno", "nueva_trova", "cumbia",
                 "reggae"}  # ← si el usuario lo pide con --genre
```

Un género puede estar en ambos o solo en uno.

### 1.3 Si es afrolatino: agregar a `GENRE_DB`

`GENRE_DB` es el conocimiento musical que usa el clasificador. Cada entrada:

```python
{
    "name": "Reggae",
    "aliases": ["Roots Reggae", "Rocksteady"],
    "artists_key": ["Bob Marley", "Peter Tosh", "Burning Spear"],
    "rhythm_traits": ["riddim", "one drop", "offbeat guitar"],
    "instrumentation": {
        "core": ["bajo", "batería", "guitarra eléctrica", "órgano"],
        "optional": ["metales", "coro"],
    },
    "signature_tracks": ["No Woman No Cry", "Redemption Song"],
    "negative": ["reggaeton", "dancehall comercial"],
},
```

Campos `negative` son críticos — evitan falsos positivos con géneros similares.

Opcionalmente agregar a `ANCHOR_ARTISTS`, `GENRE_RULES`, y `BACKFILL` si quieres
que el planner tenga mejores resultados al buscarlo en Discogs/MusicBrainz.

---

## 2. `dl-music-system.sh`

Agregar el mapeo de comando → directorio en el `case` de `dl_music()`:

```bash
case $GENERO in
    ...
    "dl-cumbia") GENRE_DIR="cumbia" ;;
    "dl-reggae") GENRE_DIR="reggae" ;;   # ← nuevo
    *)
        echo "❌ Género no reconocido: $GENERO"
        return 1
        ;;
esac
```

---

## Verificar

```bash
# El nuevo género debe aparecer en la lista
mala-pata genres

# Probarlo
mala-pata create "5 canciones de reggae" --genre reggae --dry-run
```

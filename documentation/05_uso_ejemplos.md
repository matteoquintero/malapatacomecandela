# Uso y Ejemplos

## Comandos del día a día

### Crear lista desde lenguaje natural

```bash
# Playlist de género
mala-pata create "10 canciones de salsa dura underground"
mala-pata create "15 mambos de los 50s"
mala-pata create "8 boogaloos poco conocidos"

# Artista específico
mala-pata create "5 canciones de Héctor Lavoe"
mala-pata create --artist "Ray Barretto" -n 10

# Álbum completo
mala-pata create --artist "Willie Colón" --album "El Malo"

# Género directo (sin clasificador afrolatino)
mala-pata create "silvio rodriguez" --genre nueva_trova
mala-pata create "10 cumbias" --genre cumbia

# Ver qué va a hacer antes de ejecutar
mala-pata create "10 de timba" --dry-run

# Añadir al CSV sin sobreescribir
mala-pata create "5 de Eddie Palmieri" --append
```

### Importar desde Spotify

```bash
# Playlist (detecta el tipo automáticamente)
mala-pata create --spotify https://open.spotify.com/playlist/XXXX

# Álbum con límite y género asignado
mala-pata create --spotify https://open.spotify.com/album/XXXX --count 10 --genre mambo

# El alias mala-pata-spotify sigue funcionando
mala-pata-spotify https://open.spotify.com/playlist/XXXX
```

### Descargar

```bash
# Descarga todo lo que hay en canciones.csv
mala-pata download

# El alias come-candela sigue funcionando
come-candela
```

### Borrar una canción

```bash
# Por nombre de archivo
mala-pata delete --filename "Héctor Lavoe - El Cantante.mp3"

# Por artista + título (borra todas las coincidencias)
mala-pata delete --artist "Héctor Lavoe" --title "El Cantante" --all

# El alias mala-candela sigue funcionando
mala-candela "Héctor Lavoe - El Cantante.mp3"
```

### Utilidades

```bash
# Ver canciones en el CSV actual
mala-pata list
mala-pata list otro_archivo.csv

# Ver géneros disponibles
mala-pata genres

# Ayuda
mala-pata --help
mala-pata create --help
```

---

## Flujo completo de ejemplo

```bash
# 1. Generar lista
mala-pata create "10 canciones de salsa dura clasica underground"

# 2. Revisar qué se generó
mala-pata list

# 3. Descargar
mala-pata download

# 4. Si algo no quedó bien, borrarlo
mala-pata delete --artist "X" --title "Y"
```

---

## Variables de entorno relevantes

| Variable | Efecto |
|---|---|
| `CLASSIFIER_MODE=HEURISTIC_ONLY` | Sin LLM en el clasificador |
| `OPENAI_API_KEY=` (vacía) | Desactiva LLM en el planner y clasificador |

---

## Flags completos de `mala-pata create`

```
mala-pata create [QUERY] [opciones]

  QUERY               Pedido en lenguaje natural

  --spotify URL       Importar desde Spotify
  --type playlist|album  Forzar tipo Spotify
  -n, --count N       Número de canciones (default: 10)
  -g, --genre SLUG    Forzar género
  -a, --artist ARTISTA  Focalizar en artista
  --album ALBUM       Álbum específico (requiere --artist)
  --style underground|comercial  Sesgo de selección
  --append            Añadir al CSV existente
  --out ARCHIVO       CSV de salida (default: canciones.csv)
  --dry-run           Mostrar plan sin escribir nada
  -v / -vv            Verbosidad (INFO / DEBUG)
```

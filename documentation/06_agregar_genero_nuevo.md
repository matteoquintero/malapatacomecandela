# 🎵 Guía para Agregar un Género Nuevo al Sistema

Esta guía documenta TODOS los lugares donde debes agregar un nuevo género directo al sistema `mala-pata-come-candela`.

## 📋 Checklist de Archivos a Modificar

Cuando agregues un nuevo género (ejemplo: `dl-cumbia`), debes modificar estos **5 archivos**:

### ✅ 1. `request_to_csv.py`

**Ubicaciones a modificar (3 lugares):**

#### 1.1 Lista de géneros directos (línea ~1792)

```python
# ===== Géneros Directos =====
DIRECT_GENRES = ["balada", "house", "nueva_trova", "techno", "dl-cumbia"]  # ← Agregar aquí
```

#### 1.2 Documentación en SYSTEM_DIRECT_GENRE (línea ~558-565)

```python
"GÉNEROS DIRECTOS:\n"
"- balada: música romántica y baladas\n"
"- house: música house y electrónica\n"
"- nueva_trova: nueva trova cubana\n"
"- techno: música techno\n"
"- dl-cumbia: cumbia digital y cumbia electrónica\n"  # ← Agregar descripción
"\n"
```

#### 1.3 Títulos ficticios para fallback (línea ~1498-1504)

```python
genre_titles = {
    "salsa": ["Salsa Caliente", "El Son de la Salsa", "Baila Salsa", "Ritmo Salsero"],
    "balada": ["Amor Eterno", "Te Extraño", "Mi Corazón", "Siempre Te Amaré"],
    "house": ["House Party", "Dance Floor", "Electronic Dreams", "Night Club"],
    "techno": ["Techno Beat", "Digital World", "Machine Music", "Future Sound"],
    "nueva_trova": ["Canción de Protesta", "El Pueblo Canta", "Libertad", "Revolución"],
    "dl-cumbia": ["Cumbia Digital", "Ritmo Electrónico", "Fiesta Cumbiera", "Baile Tropical"]  # ← Agregar títulos
}
```

---

### ✅ 2. `dl-music-system.sh`

**Ubicaciones a modificar (3 lugares):**

#### 2.1 Unalias al inicio (línea ~14-34)

```bash
unalias dl-cumbia 2>/dev/null || true  # ← Agregar aquí
```

#### 2.2 Case statement en función dl_music (línea ~92-118)

```bash
case $GENERO in
    "dl-salsa-dura-revival") GENRE_DIR="salsa_dura_revival" ;;
    # ... otros géneros ...
    "dl-techno") GENRE_DIR="techno" ;;
    "dl-cumbia") GENRE_DIR="cumbia" ;;  # ← Agregar aquí (nota: sin "dl-" en GENRE_DIR)
    *)
        echo "❌ Género no reconocido: $GENERO"
        return 1
        ;;
esac
```

#### 2.3 Funciones al final del script (línea ~264-286)

```bash
dl-techno() { dl_music "dl-techno" "$@"; }
dl-cumbia() { dl_music "dl-cumbia" "$@"; }  # ← Agregar aquí
```

---

### ✅ 3. `shell_setup.zsh`

**Ubicación a modificar:**

#### 3.1 Aliases simples (línea ~9-30)

```zsh
# Alias simples (yt-dlp directo)
alias dl-techno="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/techno/%(title)s.%(ext)s\""
alias dl-cumbia="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/cumbia/%(title)s.%(ext)s\""  # ← Agregar aquí
```

---

### ✅ 4. `pipeline_music.py`

**Ubicaciones a modificar (2 lugares):**

#### 4.1 Diccionario GENRE_COMMAND (línea ~243-252)

```python
GENRE_COMMAND: Dict[str, str] = {
    # ... géneros afrolatinos ...
    # Géneros directos
    "balada": "dl-balada",
    "house": "dl-house",
    "nueva_trova": "dl-nueva-troba",
    "techno": "dl-techno",
    "cumbia": "dl-cumbia",  # ← Agregar aquí (nota: sin "dl-" en la key)
}
```

#### 4.2 Mapeo en función process_csv (línea ~1782-1791)

```python
genre_to_command = {
    "balada": "dl-balada",
    "house": "dl-house",
    "nueva_trova": "dl-nueva-trova",
    "techno": "dl-techno",
    "dl-cumbia": "dl-cumbia"  # ← Agregar aquí (con "dl-" porque así viene del CSV)
}
```

---

### ✅ 5. `env.example` (opcional pero recomendado)

Si hay documentación de géneros en el archivo de ejemplo de configuración, actualízala también.

---

## 🎯 Nomenclatura y Convenciones

### Nombres importantes:

- **Comando shell**: `dl-cumbia` (con guiones)
- **Directorio**: `cumbia` (sin prefijo, con underscores si es necesario)
- **Key en Python**: `"cumbia"` o `"dl-cumbia"` (depende del contexto)

### Reglas:

1. Los **comandos shell** usan formato `dl-nombre-genero` con guiones
2. Los **directorios** usan `nombre_genero` con underscores (sin prefijo `dl-`)
3. En **DIRECT_GENRES** usa `"dl-cumbia"` si tiene guiones en el comando
4. En **GENRE_COMMAND** usa la key sin `dl-` pero el valor con `dl-`

---

## 🧪 Verificación Post-Integración

Después de agregar un género nuevo, verifica que funcione:

```bash
# 1. Compilación Python
python3 -m py_compile request_to_csv.py
python3 -m py_compile pipeline_music.py

# 2. Test del planner
mala-pata "5 canciones de bomba estereo" "dl-cumbia"

# 3. Test de descarga directa
dl-cumbia "VIDEO_ID" "Artista" "Título"

# 4. Test del pipeline completo
come-candela
```

---

## 📝 Ejemplo Completo: Agregando "dl-cumbia"

### 1. request_to_csv.py

```python
# Línea 1792
DIRECT_GENRES = ["balada", "house", "nueva_trova", "techno", "dl-cumbia"]

# Línea 563
"- dl-cumbia: cumbia digital y cumbia electrónica\n"

# Línea 1504
"dl-cumbia": ["Cumbia Digital", "Ritmo Electrónico", "Fiesta Cumbiera", "Baile Tropical"]
```

### 2. dl-music-system.sh

```bash
# Línea ~34
unalias dl-cumbia 2>/dev/null || true

# Línea ~113
"dl-cumbia") GENRE_DIR="cumbia" ;;

# Línea ~285
dl-cumbia() { dl_music "dl-cumbia" "$@"; }
```

### 3. shell_setup.zsh

```zsh
# Línea ~13
alias dl-cumbia="yt-dlp -x --audio-format mp3 -o \"$MUSIC_BASE/cumbia/%(title)s.%(ext)s\""
```

### 4. pipeline_music.py

```python
# Línea ~251
"cumbia": "dl-cumbia",

# Línea ~1790
"dl-cumbia": "dl-cumbia"
```

---

## 🚨 Errores Comunes

1. **Olvidar el unalias** → El script fallará si el alias ya existe
2. **Inconsistencia de nombres** → `dl-cumbia` vs `cumbia` vs `dl_cumbia`
3. **Falta el case statement** → Error "Género no reconocido"
4. **No agregar en pipeline_music.py** → El pipeline no procesará el género
5. **Olvidar los títulos ficticios** → Fallback no funcionará bien

---

## ✅ Checklist Final

Antes de hacer commit, verifica:

- [ ] `request_to_csv.py` - 3 lugares modificados
- [ ] `dl-music-system.sh` - 3 lugares modificados
- [ ] `shell_setup.zsh` - 1 lugar modificado
- [ ] `pipeline_music.py` - 2 lugares modificados
- [ ] Pruebas ejecutadas sin errores
- [ ] Documentación actualizada (este archivo)

---

**Última actualización**: Octubre 2025
**Mantenedor**: Sistema Mala Pata Come Candela

# mpc/catalog/genres.py
# -*- coding: utf-8 -*-
"""
Fuente única de verdad para toda la información de géneros.
31 slugs activos (26 afrolatinos + 5 directos).

Campos de GENRE_DB:
  slug        — identificador canónico
  year_from   — primer año de grabaciones/uso documentado
  year_to     — último año del período principal; None = sigue activo
                El clasificador usa estos como señal SUAVE (bonus/penalty leve),
                no como filtro estricto: un son cubano moderno sigue siendo son cubano.
"""

from typing import Dict, List, Optional

# ── Mapa genre_slug → comando dl-music-system.sh ─────────────────────────────
GENRE_COMMAND: Dict[str, str] = {
    # Afrolatinos / caribeños (orden cronológico aproximado)
    "changui":                  "dl-changui",
    "bomba":                    "dl-bomba",
    "danzon":                   "dl-danzon",
    "bolero":                   "dl-bolero",
    "rumba_guaguanco":          "dl-rumba-guaguanco",
    "son_cubano":               "dl-son-cubano",
    "guaracha":                 "dl-guaracha",
    "guajira_moderna":          "dl-guajira-moderna",
    "plena":                    "dl-plena",
    "son_montuno":              "dl-son-montuno",
    "afro_cuban_jazz":          "dl-afro-cuban-jazz",
    "mambo":                    "dl-mambo",
    "descarga":                 "dl-descarga",
    "cha_cha_cha":              "dl-cha-cha-cha",
    "exotica":                  "dl-exotica",
    "pachanga":                 "dl-pachanga",
    "mozambique":               "dl-mozambique",
    "boogaloo":                 "dl-boogaloo",
    "latin_soul":               "dl-latin-soul",
    "salsa_dura_clasica":       "dl-salsa-dura-clasica",
    "guaguanco_fusionado":      "dl-guaguanco-fusionado",
    "songo":                    "dl-songo",
    "salsa_romantica":          "dl-salsa-romantica",
    "timba":                    "dl-timba",
    "salsa_dura_revival":       "dl-salsa-dura-revival",
    "salsa_choke":              "dl-salsa-choke",
    # Directos (sin clasificador afrolatino)
    "balada":                   "dl-balada",
    "house":                    "dl-house",
    "nueva_trova":              "dl-nueva-trova",
    "techno":                   "dl-techno",
    "cumbia":                   "dl-cumbia",
}

ALL_SLUGS: List[str] = list(GENRE_COMMAND.keys())

# ── Mapa genre_slug → subdirectorio en la librería ───────────────────────────
GENRE_DIR: Dict[str, str] = {slug: slug for slug in ALL_SLUGS}

# ── Slugs deprecated: se conservan para que la library.db existente no rompa.
#    El script scripts/migrate_genre_splits.py los migra a los slugs nuevos.
DEPRECATED_SLUGS: Dict[str, str] = {
    "plena_bomba":              "plena",          # → plena o bomba según reclasificación
    "afro_cuban_jazz_descarga": "afro_cuban_jazz", # → afro_cuban_jazz o descarga
}

# ── Clasificación de flujo ────────────────────────────────────────────────────
DIRECT_GENRES: List[str] = ["balada", "house", "nueva_trova", "techno", "cumbia"]
AFROLATINO_SLUGS: List[str] = [s for s in ALL_SLUGS if s not in DIRECT_GENRES]

# ── Base de conocimiento (usada por el clasificador heurístico y el LLM) ──────
def genre_name(slug: str) -> str:
    """Retorna el nombre legible del género para usar en TCON.
    Lookup en GENRE_DB, fallback a slug humanizado."""
    if not slug:
        return ""
    for g in GENRE_DB:
        if g.get("slug") == slug:
            name = g.get("name") or ""
            if name:
                return name
    # Fallback: salsa_dura_clasica → "Salsa Dura Clasica"
    return slug.replace("_", " ").title()


GENRE_DB: List[Dict] = [
    # ── Raíces afrocaribeñas ──────────────────────────────────────────────────
    {
        "slug": "changui",
        "name": "Changüí",
        "year_from": 1860, "year_to": None,
        "aliases": ["Changui", "Changüí de Guantánamo", "Changüí de Yateras", "Son oriental primitivo"],
        "artists_key": ["Grupo Changüí de Guantánamo", "Elio Revé", "Nené Manfugás", "Grupo El Güirito"],
        "rhythm_traits": ["marímbula en lugar de bajo", "bongó changüisero", "son primitivo", "tumbador", "tres guantanamero"],
        "instrumentation": {
            "core": ["tres", "marímbula", "bongó", "maracas", "güiro"],
        },
        "signature_tracks": ["El Guararey de Pastorita", "Changüí de Guantánamo"],
        "negative": ["salsa dura trombones", "mambo big band", "piano moderno sintetizado"],
    },
    {
        "slug": "bomba",
        "name": "Bomba",
        "year_from": 1650, "year_to": None,
        "aliases": ["Bomba puertorriqueña", "Bomba sicá", "Bomba yubá", "Bomba holandés", "barriles de bomba", "Bomba cuembé"],
        "artists_key": ["Rafael Cortijo", "Cortijo y su Combo", "Plena Libre", "Los Pleneros de la 21", "Grupo Yuba"],
        "rhythm_traits": ["barriles", "sicá", "yubá", "llamada y respuesta percusiva", "diálogo bailarín-tamborero"],
        "instrumentation": {
            "core": ["barril buleador", "barril primo", "cuá", "maraca"],
        },
        "signature_tracks": ["Leña Verde", "Protesta de los Tambores", "Bomba de Aquí"],
        "negative": ["panderetas plena", "piano salsa", "metales salsa pesados"],
    },
    {
        "slug": "danzon",
        "name": "Danzón",
        "year_from": 1879, "year_to": None,
        "aliases": ["Danzonete", "Danzón mambo", "Danzón de nuevo ritmo", "Danzonero"],
        "artists_key": ["Miguel Faílde", "Arcaño y sus Maravillas", "Antonio Arcaño", "Orquesta Aragón", "Aniceto Díaz"],
        "rhythm_traits": ["paseo introductorio", "trío melodioso", "charanga cubana", "compás de 2/4", "ritmo cuadrado"],
        "instrumentation": {
            "core": ["flauta", "violines", "piano", "contrabajo", "timbales", "güiro"],
        },
        "signature_tracks": ["Las Alturas de Simpson", "Rompiendo la Rutina", "Tres Lindas Cubanas"],
        "negative": ["mambo big band trombones", "salsa dura", "reggaeton"],
    },
    {
        "slug": "bolero",
        "name": "Bolero Cubano",
        "year_from": 1883, "year_to": None,
        "aliases": ["Bolero", "Bolero-son", "Filin", "Bolero-mambo", "Bolero-cha", "Bolero-beguine", "bolero cubano"],
        "artists_key": ["Trío Matamoros", "Ibrahim Ferrer", "Beny Moré", "Omara Portuondo", "Isolina Carrillo", "Vicentico Valdés", "Pepe Sánchez"],
        "rhythm_traits": ["lento romántico", "filin melódico", "cadencia suave", "melodía vocal protagonista", "bolero-son híbrido"],
        "instrumentation": {
            "core": ["guitarra", "tres", "contrabajo", "bongó", "voz solista"],
            "optional": ["cuerdas", "piano", "flauta"],
        },
        "signature_tracks": ["Dos Gardenias", "Quiéreme Mucho", "Bésame Mucho", "Tristezas"],
        "negative": ["salsa dura trombones", "reggaeton", "guaracha rápida"],
    },
    {
        "slug": "rumba_guaguanco",
        "name": "Rumba Guaguancó",
        "year_from": 1880, "year_to": None,
        "aliases": ["Guaguancó", "Yambú", "Columbia", "Guarapachangueo", "Batá-rumba", "Rumba cubana"],
        "artists_key": ["Los Muñequitos de Matanzas", "Yoruba Andabo", "Clave y Guaguancó", "Los Papines", "Grupo AfroCuba de Matanzas"],
        "rhythm_traits": ["polirritmia", "quinto improvisador", "vacunao", "yambú lento", "columbia vertical"],
        "instrumentation": {
            "core": ["quinto", "tres golpes", "tumba", "claves", "guagua", "voz", "coro"],
            "optional": ["chekeré", "palmas"],
        },
        "signature_tracks": ["Rumba pa' los rumberos", "Llora como lloré"],
        "negative": ["mambo big band", "metales salsa pesados"],
    },
    {
        "slug": "son_cubano",
        "name": "Son Cubano",
        "year_from": 1890, "year_to": None,
        "aliases": ["Son", "Son Habanero", "Son Oriental", "Son Pregón", "Sucu-sucu", "septeto"],
        "artists_key": ["Trío Matamoros", "Septeto Nacional", "Ignacio Piñeiro", "Compay Segundo", "Eliades Ochoa", "Cuarteto Oriental"],
        "rhythm_traits": ["tumbao de bajo caminante", "montuno", "llamada y respuesta"],
        "instrumentation": {
            "core": ["tres cubano", "guitarra", "piano", "bongó", "maracas", "claves", "contrabajo", "trompeta"],
            "optional": ["conga", "flauta", "violín"],
        },
        "signature_tracks": ["Lágrimas Negras", "Échale Salsita", "Chan Chan"],
        "negative": ["salsa romantica", "bachata", "reggaeton"],
    },
    {
        "slug": "guaracha",
        "name": "Guaracha",
        "year_from": 1920, "year_to": None,
        "aliases": ["Guaracha-son", "Guaracha soneada"],
        "artists_key": ["Beny Moré", "Celia Cruz", "Ñico Saquito", "Sonora Matancera"],
        "rhythm_traits": ["coros rápidos", "soneo juguetón", "doble sentido"],
        "instrumentation": {
            "core": ["tres", "guitarra", "piano", "bongó", "maracas", "claves", "contrabajo", "trompeta"],
            "optional": ["conga", "saxofón"],
        },
        "signature_tracks": ["Cuidadito Compay Gallo", "María Cristina", "Francisco Guayabal"],
        "negative": ["balada", "romantica"],
    },
    {
        "slug": "guajira_moderna",
        "name": "Guajira Moderna",
        "year_from": 1925, "year_to": None,
        "aliases": ["Guajira Son", "Guajira-son", "Guajira lenta", "Son montuno lento"],
        "artists_key": ["Guillermo Portabales", "Compay Segundo", "Eliades Ochoa"],
        "rhythm_traits": ["tumbao suave", "énfasis melódico y poético"],
        "instrumentation": {
            "core": ["tres", "guitarra", "bongó", "maracas", "contrabajo", "claves"],
            "optional": ["flauta", "violín"],
        },
        "signature_tracks": ["El Carretero", "Chan Chan", "Rico Vacilón"],
        "negative": ["mambo explosivo", "guaracha rapida", "salsa romantica"],
    },
    {
        "slug": "plena",
        "name": "Plena",
        "year_from": 1900, "year_to": None,
        "aliases": ["Plena puertorriqueña", "Plena de pandero", "Plena de orquesta", "Plena fusión", "periódico cantado"],
        "artists_key": ["Ismael Rivera", "Pleneros de la 21", "Viento de Agua", "Manuel Canario", "Plena Libre"],
        "rhythm_traits": ["panderetas", "güiro", "llamada y respuesta cantada", "crónica social", "pandero seguidor"],
        "instrumentation": {
            "core": ["panderetas", "güiro", "coro"],
            "optional": ["cuatro", "guitarra", "metales orquesta"],
        },
        "signature_tracks": ["Las Caras Lindas", "Maquinolandera", "Santa María"],
        "negative": ["barriles bomba", "salsa dura metales pesados"],
    },
    {
        "slug": "son_montuno",
        "name": "Son Montuno",
        "year_from": 1940, "year_to": None,
        "aliases": ["Conjunto sonero", "Son de conjunto", "Son montuno rápido", "Guaracha-son"],
        "artists_key": ["Arsenio Rodríguez", "Conjunto Casino", "Roberto Faz", "Conjunto Chappottín", "Miguelito Cuní"],
        "rhythm_traits": ["tumbao de bajo con conga", "cuatro trompetas", "call and response intenso", "montuno rápido", "conjunto sonero"],
        "instrumentation": {
            "core": ["tres", "piano", "conga", "bongó", "contrabajo", "trompetas", "maracas", "claves"],
        },
        "signature_tracks": ["Bruca Maniguá", "Fuego en el 23", "Dame un Cachito Pa' Huele"],
        "negative": ["charanga pura flauta violines", "cha cha cha", "balada romántica"],
    },
    {
        "slug": "afro_cuban_jazz",
        "name": "Afro Cuban Jazz",
        "year_from": 1943, "year_to": None,
        "aliases": ["Afro-Cuban Jazz", "Latin Jazz clásico", "Cubop", "jazz afrocubano", "latin jazz"],
        "artists_key": ["Machito", "Mario Bauzá", "Tito Puente", "Mongo Santamaría", "Cal Tjader", "Dizzy Gillespie"],
        "rhythm_traits": ["tema–solos–tema", "clave en jazz", "improvisación jazz sobre ritmo cubano"],
        "instrumentation": {
            "core": ["piano", "bajo", "congas", "timbales", "bongó", "metales", "saxos"],
            "optional": ["batá", "flauta", "vibráfono"],
        },
        "signature_tracks": ["Tanga", "Manteca", "Afro Blue"],
        "negative": ["descarga jam sin arreglo compuesto", "balada", "romantica"],
    },
    {
        "slug": "mambo",
        "name": "Mambo",
        "year_from": 1945, "year_to": 1965,
        "aliases": ["Mambo big band", "Mambo doble", "Mambo triple", "Mambo de big band"],
        "artists_key": ["Pérez Prado", "Tito Puente", "Machito"],
        "rhythm_traits": ["síncopas cortantes", "breaks de metales", "mambos instrumentales"],
        "instrumentation": {
            "core": ["piano", "bajo", "congas", "timbales", "bongó", "trompetas", "trombones", "saxofones"],
        },
        "signature_tracks": ["Mambo No. 5", "Ran Kan Kan", "Mambo Inn"],
        "negative": ["charanga pura flauta violines"],
    },
    {
        "slug": "descarga",
        "name": "Descarga",
        "year_from": 1950, "year_to": None,
        "aliases": ["Descarga cubana", "Descarga instrumental", "Jam session latina", "Descarga vocal", "jam session"],
        "artists_key": ["Israel Cachao López", "Bebo Valdés", "Tata Güines", "Chombo Silva"],
        "rhythm_traits": ["improvisación colectiva", "jam session", "descarga libre", "solos extendidos sin arreglo"],
        "instrumentation": {
            "core": ["piano", "bajo", "congas", "timbales", "bongó"],
            "optional": ["flauta", "saxo", "trompeta"],
        },
        "signature_tracks": ["Descarga Cachao", "Descarga Total", "Descargas en Miniatura"],
        "negative": ["arreglos big band compuestos", "balada", "romantica", "coro cantado"],
    },
    {
        "slug": "cha_cha_cha",
        "name": "Cha Cha Chá",
        "year_from": 1953, "year_to": None,
        "aliases": ["Chachachá", "Cha-cha-cha", "Charanga cubana", "Charanga con trompetas"],
        "artists_key": ["Orquesta América", "Orquesta Aragón", "José Fajardo", "Enrique Jorrín", "Orquesta Broadway"],
        "rhythm_traits": ["1–2–cha-cha-chá", "charanga", "flauta y violines"],
        "instrumentation": {
            "core": ["flauta", "violines", "piano", "contrabajo", "timbales", "güiro", "maracas"],
        },
        "signature_tracks": ["La Engañadora", "Me lo Dijo Adela", "El Bodeguero"],
        "negative": ["trombones pesados 70s"],
    },
    {
        "slug": "exotica",
        "name": "Exotica",
        "year_from": 1957, "year_to": 1965,
        "aliases": ["Tiki music", "Space age pop", "Caribbean exotica", "Lounge", "Polynesian exotica"],
        "artists_key": ["Martin Denny", "Les Baxter", "Yma Sumac", "Arthur Lyman"],
        "rhythm_traits": ["atmósfera cinematográfica", "selva", "vibráfono", "lounge"],
        "instrumentation": {
            "core": ["percusión suave", "marimba", "vibráfono", "cuerdas", "flautas"],
        },
        "signature_tracks": ["Quiet Village", "Taboo"],
        "negative": ["salsa dura", "boogaloo"],
    },
    {
        "slug": "pachanga",
        "name": "Pachanga",
        "year_from": 1959, "year_to": 1965,
        "aliases": ["Pachanga neoyorquina", "Alegre Sound", "Pre-salsa neoyorquina", "Mambo de barrio"],
        "artists_key": ["Eduardo Davidson", "Johnny Pacheco", "Charlie Palmieri", "Orquesta Broadway"],
        "rhythm_traits": ["ritmo animado bailable", "flauta dominante", "coro festivo", "güiro fuerte", "pachanga beat"],
        "instrumentation": {
            "core": ["flauta", "violines", "piano", "bajo", "timbales", "güiro", "coro"],
        },
        "signature_tracks": ["La Pachanga", "Cañonazo", "Muévete"],
        "negative": ["salsa dura trombones pesados", "timba moderna", "reggaeton"],
    },
    {
        "slug": "mozambique",
        "name": "Mozambique",
        "year_from": 1963, "year_to": 1975,
        "aliases": ["Mozambique cubano", "ritmo mozambique", "mozambique de Pello"],
        "artists_key": ["Pello el Afrokán", "Pedro Izquierdo", "Orquesta Ritmo Oriental"],
        "rhythm_traits": ["polirritmo afrocubano masivo", "clave mozambique", "comparsa callejera", "bloques percusivos"],
        "instrumentation": {
            "core": ["batería de percusión colectiva", "trompetas", "timbales", "conga", "coro masivo"],
        },
        "signature_tracks": ["Camina y Ven", "Mozambique"],
        "negative": ["salsa romantica", "cha cha cha charanga", "reggaeton"],
    },
    {
        "slug": "boogaloo",
        "name": "Boogaloo",
        "year_from": 1965, "year_to": 1972,
        "aliases": ["Latin Boogaloo", "Bugalú", "Shing-a-ling", "watusi"],
        "artists_key": ["Pete Rodríguez", "Joe Cuba", "Johnny Colón", "Ray Barretto"],
        "rhythm_traits": ["groove soul", "spanglish", "shing-a-ling", "watusi"],
        "instrumentation": {
            "core": ["órgano", "piano", "bajo eléctrico", "congas", "timbales", "bongó", "metales"],
        },
        "signature_tracks": ["I Like It Like That", "Bang Bang", "Boogaloo Blues"],
        "negative": ["latin soul balada suave"],
    },
    {
        "slug": "latin_soul",
        "name": "Latin Soul",
        "year_from": 1965, "year_to": 1978,
        "aliases": ["Nuyorican soul", "Latin funk", "Latin R&B"],
        "artists_key": ["Joe Bataan", "Ralfi Pagán", "Harvey Averne", "Malo"],
        "rhythm_traits": ["balada soul con conga", "órgano", "doo-wop"],
        "instrumentation": {
            "core": ["voz soul", "órgano", "guitarra", "bajo", "batería", "conga", "bongó"],
            "optional": ["metales suaves"],
        },
        "signature_tracks": ["Ordinary Guy", "Gypsy Woman", "I'm Your Puppet"],
        "negative": ["boogaloo shing a ling explosivo"],
    },
    {
        "slug": "salsa_dura_clasica",
        "name": "Salsa Dura Clásica",
        "year_from": 1968, "year_to": 1985,
        "aliases": ["Salsa Brava", "Salsa 70s", "Salsa de trombones", "Salsa consciente", "salsa brava fania"],
        "artists_key": ["Willie Colón", "Héctor Lavoe", "Rubén Blades", "Ray Barretto", "Eddie Palmieri", "Fania All Stars", "Sonora Ponceña", "Raphy Leavitt"],
        "rhythm_traits": ["coro–soneo intenso", "mambos de metales", "descargas", "montuno"],
        "instrumentation": {
            "core": ["piano", "bajo", "congas", "bongó", "timbales", "trombones", "trompetas", "coros"],
        },
        "signature_tracks": ["Aguanile", "Plástico", "Indestructible", "Quítate Tú"],
        "negative": ["romantica", "erotica"],
    },
    {
        "slug": "guaguanco_fusionado",
        "name": "Guaguancó Fusionado",
        "year_from": 1970, "year_to": None,
        "aliases": ["Guaguancó jazzístico", "Guaguancó salsero", "Batacumbele"],
        "artists_key": ["Eddie Palmieri", "Irakere", "Batacumbele", "Los Van Van"],
        "rhythm_traits": ["toque rumbero en salsa", "bloques rumberos"],
        "instrumentation": {
            "core": ["congas", "quinto", "piano", "bajo", "metales", "coros"],
            "optional": ["batá"],
        },
        "signature_tracks": ["Adoración", "Un Día Bonito"],
        "negative": ["puro folklor sin orquesta"],
    },
    {
        "slug": "songo",
        "name": "Songo",
        "year_from": 1975, "year_to": None,
        "aliases": ["Son-funk cubano", "Songo fusión", "Songo con batería"],
        "artists_key": ["Los Van Van", "Juan Formell", "César Pupy Pedroso"],
        "rhythm_traits": ["batería rock con timbal", "son con funk", "bajo eléctrico protagónico", "songo beat"],
        "instrumentation": {
            "core": ["batería", "timbales", "bajo eléctrico", "piano", "teclados", "metales", "coros"],
        },
        "signature_tracks": ["Anda Ven y Muévete", "Sandunguera", "El Buey Cansao"],
        "negative": ["salsa romantica", "reggaeton", "timba hip hop"],
    },
    {
        "slug": "salsa_romantica",
        "name": "Salsa Romántica",
        "year_from": 1984, "year_to": 1999,
        "aliases": ["Salsa sensual", "Salsa erótica", "Salsa pop"],
        "artists_key": ["Lalo Rodríguez", "Frankie Ruiz", "Eddie Santiago", "Gilberto Santa Rosa", "Jerry Rivera", "Luis Enrique"],
        "rhythm_traits": ["coro emotivo", "menos agresividad percusiva", "producción pulida"],
        "instrumentation": {
            "core": ["piano", "bajo", "congas", "bongó", "timbales suaves", "metales contenidos", "voz protagonista"],
            "optional": ["sintetizadores"],
        },
        "signature_tracks": ["Ven Devórame Otra Vez", "Desnúdate Mujer", "Amores Como el Nuestro"],
        "negative": ["trombones agresivos 70s", "soneo largo"],
    },
    {
        "slug": "timba",
        "name": "Timba",
        "year_from": 1988, "year_to": None,
        "aliases": ["Timba clásica", "Timba fusión", "Timba con hip hop"],
        "artists_key": ["NG La Banda", "Los Van Van", "Charanga Habanera", "Pupy y Los Que Son Son", "Manolín"],
        "rhythm_traits": ["bloqueos y cortes", "bajo protagónico", "cambios súbitos"],
        "instrumentation": {
            "core": ["piano", "bajo eléctrico", "batería", "congas", "timbales", "metales", "coros"],
            "optional": ["teclados"],
        },
        "signature_tracks": ["Te Pone la Cabeza Mala", "La Habana Me Llama", "Soy Todo"],
        "negative": ["boogaloo", "salsa romantica"],
    },
    {
        "slug": "salsa_dura_revival",
        "name": "Salsa Dura Revival",
        "year_from": 2000, "year_to": None,
        "aliases": ["Neosalsa", "Neo salsa", "Salsa brava moderna", "Salsa académica"],
        "artists_key": ["La-33", "Spanish Harlem Orchestra", "La Excelencia", "El Macabeo", "La Mambanegra", "Tromboranga", "Los Hacheros"],
        "rhythm_traits": ["mambos pesados", "soneo vivo", "producción nítida"],
        "instrumentation": {
            "core": ["piano", "bajo", "congas", "bongó", "timbales", "trombones", "trompetas", "coros fuertes"],
        },
        "signature_tracks": ["La Pantera Mambo", "Salsa Dura", "Un Poquito de Swing"],
        "negative": ["romantica noventera"],
    },
    {
        "slug": "salsa_choke",
        "name": "Salsa Choke",
        "year_from": 2004, "year_to": None,
        "aliases": ["Choke", "Salsa urbana colombiana", "Choke clásico", "Choke electrónico"],
        "artists_key": ["CJ Castro", "Cali Flow Latino", "Jhonny Rivera", "Alexis Play"],
        "rhythm_traits": ["ritmo sincopado urbano", "sample loop", "coros cortos repetitivos", "bajo electrónico", "beat choke"],
        "instrumentation": {
            "core": ["beat electrónico", "bajo eléctrico", "voz", "coros", "sintetizadores"],
        },
        "signature_tracks": ["Ras Tas Tas", "Chichoky", "Movimiento"],
        "negative": ["salsa dura clásica trombones", "timba cubana", "reggaeton puro"],
    },
]

# ── Defaults para campos opcionales (se irán poblando por género) ─────────────
# known_channels:     canales de YouTube típicos del género (boost fuerte si matchea).
# typical_duration_sec: rango esperado en segundos (boost suave si el track cae dentro).
#                       None = sin rango conocido (no aplica señal).
for _g in GENRE_DB:
    _g.setdefault("known_channels", [])
    _g.setdefault("typical_duration_sec", None)

_CHANNEL_SEEDS: Dict[str, List[str]] = {
    "salsa_dura_clasica":   ["Fania Records", "Fania All Stars", "Craft Recordings", "Tico Records", "Vaya Records", "Cotique Records"],
    "salsa_dura_revival":   ["La-33", "Spanish Harlem Orchestra", "La Mambanegra Official", "La Excelencia Salsa Dura", "Orquesta El Macabeo", "Jimmy Bosch"],
    "son_cubano":           ["World Circuit", "Buena Vista Social Club", "Egrem", "Tumbao Cuban Classics", "Septeto Nacional"],
    "son_montuno":          ["Egrem", "Tumbao Cuban Classics", "Arsenio Rodriguez", "Conjunto Chappottin"],
    "bolero":               ["Egrem", "Buena Vista Social Club", "Omara Portuondo", "Ibrahim Ferrer"],
    "rumba_guaguanco":      ["Egrem", "Unicornio", "Los Munequitos de Matanzas", "Yoruba Andabo"],
    "danzon":               ["Egrem", "Orquesta Aragon", "Failde"],
    "mambo":                ["RCA Victor", "Tumbao Cuban Classics", "Perez Prado"],
    "descarga":             ["Panart", "Tumbao Cuban Classics", "Maype", "Alegre All Stars"],
    "cha_cha_cha":          ["Egrem", "Orquesta Aragón", "Orquesta America"],
    "pachanga":             ["Alegre Records", "Fania Records", "Charanga Duboney"],
    "boogaloo":             ["Fania Records", "Tico Records", "Alegre Records", "Cotique Records"],
    "latin_soul":           ["Fania Records", "Salsoul Records", "Tico Records"],
    "timba":                ["Egrem", "Bis Music", "NG La Banda", "Havana Caliente"],
    "songo":                ["Egrem", "Los Van Van", "Areito"],
    "mozambique":           ["Egrem", "Pello el Afrokan"],
    "salsa_romantica":      ["Sony Music Latin", "WEA Latina", "RMM Records", "TH-Rodven"],
    "exotica":              ["Capitol Records", "Liberty Records", "Martin Denny"],
    "changui":              ["Egrem", "Grupo Changui de Guantanamo"],
    "guaracha":             ["Egrem", "Tumbao Cuban Classics"],
    "guajira_moderna":      ["Egrem", "Eliades Ochoa"],
    "plena":                ["Viento de Agua", "Plena Libre", "Ismael Rivera"],
    "bomba":                ["Viento de Agua", "Los Pleneros de la 21", "Cortijo y su Combo"],
    "afro_cuban_jazz":      ["Blue Note Records", "Concord Jazz", "Verve Records"],
    "guaguanco_fusionado":  ["Fania Records", "Eddie Palmieri"],
    "salsa_choke":          ["Chocquibtown", "Sony Music Colombia"],
    "cumbia":               ["Discos Fuentes", "Codiscos", "Sonolux"],
    "nueva_trova":          ["Egrem", "Silvio Rodriguez", "Pablo Milanes"],
}
_DURATION_SEEDS: Dict[str, tuple] = {
    "boogaloo":           (140, 240),
    "pachanga":           (150, 230),
    "cha_cha_cha":        (150, 240),
    "guaracha":           (150, 240),
    "salsa_romantica":    (200, 320),
    "salsa_dura_clasica": (200, 420),
    "salsa_dura_revival": (200, 420),
    "descarga":           (300, 720),
    "afro_cuban_jazz":    (300, 600),
    "timba":              (240, 480),
    "balada":             (200, 300),
    "bolero":             (180, 280),
}
for _g in GENRE_DB:
    if not _g["known_channels"] and _g["slug"] in _CHANNEL_SEEDS:
        _g["known_channels"] = _CHANNEL_SEEDS[_g["slug"]]
    if _g["typical_duration_sec"] is None and _g["slug"] in _DURATION_SEEDS:
        _g["typical_duration_sec"] = _DURATION_SEEDS[_g["slug"]]

# ── Artistas ancla por género ──────────────────────────────────────────────────
ANCHOR_ARTISTS: Dict[str, List[str]] = {g["slug"]: g["artists_key"] for g in GENRE_DB}

# ── Reglas de búsqueda por género ─────────────────────────────────────────────
GENRE_RULES: Dict[str, Dict] = {
    "changui":          {"query_hint": ["changüí", "changui", "guantánamo", "marímbula", "tres guantanamero"], "negative_hint": ["salsa dura", "mambo big band"], "mb_tags": ["changüí", "cuban folk"]},
    "bomba":            {"query_hint": ["bomba", "barriles", "sicá", "yubá", "bomba puertorriqueña"], "negative_hint": ["panderetas plena", "piano salsa"], "mb_tags": ["bomba", "puerto rican"]},
    "danzon":           {"query_hint": ["danzón", "danzon", "danzonete", "charanga cubana", "paseo", "flauta violines"], "negative_hint": ["mambo big band", "salsa dura", "reggaeton"], "mb_tags": ["danzón", "cuban"]},
    "bolero":           {"query_hint": ["bolero", "bolero cubano", "filin", "bolero-son", "romántico cubano"], "negative_hint": ["salsa dura", "guaracha rápida", "reggaeton"], "mb_tags": ["bolero", "cuban", "romantic"]},
    "rumba_guaguanco":  {"query_hint": ["guaguancó", "rumba", "vacunao", "yambú", "columbia"], "negative_hint": ["metales salsa", "mambo big band"], "mb_tags": ["rumba", "guaguancó", "afrocuban"]},
    "son_cubano":       {"query_hint": ["son cubano", "son habanero", "son oriental", "son pregón", "septeto", "tres cubano"], "negative_hint": ["salsa romantica", "bachata", "reggaeton"], "mb_tags": ["son", "cuban"]},
    "guaracha":         {"query_hint": ["guaracha", "doble sentido", "vacilón", "jocosa"], "negative_hint": ["balada", "romantica"], "mb_tags": ["guaracha", "cuban"]},
    "guajira_moderna":  {"query_hint": ["guajira", "guajira son", "tres", "campesina", "guajiro"], "negative_hint": ["mambo explosivo", "guaracha rapida", "salsa romantica"], "mb_tags": ["guajira", "cuban"]},
    "plena":            {"query_hint": ["plena", "panderetas", "periódico cantado", "plena puertorriqueña"], "negative_hint": ["barriles bomba", "metales pesados salsa"], "mb_tags": ["plena", "puerto rican"]},
    "son_montuno":      {"query_hint": ["son montuno", "conjunto sonero", "arsenio", "trompetas son", "guaracha son"], "negative_hint": ["charanga flauta violín", "cha cha cha"], "mb_tags": ["son montuno", "cuban"]},
    "afro_cuban_jazz":  {"query_hint": ["afro-cuban jazz", "latin jazz", "cubop", "solo de", "instrumental jazz clave"], "negative_hint": ["coro romántico", "balada", "descarga jam"], "mb_tags": ["latin jazz", "cubop"]},
    "mambo":            {"query_hint": ["mambo", "big band", "trombones", "trompetas", "breaks mambo"], "negative_hint": ["charanga flauta violín puro cha cha"], "mb_tags": ["mambo", "latin"]},
    "descarga":         {"query_hint": ["descarga", "descarga cubana", "jam session", "descarga instrumental", "cachao"], "negative_hint": ["arreglos big band", "balada", "coro cantado"], "mb_tags": ["descarga", "cuban jazz"]},
    "cha_cha_cha":      {"query_hint": ["cha cha cha", "chachachá", "charanga", "flauta", "violines"], "negative_hint": ["trombones pesados salsa dura"], "mb_tags": ["cha-cha-cha", "charanga"]},
    "exotica":          {"query_hint": ["exotica", "tiki", "lounge", "vibráfono", "selva"], "negative_hint": ["salsa dura", "boogaloo"], "mb_tags": ["exotica", "lounge"]},
    "pachanga":         {"query_hint": ["pachanga", "alegre sound", "pachanga beat", "johnny pacheco flauta"], "negative_hint": ["salsa dura trombones", "timba"], "mb_tags": ["pachanga", "nuyorican"]},
    "mozambique":       {"query_hint": ["mozambique", "pello el afrokán", "pello afrokan", "ritmo mozambique"], "negative_hint": ["salsa romantica", "reggaeton"], "mb_tags": ["mozambique", "cuban"]},
    "boogaloo":         {"query_hint": ["boogaloo", "bugalú", "shing-a-ling", "watusi", "spanglish"], "negative_hint": ["latin soul balada suave"], "mb_tags": ["boogaloo", "nuyorican"]},
    "latin_soul":       {"query_hint": ["latin soul", "doo-wop", "balada soul", "nuyorican soul", "órgano motown"], "negative_hint": ["boogaloo shing-a-ling explosivo"], "mb_tags": ["latin soul", "nuyorican"]},
    "salsa_dura_clasica":   {"query_hint": ["salsa dura", "fania", "soneo", "montuno", "mambo de metales", "salsa brava"], "negative_hint": ["romántica", "erótica"], "mb_tags": ["salsa", "fania"]},
    "guaguanco_fusionado":  {"query_hint": ["guaguancó en salsa", "rumba en salsa", "toque rumbero", "bloques rumberos"], "negative_hint": ["puro folklor sin orquesta"], "mb_tags": ["salsa", "rumba"]},
    "songo":            {"query_hint": ["songo", "los van van", "son funk", "batería son", "juan formell"], "negative_hint": ["salsa romantica", "reggaeton"], "mb_tags": ["songo", "cuban"]},
    "salsa_romantica":  {"query_hint": ["salsa romántica", "salsa erótica", "balada salsa", "producción pulida"], "negative_hint": ["trombones agresivos 70s", "soneo largo"], "mb_tags": ["salsa romantica", "salsa"]},
    "timba":            {"query_hint": ["timba", "bloques", "cortes", "bajo protagónico", "charanga moderna"], "negative_hint": ["salsa romantica", "boogaloo"], "mb_tags": ["timba", "cuban"]},
    "salsa_dura_revival":   {"query_hint": ["salsa dura revival", "neosalsa", "new york style moderno", "trombones pesados"], "negative_hint": ["romántica noventera"], "mb_tags": ["salsa", "revival"]},
    "salsa_choke":      {"query_hint": ["salsa choke", "choke", "tumaco", "cali flow", "choke colombiano"], "negative_hint": ["salsa dura clásica", "timba cubana"], "mb_tags": ["salsa choke", "colombian"]},
}

# ── Backfill canónico por género ───────────────────────────────────────────────
BACKFILL: Dict[str, List[Dict[str, str]]] = {
    "changui": [
        {"artist": "Grupo Changüí de Guantánamo", "title": "El Guararey de Pastorita"},
        {"artist": "Grupo El Güirito", "title": "Pero báilalo"},
        {"artist": "Elio Revé y su Charangón", "title": "Changüí"},
    ],
    "bomba": [
        {"artist": "Cortijo y su Combo", "title": "Leña Verde"},
        {"artist": "Los Pleneros de la 21", "title": "Bomba de Aquí"},
        {"artist": "Plena Libre", "title": "Protesta de los Tambores"},
    ],
    "danzon": [
        {"artist": "Miguel Faílde", "title": "Las Alturas de Simpson"},
        {"artist": "Arcaño y sus Maravillas", "title": "Tres Lindas Cubanas"},
        {"artist": "Aniceto Díaz", "title": "Rompiendo la Rutina"},
        {"artist": "Orquesta Aragón", "title": "Pare Cochero"},
    ],
    "bolero": [
        {"artist": "Trío Matamoros", "title": "Lágrimas Negras"},
        {"artist": "Ibrahim Ferrer", "title": "Dos Gardenias"},
        {"artist": "Beny Moré", "title": "Qué Bueno Baila Usted"},
        {"artist": "Omara Portuondo", "title": "Quizás Quizás Quizás"},
    ],
    "rumba_guaguanco": [
        {"artist": "Los Muñequitos de Matanzas", "title": "Rumba Pa' los Rumberos"},
        {"artist": "Yoruba Andabo", "title": "Columbia del Solar"},
        {"artist": "Clave y Guaguancó", "title": "Rumbero Soy Yo"},
        {"artist": "Los Papines", "title": "Baila Mi Rumba"},
    ],
    "son_cubano": [
        {"artist": "Buena Vista Social Club", "title": "Chan Chan"},
        {"artist": "Trío Matamoros", "title": "Lágrimas Negras"},
        {"artist": "Ignacio Piñeiro", "title": "Échale Salsita"},
        {"artist": "Eliades Ochoa", "title": "Al Vaivén de Mi Carreta"},
    ],
    "guaracha": [
        {"artist": "Celia Cruz y Sonora Matancera", "title": "Cuidadito Compay Gallo"},
        {"artist": "Ñico Saquito", "title": "María Cristina"},
        {"artist": "Beny Moré", "title": "Francisco Guayabal"},
        {"artist": "La Sonora Ponceña", "title": "Cógela Que Va Sin Jockey"},
    ],
    "guajira_moderna": [
        {"artist": "Guillermo Portabales", "title": "El Carretero"},
        {"artist": "Eliades Ochoa", "title": "Al Vaivén de Mi Carreta"},
        {"artist": "Joséíto Fernández", "title": "Guajira Guantanamera"},
    ],
    "plena": [
        {"artist": "Ismael Rivera", "title": "Las Caras Lindas"},
        {"artist": "Pleneros de la 21", "title": "Maquinolandera"},
        {"artist": "Viento de Agua", "title": "Tembleque"},
        {"artist": "Plena Libre", "title": "Santa María"},
    ],
    "son_montuno": [
        {"artist": "Arsenio Rodríguez", "title": "Bruca Maniguá"},
        {"artist": "Arsenio Rodríguez", "title": "Fuego en el 23"},
        {"artist": "Conjunto Casino", "title": "El Rey del Mundo"},
        {"artist": "Conjunto Chappottín", "title": "Échale Salsita"},
    ],
    "afro_cuban_jazz": [
        {"artist": "Machito & His Afro-Cubans", "title": "Tanga"},
        {"artist": "Dizzy Gillespie & Chano Pozo", "title": "Manteca"},
        {"artist": "Mongo Santamaría", "title": "Afro Blue"},
    ],
    "mambo": [
        {"artist": "Tito Puente", "title": "Ran Kan Kan"},
        {"artist": "Pérez Prado", "title": "Mambo No. 5"},
        {"artist": "Machito", "title": "Mambo Inn"},
        {"artist": "Beny Moré", "title": "Locas por el Mambo"},
    ],
    "descarga": [
        {"artist": "Israel Cachao López", "title": "Descarga Cachao"},
        {"artist": "Cachao", "title": "Descarga Total"},
        {"artist": "Bebo Valdés", "title": "Descarga en Miniatura"},
        {"artist": "Tata Güines", "title": "Descarga"},
    ],
    "cha_cha_cha": [
        {"artist": "Orquesta América", "title": "La Engañadora"},
        {"artist": "Orquesta Aragón", "title": "Me lo Dijo Adela"},
        {"artist": "José Fajardo", "title": "Los Tamalitos de Olga"},
        {"artist": "Orquesta Aragón", "title": "El Bodeguero"},
    ],
    "exotica": [
        {"artist": "Martin Denny", "title": "Quiet Village"},
        {"artist": "Les Baxter", "title": "Jungle River Boat"},
        {"artist": "Yma Sumac", "title": "Goomba Boomba"},
        {"artist": "Arthur Lyman", "title": "Taboo"},
    ],
    "pachanga": [
        {"artist": "Eduardo Davidson", "title": "La Pachanga"},
        {"artist": "Johnny Pacheco", "title": "Cañonazo"},
        {"artist": "Charlie Palmieri", "title": "Pachanga con Palmieri"},
        {"artist": "Orquesta Broadway", "title": "Muévete"},
    ],
    "mozambique": [
        {"artist": "Pello el Afrokán", "title": "Camina y Ven"},
        {"artist": "Pello el Afrokán", "title": "Mozambique"},
        {"artist": "Orquesta Ritmo Oriental", "title": "Cómo se Goza"},
    ],
    "boogaloo": [
        {"artist": "Pete Rodríguez", "title": "I Like It Like That"},
        {"artist": "Joe Cuba Sextet", "title": "Bang Bang"},
        {"artist": "Johnny Colón", "title": "Boogaloo Blues"},
        {"artist": "Ray Barretto", "title": "El Watusi"},
    ],
    "latin_soul": [
        {"artist": "Joe Bataan", "title": "Ordinary Guy"},
        {"artist": "Ralfi Pagán", "title": "Make It With You"},
        {"artist": "Joe Bataan", "title": "I Wish You Love"},
        {"artist": "Malo", "title": "Suavecito"},
    ],
    "salsa_dura_clasica": [
        {"artist": "Willie Colón & Héctor Lavoe", "title": "Aguanilé"},
        {"artist": "Rubén Blades & Willie Colón", "title": "Plástico"},
        {"artist": "Ray Barretto", "title": "Indestructible"},
        {"artist": "Fania All Stars", "title": "Quítate Tú"},
        {"artist": "Eddie Palmieri", "title": "Muñeca"},
    ],
    "guaguanco_fusionado": [
        {"artist": "Rubén Blades & Willie Colón", "title": "Plástico"},
        {"artist": "Eddie Palmieri", "title": "Ritmo Caliente"},
        {"artist": "Batacumbele", "title": "Adoración"},
    ],
    "songo": [
        {"artist": "Los Van Van", "title": "Anda Ven y Muévete"},
        {"artist": "Los Van Van", "title": "Sandunguera"},
        {"artist": "Los Van Van", "title": "El Buey Cansao"},
    ],
    "salsa_romantica": [
        {"artist": "Lalo Rodríguez", "title": "Ven, Devórame Otra Vez"},
        {"artist": "Frankie Ruiz", "title": "Desnúdate Mujer"},
        {"artist": "Eddie Santiago", "title": "Tú Me Vuelves Loco"},
        {"artist": "Jerry Rivera", "title": "Amores Como el Nuestro"},
        {"artist": "Gilberto Santa Rosa", "title": "Conteo Regresivo"},
    ],
    "timba": [
        {"artist": "Los Van Van", "title": "Te Pone la Cabeza Mala"},
        {"artist": "NG La Banda", "title": "Soy Todo"},
        {"artist": "Manolín El Médico de la Salsa", "title": "La Habana Me Llama"},
        {"artist": "Pupy y Los Que Son Son", "title": "El Tranquilo"},
        {"artist": "Charanga Habanera", "title": "Esto Está Bueno"},
    ],
    "salsa_dura_revival": [
        {"artist": "La-33", "title": "La Pantera Mambo"},
        {"artist": "La Excelencia", "title": "Salsa Dura"},
        {"artist": "Orquesta El Macabeo", "title": "Swing"},
        {"artist": "Spanish Harlem Orchestra", "title": "Un Poquito de Swing"},
        {"artist": "La Mambanegra", "title": "Mambo Negro"},
    ],
    "salsa_choke": [
        {"artist": "CJ Castro", "title": "Chichoky"},
        {"artist": "Cali Flow Latino", "title": "Ras Tas Tas"},
        {"artist": "Alexis Play", "title": "Movimiento"},
    ],
}

# ── Estilos Discogs por género ─────────────────────────────────────────────────
DISCOGS_STYLE_MAP: Dict[str, List[str]] = {
    "changui":          ["Son", "Cuban Folk"],
    "bomba":            ["Bomba", "Puerto Rican"],
    "danzon":           ["Danzón", "Charanga"],
    "bolero":           ["Bolero", "Bolero-Son", "Filin"],
    "rumba_guaguanco":  ["Rumba"],
    "son_cubano":       ["Son", "Son Montuno"],
    "guaracha":         ["Guaracha"],
    "guajira_moderna":  ["Guajira", "Son"],
    "plena":            ["Plena"],
    "son_montuno":      ["Son Montuno", "Son", "Cuban Son"],
    "afro_cuban_jazz":  ["Latin Jazz", "Cubop"],
    "mambo":            ["Mambo"],
    "descarga":         ["Descarga", "Latin Jazz"],
    "cha_cha_cha":      ["Cha-Cha", "Charanga"],
    "exotica":          ["Exotica", "Easy Listening"],
    "pachanga":         ["Pachanga"],
    "mozambique":       ["Mozambique", "Cuban"],
    "boogaloo":         ["Boogaloo"],
    "latin_soul":       ["Latin Soul", "Soul", "Funk"],
    "salsa_dura_clasica":   ["Salsa"],
    "guaguanco_fusionado":  ["Salsa", "Rumba"],
    "songo":            ["Songo", "Cuban Funk"],
    "salsa_romantica":  ["Salsa"],
    "timba":            ["Timba", "Salsa"],
    "salsa_dura_revival":   ["Salsa"],
    "salsa_choke":      ["Salsa Choke", "Colombian Salsa"],
}

# ── Lista de géneros y artistas bloqueados ────────────────────────────────────
BLOCKED_ARTISTS: List[str] = [
    "bad bunny", "j balvin", "ozuna", "maluma", "karol g", "anuel aa",
    "daddy yankee", "don omar", "wisin", "yandel", "nicky jam", "farruko",
    "jhay cortez", "myke towers", "rauw alejandro", "sech", "feid",
    "ryan castro", "manuel turizo", "camilo",
]

BLOCKED_GENRES: List[str] = [
    "reggaeton", "trap", "urban", "latin trap", "reggaetonero", "reggaetonera",
]

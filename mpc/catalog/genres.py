# mpc/catalog/genres.py
# -*- coding: utf-8 -*-
"""
Fuente única de verdad para toda la información de géneros.
Importado por: request_to_csv, pipeline_music, mpc/planner, mpc/builders.

IMPORTANTE: No modificar GENRE_DB sin actualizar también GENRE_RULES y BACKFILL.
El clasificador en pipeline_music.py deriva sus heurísticas desde GENRE_DB.
"""

from typing import Dict, List

# ── Mapa genre_slug → comando dl-music-system.sh ─────────────────────────────
GENRE_COMMAND: Dict[str, str] = {
    "son_cubano":               "dl-son-cubano",
    "guajira_moderna":          "dl-guajira-moderna",
    "guaracha":                 "dl-guaracha",
    "rumba_guaguanco":          "dl-rumba-guaguanco",
    "afro_cuban_jazz_descarga": "dl-afro-cuban-jazz",
    "mambo":                    "dl-mambo",
    "cha_cha_cha":              "dl-cha-cha-cha",
    "boogaloo":                 "dl-boogaloo",
    "salsa_dura_clasica":       "dl-salsa-dura-clasica",
    "guaguanco_fusionado":      "dl-guaguanco-fusionado",
    "exotica":                  "dl-exotica",
    "latin_soul":               "dl-latin-soul",
    "plena_bomba":              "dl-plena-bomba",
    "salsa_romantica":          "dl-salsa-romantica",
    "timba":                    "dl-timba",
    "salsa_dura_revival":       "dl-salsa-dura-revival",
    # Géneros directos
    "balada":                   "dl-balada",
    "house":                    "dl-house",
    "nueva_trova":              "dl-nueva-trova",
    "techno":                   "dl-techno",
    "cumbia":                   "dl-cumbia",
}

ALL_SLUGS: List[str] = list(GENRE_COMMAND.keys())

# ── Mapa genre_slug → subdirectorio en la librería ───────────────────────────
# Fuente única de verdad: sustituye el case statement duplicado en dl-music-system.sh
GENRE_DIR: Dict[str, str] = {
    "son_cubano":               "son_cubano",
    "guajira_moderna":          "guajira_moderna",
    "guaracha":                 "guaracha",
    "rumba_guaguanco":          "rumba_guaguanco",
    "afro_cuban_jazz_descarga": "afro_cuban_jazz_descarga",
    "mambo":                    "mambo",
    "cha_cha_cha":              "cha_cha_cha",
    "boogaloo":                 "boogaloo",
    "salsa_dura_clasica":       "salsa_dura_clasica",
    "guaguanco_fusionado":      "guaguanco_fusionado",
    "exotica":                  "exotica",
    "latin_soul":               "latin_soul",
    "plena_bomba":              "plena_bomba",
    "salsa_romantica":          "salsa_romantica",
    "timba":                    "timba",
    "salsa_dura_revival":       "salsa_dura_revival",
    "balada":                   "balada",
    "house":                    "house",
    "nueva_trova":              "nueva_trova",
    "techno":                   "techno",
    "cumbia":                   "cumbia",
}

# Géneros con flujo de búsqueda simplificado (sin clasificador afrolatino)
DIRECT_GENRES: List[str] = ["balada", "house",
                            "nueva_trova", "techno", "cumbia"]

# Géneros afrolatinos (clasificador completo)
AFROLATINO_SLUGS: List[str] = [s for s in ALL_SLUGS if s not in DIRECT_GENRES]

# ── Base de conocimiento de géneros (usada por el clasificador) ───────────────
GENRE_DB: List[Dict] = [
    {
        "name": "Son Cubano",
        "aliases": ["Son", "Son Montuno (genérico)"],
        "artists_key": ["Trío Matamoros", "Arsenio Rodríguez", "Septeto Nacional", "Ignacio Piñeiro", "Compay Segundo", "Eliades Ochoa"],
        "rhythm_traits": ["tumbao de bajo caminante", "montuno", "llamada y respuesta"],
        "instrumentation": {
            "core": ["tres cubano", "guitarra", "piano", "bongó", "maracas", "claves", "contrabajo", "trompeta"],
            "optional": ["conga", "flauta", "violín"],
        },
        "signature_tracks": ["Lágrimas Negras", "Échale Salsita", "Bruca Maniguá"],
        "negative": ["salsa romantica", "bachata", "reggaeton"],
    },
    {
        "name": "Guajira Moderna",
        "aliases": ["Guajira Son", "Son Montuno Lento"],
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
        "name": "Guaracha",
        "aliases": [],
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
        "name": "Rumba Guaguancó",
        "aliases": ["Guaguancó"],
        "artists_key": ["Los Muñequitos de Matanzas", "Yoruba Andabo", "Clave y Guaguancó", "Los Papines"],
        "rhythm_traits": ["polirritmia", "quinto improvisador", "vacunao"],
        "instrumentation": {
            "core": ["quinto", "tres golpes", "tumba", "claves", "guagua", "voz", "coro"],
            "optional": ["chekeré", "palmas"],
        },
        "signature_tracks": ["Rumba pa' los rumberos"],
        "negative": ["mambo big band", "metales salsa pesados"],
    },
    {
        "name": "Afro Cuban Jazz Descarga",
        "aliases": ["Afro-Cuban Jazz", "Latin Jazz (clásico)", "Descarga"],
        "artists_key": ["Machito", "Mario Bauzá", "Tito Puente", "Cachao", "Mongo Santamaría", "Cal Tjader", "Dizzy Gillespie"],
        "rhythm_traits": ["tema–solos–tema", "descarga"],
        "instrumentation": {
            "core": ["piano", "bajo", "contrabajo", "congas", "timbales", "bongó", "metales", "saxos"],
            "optional": ["batá", "flauta", "vibráfono"],
        },
        "signature_tracks": ["Tanga", "Manteca", "Afro Blue", "Descarga Cachao"],
        "negative": ["balada", "romantica"],
    },
    {
        "name": "Mambo",
        "aliases": [],
        "artists_key": ["Pérez Prado", "Tito Puente", "Machito"],
        "rhythm_traits": ["síncopas cortantes", "breaks de metales", "mambos instrumentales"],
        "instrumentation": {
            "core": ["piano", "bajo", "congas", "timbales", "bongó", "trompetas", "trombones", "saxofones"],
        },
        "signature_tracks": ["Mambo No. 5", "Ran Kan Kan", "Mambo Inn"],
        "negative": ["charanga pura"],
    },
    {
        "name": "Cha Cha Cha",
        "aliases": ["Chachachá", "Cha-cha-cha"],
        "artists_key": ["Orquesta América", "Orquesta Aragón", "José Fajardo", "Enrique Jorrín"],
        "rhythm_traits": ["1–2–cha-cha-chá", "charanga"],
        "instrumentation": {
            "core": ["flauta", "violines", "fondo piano/contrabajo", "timbales", "güiro", "maracas"],
        },
        "signature_tracks": ["La Engañadora", "Me lo Dijo Adela", "El Bodeguero"],
        "negative": ["trombones pesados 70s"],
    },
    {
        "name": "Boogaloo",
        "aliases": ["Latin Boogaloo", "Bugalú"],
        "artists_key": ["Pete Rodríguez", "Joe Cuba", "Johnny Colón", "Ray Barretto"],
        "rhythm_traits": ["groove soul", "spanglish", "shing-a-ling", "watusi"],
        "instrumentation": {
            "core": ["órgano", "piano", "bajo eléctrico", "congas", "timbales", "bongó", "metales"],
        },
        "signature_tracks": ["I Like It Like That", "Bang Bang", "Boogaloo Blues"],
        "negative": ["latin soul balada suave"],
    },
    {
        "name": "Salsa Dura Clásica",
        "aliases": ["Salsa Brava", "Salsa 70s"],
        "artists_key": ["Willie Colón", "Héctor Lavoe", "Rubén Blades", "Ray Barretto", "Eddie Palmieri", "Fania All Stars", "Sonora Ponceña", "Raphy Leavitt"],
        "rhythm_traits": ["coro–soneo intenso", "mambos de metales", "descargas", "montuno"],
        "instrumentation": {
            "core": ["piano", "bajo", "congas", "bongó", "timbales", "trombones", "trompetas", "coros"],
        },
        "signature_tracks": ["Aguanile", "Plástico", "Indestructible", "Quítate Tú"],
        "negative": ["romantica", "erotica"],
    },
    {
        "name": "Guaguancó Fusionado",
        "aliases": [],
        "artists_key": ["Eddie Palmieri", "Irakere", "Batacumbele", "Los Van Van"],
        "rhythm_traits": ["toque rumbero en salsa", "bloques rumberos"],
        "instrumentation": {
            "core": ["congas/quinto", "piano", "bajo", "metales", "coros"],
            "optional": ["batá"],
        },
        "signature_tracks": ["Plástico (intro rumbera)"],
        "negative": ["puro folklor sin orquesta"],
    },
    {
        "name": "Exotica",
        "aliases": [],
        "artists_key": ["Martin Denny", "Les Baxter", "Yma Sumac", "Arthur Lyman"],
        "rhythm_traits": ["atmósfera cinematográfica", "selva", "vibráfono"],
        "instrumentation": {
            "core": ["percusión suave", "marimba/vibráfono", "cuerdas", "flautas"],
        },
        "signature_tracks": ["Quiet Village", "Taboo"],
        "negative": ["salsa dura", "boogaloo"],
    },
    {
        "name": "Latin Soul",
        "aliases": [],
        "artists_key": ["Joe Bataan", "Ralfi Pagán", "Harvey Averne", "Malo"],
        "rhythm_traits": ["balada soul con conga", "órgano", "doo-wop"],
        "instrumentation": {
            "core": ["voz soul", "órgano/guitarra", "bajo", "batería", "conga/bongó"],
            "optional": ["metales suaves"],
        },
        "signature_tracks": ["Ordinary Guy", "Gypsy Woman", "I'm Your Puppet"],
        "negative": ["boogaloo shing a ling explosivo"],
    },
    {
        "name": "Plena Bomba",
        "aliases": ["Plena", "Bomba"],
        "artists_key": ["Rafael Cortijo", "Ismael Rivera", "Pleneros de la 21", "Viento de Agua"],
        "rhythm_traits": ["llamada-respuesta", "panderetas", "barriles"],
        "instrumentation": {
            "core": ["panderetas y güiro", "barriles", "maraca", "cuá"],
        },
        "signature_tracks": ["Maquinolandera", "El Bombón de Elena"],
        "negative": ["metales pesados salsa (si no es fusión)"],
    },
    {
        "name": "Salsa Romántica",
        "aliases": ["Salsa sensual", "Salsa erótica"],
        "artists_key": ["Lalo Rodríguez", "Frankie Ruiz", "Eddie Santiago", "Gilberto Santa Rosa", "Jerry Rivera", "Luis Enrique"],
        "rhythm_traits": ["coro emotivo", "menos agresividad percusiva", "producción pulida"],
        "instrumentation": {
            "core": ["piano", "bajo", "congas/bongó/timbales suaves", "metales contenidos", "voz protagonista"],
            "optional": ["sintetizadores"],
        },
        "signature_tracks": ["Ven Devórame Otra Vez", "Desnúdate Mujer", "Amores Como el Nuestro"],
        "negative": ["trombones agresivos 70s", "soneo largo"],
    },
    {
        "name": "Timba",
        "aliases": [],
        "artists_key": ["NG La Banda", "Los Van Van", "Charanga Habanera", "Pupy y Los Que Son Son", "Manolín"],
        "rhythm_traits": ["bloqueos y cortes", "bajo protagónico", "cambios súbitos"],
        "instrumentation": {
            "core": ["piano", "bajo eléctrico", "batería", "congas", "timbales", "metales", "coros"],
            "optional": ["teclados"],
        },
        "signature_tracks": ["Te Pone la Cabeza Mala", "La Habana Me Llama"],
        "negative": ["boogaloo", "salsa romantica"],
    },
    {
        "name": "Salsa Dura Revival",
        "aliases": ["Neosalsa", "Salsa dura moderna"],
        "artists_key": ["La-33", "Spanish Harlem Orchestra", "La Excelencia", "El Macabeo", "La Mambanegra", "Tromboranga", "Los Hacheros"],
        "rhythm_traits": ["mambos pesados", "soneo vivo", "producción nítida"],
        "instrumentation": {
            "core": ["piano", "bajo", "congas/bongó/timbales", "trombones/trompetas", "coros fuertes"],
        },
        "signature_tracks": ["La Pantera Mambo", "Salsa Dura"],
        "negative": ["romantica noventera"],
    },
]

# ── Artistas ancla por género (para sesgo underground/comercial) ──────────────
ANCHOR_ARTISTS: Dict[str, List[str]] = {
    "son_cubano":               ["Trío Matamoros", "Arsenio Rodríguez", "Septeto Nacional", "Ignacio Piñeiro", "Compay Segundo", "Eliades Ochoa"],
    "guajira_moderna":          ["Guillermo Portabales", "Compay Segundo", "Eliades Ochoa"],
    "guaracha":                 ["Beny Moré", "Celia Cruz", "Ñico Saquito", "Sonora Matancera"],
    "rumba_guaguanco":          ["Los Muñequitos de Matanzas", "Clave y Guaguancó", "Yoruba Andabo", "Los Papines"],
    "afro_cuban_jazz_descarga": ["Machito", "Mario Bauzá", "Tito Puente", "Cachao", "Mongo Santamaría", "Cal Tjader"],
    "mambo":                    ["Pérez Prado", "Tito Puente", "Machito"],
    "cha_cha_cha":              ["Orquesta América", "Orquesta Aragón", "José Fajardo", "Enrique Jorrín"],
    "boogaloo":                 ["Pete Rodríguez", "Joe Cuba", "Johnny Colón", "Ray Barretto"],
    "salsa_dura_clasica":       ["Willie Colón", "Héctor Lavoe", "Rubén Blades", "Ray Barretto", "Eddie Palmieri", "Fania All Stars", "Sonora Ponceña", "Raphy Leavitt"],
    "guaguanco_fusionado":      ["Eddie Palmieri", "Irakere", "Batacumbele", "Los Van Van"],
    "exotica":                  ["Martin Denny", "Les Baxter", "Yma Sumac", "Arthur Lyman"],
    "latin_soul":               ["Joe Bataan", "Ralfi Pagán", "Harvey Averne", "Malo"],
    "plena_bomba":              ["Rafael Cortijo", "Ismael Rivera", "Pleneros de la 21", "Viento de Agua"],
    "salsa_romantica":          ["Lalo Rodríguez", "Frankie Ruiz", "Eddie Santiago", "Gilberto Santa Rosa", "Jerry Rivera", "Luis Enrique"],
    "timba":                    ["NG La Banda", "Los Van Van", "Charanga Habanera", "Pupy y Los Que Son Son", "Manolín"],
    "salsa_dura_revival":       ["La-33", "Spanish Harlem Orchestra", "La Excelencia", "El Macabeo", "Tromboranga", "La Mambanegra", "Los Hacheros"],
}

# ── Reglas de búsqueda por género ─────────────────────────────────────────────
GENRE_RULES: Dict[str, Dict] = {
    "son_cubano":               {"query_hint": ["son cubano", "son montuno", "septeto", "tres cubano", "montuno", "llamada y respuesta"], "negative_hint": ["salsa romantica", "bachata", "reggaeton"], "mb_tags": ["son", "cuban"]},
    "guajira_moderna":          {"query_hint": ["guajira", "guajira son", "tres", "campesina"], "negative_hint": ["mambo explosivo", "guaracha rapida", "salsa romantica"], "mb_tags": ["guajira", "cuban"]},
    "guaracha":                 {"query_hint": ["guaracha", "doble sentido", "vacilón", "jocosa"], "negative_hint": ["balada", "romantica"], "mb_tags": ["guaracha", "cuban"]},
    "rumba_guaguanco":          {"query_hint": ["guaguancó", "rumba", "vacunao", "yambú", "columbia"], "negative_hint": ["metales salsa", "mambo big band"], "mb_tags": ["rumba", "guaguancó", "afrocuban"]},
    "afro_cuban_jazz_descarga": {"query_hint": ["descarga", "afro-cuban jazz", "latin jazz", "solo de", "instrumental"], "negative_hint": ["coro romántico", "balada"], "mb_tags": ["latin jazz", "descarga"]},
    "mambo":                    {"query_hint": ["mambo", "big band", "trombones", "trompetas", "breaks"], "negative_hint": ["charanga flauta violín puro cha cha"], "mb_tags": ["mambo", "latin"]},
    "cha_cha_cha":              {"query_hint": ["cha cha cha", "chachachá", "charanga", "flauta", "violines"], "negative_hint": ["trombones pesados (salsa dura)"], "mb_tags": ["cha-cha-cha", "charanga"]},
    "boogaloo":                 {"query_hint": ["boogaloo", "bugalú", "shing-a-ling", "watusi", "spanglish"], "negative_hint": ["latin soul balada suave"], "mb_tags": ["boogaloo", "nuyorican"]},
    "salsa_dura_clasica":       {"query_hint": ["salsa dura", "fania", "soneo", "montuno", "mambo de metales", "descarga"], "negative_hint": ["romántica", "erótica"], "mb_tags": ["salsa", "fania"]},
    "guaguanco_fusionado":      {"query_hint": ["guaguancó en salsa", "rumba en salsa", "toque rumbero", "bloques rumberos"], "negative_hint": ["puro folklor sin orquesta"], "mb_tags": ["salsa", "rumba"]},
    "exotica":                  {"query_hint": ["exotica", "tiki", "lounge", "vibráfono", "selva"], "negative_hint": ["salsa dura", "boogaloo"], "mb_tags": ["exotica", "lounge"]},
    "latin_soul":               {"query_hint": ["latin soul", "doo-wop", "balada soul", "órgano", "motown vibe"], "negative_hint": ["boogaloo shing-a-ling explosivo"], "mb_tags": ["latin soul", "nuyorican"]},
    "plena_bomba":              {"query_hint": ["plena", "bomba", "panderetas", "barriles", "boricua"], "negative_hint": ["metales pesados salsa (si no es fusión)"], "mb_tags": ["plena", "bomba", "puerto rican"]},
    "salsa_romantica":          {"query_hint": ["salsa romántica", "salsa erótica", "balada salsa", "producción pulida"], "negative_hint": ["trombones agresivos 70s", "soneo largo"], "mb_tags": ["salsa romantica", "salsa"]},
    "timba":                    {"query_hint": ["timba", "bloques", "cortes", "bajo protagónico", "charanga moderna"], "negative_hint": ["salsa romantica", "boogaloo"], "mb_tags": ["timba", "cuban"]},
    "salsa_dura_revival":       {"query_hint": ["salsa dura revival", "neosalsa", "new york style moderno", "trombones pesados"], "negative_hint": ["romántica noventera"], "mb_tags": ["salsa", "revival"]},
}

# ── Backfill canónico por género ───────────────────────────────────────────────
BACKFILL: Dict[str, List[Dict[str, str]]] = {
    "son_cubano": [
        {"artist": "Buena Vista Social Club", "title": "Chan Chan"},
        {"artist": "Trío Matamoros", "title": "Lágrimas Negras"},
        {"artist": "Ignacio Piñeiro", "title": "Échale Salsita"},
        {"artist": "Arsenio Rodríguez", "title": "Bruca Maniguá"},
    ],
    "guajira_moderna": [
        {"artist": "Guillermo Portabales", "title": "El Carretero"},
        {"artist": "Eliades Ochoa", "title": "Al Vaivén de Mi Carreta"},
        {"artist": "Joséíto Fernández", "title": "Guajira Guantanamera"},
        {"artist": "Guillermo Portabales", "title": "Rico Vacilón"},
    ],
    "guaracha": [
        {"artist": "Celia Cruz y Sonora Matancera",
            "title": "Cuidadito Compay Gallo"},
        {"artist": "Ñico Saquito", "title": "María Cristina"},
        {"artist": "Beny Moré", "title": "Francisco Guayabal"},
        {"artist": "La Sonora Ponceña", "title": "Cógela Que Va Sin Jockey"},
    ],
    "rumba_guaguanco": [
        {"artist": "Los Muñequitos de Matanzas",
            "title": "Rumba Pa' los Rumberos"},
        {"artist": "Yoruba Andabo", "title": "Columbia del Solar"},
        {"artist": "Clave y Guaguancó", "title": "Rumbero Soy Yo"},
        {"artist": "Los Papines", "title": "Baila Mi Rumba"},
    ],
    "afro_cuban_jazz_descarga": [
        {"artist": "Machito & His Afro-Cubans", "title": "Tanga"},
        {"artist": "Dizzy Gillespie & Chano Pozo", "title": "Manteca"},
        {"artist": "Mongo Santamaría", "title": "Afro Blue"},
        {"artist": "Israel 'Cachao' López", "title": "Descarga Cachao"},
    ],
    "mambo": [
        {"artist": "Tito Puente", "title": "Ran Kan Kan"},
        {"artist": "Pérez Prado", "title": "Mambo No. 5"},
        {"artist": "Machito", "title": "Mambo Inn"},
        {"artist": "Beny Moré", "title": "Locas por el Mambo"},
    ],
    "cha_cha_cha": [
        {"artist": "Orquesta América", "title": "La Engañadora"},
        {"artist": "Orquesta Aragón", "title": "Me lo Dijo Adela"},
        {"artist": "José Fajardo", "title": "Los Tamalitos de Olga"},
        {"artist": "Orquesta Aragón", "title": "El Bodeguero"},
    ],
    "boogaloo": [
        {"artist": "Pete Rodríguez", "title": "I Like It Like That"},
        {"artist": "Joe Cuba Sextet", "title": "Bang Bang"},
        {"artist": "Johnny Colón", "title": "Boogaloo Blues"},
        {"artist": "Ray Barretto", "title": "El Watusi"},
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
        {"artist": "Batacumbele", "title": "La Rumba Está Buena"},
        {"artist": "Irakere & Los Muñequitos de Matanzas",
            "title": "De La Habana a Matanzas"},
    ],
    "exotica": [
        {"artist": "Martin Denny", "title": "Quiet Village"},
        {"artist": "Les Baxter", "title": "Jungle River Boat"},
        {"artist": "Yma Sumac", "title": "Goomba Boomba"},
        {"artist": "Arthur Lyman", "title": "Taboo"},
    ],
    "latin_soul": [
        {"artist": "Joe Bataan", "title": "Ordinary Guy"},
        {"artist": "Ralfi Pagán", "title": "Make It With You"},
        {"artist": "Joe Bataan", "title": "I Wish You Love"},
        {"artist": "Malo", "title": "Suavecito"},
    ],
    "plena_bomba": [
        {"artist": "Ismael Rivera", "title": "Las Caras Lindas"},
        {"artist": "Cortijo y su Combo", "title": "El Bombón de Elena"},
        {"artist": "Pleneros de la 21", "title": "Maquinolandera"},
        {"artist": "Viento de Agua", "title": "Tembleque"},
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
        {"artist": "Manolín, El Médico de la Salsa", "title": "La Habana Me Llama"},
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
}

# ── Estilos Discogs por género ─────────────────────────────────────────────────
DISCOGS_STYLE_MAP: Dict[str, List[str]] = {
    "cha_cha_cha":              ["Cha-Cha", "Charanga"],
    "boogaloo":                 ["Boogaloo"],
    "mambo":                    ["Mambo"],
    "latin_soul":               ["Latin Soul", "Soul", "Funk"],
    "salsa_dura_clasica":       ["Salsa"],
    "salsa_dura_revival":       ["Salsa"],
    "salsa_romantica":          ["Salsa"],
    "son_cubano":               ["Son", "Son Montuno"],
    "guajira_moderna":          ["Guajira", "Son"],
    "guaracha":                 ["Guaracha"],
    "plena_bomba":              ["Plena", "Bomba"],
    "rumba_guaguanco":          ["Rumba"],
    "afro_cuban_jazz_descarga": ["Latin Jazz", "Descarga"],
    "guaguanco_fusionado":      ["Salsa", "Rumba"],
    "exotica":                  ["Exotica", "Easy Listening"],
    "timba":                    ["Timba", "Salsa"],
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

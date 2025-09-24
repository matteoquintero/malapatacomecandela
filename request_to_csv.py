# request_to_csv.py
# -*- coding: utf-8 -*-
"""
Genera canciones.csv desde un pedido en lenguaje natural (sin YouTube):
- Planner LLM (opcional) decide: task [playlist/album], count, genre (16), substyle [underground/comercial], artist/album
- Fuentes: Discogs (discogs_client) [PRIORIDAD] + MusicBrainz + Backfill canónico
- Soporta 'artist only' (ej: "5 canciones de Larry Harlow", "solo Ismael Rivera")
- Dedupe por (artist,title)
Salida CSV: artist,title,query_override,source
"""

import requests
import os
import re
import time
import csv
import json
import argparse
import random
import unicodedata
from typing import List, Dict, Optional
from openai import OpenAI
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
# ===== .env =====
try:
    from dotenv import load_dotenv
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
    _env_path = os.path.join(PROJECT_DIR, ".env")
    load_dotenv(_env_path)

    # Configurar modo debug
    DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() in [
        "true", "1", "yes", "on"]

    def debug_print(*args, **kwargs):
        """Función para imprimir mensajes de debug solo si DEBUG_MODE está activado."""
        if DEBUG_MODE:
            print(*args, **kwargs)

    try:
        debug_print(
            f"[DBG] .env path={_env_path} exists={os.path.exists(_env_path)}")
    except Exception:
        pass
except Exception:
    DEBUG_MODE = False

    def debug_print(*args, **kwargs):
        """Función de debug deshabilitada."""
        pass


# ===== OpenAI opcional =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_openai = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        _openai = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        print("No se pudo cargar OpenAI (opcional).")
        _openai = None
try:
    debug_print(
        f"[DBG] OpenAI={'ON' if _openai else 'OFF'} API_KEY_set={'YES' if bool(OPENAI_API_KEY) else 'NO'}")
except Exception:
    pass

# ===== Spotify opcional =====
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
_spotify = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        client_credentials_manager = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        )
        _spotify = spotipy.Spotify(
            client_credentials_manager=client_credentials_manager)
    except Exception as e:
        print(f"No se pudo cargar Spotify (opcional): {e}")
        _spotify = None
try:
    debug_print(
        f"[DBG] Spotify={'ON' if _spotify else 'OFF'} CLIENT_ID_set={'YES' if bool(SPOTIFY_CLIENT_ID) else 'NO'}")
except Exception:
    pass

# ===== Discogs (SDK oficial) =====
DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN", "")
discogs = None
try:
    import discogs_client
    if DISCOGS_TOKEN:
        try:
            discogs = discogs_client.Client(
                "mala-pata-come-candela/1.0 (mateoquintero)",
                user_token=DISCOGS_TOKEN
            )
        except Exception as e:
            debug_print(f"[DBG] Discogs client error: {e}")
            discogs = None
    try:
        debug_print(
            f"[DBG] DiscogsToken={'YES' if bool(DISCOGS_TOKEN) else 'NO'} DiscogsClient={'ON' if discogs else 'OFF'}")
    except Exception:
        pass
except ImportError:
    print("No se pudo cargar discogs_client (opcional).")
    discogs_client = None  # no instalado

# ===== MusicBrainz =====
MB_BASE = "https://musicbrainz.org/ws/2"
UA = {"User-Agent": "mala-pata-come-candela/1.0 (mateoquintero)"}


def mb_get(path: str, params: Dict) -> Dict:
    params = {**params, "fmt": "json"}
    try:
        r = requests.get(f"{MB_BASE}/{path}", params=params,
                         headers=UA, timeout=30)
        time.sleep(1.0)  # rate-friendly
        try:
            debug_print(f"[DBG] MB GET {path} status={r.status_code}")
        except Exception:
            pass
        r.raise_for_status()
        return r.json()
    except Exception as e:
        try:
            debug_print(f"[DBG] MB GET error {path}: {e}")
        except Exception:
            pass
        raise

# ===== helpers de normalización/dedupe =====


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def simp(s: str) -> str:
    s = _strip_accents(s).lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def key_pair(artist: str, title: str) -> str:
    return f"{simp(artist)}|{simp(title)}"


# ===== extracción de cantidad desde texto =====
_NUM_WORDS_ES = {
    "un": 1, "una": 1, "uno": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "dieciséis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50
}


def _word_to_num_es(token: str) -> Optional[int]:
    token = _strip_accents(token.lower())
    return _NUM_WORDS_ES.get(token)


def extract_count(user_text: str) -> Optional[int]:
    """
    Entiende: 2, dos, unas 5, al menos 8, hasta 10, entre 5 y 8, 5-8, como 7...
    """
    t = user_text.strip()
    t_norm = _strip_accents(t.lower())

    m = re.search(r"\bentre\s+(\d{1,2})\s+y\s+(\d{1,2})\b", t_norm)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        n = max(a, b)
        if 1 <= n <= 50:
            return n
    m = re.search(r"\bde\s+(\d{1,2})\s+a\s+(\d{1,2})\b", t_norm)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        n = max(a, b)
        if 1 <= n <= 50:
            return n
    m = re.search(r"\b(\d{1,2})\s*-\s*(\d{1,2})\b", t_norm)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        n = max(a, b)
        if 1 <= n <= 50:
            return n

    m = re.search(
        r"\b(al\s+menos|por\s+lo\s+menos|minimo|mínimo)\s+(\d{1,2})\b", t_norm)
    if m:
        n = int(m.group(2))
        if 1 <= n <= 50:
            return n

    m = re.search(r"\b(hasta|maximo|máximo)\s+(\d{1,2})\b", t_norm)
    if m:
        n = int(m.group(2))
        if 1 <= n <= 50:
            return n

    m = re.search(
        r"\b(unas|unos|como|cerca\s+de|aprox(?:imadamente)?)\s+(\d{1,2})\b", t_norm)
    if m:
        n = int(m.group(2))
        if 1 <= n <= 50:
            return n

    m = re.search(r"\b(\d{1,2})\b", t_norm)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 50:
            return n

    tokens = re.findall(r"[a-záéíóúñ]+", t_norm)
    for tok in tokens:
        n = _word_to_num_es(tok)
        if n and 1 <= n <= 50:
            return n

    return None


# ===== Anclas por género =====
ANCHOR_ARTISTS: Dict[str, List[str]] = {
    "son_cubano": ["Trío Matamoros", "Arsenio Rodríguez", "Septeto Nacional", "Ignacio Piñeiro", "Compay Segundo", "Eliades Ochoa"],
    "guajira_moderna": ["Guillermo Portabales", "Compay Segundo", "Eliades Ochoa"],
    "guaracha": ["Beny Moré", "Celia Cruz", "Ñico Saquito", "Sonora Matancera"],
    "rumba_guaguanco": ["Los Muñequitos de Matanzas", "Clave y Guaguancó", "Yoruba Andabo", "Los Papines"],
    "afro_cuban_jazz_descarga": ["Machito", "Mario Bauzá", "Tito Puente", "Cachao", "Mongo Santamaría", "Cal Tjader"],
    "mambo": ["Pérez Prado", "Tito Puente", "Machito"],
    "cha_cha_cha": ["Orquesta América", "Orquesta Aragón", "José Fajardo", "Enrique Jorrín"],
    "boogaloo": ["Pete Rodríguez", "Joe Cuba", "Johnny Colón", "Ray Barretto"],
    "salsa_dura_clasica": ["Willie Colón", "Héctor Lavoe", "Rubén Blades", "Ray Barretto", "Eddie Palmieri", "Fania All Stars", "Sonora Ponceña", "Raphy Leavitt"],
    "guaguanco_fusionado": ["Eddie Palmieri", "Irakere", "Batacumbele", "Los Van Van"],
    "exotica": ["Martin Denny", "Les Baxter", "Yma Sumac", "Arthur Lyman"],
    "latin_soul": ["Joe Bataan", "Ralfi Pagán", "Harvey Averne", "Malo"],
    "plena_bomba": ["Rafael Cortijo", "Ismael Rivera", "Pleneros de la 21", "Viento de Agua"],
    "salsa_romantica": ["Lalo Rodríguez", "Frankie Ruiz", "Eddie Santiago", "Gilberto Santa Rosa", "Jerry Rivera", "Luis Enrique"],
    "timba": ["NG La Banda", "Los Van Van", "Charanga Habanera", "Pupy y Los Que Son Son", "Manolín"],
    "salsa_dura_revival": ["La-33", "Spanish Harlem Orchestra", "La Excelencia", "El Macabeo", "Tromboranga", "La Mambanegra", "Los Hacheros"],
}

# ===== Reglas de género =====
GENRE_RULES: Dict[str, Dict] = {
    "son_cubano": {
        "query_hint": ["son cubano", "son montuno", "septeto", "tres cubano", "montuno", "llamada y respuesta"],
        "negative_hint": ["salsa romantica", "bachata", "reggaeton"],
        "mb_tags": ["son", "cuban"],
    },
    "guajira_moderna": {
        "query_hint": ["guajira", "guajira son", "tres", "campesina"],
        "negative_hint": ["mambo explosivo", "guaracha rapida", "salsa romantica"],
        "mb_tags": ["guajira", "cuban"],
    },
    "guaracha": {
        "query_hint": ["guaracha", "doble sentido", "vacilón", "jocosa"],
        "negative_hint": ["balada", "romantica"],
        "mb_tags": ["guaracha", "cuban"],
    },
    "rumba_guaguanco": {
        "query_hint": ["guaguancó", "rumba", "vacunao", "yambú", "columbia"],
        "negative_hint": ["metales salsa", "mambo big band"],
        "mb_tags": ["rumba", "guaguancó", "afrocuban"],
    },
    "afro_cuban_jazz_descarga": {
        "query_hint": ["descarga", "afro-cuban jazz", "latin jazz", "solo de", "instrumental"],
        "negative_hint": ["coro romántico", "balada"],
        "mb_tags": ["latin jazz", "descarga"],
    },
    "mambo": {
        "query_hint": ["mambo", "big band", "trombones", "trompetas", "breaks"],
        "negative_hint": ["charanga flauta violín puro cha cha"],
        "mb_tags": ["mambo", "latin"],
    },
    "cha_cha_cha": {
        "query_hint": ["cha cha cha", "chachachá", "charanga", "flauta", "violines"],
        "negative_hint": ["trombones pesados (salsa dura)"],
        "mb_tags": ["cha-cha-cha", "charanga"],
    },
    "boogaloo": {
        "query_hint": ["boogaloo", "bugalú", "shing-a-ling", "watusi", "spanglish"],
        "negative_hint": ["latin soul balada suave"],
        "mb_tags": ["boogaloo", "nuyorican"],
    },
    "salsa_dura_clasica": {
        "query_hint": ["salsa dura", "fania", "soneo", "montuno", "mambo de metales", "descarga"],
        "negative_hint": ["romántica", "erótica"],
        "mb_tags": ["salsa", "fania"],
    },
    "guaguanco_fusionado": {
        "query_hint": ["guaguancó en salsa", "rumba en salsa", "toque rumbero", "bloques rumberos"],
        "negative_hint": ["puro folklor sin orquesta"],
        "mb_tags": ["salsa", "rumba"],
    },
    "exotica": {
        "query_hint": ["exotica", "tiki", "lounge", "vibráfono", "selva"],
        "negative_hint": ["salsa dura", "boogaloo"],
        "mb_tags": ["exotica", "lounge"],
    },
    "latin_soul": {
        "query_hint": ["latin soul", "doo-wop", "balada soul", "órgano", "motown vibe"],
        "negative_hint": ["boogaloo shing-a-ling explosivo"],
        "mb_tags": ["latin soul", "nuyorican"],
    },
    "plena_bomba": {
        "query_hint": ["plena", "bomba", "panderetas", "barriles", "boricua"],
        "negative_hint": ["metales pesados salsa (si no es fusión)"],
        "mb_tags": ["plena", "bomba", "puerto rican"],
    },
    "salsa_romantica": {
        "query_hint": ["salsa romántica", "salsa erótica", "balada salsa", "producción pulida"],
        "negative_hint": ["trombones agresivos 70s", "soneo largo"],
        "mb_tags": ["salsa romantica", "salsa"],
    },
    "timba": {
        "query_hint": ["timba", "bloques", "cortes", "bajo protagónico", "charanga moderna"],
        "negative_hint": ["salsa romantica", "boogaloo"],
        "mb_tags": ["timba", "cuban"],
    },
    "salsa_dura_revival": {
        "query_hint": ["salsa dura revival", "neosalsa", "new york style moderno", "trombones pesados"],
        "negative_hint": ["romántica noventera"],
        "mb_tags": ["salsa", "revival"],
    },
}

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
            "title": "Rumba Pa’ los Rumberos"},
        {"artist": "Yoruba Andabo", "title": "Columbia del Solar"},
        {"artist": "Clave y Guaguancó", "title": "Rumbero Soy Yo"},
        {"artist": "Los Papines", "title": "Baila Mi Rumba"},
    ],
    "afro_cuban_jazz_descarga": [
        {"artist": "Machito & His Afro-Cubans", "title": "Tanga"},
        {"artist": "Dizzy Gillespie & Chano Pozo", "title": "Manteca"},
        {"artist": "Mongo Santamaría", "title": "Afro Blue"},
        {"artist": "Israel “Cachao” López", "title": "Descarga Cachao"},
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

# ===== Planner LLM =====
SYSTEM = (
    "Eres un planificador musical experto en música afrolatina.\n"
    "Lee la instrucción del usuario y devuelve SOLO JSON (sin explicaciones) con este esquema exacto:\n"
    "{\n"
    "  \"task\": \"album\" | \"playlist\",\n"
    "  \"count\": <int or null>,\n"
    "  \"genre\": <string or null>,\n"
    "  \"substyle\": <\"underground\"|\"comercial\"|null>,\n"
    "  \"artist\": <string or null>,\n"
    "  \"album\": <string or null>\n"
    "}\n"
    "Reglas:\n"
    "- Si pide un álbum, task=\"album\" y completa artist/album.\n"
    "- Si pide canciones, task=\"playlist\". Si menciona un artista sin álbum: rellena artist y deja album=null.\n"
    "- Si no dice cuántas, usa 10.\n"
    "- substyle: detecta 'underground' vs 'comercial' por tono; si no hay pista, deja null.\n"
    "- genre debe ser uno de: son_cubano, guajira_moderna, guaracha, rumba_guaguanco, afro_cuban_jazz_descarga,\n"
    "  mambo, cha_cha_cha, boogaloo, salsa_dura_clasica, guaguanco_fusionado, exotica, latin_soul,\n"
    "  plena_bomba, salsa_romantica, timba, salsa_dura_revival. Si no hay género explícito, deja null.\n"
    "- Devuelve **JSON válido** y nada más."
)

SYSTEM_DIRECT_GENRE = (
    "Eres un asistente especializado en análisis de solicitudes musicales para descarga directa.\n"
    "Tu tarea es extraer información específica de la solicitud del usuario y estructurarla en JSON.\n"
    "\n"
    "Devuelve SOLO JSON válido con este esquema exacto:\n"
    "{\n"
    "  \"task\": \"album\" | \"playlist\",\n"
    "  \"count\": <int or null>,\n"
    "  \"genre\": \"{DIRECT_GENRE}\",\n"
    "  \"substyle\": null,\n"
    "  \"artist\": <string or null>,\n"
    "  \"album\": <string or null>\n"
    "}\n"
    "\n"
    "INSTRUCCIONES CRÍTICAS:\n"
    "- Si pide un álbum, task=\"album\" y completa artist/album.\n"
    "- Si pide canciones, task=\"playlist\". Si menciona un artista sin álbum: rellena artist y deja album=null.\n"
    "- Si no dice cuántas, usa 10.\n"
    "- genre: SIEMPRE \"{DIRECT_GENRE}\" (NUNCA cambies este valor)\n"
    "- substyle: SIEMPRE null (no aplica para géneros directos)\n"
    "- artist: Extrae nombres de artistas sin importar mayúsculas/minúsculas\n"
    "  Ejemplos: 'silvio rodriguez' → 'Silvio Rodríguez', 'DAFT PUNK' → 'Daft Punk'\n"
    "- count: Extrae números del texto (1, 2, 3, etc.) o usa 10 por defecto\n"
    "\n"
    "GÉNEROS DIRECTOS:\n"
    "- balada: música romántica y baladas\n"
    "- house: música house y electrónica\n"
    "- nueva_trova: nueva trova cubana\n"
    "- techno: música techno\n"
    "\n"
    "Devuelve ÚNICAMENTE el JSON, sin explicaciones adicionales."
)


def _clean_artist_name(artist_name: str) -> str:
    """
    Limpia el nombre del artista removiendo palabras descriptivas comunes.
    """
    if not artist_name:
        return artist_name

    # Palabras descriptivas que no son parte del nombre del artista
    descriptive_words = [
        "ineditas", "inedita", "inéditas", "inédita",
        "raras", "rara", "raros", "raro",
        "clasicas", "clasica", "clásicas", "clásica",
        "mejores", "mejor", "top", "hits", "hit",
        "underground", "comercial", "popular", "famosas", "famosos",
        "nuevas", "nueva", "nuevos", "nuevo",
        "viejas", "vieja", "viejos", "viejo",
        "tempranas", "temprana", "tempranos", "temprano",
        "tardias", "tardia", "tardios", "tardio",
        "temas", "tema", "canciones", "cancion"
    ]

    # Convertir a minúsculas para comparación
    words = artist_name.lower().split()
    cleaned_words = []

    for word in words:
        # Remover puntuación
        clean_word = re.sub(r'[^\w]', '', word)
        if clean_word and clean_word not in descriptive_words:
            cleaned_words.append(word)

    # Reconstruir el nombre manteniendo la capitalización original
    if cleaned_words:
        # Encontrar las posiciones de las palabras limpias en el texto original
        original_words = artist_name.split()
        result_words = []

        for orig_word in original_words:
            clean_orig = re.sub(r'[^\w]', '', orig_word.lower())
            if clean_orig in [re.sub(r'[^\w]', '', w.lower()) for w in cleaned_words]:
                result_words.append(orig_word)

        return ' '.join(result_words)

    return artist_name


def _guess_artist_from_text(user_text: str) -> Optional[str]:
    """
    Heurística rápida para detectar 'solo <artista>' / 'de <artista>' / comillas.
    No reemplaza al LLM; ayuda si no hay OpenAI.
    """
    t = user_text.strip()
    t_norm = _strip_accents(t.lower())

    # entre comillas “...”
    m = re.search(r"[\"“”']\s*([^\"“”']+?)\s*[\"“”']", t)
    if m:
        name = m.group(1).strip()
        if 3 <= len(name) <= 80:
            return name

    # "solo X", "de X", "de: X"
    m = re.search(
        r"\b(?:solo|s[óo]lo|de)\s+([a-záéíóúñ][\w\s\.\-&']{2,80})$", t_norm, flags=re.I)
    if m:
        cand = t[m.start(1):m.end(1)].strip(" :")
        if len(cand) >= 3:
            return cand

    # "canciones de X"
    m = re.search(
        r"canciones\s+de\s+([a-záéíóúñ][\w\s\.\-&']{2,80})", t_norm, flags=re.I)
    if m:
        cand = t[m.start(1):m.end(1)].strip(" :")
        if len(cand) >= 3:
            return cand

    # "cancion de X" (singular) - case insensitive
    m = re.search(
        r"cancion\s+de\s+([a-záéíóúñ][\w\s\.\-&']{2,80})", t_norm, flags=re.I)
    if m:
        cand = t[m.start(1):m.end(1)].strip(" :")
        if len(cand) >= 3:
            return _clean_artist_name(cand)

    # "cancion X" (sin "de") - case insensitive
    m = re.search(
        r"cancion\s+([a-záéíóúñ][\w\s\.\-&']{2,80})$", t_norm, flags=re.I)
    if m:
        cand = t[m.start(1):m.end(1)].strip(" :")
        if len(cand) >= 3:
            return _clean_artist_name(cand)

    # "canciones X" (sin "de") - case insensitive
    m = re.search(
        r"canciones\s+([a-záéíóúñ][\w\s\.\-&']{2,80})$", t_norm, flags=re.I)
    if m:
        cand = t[m.start(1):m.end(1)].strip(" :")
        if len(cand) >= 3:
            return _clean_artist_name(cand)

    # "cancion X" (sin "de") - case insensitive
    m = re.search(
        r"cancion\s+([a-záéíóúñ][\w\s\.\-&']{2,80})$", t_norm, flags=re.I)
    if m:
        cand = t[m.start(1):m.end(1)].strip(" :")
        if len(cand) >= 3:
            return _clean_artist_name(cand)

    return None


def llm_plan(user_text: str, direct_genre: str = None) -> Dict:
    default = {"task": "playlist", "count": 10, "genre": None,
               "substyle": None, "artist": None, "album": None}

    # sin OpenAI: heurística + conteo desde texto
    if not _openai:
        txt = user_text.lower()
        # substyle
        sub = "underground" if any(w in txt for w in ["underground", "oscuro", "crudo", "rare", "deep"]) else \
              ("comercial" if any(w in txt for w in [
               "hit", "clásico", "clasico", "popular", "radio", "mainstream"]) else None)
        plan = {**default, "substyle": sub}

        # count
        cnt = extract_count(user_text)
        if cnt:
            plan["count"] = cnt

        # artist y/o género
        cand_artist = _guess_artist_from_text(user_text)
        if cand_artist:
            plan["artist"] = cand_artist

        gtxt = simp(user_text)
        ghits = []
        for g in GENRE_RULES.keys():
            if simp(g.replace("_", " ")) in gtxt or simp(g) in gtxt:
                ghits.append(g)
        if ghits:
            plan["genre"] = ghits[0]

        # Si menciona “álbum X de Y”
        m = re.search(r"album\s+([\"“”']?)(.+?)\1\s+de\s+(.+)$",
                      _strip_accents(user_text), flags=re.I)
        if m:
            plan["task"] = "album"
            plan["album"] = m.group(2).strip()
            plan["artist"] = m.group(3).strip()

        return plan

    # con OpenAI
    try:
        # Usar SYSTEM específico para géneros directos
        system_prompt = SYSTEM
        if direct_genre:
            system_prompt = SYSTEM_DIRECT_GENRE.replace(
                "{DIRECT_GENRE}", direct_genre)
            default["genre"] = direct_genre
            default["substyle"] = None

        resp = _openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            temperature=0
        )
        txt = resp.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", txt, flags=re.S)
        if m:
            txt = m.group(0)
        data = json.loads(txt)

        # defaults sensatos
        data.setdefault("task", "playlist")
        data.setdefault("count", 10)
        data.setdefault("genre", None)
        data.setdefault("substyle", None)
        data.setdefault("artist", None)
        data.setdefault("album", None)

        # refuerza count desde texto si viene explícito
        cnt = extract_count(user_text)
        if cnt:
            data["count"] = cnt

        # si no detectó artista y el texto dice "solo X", intenta heurística
        if not data.get("artist"):
            cand_artist = _guess_artist_from_text(user_text)
            if cand_artist:
                data["artist"] = cand_artist

        return data
    except Exception:
        plan = default.copy()
        cnt = extract_count(user_text)
        if cnt:
            plan["count"] = cnt
        cand_artist = _guess_artist_from_text(user_text)
        if cand_artist:
            plan["artist"] = cand_artist
        return plan

# ===== MusicBrainz search (source anotado) =====


def mb_search_recordings(query: str, limit: int = 100) -> List[Dict]:
    try:
        data = mb_get("recording", {"query": query,
                      "limit": limit, "offset": 0})
    except Exception:
        return []
    out: List[Dict] = []
    for it in data.get("recordings", []):
        title = it.get("title")
        ac = it.get("artist-credit", [])
        names: List[str] = []
        for c in ac:
            if isinstance(c, dict) and c.get("name"):
                names.append(c["name"])
            elif isinstance(c, str):
                names.append(c)
        artist = " & ".join(names) if names else ""
        if title and artist:
            out.append({"artist": artist, "title": title,
                       "source": "musicbrainz"})
    return out


def mb_search_recordings_by_artist(artist: str, limit: int = 200) -> List[Dict]:
    """
    Busca grabaciones (tracks) de un artista específico.
    Usa combinación de campos: artist + recording, evitando mezclar otros artistas.
    """
    a = _lucene_escape(artist)
    # Combinamos dos queries: una estricta y una laxa
    queries = [
        # estricto por artista
        f'artist:"{a}"',
        # nombre de artista en credit
        f'artistname:"{a}" AND recording:*',
    ]
    out: List[Dict] = []
    seen = set()
    for q in queries:
        rs = mb_search_recordings(q, limit=limit)
        for r in rs:
            # Filtro: primer artista en credit debe contener el nombre (aprox)
            if simp(artist).split()[0] not in simp(r["artist"]):
                # si es un & colab, aún puede valer si incluye artista en la cadena
                if simp(artist) not in simp(r["artist"]):
                    continue
            k = key_pair(r["artist"], r["title"])
            if k in seen:
                continue
            seen.add(k)
            out.append(r)
    return out[:limit]


def search_by_rule(key: str, limit: int = 120) -> List[Dict]:
    rule = GENRE_RULES[key]
    hints_or = " OR ".join([f'"{h}"' for h in rule["query_hint"]])
    negs = rule.get("negative_hint", [])
    negs_and = " ".join([f'NOT "{n}"' for n in negs]) if negs else ""
    tags_or = " OR ".join(
        [f'tag:"{t}"' for t in rule.get("mb_tags", [])]) or 'tag:"latin"'
    q = f'recording:({hints_or}) AND ({tags_or}) {negs_and}'.strip()
    return mb_search_recordings(q, limit=limit)


def search_by_anchors(key: str, anchors: List[str], limit_each: int = 40) -> List[Dict]:
    rule = GENRE_RULES[key]
    hints_or = " OR ".join([f'"{h}"' for h in rule["query_hint"]])
    tags_or = " OR ".join(
        [f'tag:"{t}"' for t in rule.get("mb_tags", [])]) or 'tag:"latin"'
    out: List[Dict] = []
    for a in anchors:
        q = f'recording:({hints_or}) AND ({tags_or}) AND artist:"{a}"'
        out.extend(mb_search_recordings(q, limit=limit_each))
    return out


# ===== Discogs (source anotado) =====
DISCOGS_STYLE_MAP: Dict[str, List[str]] = {
    "cha_cha_cha": ["Cha-Cha", "Charanga"],
    "boogaloo": ["Boogaloo"],
    "mambo": ["Mambo"],
    "latin_soul": ["Latin Soul", "Soul", "Funk"],
    "salsa_dura_clasica": ["Salsa"],
    "salsa_dura_revival": ["Salsa"],
    "salsa_romantica": ["Salsa"],
    "son_cubano": ["Son", "Son Montuno"],
    "guajira_moderna": ["Guajira", "Son"],
    "guaracha": ["Guaracha"],
    "plena_bomba": ["Plena", "Bomba"],
    "rumba_guaguanco": ["Rumba"],
    "afro_cuban_jazz_descarga": ["Latin Jazz", "Descarga"],
    "guaguanco_fusionado": ["Salsa", "Rumba"],
    "exotica": ["Exotica", "Easy Listening"],
    "timba": ["Timba", "Salsa"],
}


def _discogs_release_to_pair(rel) -> Optional[Dict[str, str]]:
    try:
        t = getattr(rel, "title", None)
        if isinstance(t, str) and " - " in t:
            a, s = t.split(" - ", 1)
            a, s = a.strip(), s.strip()
            if a and s:
                return {"artist": a, "title": s, "source": "discogs"}
        artists = getattr(rel, "artists", None)
        name = None
        if artists:
            name = getattr(artists[0], "name", None) or getattr(
                artists[0], "anv", None)
        title = getattr(rel, "title", None)
        if name and title:
            return {"artist": str(name).strip(" ,"), "title": str(title).strip(), "source": "discogs"}
    except Exception:
        pass
    return None


def discogs_search_rule(key: str, rule: Dict, limit: int = 100) -> List[Dict]:
    if not discogs:
        return []
    out: List[Dict] = []
    styles = DISCOGS_STYLE_MAP.get(key, [])
    try:
        # 1) Estilos específicos
        for st in styles:
            rs = discogs.search(type="release", genre="Latin", style=st)
            for rel in rs.page(1):
                pair = _discogs_release_to_pair(rel)
                if pair:
                    out.append(pair)
                if len(out) >= limit:
                    return out[:limit]
        # 2) Query textual por hints si falta
        if len(out) < limit:
            hints = " ".join(rule.get("query_hint", [])
                             ) or key.replace("_", " ")
            rs = discogs.search(type="release", genre="Latin", q=hints)
            for rel in rs.page(1):
                pair = _discogs_release_to_pair(rel)
                if pair:
                    out.append(pair)
                if len(out) >= limit:
                    break
        return out[:limit]
    except Exception:
        return out[:limit]


def discogs_search_anchors(key: str, anchors: List[str], rule: Dict, limit_each: int = 30) -> List[Dict]:
    if not discogs or not anchors:
        return []
    out: List[Dict] = []
    try:
        for a in anchors:
            rs = discogs.search(type="release", genre="Latin", artist=a)
            count = 0
            for rel in rs.page(1):
                pair = _discogs_release_to_pair(rel)
                if pair:
                    out.append(pair)
                    count += 1
                if count >= limit_each:
                    break
        return out
    except Exception:
        return out


def discogs_search_by_artist(artist: str, limit: int = 120) -> List[Dict]:
    """
    Búsqueda simple por artista en Discogs; devuelve pares aproximados.
    Nota: muchos resultados son releases (álbum/single). Úsalo solo como backfill.
    """
    if not discogs:
        return []
    out: List[Dict] = []
    try:
        rs = discogs.search(type="release", artist=artist, genre="Latin")
        count = 0
        for rel in rs.page(1):
            pair = _discogs_release_to_pair(rel)
            if pair:
                # fuerza artista igual si es ANV/variante
                if simp(artist).split()[0] not in simp(pair["artist"]):
                    continue
                out.append(pair)
                count += 1
            if count >= limit:
                break
        return out
    except Exception:
        return out

# ===== Playlist builders =====


def add_unique(rows: List[Dict], seen: set, artist: str, title: str, source: str = "", query_override: str = ""):
    k = key_pair(artist, title)
    if k not in seen:
        rows.append({
            "artist": artist,
            "title": title,
            "query_override": query_override,
            "source": source
        })
        seen.add(k)


def pick_playlist(genre: str, substyle: Optional[str], count: int) -> List[Dict]:
    key = genre.lower().strip().replace("-", "_").replace(" ", "_")
    if key not in GENRE_RULES:
        key = "salsa_dura_clasica"
    rule = GENRE_RULES[key]

    anchors = ANCHOR_ARTISTS.get(key, [])
    anchor_set = {simp(a) for a in anchors}

    def is_anchor(artist: str) -> bool:
        return simp(artist) in anchor_set

    # 1) Discogs (prioridad)
    dc_base = discogs_search_rule(key, rule, limit=180)
    dc_anch = discogs_search_anchors(
        key, anchors, rule, limit_each=30) if anchors else []

    # 2) MusicBrainz (fallback)
    mb_base = search_by_rule(key, limit=160)
    mb_anch = search_by_anchors(key, anchors, limit_each=30) if anchors else []

    try:
        debug_print(
            f"[DBG] pick_playlist sources: DC_base={len(dc_base)} DC_anchor={len(dc_anch)} MB_base={len(mb_base)} MB_anchor={len(mb_anch)}")
    except Exception:
        pass

    pool = dc_base + dc_anch + mb_base + mb_anch

    # Unión + dedupe
    seen = set()
    deduped: List[Dict] = []
    for c in pool:
        artist, title = c.get("artist"), c.get("title")
        if not artist or not title:
            continue
        k = key_pair(artist, title)
        if k in seen:
            continue
        seen.add(k)
        # asegura source
        src = c.get("source") or ("discogs" if c in (
            dc_base + dc_anch) else "musicbrainz")
        deduped.append({"artist": artist, "title": title, "source": src})

    # Orden según substyle
    if substyle == "comercial":
        ordered = [c for c in deduped if is_anchor(
            c["artist"])] + [c for c in deduped if not is_anchor(c["artist"])]
    elif substyle == "underground":
        ordered = [c for c in deduped if not is_anchor(
            c["artist"])] + [c for c in deduped if is_anchor(c["artist"])]
    else:
        random.shuffle(deduped)
        ordered = deduped

    # Selección hasta count
    rows: List[Dict] = []
    used = set()
    for c in ordered:
        if len(rows) >= count:
            break
        add_unique(rows, used, c["artist"], c["title"], c.get("source", ""))

    try:
        debug_print(
            f"[DBG] pick_playlist after ordered-select: {len(rows)} / {count}")
    except Exception:
        pass

    # Backfill si falta
    if len(rows) < count and key in BACKFILL:
        bfill = BACKFILL[key][:]
        if substyle == "underground":
            # anchors al final
            bfill.sort(key=lambda x: simp(x["artist"]) in anchor_set)
        else:
            # anchors primero
            bfill.sort(key=lambda x: simp(x["artist"]) not in anchor_set)
        for it in bfill:
            if len(rows) >= count:
                break
            add_unique(rows, used, it["artist"], it["title"], "backfill")

    # Último recurso genérico (MB)
    if len(rows) < count:
        gen = mb_search_recordings(
            'recording:"salsa" AND tag:"latin"', limit=120)
        for r in gen:
            if len(rows) >= count:
                break
            add_unique(rows, used, r["artist"], r["title"], "musicbrainz")

    return rows[:count]


def pick_artist_playlist(artist: str, count: int, genre: Optional[str] = None) -> List[Dict]:
    """
    Construye una lista SOLO del artista dado, priorizando grabaciones (tracks) reales.
    - MusicBrainz (recordings por artista)
    - Discogs (backfill aproximado)
    - Filtro opcional por 'genre' (si viene, intenta sesgar resultados por hints del género)
    """
    rows: List[Dict] = []
    seen = set()

    # 1) MB: recordings del artista
    mb_tracks = mb_search_recordings_by_artist(artist, limit=400)
    try:
        debug_print(
            f"[DBG] pick_artist_playlist: MB_tracks={len(mb_tracks)} artist='{artist}'")
    except Exception:
        pass

    # Si hay 'genre', reordena por coincidencia con hints
    if genre:
        key = genre.lower().strip().replace("-", "_").replace(" ", "_")
        hints = GENRE_RULES.get(key, {}).get("query_hint", [])

        def score_g(item):
            txt = f"{item['artist']} {item['title']}".lower()
            sc = sum(1 for h in hints if h.lower() in txt)
            return sc
        mb_tracks.sort(key=score_g, reverse=True)

    for r in mb_tracks:
        if len(rows) >= count:
            break
        add_unique(rows, seen, r["artist"], r["title"],
                   "musicbrainz", query_override=f'{artist} {r["title"]}')

    # 2) Discogs como backfill (apróx.)
    if len(rows) < count:
        dc = discogs_search_by_artist(artist, limit=200)
        try:
            debug_print(f"[DBG] pick_artist_playlist: DC_backfill={len(dc)}")
        except Exception:
            pass
        for d in dc:
            if len(rows) >= count:
                break
            add_unique(rows, seen, d["artist"], d["title"],
                       "discogs", query_override=f'{artist} {d["title"]}')

    # Último recurso: si aún faltan, intenta MB genérico pero filtrando por nombre
    if len(rows) < count:
        more = mb_search_recordings(
            f'artist:"{_lucene_escape(artist)}" AND recording:*', limit=200)
        try:
            debug_print(f"[DBG] pick_artist_playlist: MB_more={len(more)}")
        except Exception:
            pass
        for r in more:
            if len(rows) >= count:
                break
            if simp(artist) not in simp(r["artist"]):
                continue
            add_unique(rows, seen, r["artist"], r["title"],
                       "musicbrainz", query_override=f'{artist} {r["title"]}')

    try:
        debug_print(
            f"[DBG] pick_artist_playlist: selected={len(rows)} / target={count}")
    except Exception:
        pass
    return rows[:count]


def _lucene_escape(s: str) -> str:
    return (s or "").replace('"', r'\"').strip()

# ===== Fallback OpenAI para artistas no encontrados =====


def search_real_songs_spotify(artist: str, count: int, genre: Optional[str] = None) -> List[Dict]:
    """
    Busca canciones reales del artista en Spotify.
    """
    if not _spotify:
        print("⚠️ Spotify no disponible")
        return []

    try:
        # Buscar el artista en Spotify
        search_query = f'{artist}'
        if not genre:
            # Agregar "salsa" al query de búsqueda cuando no viene género específico
            search_query = f'{artist} salsa'

        debug_print(f"[DBG] Spotify search query: {search_query}")
        debug_print(f"[DBG] Spotify search params: type=track, limit=50")

        results = _spotify.search(
            q=search_query, type='track', limit=50)
        debug_print(f"[DBG] Spotify search results: {results}")
        tracks = results['tracks']['items']

        debug_print(f"[DBG] Spotify returned {len(tracks)} tracks")

        if not tracks:
            print(f"🔍 Spotify no encontró canciones de {artist}")
            return []

        # Filtrar por artista exacto y crear lista
        rows = []
        seen = set()
        filtered_count = 0

        for track in tracks:
            # Verificar que el artista coincida con lógica mejorada
            track_artists = [artist_info['name'].lower()
                             for artist_info in track['artists']]

            # Función mejorada de matching de artistas
            def artist_matches(search_artist: str, track_artists: List[str]) -> bool:
                search_artist = search_artist.lower().strip()
                track_artists_lower = [artist.lower()
                                       for artist in track_artists]

                # 1. Coincidencia exacta
                if search_artist in track_artists_lower:
                    return True

                # 2. Coincidencia con palabras separadas
                # Si el artista de búsqueda tiene espacios, verificar si todas las palabras están en el artista del track
                search_words = search_artist.split()
                if len(search_words) > 1:
                    for track_artist in track_artists_lower:
                        track_words = track_artist.split()
                        # Verificar si todas las palabras de búsqueda están en el artista del track
                        if all(word in track_words for word in search_words):
                            return True
                        # Verificar si todas las palabras del artista del track están en la búsqueda
                        if all(word in search_words for word in track_words):
                            return True

                # 3. Coincidencia parcial (para casos como "La Mambanegra" vs "Mambanegra")
                for track_artist in track_artists_lower:
                    if search_artist in track_artist or track_artist in search_artist:
                        return True

                # 4. Coincidencia flexible para casos como "mamba negra" vs "mambanegra"
                # Remover espacios y artículos comunes para comparación más flexible
                def normalize_artist_name(name: str) -> str:
                    # Remover artículos comunes
                    articles = ['la', 'el', 'los', 'las', 'le',
                                'les', 'un', 'una', 'de', 'del', 'y', '&']
                    words = name.split()
                    filtered_words = [
                        word for word in words if word not in articles]
                    # Unir sin espacios para comparación
                    return ''.join(filtered_words)

                search_normalized = normalize_artist_name(search_artist)
                for track_artist in track_artists_lower:
                    track_normalized = normalize_artist_name(track_artist)
                    # Verificar si los nombres normalizados son similares
                    if search_normalized in track_normalized or track_normalized in search_normalized:
                        return True
                    # Verificar similitud con un mínimo de caracteres (para evitar matches muy cortos)
                    if len(search_normalized) >= 4 and len(track_normalized) >= 4:
                        # Calcular similitud simple basada en caracteres comunes
                        common_chars = sum(
                            1 for c in search_normalized if c in track_normalized)
                        similarity = common_chars / \
                            max(len(search_normalized), len(track_normalized))
                        if similarity >= 0.7:  # 70% de similitud
                            return True

                return False

            if not artist_matches(artist, track_artists):
                filtered_count += 1
                debug_print(
                    f"[DBG] Spotify filtered out: {track['artists'][0]['name']} - {track['name']} (artist mismatch)")
                continue

            title = track['name']
            artist_name = track['artists'][0]['name']  # Usar el primer artista

            # Evitar duplicados
            key = f"{artist_name.lower()}|{title.lower()}"
            if key in seen:
                continue
            seen.add(key)

            # Agregar contexto de género si no se especificó
            query_override = f"{artist_name} {title}"
            if not genre:
                # Buscar versiones de salsa de la canción específica
                query_override = f"{title} salsa"

            rows.append({
                "artist": artist_name,
                "title": title,
                "query_override": query_override,
                "source": "spotify"
            })

            # Debug: mostrar cada canción encontrada
            debug_print(f"[DBG] Spotify found: {artist_name} - {title}")
            debug_print(f"[DBG] Query override: {query_override}")

            if len(rows) >= count:
                break

        debug_print(
            f"[DBG] Spotify filtering summary: {len(tracks)} total tracks, {filtered_count} filtered out, {len(rows)} final matches")
        print(f"🎵 Spotify encontró {len(rows)} canciones reales de {artist}")
        return rows

    except Exception as e:
        print(f"⚠️ Error buscando en Spotify: {e}")
        return []


def generate_real_songs_with_openai(artist: str, count: int, genre: Optional[str] = None) -> List[Dict]:
    """
    Usa OpenAI para encontrar canciones reales del artista cuando no se encuentra en MusicBrainz/Discogs.
    """
    try:
        # Intentar usar OpenAI primero
        if _openai:
            # Crear prompt para OpenAI
            genre_context = ""
            if genre:
                genre_context = f" en el estilo de {genre.replace('_', ' ')}"

            prompt = f"""Necesito que me proporciones {count} canciones REALES del artista "{artist}"{genre_context}.

IMPORTANTE:
- Debe ser canciones que realmente existen
- No inventes títulos ficticios
- Si no conoces canciones reales de este artista, responde "NO_CONOZCO"
- Responde SOLO con los títulos de las canciones, uno por línea
- No incluyas explicaciones ni numeración

Ejemplo de respuesta:
Canción 1
Canción 2
Canción 3"""

            response = _openai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Eres un experto en música con conocimiento extenso de artistas y sus canciones reales. Solo proporciona información verídica."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.8
            )

            # Procesar respuesta
            titles_text = response.choices[0].message.content.strip()

            # Verificar si OpenAI no conoce al artista
            if "NO_CONOZCO" in titles_text.upper() or "NO CONOZCO" in titles_text.upper():
                print(f"🤖 OpenAI no conoce canciones reales de {artist}")
                return []

            titles = [title.strip() for title in titles_text.split('\n') if title.strip(
            ) and not title.strip().startswith(('1.', '2.', '3.', '4.', '5.'))]

            print(
                f"🤖 OpenAI encontró {len(titles)} canciones reales de {artist}")
        else:
            # Fallback: generador básico sin OpenAI
            print("⚠️ OpenAI no disponible, usando generador básico")
            titles = generate_basic_fictional_titles(artist, count, genre)

        # Crear lista de canciones reales
        rows = []
        for title in titles[:count]:
            # Agregar contexto de género si no se especificó
            query_override = f"{artist} {title}"
            if not genre:
                # Buscar versiones de salsa de la canción específica
                query_override = f"{title} salsa"

            rows.append({
                "artist": artist,
                "title": title,
                "query_override": query_override,
                "source": "openai_real"
            })

        return rows

    except Exception as e:
        print(f"⚠️ Error generando canciones: {e}")
        # Fallback final: generador básico
        print("🔄 Usando generador básico como fallback")
        titles = generate_basic_fictional_titles(artist, count, genre)
        rows = []
        for title in titles[:count]:
            rows.append({
                "artist": artist,
                "title": title,
                "query_override": f"{artist} {title}",
                "source": "fictional_basic"
            })
        return rows


def generate_basic_fictional_titles(artist: str, count: int, genre: Optional[str] = None) -> List[str]:
    """
    Generador básico de títulos ficticios sin OpenAI.
    """
    # Títulos genéricos en español
    generic_titles = [
        "La Noche Perfecta",
        "Sueños de Amor",
        "Ritmo del Corazón",
        "Baila Conmigo",
        "Mi Vida Es Música",
        "El Sonido de la Calle",
        "Cuando Te Veo",
        "Noches de Fiesta",
        "El Ritmo Que Me Mueve",
        "Siempre Contigo",
        "La Música No Para",
        "Déjame Soñar",
        "El Baile de la Vida",
        "Mi Corazón Canta",
        "La Fiesta Continúa"
    ]

    # Títulos específicos por género
    genre_titles = {
        "salsa": ["Salsa Caliente", "El Son de la Salsa", "Baila Salsa", "Ritmo Salsero"],
        "balada": ["Amor Eterno", "Te Extraño", "Mi Corazón", "Siempre Te Amaré"],
        "house": ["House Party", "Dance Floor", "Electronic Dreams", "Night Club"],
        "techno": ["Techno Beat", "Digital World", "Machine Music", "Future Sound"],
        "nueva_trova": ["Canción de Protesta", "El Pueblo Canta", "Libertad", "Revolución"]
    }

    # Seleccionar títulos
    selected_titles = []

    # Agregar títulos específicos del género si existe
    if genre and genre in genre_titles:
        selected_titles.extend(genre_titles[genre][:min(3, count)])

    # Completar con títulos genéricos
    remaining = count - len(selected_titles)
    if remaining > 0:
        available_generic = [
            t for t in generic_titles if t not in selected_titles]
        selected_titles.extend(available_generic[:remaining])

    return selected_titles[:count]

# ===== Álbum (MusicBrainz) =====


def mb_search_release(artist: str, album: str) -> Optional[Dict]:
    """
    Devuelve el mejor release-group para (artist, album).
    Usa campos correctos: releasegroup/release + artist + primarytype.
    """
    a = _lucene_escape(artist)
    al = _lucene_escape(album)
    q = (
        f'artist:"{a}" AND (releasegroup:"{al}" OR release:"{al}") '
        f'AND primarytype:"album"'
    )
    try:
        data = mb_get("release-group", {"query": q, "limit": 5})
    except Exception:
        return None
    rgs = data.get("release-groups", [])
    if not rgs:
        return None
    # Preferir coincidencias más cercanas por título y por fecha más antigua

    def score(rg):
        title = (rg.get("title") or "").lower()
        exact = 0 if _strip_accents(
            title) == _strip_accents(album).lower() else 1
        date = rg.get("first-release-date", "9999-99-99")
        return (exact, date)
    rgs.sort(key=score)
    return rgs[0]

# --- obtener tracks vía release LOOKUP (no sólo browse) ---


def mb_release_tracks(release_group_id: str) -> List[Dict]:
    """
    1) Navega releases del release-group para elegir uno.
    2) Lookup a /release/{id}?inc=recordings para extraer el tracklist.
    """
    try:
        # Paso 1: conseguir algunas ediciones del grupo
        data = mb_get(
            "release", {"release-group": release_group_id, "limit": 10})
    except Exception:
        return []
    rels = data.get("releases", []) or []
    if not rels:
        return []

    # Elegimos una edición "mejor": prioriza status=Official y la más antigua
    def rkey(r):
        status = (r.get("status") or "zzz").lower()
        is_official = 0 if status == "official" else 1
        date = r.get("date") or "9999-99-99"
        return (is_official, date)
    rels.sort(key=rkey)
    release_id = rels[0]["id"]

    # Paso 2: lookup con recordings (tracklist completo)
    try:
        rel = mb_get(f"release/{release_id}",
                     {"inc": "recordings+artist-credits"})
    except Exception:
        return []

    tracks: List[Dict] = []
    media = rel.get("media", [])
    for med in media:
        for t in med.get("tracks", []):
            rec = t.get("recording", {}) or {}
            title = rec.get("title") or t.get("title")
            # artista por track (si existe), si no el del release
            ac = rec.get("artist-credit") or rel.get("artist-credit") or []
            names = []
            for c in ac:
                if isinstance(c, dict) and c.get("name"):
                    names.append(c["name"])
                elif isinstance(c, str):
                    names.append(c)
            artist_name = " & ".join(names) if names else ""
            if title and artist_name:
                tracks.append({"artist": artist_name, "title": title})
    return tracks

# --- usa las funciones de arriba ---


def build_album_csv(artist: str, album: str) -> List[Dict]:
    rg = mb_search_release(artist, album)
    if not rg:
        try:
            debug_print(
                f"[DBG] build_album_csv: sin release-group para '{artist}' — '{album}'")
        except Exception:
            pass
        return []
    try:
        debug_print(
            f"[DBG] build_album_csv: release-group OK id={rg.get('id', '?')} title={rg.get('title', '?')}")
    except Exception:
        pass
    tracks = mb_release_tracks(rg["id"])
    try:
        debug_print(f"[DBG] build_album_csv: tracks={len(tracks)}")
    except Exception:
        pass
    rows: List[Dict] = []
    seen = set()
    for t in tracks:
        k = key_pair(t["artist"], t["title"])
        if k in seen:
            continue
        seen.add(k)
        rows.append({
            "artist": t["artist"],
            "title": t["title"],
            # query de apoyo para el pipeline/YouTube si lo usas
            "query_override": f'{t["artist"]} {t["title"]} {album}',
            "source": "musicbrainz"
        })
    return rows

# ===== CSV writer =====


def write_csv(rows: List[Dict], path: str, direct_genre: str = None):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # Determinar columnas según si hay género directo
    if direct_genre:
        fieldnames = ["artist", "title", "query_override", "source", "gnere"]
    else:
        fieldnames = ["artist", "title", "query_override", "source"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            row_data = {
                "artist": r["artist"],
                "title": r["title"],
                "query_override": r.get("query_override", ""),
                "source": r.get("source", "")
            }
            if direct_genre:
                row_data["gnere"] = direct_genre
            w.writerow(row_data)

# ===== Runner =====


def run_request(nl_request: str, out_csv: str):
    print("🧠 Interpretando pedido…")
    plan = llm_plan(nl_request)

    # Si es playlist y no trae substyle, sesgo por defecto (como tenías)
    if plan.get("task") == "playlist" and not plan.get("substyle"):
        g = (plan.get("genre") or "").lower()
        plan["substyle"] = "underground" if "salsa_dura_clasica" in g else None

    print("   Plan:", plan)

    # Verificar si el artista está prohibido
    if plan.get("artist"):
        if is_bad_not_permitted(plan["artist"]):
            show_bad_not_permitted_message(plan["artist"])
            return

    rows: List[Dict] = []
    if plan["task"] == "album" and plan.get("artist") and plan.get("album"):
        print(f"💿 Buscando álbum: {plan['artist']} — {plan['album']}")
        rows = build_album_csv(plan["artist"], plan["album"])
        if not rows:
            print("   ⚠️ No se encontró el álbum en MusicBrainz.")
    else:
        count = int(plan.get("count") or 10)
        artist = (plan.get("artist") or "").strip() or None
        genre = (plan.get("genre") or None)
        substyle = plan.get("substyle")

        if artist and not plan.get("album"):
            # *** NUEVO: modo artista ***
            print(
                f"👤 Playlist por artista: {count} temas | {artist} | género filtro: {genre or '—'}")
            rows = pick_artist_playlist(artist, count, genre=genre)
        else:
            # modo por género (el de siempre)
            g = (genre or "salsa_dura_clasica").lower()
            print(f"🎚️ Playlist: {count} temas | {g} | {substyle or 'mixto'}")
            rows = pick_playlist(g, substyle, count)
        try:
            debug_print(f"[DBG] run_request: rows_before_final={len(rows)}")
        except Exception:
            pass

    if not rows:
        try:
            debug_print(f"[DBG] run_request: no rows generated. plan={plan}")
        except Exception:
            pass

        # Fallback: buscar canciones reales en Spotify, luego OpenAI
        if plan.get("artist") and plan.get("task") == "playlist":
            print(
                f"🔍 No se encontraron canciones en MusicBrainz/Discogs, buscando en Spotify...")
            rows = search_real_songs_spotify(
                plan["artist"],
                int(plan.get("count") or 10),
                genre
            )

            # Si Spotify no encuentra nada, usar OpenAI con prompt del usuario
            if not rows:
                print(
                    f"🤖 Spotify no encontró nada, usando OpenAI para buscar canciones reales...")
                rows = generate_real_songs_with_openai(
                    plan["artist"],
                    int(plan.get("count") or 10),
                    genre
                )

        if not rows:
            print("❌ No se pudo generar el CSV.")
            return

    # dedupe final y corte
    final: List[Dict] = []
    seen = set()
    target = int(plan.get("count") or len(rows))
    for r in rows:
        k = key_pair(r["artist"], r["title"])
        if k in seen:
            continue
        seen.add(k)
        final.append(r)
        if len(final) >= target:
            break

    write_csv(final, out_csv)
    print(f"✅ CSV generado: {out_csv}  ({len(final)} filas)")
    print("   Ejecuta ahora:  come-candela")


# ===== Géneros Directos =====
DIRECT_GENRES = ["balada", "house", "nueva_trova", "techno"]

# ===== Lista de Artistas y Géneros Prohibidos =====
# Para agregar nuevos artistas prohibidos, simplemente añádelos a BLOCKED_ARTISTS
# Para agregar nuevos géneros prohibidos, añádelos a BLOCKED_GENRES
# El sistema detectará automáticamente cualquier coincidencia (case-insensitive, sin acentos)

BLOCKED_ARTISTS = [
    "bad bunny", "j balvin", "ozuna", "maluma", "karol g", "anuel aa", "daddy yankee",
    "don omar", "wisin", "yandel", "nicky jam", "farruko", "jhay cortez", "myke towers",
    "rauw alejandro", "sech", "feid", "ryan castro", "manuel turizo", "camilo"
    # Agregar más artistas aquí según sea necesario
]

BLOCKED_GENRES = [
    "reggaeton", "trap", "urban", "latin trap", "reggaetonero", "reggaetonera"
    # Agregar más géneros aquí según sea necesario
]


def is_blocked_artist(artist_name: str) -> bool:
    """
    Detecta si el artista está en la lista de artistas prohibidos.
    """
    if not artist_name:
        return False

    artist_lower = _strip_accents(artist_name.lower())

    # Verificar si el nombre del artista está en la lista de artistas prohibidos
    for blocked_artist in BLOCKED_ARTISTS:
        if blocked_artist in artist_lower:
            return True

    return False


def is_blocked_genre(artist_name: str) -> bool:
    """
    Detecta si el artista contiene palabras clave de géneros prohibidos.
    """
    if not artist_name:
        return False

    artist_lower = _strip_accents(artist_name.lower())

    # Verificar si el texto contiene palabras clave de géneros prohibidos
    for blocked_genre in BLOCKED_GENRES:
        if blocked_genre in artist_lower:
            return True

    return False


def is_bad_not_permitted(artist_name: str) -> bool:
    """
    Detecta si el artista o género está prohibido.
    """
    return is_blocked_artist(artist_name) or is_blocked_genre(artist_name)


def show_bad_not_permitted_message(artist_name: str):
    """
    Muestra un mensaje gracioso cuando se detecta un artista o género prohibido.
    """
    messages = [
        f"🚫 ¡Alto ahí! {artist_name} trae reggaetón barato. El portal de la candela no se abre con esa llave.",
        f"🎭 {artist_name}? Eso suena a reggaetón de baja frecuencia. Aquí solo vibra el eco de Lavoe y Colón.",
        f"❌ {artist_name} está vetado por los ancestros de la salsa. Trae guaguancó o no entres.",
        f"🔥 {artist_name} = reggaetón. Aquí solo se encienden discos que hacen sudar la clave.",
        f"🎶 {artist_name}? Hermano, eso es ruido de reggaetón. Pide a Fania, pide a la Ponceña, invoca calidad.",
        f"🚫 {artist_name}? Los dioses del mambo lo rechazaron. Aquí solo gira vinilo fino.",
        f"🎵 {artist_name} es reggaetón, pana. La candela pide Palmieri, Blades, Raphy Leavitt… no eso.",
        f"❌ {artist_name} no cruza este umbral. El reggaetón se queda afuera del templo de la clave.",
        f"🔥 {artist_name}? Eso es reggaetón. La máquina de fuego solo entiende salsa dura y son cubano.",
        f"🎶 {artist_name}? Bah. Aquí quemamos descargas y soneos, no ese plástico de reggaetón."
    ]

    import random
    message = random.choice(messages)
    print(message)
    print("")


def parse_direct_genre_request(user_input: str, genre_arg: str = None) -> tuple:
    """
    Parsea solicitudes con género directo: "instrucción" "género"
    Retorna (instrucción, género) o (user_input, None) si no es formato directo
    """
    # Si se pasó género como argumento separado
    if genre_arg:
        genre_lower = genre_arg.lower()
        if genre_lower in DIRECT_GENRES:
            return user_input, genre_lower
        else:
            # Género directo inválido - mostrar error
            print(f"❌ Error: Género directo inválido: '{genre_arg}'")
            print(f"   Géneros válidos: {', '.join(DIRECT_GENRES)}")
            print(f"   Formato correcto: mala-pata \"instrucción\" \"género\"")
            exit(1)

    # Buscar patrón: "texto" "género" (formato original con comillas anidadas)
    import shlex
    try:
        parts = shlex.split(user_input)
        if len(parts) == 2:
            instruction, genre = parts
            genre_lower = genre.lower()
            if genre_lower in DIRECT_GENRES:
                return instruction, genre_lower
            else:
                # Género directo inválido - mostrar error
                print(f"❌ Error: Género directo inválido: '{genre}'")
                print(f"   Géneros válidos: {', '.join(DIRECT_GENRES)}")
                print(f"   Formato correcto: mala-pata \"instrucción\" \"género\"")
                exit(1)
    except ValueError:
        pass

    return user_input, None


def run_request_with_direct_genre(nl_request: str, direct_genre: str, out_csv: str):
    """
    Ejecuta solicitud con género directo (sin análisis de género).
    """
    print("🧠 Interpretando pedido con género directo…")
    plan = llm_plan(nl_request, direct_genre=direct_genre)

    print("   Plan:", plan)

    # Verificar si el artista está prohibido
    if plan.get("artist"):
        if is_bad_not_permitted(plan["artist"]):
            show_bad_not_permitted_message(plan["artist"])
            return

    rows: List[Dict] = []
    if plan["task"] == "album" and plan.get("artist") and plan.get("album"):
        print(f"💿 Buscando álbum: {plan['artist']} — {plan['album']}")
        rows = build_album_csv(plan["artist"], plan["album"])
        if not rows:
            print("   ⚠️ No se encontró el álbum en MusicBrainz.")
    else:
        count = int(plan.get("count") or 10)
        artist = (plan.get("artist") or "").strip() or None

        if artist and not plan.get("album"):
            print(
                f"👤 Playlist por artista: {count} temas | {artist} | género: {direct_genre}")
            rows = pick_artist_playlist(
                artist, count, genre=None)  # Sin filtro de género

            # Si no encuentra canciones del artista específico, usar OpenAI fallback
            if not rows:
                print(
                    f"   ⚠️ No se encontraron canciones de {artist} en MusicBrainz/Discogs.")
                print(f"   🤖 Generando canciones con OpenAI...")
                rows = generate_real_songs_with_openai(
                    artist, count, direct_genre)
        else:
            # Para géneros directos sin artista específico, usar búsqueda genérica
            print(
                f"🎚️ Playlist: {count} temas | género directo: {direct_genre}")
            # Usar salsa como base genérica
            rows = pick_playlist("salsa_dura_clasica", None, count)

    if not rows:
        print("❌ No se pudo generar el CSV.")
        return

    # Deduplicación final
    final: List[Dict] = []
    seen = set()
    target = int(plan.get("count") or len(rows))
    for r in rows:
        k = key_pair(r["artist"], r["title"])
        if k in seen:
            continue
        seen.add(k)
        final.append(r)
        if len(final) >= target:
            break

    write_csv(final, out_csv, direct_genre=direct_genre)
    print(
        f"✅ CSV generado con género directo: {out_csv}  ({len(final)} filas)")
    print(f"🎯 Género asignado: {direct_genre}")
    print("   Ejecuta ahora:  come-candela")


# ===== CLI =====
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convierte un pedido natural en canciones.csv (Discogs→MB, con fuente) para el pipeline")
    parser.add_argument(
        "pedido", help="Ej: 'descárgame 10 canciones de salsa dura clasica' o '5 canciones de Larry Harlow'")
    parser.add_argument(
        "genero", nargs="?", help="Género directo: balada, house, nueva_trova, techno")
    # Por defecto, escribir en el directorio del proyecto
    default_out = os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "canciones.csv")
    parser.add_argument("--out", default=default_out,
                        help="CSV de salida (default: canciones.csv)")
    args = parser.parse_args()
    out_path = args.out
    # Si pasaron una ruta relativa, anclarla al directorio del proyecto
    if not os.path.isabs(out_path):
        out_path = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), out_path)

    # Verificar si es solicitud con género directo
    instruction, direct_genre = parse_direct_genre_request(
        args.pedido, args.genero)

    if direct_genre:
        print(f"🎯 Modo género directo: {direct_genre}")
        print(f"📝 Instrucción: {instruction}")
        run_request_with_direct_genre(instruction, direct_genre, out_path)
    else:
        run_request(args.pedido, out_path)

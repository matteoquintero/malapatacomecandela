# mpc/sources/openai_source.py
# -*- coding: utf-8 -*-
"""
Fuente OpenAI: consulta canciones REALES de un artista.
NO genera títulos ficticios. Si no conoce al artista, falla explícitamente.
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger("mpc.sources.openai")


def get_openai_client(api_key: str, model: str = "gpt-4o-mini"):
    """Devuelve (client, model) o (None, model) si no está disponible."""
    if not api_key:
        return None, model
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        logger.debug("OpenAI client OK model=%s", model)
        return client, model
    except ImportError:
        logger.warning("openai no instalado. pip install openai")
        return None, model
    except Exception as e:
        logger.warning("Error iniciando OpenAI: %s", e)
        return None, model


def find_real_songs(
    client,
    model: str,
    artist: str,
    count: int,
    genre: Optional[str] = None,
    user_request: Optional[str] = None,
) -> List[Dict]:
    """
    Pide a OpenAI {count} canciones REALES del artista.
    Devuelve lista de dicts {artist, title, query_override, source} o [] si falla.

    No genera canciones ficticias. Si OpenAI responde "NO_CONOZCO", devuelve [].
    """
    if not client:
        return []

    genre_ctx = f" en el estilo de {genre.replace('_', ' ')}" if genre else ""
    req_ctx = f'\n\nContexto del usuario: "{user_request}"' if user_request else ""

    prompt = (
        f"Necesito {count} canciones REALES del artista \"{artist}\"{genre_ctx}.{req_ctx}\n\n"
        "REGLAS ESTRICTAS:\n"
        "- Solo canciones que realmente existen y están grabadas\n"
        "- Si no conoces canciones reales de este artista, responde exactamente: NO_CONOZCO\n"
        "- Responde SOLO con los títulos, uno por línea, sin numeración ni explicaciones\n"
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Eres un experto en música. Solo proporciona información verídica. "
                               "Si no conoces canciones reales de un artista, di NO_CONOZCO.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.3,
        )

        text = resp.choices[0].message.content.strip()
        logger.debug("OpenAI find_real_songs response: %s", text[:200])

        if "NO_CONOZCO" in text.upper() or "NO CONOZCO" in text.upper():
            logger.info("OpenAI no conoce al artista '%s'", artist)
            return []

        titles = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip()[:3].rstrip(". ").isdigit()
        ]

        if not titles:
            return []

        rows = []
        for title in titles[:count]:
            rows.append({
                "artist": artist,
                "title": title,
                "query_override": f"{artist} {title}",
                "source": "openai_real",
            })

        logger.info("OpenAI encontró %d canciones de '%s'", len(rows), artist)
        return rows

    except Exception as e:
        logger.warning("Error en OpenAI find_real_songs: %s", e)
        return []

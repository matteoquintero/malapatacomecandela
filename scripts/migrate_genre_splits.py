#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/migrate_genre_splits.py

Migra tracks de slugs deprecados a los slugs nuevos (plena/bomba,
afro_cuban_jazz/descarga) reclasificándolos uno a uno con la heurística +
LLM (modo LLM_FALLBACK). Restringe la elección al par correspondiente del
slug deprecado.

Acciones por track (solo con --apply):
  1. Mover MP3 de LIB_BASE_DIR/<old_slug>/ a LIB_BASE_DIR/<new_slug>/
  2. Reescribir ID3: TCON (genre) y TALB (album = new_slug)
  3. UPDATE tracks SET genre_slug=?, filepath=? WHERE track_id=?

Por defecto es dry-run: muestra la tabla de cambios propuestos sin tocar nada.

Uso:
  python3 scripts/migrate_genre_splits.py             # dry-run
  python3 scripts/migrate_genre_splits.py --apply     # ejecuta
  python3 scripts/migrate_genre_splits.py --heuristic-only   # sin LLM
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mpc.acquisition.engine import DownloadConfig
from mpc.acquisition.steps.classifier import heuristic_classify, llm_classify
from mpc.catalog.genres import DEPRECATED_SLUGS, GENRE_COMMAND, GENRE_DB

# Para cada slug deprecado, los candidatos válidos en los slugs nuevos.
CANDIDATES: Dict[str, List[str]] = {
    "plena_bomba": ["plena", "bomba"],
    "afro_cuban_jazz_descarga": ["afro_cuban_jazz", "descarga"],
}


def _build_genres_ref_for(slugs: List[str]) -> str:
    """Referencia reducida para el LLM: solo los géneros candidatos."""
    ref = []
    for g in GENRE_DB:
        if g["slug"] in slugs:
            ref.append({
                "name": g["name"], "slug": g["slug"],
                "aliases": g.get("aliases", []),
                "rhythm_traits": g.get("rhythm_traits", []),
                "artists_key": g.get("artists_key", []),
                "year_from": g.get("year_from"), "year_to": g.get("year_to"),
            })
    return json.dumps({"genres": ref}, ensure_ascii=False)


def restricted_classify(
    track: Dict,
    candidates: List[str],
    openai_client,
    openai_model: str,
    heuristic_only: bool,
) -> Tuple[str, float, str]:
    """Clasifica restringiendo a los 2 candidatos. Retorna (slug, confidence, rationale)."""
    meta = {
        "title": track.get("title", ""),
        "artist": track.get("artist", ""),
        "description": "",
        "channel": "",
        "release_year": None,
        "duration_sec": None,
    }

    h = heuristic_classify(meta, enrichment={})
    # Si la heurística ya eligió uno de los candidatos con buena confianza, úsalo.
    if h["slug"] in candidates and h["confidence"] >= 0.65:
        return h["slug"], h["confidence"], f"heuristic: {h['rationale']}"

    # Comparar el score crudo de los candidatos desde top3.
    cand_scores = {s: 0.0 for s in candidates}
    for slug, score in h.get("top3", []):
        if slug in cand_scores:
            cand_scores[slug] = score

    if heuristic_only or not openai_client:
        best = max(candidates, key=lambda s: cand_scores[s])
        # Si todos los scores son 0, fallback al default del DEPRECATED_SLUGS.
        if all(v == 0.0 for v in cand_scores.values()):
            return candidates[0], 0.3, "heuristic-only: sin señal, default al primer candidato"
        return best, 0.6, f"heuristic-only: scores {cand_scores}"

    # LLM restringido a los 2 candidatos
    genres_ref = _build_genres_ref_for(candidates)
    prompt_meta = dict(meta)
    try:
        slugs_csv = ", ".join(candidates)
        prompt = f"""Eres musicólogo experto. Debes elegir EXACTAMENTE uno de estos dos slugs: {slugs_csv}.

Caso:
Artista: {meta['artist']}
Título: {meta['title']}

Referencia de géneros (JSON):
{genres_ref}

Responde JSON estricto: {{"slug": "...", "confidence": 0.0-1.0, "rationale": "2-3 frases"}}"""
        comp = openai_client.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": "Eres musicólogo. Responde SOLO JSON válido."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(comp.choices[0].message.content.strip())
        slug = (data.get("slug") or "").strip()
        if slug not in candidates:
            slug = candidates[0]
        conf = max(0.0, min(1.0, float(data.get("confidence", 0.7))))
        return slug, conf, f"llm: {data.get('rationale', '').strip()[:200]}"
    except Exception as e:
        best = max(candidates, key=lambda s: cand_scores[s])
        return best, 0.5, f"llm error fallback ({e}): scores {cand_scores}"


def rewrite_id3(filepath: str, new_slug: str) -> bool:
    """Reescribe tags ID3 genre y album con el nuevo slug. Usa mutagen."""
    try:
        from mutagen.id3 import ID3, TCON, TALB, ID3NoHeaderError
    except ImportError:
        print(f"   ⚠️  mutagen no disponible; saltando ID3 de {filepath}")
        return False

    try:
        try:
            tags = ID3(filepath)
        except ID3NoHeaderError:
            tags = ID3()
        genre_label = new_slug.replace("_", " ")
        tags["TCON"] = TCON(encoding=3, text=[genre_label])
        tags["TALB"] = TALB(encoding=3, text=[new_slug])
        tags.save(filepath)
        return True
    except Exception as e:
        print(f"   ⚠️  error ID3 en {filepath}: {e}")
        return False


def migrate_file(old_path: str, old_slug: str, new_slug: str, lib_base_dir: str) -> Optional[str]:
    """Mueve el MP3 de old_slug/ a new_slug/. Retorna el nuevo filepath o None si falla."""
    if not old_path or not os.path.exists(old_path):
        return None

    # Reemplazo robusto: no simple str.replace (podría matchear mid-path).
    # Busca el segmento exacto /<old_slug>/ en el path.
    sep_old = os.sep + old_slug + os.sep
    sep_new = os.sep + new_slug + os.sep
    if sep_old in old_path:
        new_path = old_path.replace(sep_old, sep_new, 1)
    else:
        # Fallback: reconstruir desde lib_base_dir
        filename = os.path.basename(old_path)
        new_path = os.path.join(lib_base_dir, new_slug, filename)

    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    if os.path.exists(new_path) and os.path.abspath(new_path) != os.path.abspath(old_path):
        print(f"   ⚠️  destino ya existe: {new_path} — dejando original en su lugar")
        return None
    shutil.move(old_path, new_path)
    return new_path


def main() -> int:
    p = argparse.ArgumentParser(description="Migra tracks de slugs deprecados a los nuevos.")
    p.add_argument("--apply", action="store_true", help="Ejecuta cambios (default: dry-run).")
    p.add_argument("--heuristic-only", action="store_true", help="No llamar al LLM, solo heurística.")
    p.add_argument("--limit", type=int, default=0, help="Limitar a N tracks (0 = todos).")
    args = p.parse_args()

    cfg = DownloadConfig.from_env()
    db_path = cfg.resolved_db_path()
    if not os.path.exists(db_path):
        print(f"❌ library.db no existe en {db_path}")
        return 1

    # OpenAI client opcional
    openai_client = None
    if not args.heuristic_only and cfg.openai_api_key:
        try:
            from openai import OpenAI
            openai_client = OpenAI(api_key=cfg.openai_api_key)
        except Exception as e:
            print(f"⚠️  OpenAI no disponible, usando solo heurística: {e}")

    # 1) Cargar todos los tracks con slug deprecado
    deprecated_slugs = list(DEPRECATED_SLUGS.keys())
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(deprecated_slugs))
    rows = con.execute(
        f"SELECT * FROM tracks WHERE genre_slug IN ({placeholders}) ORDER BY genre_slug, artist",
        deprecated_slugs,
    ).fetchall()
    con.close()

    tracks = [dict(r) for r in rows]
    if args.limit > 0:
        tracks = tracks[: args.limit]

    if not tracks:
        print("✅ No hay tracks con slugs deprecados en library.db. Nada que migrar.")
        return 0

    print(f"🔎 {len(tracks)} tracks con slugs deprecados encontrados.")
    print(f"   Modo: {'APLICAR' if args.apply else 'DRY-RUN'}  |  "
          f"LLM: {'OFF' if args.heuristic_only or not openai_client else 'ON'}\n")

    # 2) Clasificar y planificar
    plan: List[Dict] = []
    for i, t in enumerate(tracks, 1):
        old_slug = t["genre_slug"]
        candidates = CANDIDATES.get(old_slug) or [DEPRECATED_SLUGS[old_slug]]
        new_slug, conf, rationale = restricted_classify(
            t, candidates, openai_client, cfg.openai_model, args.heuristic_only
        )
        plan.append({"track": t, "old_slug": old_slug, "new_slug": new_slug,
                     "confidence": conf, "rationale": rationale})
        print(f"[{i:>3}/{len(tracks)}] {t['artist'][:30]:<30} — {t['title'][:40]:<40} "
              f"{old_slug} → {new_slug}  ({conf:.2f})")

    # 3) Resumen
    print("\n📊 Resumen de la migración:")
    from collections import Counter
    counts = Counter((p["old_slug"], p["new_slug"]) for p in plan)
    for (old, new), n in counts.most_common():
        print(f"   {old:<28} → {new:<24}  {n}")

    if not args.apply:
        print("\n🧪 DRY-RUN: no se tocó nada. Corré con --apply para ejecutar.")
        return 0

    # 4) Aplicar: mover archivo + ID3 + UPDATE SQLite
    print("\n⚙️  Aplicando cambios…")
    con = sqlite3.connect(db_path, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    applied = 0
    errors = 0
    now = datetime.now().isoformat(timespec="seconds")
    try:
        for p in plan:
            t = p["track"]
            old_slug, new_slug = p["old_slug"], p["new_slug"]
            old_path = t.get("filepath") or ""
            new_path = old_path

            if old_path and os.path.exists(old_path):
                moved = migrate_file(old_path, old_slug, new_slug, cfg.lib_base_dir)
                if moved:
                    new_path = moved
                    rewrite_id3(new_path, new_slug)
                else:
                    print(f"   ⚠️  {t['artist']} — {t['title']}: no se pudo mover el archivo, actualizo solo DB.")
            elif old_path:
                print(f"   ℹ️  {t['artist']} — {t['title']}: filepath registrado pero no existe en disco; solo DB.")

            con.execute(
                "UPDATE tracks SET genre_slug=?, filepath=?, updated_at=? WHERE track_id=?",
                (new_slug, new_path, now, t["track_id"]),
            )
            applied += 1
        con.commit()
    except Exception as e:
        con.rollback()
        errors += 1
        print(f"❌ error aplicando migración: {e}")
    finally:
        con.close()

    print(f"\n✅ Migración terminada: {applied} aplicados, {errors} errores.")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

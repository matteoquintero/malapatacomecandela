#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_library.py — WRAPPER de `mala-pata curator audit`.

Corre la auditoría y genera reportes Markdown en data/audit_reports/
para visualización rápida. La lógica real vive en mpc/curator/.

READ-ONLY sobre archivos. Modifica columnas curator_* en BD.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mpc.config import get_config
from mpc.curator.auditor import Auditor
from mpc.library.repository import TrackRepository


REPORTS_DIR = REPO_ROOT / "data" / "audit_reports"


def main() -> int:
    cfg = get_config()
    music_dir = Path(cfg.lib_base_dir)
    db_path = REPO_ROOT / "cache" / "library.db"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Auditando {music_dir}")
    repo = TrackRepository(str(db_path))
    auditor = Auditor(repo, music_dir)
    result = auditor.run()

    all_tracks = repo.get_all()

    by_status = defaultdict(list)
    for t in all_tracks:
        by_status[t.get("curator_status") or "unchecked"].append(t)

    out = REPORTS_DIR / "curator_report.md"
    with out.open("w", encoding="utf-8") as f:
        f.write("# Reporte Curator\n\n")
        f.write(f"_Generado: {datetime.now().isoformat(timespec='seconds')}_\n\n")
        f.write(f"- BD total: **{result.db_total}**\n")
        f.write(f"- Disco total: **{result.disk_total}**\n")
        f.write(f"- Huérfanos creados: **{result.orphans_created}**\n\n")
        f.write("## Resumen por curator_status\n\n")
        for status, count in sorted(result.status_counts.items(), key=lambda x: -x[1]):
            f.write(f"- `{status}`: {count}\n")
        f.write("\n---\n\n")

        for status in ["missing", "orphan", "duplicate", "needs_move",
                       "needs_rename", "needs_metadata", "needs_thumbnail",
                       "needs_tags"]:
            rows = by_status.get(status, [])
            if not rows:
                continue
            f.write(f"## {status} ({len(rows)})\n\n")
            f.write("| artist | title | genre | filepath | thumb | tags |\n")
            f.write("|---|---|---|---|---|---|\n")
            for r in rows:
                f.write(
                    f"| {r['artist']} | {r['title']} | {r.get('genre_slug') or '—'} | "
                    f"`{r.get('filepath') or '—'}` | "
                    f"{'yes' if r.get('has_thumbnail') else 'no'} | "
                    f"{'yes' if r.get('has_valid_tags') else 'no'} |\n"
                )
            f.write("\n")

    print(f"\n📄 Reporte: {out.relative_to(REPO_ROOT)}")
    print(f"\n📊 Estado:")
    for status, count in sorted(result.status_counts.items(), key=lambda x: -x[1]):
        print(f"   {status:<25} {count}")
    print("\n💡 Tip: `mala-pata curator status` / `mala-pata curator fix-thumbnails`")
    return 0


if __name__ == "__main__":
    sys.exit(main())

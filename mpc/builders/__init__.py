# mpc/builders/__init__.py — compat shim → mpc.discovery
from mpc.discovery.assembler import pick_playlist, pick_artist_playlist, build_album_csv

__all__ = ["pick_playlist", "pick_artist_playlist", "build_album_csv"]

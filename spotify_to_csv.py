#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backwards-compatibility wrapper.
Delega a: mala-pata create --spotify <url> [--count N] [--genre G] [--type T] [--out F]

Uso original:   python spotify_to_csv.py URL [--count N] [--genre G]
Equivalente:    mala-pata create --spotify URL [--count N] [--genre G]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mpc.cli import main


if __name__ == "__main__":
    argv = list(sys.argv[1:])
    # El primer argumento posicional era la URL/ID de Spotify.
    # Ahora se pasa con --spotify, así que lo reescribimos.
    if argv and not argv[0].startswith("-"):
        url = argv.pop(0)
        argv = ["create", "--spotify", url] + argv
    else:
        argv = ["create"] + argv
    main(argv)

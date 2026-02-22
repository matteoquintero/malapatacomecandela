#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backwards-compatibility wrapper.
Delega a: mala-pata create <args>

Uso original:   python request_to_csv.py "10 canciones de salsa dura"
Equivalente:    mala-pata create "10 canciones de salsa dura"
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mpc.cli import main

if __name__ == "__main__":
    main(sys.argv[1:])

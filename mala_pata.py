#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entry point de mala-pata.
Redirige a mpc.cli.main().
"""

import sys
import os

# Asegurar que el directorio del proyecto esté en el path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mpc.cli import main

if __name__ == "__main__":
    main()

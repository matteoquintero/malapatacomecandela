#!/usr/bin/env python3
"""Renombra archivos con caracteres especiales."""
import os
import re
import sys

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mpc.utils.text import sanitize_filename

MUSIC_DIR = os.path.expanduser("~/Music/mala_pata_come_candela")

def get_new_name(filename):
    """Sanitiza el nombre del archivo."""
    name, ext = os.path.splitext(filename)
    return sanitize_filename(name) + ext

def main():
    renamed = 0
    
    for root, dirs, files in os.walk(MUSIC_DIR):
        for f in files:
            if f.endswith((".mp3", ".mp4")):
                # Check for bad chars
                if re.search(r'[?¿¡![\]()]+', f):
                    old_path = os.path.join(root, f)
                    new_name = get_new_name(f)
                    new_path = os.path.join(root, new_name)
                    
                    if old_path != new_path:
                        print(f"mv -n \"{old_path}\" \"{new_path}\"")
                        # Rename if target doesn't exist
                        if not os.path.exists(new_path):
                            os.rename(old_path, new_path)
                            renamed += 1
                        else:
                            print(f"  ⚠️ Ya existe: {new_path}")
    
    print(f"\n✅ {renamed} archivos renombrados")

if __name__ == "__main__":
    main()
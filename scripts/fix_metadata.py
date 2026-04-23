#!/usr/bin/env python3
"""Fix metadata for all MP3 files based on filename - simplified."""
import os
import sqlite3
from mutagen import File
from mutagen.id3 import ID3, TPE1, TIT2, TCON

DB = "/Users/matteoquintero/malapatacomecandela_system/cache/library.db"

def get_genre_display(genre_slug):
    if not genre_slug:
        return ""
    return genre_slug.replace("_", " ").title()

def main():
    updated = 0
    errors = 0
    skipped = 0

    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT artist, title, filepath, genre_slug 
            FROM tracks 
            WHERE filepath IS NOT NULL AND filepath != ''
        """)
        tracks = cur.fetchall()

    for t in tracks:
        filepath = t["filepath"]
        genre_slug = t["genre_slug"] if t["genre_slug"] else ""
        
        if not filepath or not os.path.exists(filepath):
            skipped += 1
            continue
        
        filename = os.path.basename(filepath).replace(".mp3", "")
        if " - " not in filename:
            skipped += 1
            continue
        
        file_artist, file_title = filename.split(" - ", 1)
        file_artist = file_artist.strip()
        file_title = file_title.strip()
        genre_display = get_genre_display(genre_slug)
        
        try:
            audio = File(filepath)
            if audio is None:
                errors += 1
                continue
            
            needs_update = False
            
            # Get current tags safely
            old_artist = str(audio.get("TPE1", "")) if audio else ""
            old_title = str(audio.get("TIT2", "")) if audio else ""
            old_genre = str(audio.get("TCON", "")) if audio else ""
            
            # Check if needs update
            if old_artist != file_artist:
                needs_update = True
            if old_title != file_title:
                needs_update = True
            if old_genre != genre_display and genre_display:
                needs_update = True
            
            if needs_update:
                # Clear and set new tags
                audio.delete()  # Remove all tags
                audio.tags = ID3()
                audio.tags.add(TPE1(encoding=3, text=file_artist))
                audio.tags.add(TIT2(encoding=3, text=file_title))
                if genre_display:
                    audio.tags.add(TCON(encoding=3, text=genre_display))
                audio.save()
                updated += 1
                print(f"✅ {file_artist} - {file_title}")
            else:
                print(f"⏭️  {file_artist} - {file_title} (OK)")
                
        except Exception as e:
            errors += 1
            print(f"❌ {filename}: {e}")

    print(f"\n✅ {updated} actualizados")
    print(f"⏭️  {skipped} omitidos")
    print(f"❌ {errors} errores")

if __name__ == "__main__":
    main()
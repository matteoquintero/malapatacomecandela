#!/usr/bin/env python3
"""Re-download thumbnails from YouTube and embed for modified files."""
import os
import subprocess
import sqlite3
import tempfile

DB = "/Users/matteoquintero/malapatacomecandela_system/cache/library.db"

def main():
    # Get tracks that likely had thumbnails (those we modified)
    patterns = [
        "Que Viva Chango", "Pop Corn", "Co Co", "tocoro", 
        "1999 - Remaster", "Erotic", "Lounge", "Karaoke",
        "a Mi", "por Que", "guaguanco", "Venga", "Better",
        "Montuno", "Outtake", "feat", "A Quien", "Que Te"
    ]
    
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT artist, title, video_id, filepath
            FROM tracks 
            WHERE filepath IS NOT NULL AND filepath != ''
        """)
        tracks = cur.fetchall()

    yt_dlp = "yt-dlp"
    count = 0
    found = 0
    
    for t in tracks:
        artist = t["artist"]
        title = t["title"]
        path = t["filepath"]
        video_id = t["video_id"]
        
        if not path or not os.path.exists(path):
            continue
        
        filename = os.path.basename(path).replace(".mp3", "")
        
        # Skip if already has correct format (not one we renamed)
        if " - " in filename and not any(p in filename for p in patterns):
            continue
        
        # Build query
        if video_id:
            query = f"https://youtube.com/watch?v={video_id}"
        else:
            query = f"{artist} {title}"
        
        print(f"🔍 {artist} - {title}")
        found += 1
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_file = os.path.join(tmpdir, "thumb")
            
            cmd = [
                yt_dlp,
                "--write-thumbnail", "only",
                "-o", temp_file,
                "--skip-download",
                query
            ]
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                        cwd=tmpdir)
                
                # Find the thumbnail
                thumb_found = False
                for f in os.listdir(tmpdir):
                    if f.endswith((".jpg", ".webp", ".png")):
                        thumb_path = os.path.join(tmpdir, f)
                        thumb_found = True
                        break
                
                if thumb_found:
                    # Embed using ffmpeg
                    temp_mp3 = path + ".tmp"
                    embed = [
                        "ffmpeg", "-y", "-i", path,
                        "-i", thumb_path,
                        "-map", "0:a", "-map", "1:v",
                        "-c:v", "copy", "-c:a", "copy",
                        "-id3v2_version", "3",
                        "-metadata:s:v", "title=Album Art",
                        "-metadata:s:v", "comment=Cover (front)",
                        temp_mp3
                    ]
                    
                    emb_res = subprocess.run(embed, capture_output=True, text=True)
                    
                    if emb_res.returncode == 0:
                        os.replace(temp_mp3, path)
                        count += 1
                        print(f"   ��� Embedido")
                    else:
                        if os.path.exists(temp_mp3):
                            os.remove(temp_mp3)
                        print(f"   ❌ FFmpeg error")
                else:
                    print(f"   ⚠️ No thumbnail found")
                    
            except Exception as e:
                print(f"   ❌ {e}")
        
        if found >= 30:  # Limit to 30 to start
            break
    
    print(f"\n✅ {count} thumbnails restaurados de {found} pistas")

if __name__ == "__main__":
    main()
import os
import re
import json
from flask import Flask, render_template, request, jsonify, Response
from yt_dlp import YoutubeDL

app = Flask(__name__)

# --- AUTOMATYCZNE TWORZENIE I WYKRYWANIE FOLDERU "SpotifyMe" W POBRANYCH ---
def get_spotifyme_folder():
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        downloads_dir = os.path.join(user_profile, "Downloads")
        if os.path.exists(downloads_dir):
            # Tworzymy ścieżkę do podfolderu SpotifyMe w Pobranych
            spotifyme_dir = os.path.join(downloads_dir, "SpotifyMe")
            # os.makedirs z parametrem exist_ok=True automatycznie utworzy folder 
            # tylko wtedy, gdy on jeszcze nie istnieje (nie dubluje go ani nie nadpisuje)
            os.makedirs(spotifyme_dir, exist_ok=True)
            return spotifyme_dir
            
    # Zapasowa ścieżka lokalna
    fallback_dir = os.path.join(os.getcwd(), "SpotifyMe")
    os.makedirs(fallback_dir, exist_ok=True)
    return fallback_dir

SPOTIFYME_DIR = get_spotifyme_folder()
progress_store = {}

@app.route('/')
def index():
    return render_template('index.html', logged_in=True, username="Tester")

def make_hook(download_id):
    def hook(d):
        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0%')
            clean_percent = re.sub(r'\x1b\[[0-9;]*m', '', percent_str).strip()
            match = re.search(r'([0-9]+(?:\.[0-9]+)?)', clean_percent)
            if match:
                try:
                    progress_store[download_id] = float(match.group(1))
                except ValueError:
                    pass
        elif d['status'] == 'finished':
            progress_store[download_id] = 100.0
    return hook

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
    download_id = data.get('download_id')
    
    if not url or not download_id:
        return jsonify({"error": "Brak linku lub ID!"}), 400

    try:
        progress_store[download_id] = 0.0
        
       # Określamy dokładną ścieżkę do folderu z aplikacją
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        cookies_path = os.path.join(BASE_DIR, 'cookies.txt')
        ffmpeg_path = os.path.join(BASE_DIR, 'ffmpeg')

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(SPOTIFYME_DIR, '%(title)s.%(ext)s'),
            'progress_hooks': [make_hook(download_id)],
            'nocheckcertificate': True,
            'cookiefile': cookies_path,        # <-- PEŁNA ŚCIEŻKA DO COOKIES
            'ffmpeg_location': ffmpeg_path,    # <-- PEŁNA ŚCIEŻKA DO FFMPEG
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise Exception("Nie udało się pobrać utworu.")
                
            progress_store[download_id] = 100.0
            return jsonify({"success": True})
            
    except Exception as e:
        progress_store[download_id] = -1.0
        return jsonify({"error": str(e)}), 500

@app.route('/progress/<download_id>')
def progress(download_id):
    def generate():
        while True:
            current_progress = progress_store.get(download_id, 0.0)
            yield f"data: {json.dumps({'progress': current_progress})}\n\n"
            if current_progress >= 100.0 or current_progress == -1.0:
                break
            import time
            time.sleep(0.3)
            
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(port=5000, debug=True)

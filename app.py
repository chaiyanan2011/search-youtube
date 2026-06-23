# app.py
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

@app.route('/search')
def search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'missing q'}), 400

    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'default_search': 'ytsearch15',
        'skip_download': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch15:{q}", download=False)
        results = []
        for entry in info.get('entries', []):
            results.append({
                'title': entry.get('title'),
                'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                'duration': entry.get('duration'),
                'channel': entry.get('channel') or entry.get('uploader'),
            })

    return jsonify({'results': results})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

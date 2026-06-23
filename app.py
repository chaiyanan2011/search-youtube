# app.py
from flask import Flask, request, jsonify
import requests, json, re, os, base64

app = Flask(__name__)

SPOTIFY_CLIENT_ID     = os.environ.get('SPOTIFY_CLIENT_ID', '70c31c779aa74d9a88ae0c176ad58bf4')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET', 'e9f387da33ab46b7a89db793536197b2')

YT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'th-TH,th;q=0.9,en;q=0.8',
}

# ---------- Spotify ----------
def get_spotify_token():
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    r = requests.post('https://accounts.spotify.com/api/token',
        headers={'Authorization': f'Basic {creds}'},
        data={'grant_type': 'client_credentials'}, timeout=10)
    return r.json().get('access_token')

def get_audio_features(title, artist, token):
    q = f"{title} {artist}".strip()
    r = requests.get('https://api.spotify.com/v1/search',
        headers={'Authorization': f'Bearer {token}'},
        params={'q': q, 'type': 'track', 'limit': 1}, timeout=10)
    items = r.json().get('tracks', {}).get('items', [])
    if not items:
        return None
    track_id = items[0]['id']
    r2 = requests.get(f'https://api.spotify.com/v1/audio-features/{track_id}',
        headers={'Authorization': f'Bearer {token}'}, timeout=10)
    f = r2.json()
    return {
        'energy':       f.get('energy', 0.5),
        'valence':      f.get('valence', 0.5),
        'danceability': f.get('danceability', 0.5),
        'tempo':        min(f.get('tempo', 120) / 200, 1.0),
        'acousticness': f.get('acousticness', 0.5),
        'instrumentalness': f.get('instrumentalness', 0),
    }

def similarity(a, b):
    if not a or not b:
        return 0
    keys = ['energy', 'valence', 'danceability', 'tempo', 'acousticness', 'instrumentalness']
    total = sum(1 - abs(a[k] - b[k]) for k in keys)
    return round((total / len(keys)) * 100, 1)

# ---------- YouTube ----------
def yt_search(q, limit=20):
    r = requests.get('https://www.youtube.com/results',
        params={'search_query': q, 'hl': 'th'},
        headers=YT_HEADERS, timeout=10)
    match = re.search(r'var ytInitialData\s*=\s*(\{.+?\});\s*</script>', r.text, re.DOTALL)
    if not match:
        return []
    data = json.loads(match.group(1))
    results = []
    try:
        contents = (data['contents']['twoColumnSearchResultsRenderer']
                    ['primaryContents']['sectionListRenderer']
                    ['contents'][0]['itemSectionRenderer']['contents'])
        for item in contents:
            if 'videoRenderer' not in item:
                continue
            v = item['videoRenderer']
            vid = v.get('videoId')
            if not vid:
                continue
            title   = v.get('title', {}).get('runs', [{}])[0].get('text', '')
            channel = (v.get('ownerText', {}).get('runs') or [{}])[0].get('text', '')
            dur     = v.get('lengthText', {}).get('simpleText', '')
            results.append({
                'title':   title,
                'channel': channel,
                'url':     f"https://www.youtube.com/watch?v={vid}",
                'videoId': vid,
                'duration': dur,
                'thumb':   f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            })
            if len(results) >= limit:
                break
    except:
        pass
    return results

# ---------- Routes ----------
@app.route('/search')
def search():
    q     = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)
    if not q:
        return jsonify({'error': 'missing q'}), 400
    results = yt_search(q, limit)
    return jsonify({'count': len(results), 'results': results})

@app.route('/autodj')
def autodj():
    """
    รับ seed=ชื่อเพลงตั้งต้น, limit=จำนวนเพลงใน queue
    วิเคราะห์ audio features แล้วเรียงเพลงตาม similarity
    """
    seed  = request.args.get('seed', '').strip()
    limit = min(int(request.args.get('limit', 10)), 20)
    if not seed:
        return jsonify({'error': 'missing seed'}), 400

    token = get_spotify_token()

    # หา features ของเพลงตั้งต้น
    seed_videos = yt_search(seed, 1)
    if not seed_videos:
        return jsonify({'error': 'seed not found'}), 404
    seed_video = seed_videos[0]
    seed_feat  = get_audio_features(seed_video['title'], seed_video['channel'], token)

    # ค้นหาเพลงที่เกี่ยวข้อง
    candidates = yt_search(seed, 30)

    # วิเคราะห์ similarity ทุกเพลง
    scored = []
    for v in candidates:
        feat = get_audio_features(v['title'], v['channel'], token)
        sim  = similarity(seed_feat, feat)
        scored.append({**v, 'features': feat, 'similarity': sim})

    # เรียงจากมากไปน้อย
    scored.sort(key=lambda x: x['similarity'], reverse=True)

    queue = scored[:limit]

    return jsonify({
        'seed': {**seed_video, 'features': seed_feat},
        'queue': queue
    })

@app.route('/ping')
def ping():
    return 'ok'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

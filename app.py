# app.py
from flask import Flask, request, jsonify
import requests, json, re, os, base64

app = Flask(__name__)

# นำ Client ID และ Client Secret ของจริงจาก Spotify Developer Dashboard มาใส่ตรงนี้
SPOTIFY_CLIENT_ID     = os.environ.get('SPOTIFY_CLIENT_ID', '70c31c779aa74d9a88ae0c176ad58bf4')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET', 'e9f387da33ab46b7a89db793536197b2')

YT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'th-TH,th;q=0.9,en;q=0.8',
}

# ---------- Spotify (Official API Server) ----------
def get_spotify_token():
    try:
        creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
        # เรียกไปยัง Endpoint ยืนยันตัวตนของ Spotify Accounts Service ของจริง
        r = requests.post('https://accounts.spotify.com/api/token',
            headers={'Authorization': f'Basic {creds}'},
            data={'grant_type': 'client_credentials'}, timeout=10)
        if r.status_code != 200:
            return None
        return r.json().get('access_token')
    except Exception:
        return None

def get_audio_features(title, artist, token):
    if not token:
        return None
        
    # ล้างข้อความพ่วงท้ายบน YouTube เช่น [Official MV], (Wake) ออก เพื่อให้ระบบของ Spotify หาเจอแม่นยำขึ้น
    clean_title = re.sub(r'\[.*?\]|\(.*?\)|- official.*|- MV.*', '', title, flags=re.IGNORECASE).strip()
    q = f"track:{clean_title} artist:{artist}".strip()
    
    try:
        # 1. ค้นหา ID เพลงบนระบบ Spotify API ของจริง
        r = requests.get('https://api.spotify.com/v1/search',
            headers={'Authorization': f'Bearer {token}'},
            params={'q': q, 'type': 'track', 'limit': 1}, timeout=10)
        
        if r.status_code != 200:
            return None
            
        data = r.json()
        items = data.get('tracks', {}).get('items', [])
        
        # หากไม่เจอแบบระบุชื่อศิลปิน ลองค้นหาด้วยชื่อเพลงอย่างเดียว (ช่วยกรณีที่ชื่อค่ายเพลงหรือชื่อช่อง YouTube ไม่ตรงกับชื่อศิลปินบน Spotify)
        if not items:
            r_retry = requests.get('https://api.spotify.com/v1/search',
                headers={'Authorization': f'Bearer {token}'},
                params={'q': clean_title, 'type': 'track', 'limit': 1}, timeout=10)
            items = r_retry.json().get('tracks', {}).get('items', []) if r_retry.status_code == 200 else []
            if not items:
                return None
            
        track_id = items[0]['id']
        
        # 2. นำ ID ไปดึงฟีเจอร์เสียง (Audio Features) จาก Spotify API ของจริง
        r2 = requests.get(f'https://api.spotify.com/v1/audio-features/{track_id}',
            headers={'Authorization': f'Bearer {token}'}, timeout=10)
            
        if r2.status_code != 200:
            return None
            
        f = r2.json()
        if not f:
            return None
            
        return {
            'energy':       f.get('energy', 0.5),
            'valence':      f.get('valence', 0.5),
            'danceability': f.get('danceability', 0.5),
            'tempo':        min(f.get('tempo', 120) / 200, 1.0),
            'acousticness': f.get('acousticness', 0.5),
            'instrumentalness': f.get('instrumentalness', 0),
        }
    except Exception:
        return None

def similarity(a, b):
    if not a or not b:
        return 0
    keys = ['energy', 'valence', 'danceability', 'tempo', 'acousticness', 'instrumentalness']
    total = sum(1 - abs(a[k] - b[k]) for k in keys)
    return round((total / len(keys)) * 100, 1)

# ---------- YouTube (ระบบดึงข้อมูลและค้นหาเดิม) ----------
def yt_search(q, limit=20):
    try:
        r = requests.get('https://www.youtube.com/results',
            params={'search_query': q, 'hl': 'th'},
            headers=YT_HEADERS, timeout=10)
        match = re.search(r'var ytInitialData\s*=\s*(\{.+?\});\s*</script>', r.text, re.DOTALL)
        if not match:
            return []
        data = json.loads(match.group(1))
        results = []
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
    except Exception:
        return []
    return results

# ---------- Routes (ระบบ Route เดิมอยู่ครบถ้วน) ----------

# 1. ระบบค้นหาเพลงเดิม (/search)
@app.route('/search')
def search():
    q     = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)
    if not q:
        return jsonify({'error': 'missing q'}), 400
    results = yt_search(q, limit)
    return jsonify({'count': len(results), 'results': results})

# 2. ระบบจัดคิวอัจฉริยะเดิม (/autodj)
@app.route('/autodj')
def autodj():
    seed  = request.args.get('seed', '').strip()
    limit = min(int(request.args.get('limit', 10)), 20)
    if not seed:
        return jsonify({'error': 'missing seed'}), 400

    token = get_spotify_token()
    if not token:
        return jsonify({'error': 'unable to authenticate with official spotify server'}), 500

    # หาเพลงตั้งต้นจาก YouTube
    seed_videos = yt_search(seed, 1)
    if not seed_videos:
        return jsonify({'error': 'seed not found on youtube'}), 404
    seed_video = seed_videos[0]
    seed_feat  = get_audio_features(seed_video['title'], seed_video['channel'], token)

    # ค้นหาเพลงที่เกี่ยวข้องจาก YouTube มาคัดเลือก
    candidates = yt_search(seed, 30)

    # ค่าฟีเจอร์เสียงเริ่มต้น (กรณีที่ Spotify ค้นหาบางคลิปบน YouTube ไม่เจอ)
    default_feat = {
        'energy': 0.5, 'valence': 0.5, 'danceability': 0.5, 
        'tempo': 0.6, 'acousticness': 0.5, 'instrumentalness': 0
    }
    current_seed_feat = seed_feat if seed_feat is not None else default_feat

    # วิเคราะห์ความเหมือน (Similarity) ทุกเพลง
    scored = []
    for v in candidates:
        feat = get_audio_features(v['title'], v['channel'], token)
        
        # ป้องกันคิวว่าง: หาก Spotify ไม่มีข้อมูลเพลงนั้น ให้ใช้ค่า Default ไปคำนวณความคล้าย
        display_feat = feat if feat is not None else default_feat
        sim = similarity(current_seed_feat, display_feat)
        
        scored.append({**v, 'features': feat, 'similarity': sim})

    # เรียงลำดับจากมากไปน้อยตามความเหมือนของแนวเพลง
    scored.sort(key=lambda x: x['similarity'], reverse=True)
    queue = scored[:limit]

    return jsonify({
        'seed': {**seed_video, 'features': seed_feat},
        'queue': queue
    })

# 3. ระบบทดสอบเซิร์ฟเวอร์เดิม (/ping)
@app.route('/ping')
def ping():
    return 'ok'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

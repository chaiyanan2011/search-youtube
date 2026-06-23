# app.py
from flask import Flask, request, jsonify
import requests, json, re

app = Flask(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'th-TH,th;q=0.9,en;q=0.8',
}

def parse_duration(d):
    if not d: return None
    parts = d.split(':')
    try:
        if len(parts) == 2: return int(parts[0])*60 + int(parts[1])
        if len(parts) == 3: return int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
    except: return None

def extract_videos(data, limit):
    results = []
    try:
        contents = (
            data['contents']['twoColumnSearchResultsRenderer']
               ['primaryContents']['sectionListRenderer']
               ['contents'][0]['itemSectionRenderer']['contents']
        )
        for item in contents:
            if 'videoRenderer' not in item: continue
            v = item['videoRenderer']
            vid = v.get('videoId')
            if not vid: continue
            title = v.get('title', {}).get('runs', [{}])[0].get('text', '')
            channel = (v.get('ownerText', {}).get('runs') or [{}])[0].get('text', '')
            dur_text = v.get('lengthText', {}).get('simpleText', '')
            views = v.get('viewCountText', {}).get('simpleText', '')
            thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            results.append({
                'title':    title,
                'url':      f"https://www.youtube.com/watch?v={vid}",
                'videoId':  vid,
                'channel':  channel,
                'duration': dur_text,
                'views':    views,
                'thumb':    thumb,
            })
            if len(results) >= limit: break
    except: pass
    return results

@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 30)), 50)
    if not q:
        return jsonify({'error': 'missing q'}), 400

    try:
        res = requests.get(
            'https://www.youtube.com/results',
            params={'search_query': q, 'hl': 'th'},
            headers=HEADERS,
            timeout=10
        )
        # ดึง ytInitialData JSON จากใน HTML
        match = re.search(r'var ytInitialData\s*=\s*(\{.+?\});\s*</script>', res.text, re.DOTALL)
        if not match:
            return jsonify({'error': 'parse failed'}), 500

        data = json.loads(match.group(1))
        results = extract_videos(data, limit)
        return jsonify({'count': len(results), 'results': results})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ping')
def ping():
    return 'ok'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

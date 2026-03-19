#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""국민 생활위험 코파일럿 — 재난안전 통합 정보 시스템"""

from flask import Flask, render_template, request, jsonify
from datetime import datetime
from math import radians, sin, cos, sqrt, asin
import requests
import urllib3
import time
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SAFETY_BASE = "https://www.safetydata.go.kr"

API_CONFIG = {
    'disaster_msg': {
        'url': f"{SAFETY_BASE}/V2/api/DSSP-IF-00247",
        'key': os.getenv('DISASTER_MSG_KEY', '9IXVJI4Q4RVUKL4X'),
        'name': '긴급재난문자',
    },
    'shelter': {
        'url': f"{SAFETY_BASE}/V2/api/DSSP-IF-10942",
        'key': os.getenv('SHELTER_KEY', '4T3NV3L5BG717UM0'),
        'name': '무더위쉼터',
    },
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cache & Session
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_CACHE = {}
CACHE_TTL = 60
_SESSION = requests.Session()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Utility
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def haversine_km(lat1, lon1, lat2, lon2):
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (ValueError, TypeError):
        return None
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * asin(min(1, sqrt(a)))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Fetcher
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _fetch_api(api_name, extra_params=None, page=1, rows=10):
    """재난안전데이터 공유플랫폼 API 호출 (캐시 포함)"""
    config = API_CONFIG.get(api_name)
    if not config:
        return {'error': f'Unknown API: {api_name}'}

    params = {
        'serviceKey': config['key'],
        'returnType': 'json',
        'pageNo': str(page),
        'numOfRows': str(rows),
    }
    if extra_params:
        params.update(extra_params)

    cache_key = (api_name, tuple(sorted(params.items())))
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and (now - cached[0]) < CACHE_TTL:
        return cached[1]

    try:
        r = _SESSION.get(config['url'], params=params, timeout=15, verify=False)
        r.raise_for_status()
        data = r.json()
        _CACHE[cache_key] = (now, data)
        return data
    except requests.exceptions.Timeout:
        return {'error': 'API 요청 시간 초과'}
    except requests.exceptions.ConnectionError:
        return {'error': 'API 서버 연결 실패'}
    except Exception as e:
        return {'error': str(e)}


def parse_response(data):
    """safetydata.go.kr 응답에서 items, totalCount, error 추출"""
    if isinstance(data, dict):
        if 'error' in data:
            return [], 0, data['error']
        body = data.get('body', [])
        total = data.get('totalCount', 0)
        if isinstance(body, list):
            return body, int(total) if total else len(body), None
        if isinstance(body, dict):
            items = body.get('dataArray', body.get('items', []))
            total = body.get('totalCount', total)
            return items if isinstance(items, list) else [], int(total) if total else 0, None
    return [], 0, '예상하지 못한 응답 형식'


def _fetch_disaster_newest(page=1, rows=20):
    """재난문자를 최신순(내림차순)으로 가져오기.
    API는 오름차순(오래된순)이므로 역순 페이지네이션 적용."""
    count_data = _fetch_api('disaster_msg', rows=1)
    _, total, err = parse_response(count_data)
    if err or total == 0:
        return [], total, err

    total_pages = max(1, (total + rows - 1) // rows)
    # 사용자의 1페이지 = API의 마지막 페이지
    api_page = total_pages - (page - 1)
    if api_page < 1:
        return [], total, None

    data = _fetch_api('disaster_msg', page=api_page, rows=rows)
    messages, _, error = parse_response(data)
    messages.reverse()
    return messages, total, error


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Routes — Pages
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.route('/')
def index():
    """메인 — 지도 중심 대시보드"""
    messages, msg_total, msg_error = _fetch_disaster_newest(page=1, rows=8)

    shelter_data = _fetch_api('shelter', rows=1)
    _, shelter_total, shelter_error = parse_response(shelter_data)

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render_template('index.html',
                           messages=messages,
                           msg_total=msg_total,
                           msg_error=msg_error,
                           shelter_total=shelter_total,
                           shelter_error=shelter_error,
                           server_time=now,
                           active_tab='home')


@app.route('/disaster')
def disaster():
    """긴급재난문자 목록 — 최신순"""
    page = max(1, int(request.args.get('page', 1)))
    rows = min(100, max(1, int(request.args.get('rows', 20))))

    messages, total, error = _fetch_disaster_newest(page=page, rows=rows)
    total_pages = max(1, (total + rows - 1) // rows) if total > 0 else 1

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render_template('disaster.html',
                           messages=messages,
                           total=total,
                           error=error,
                           page=page,
                           rows=rows,
                           total_pages=total_pages,
                           server_time=now,
                           active_tab='disaster')


@app.route('/shelters')
def shelters():
    """무더위쉼터 조회 — 위치 기반 필터 지원"""
    page = max(1, int(request.args.get('page', 1)))
    rows = min(200, max(1, int(request.args.get('rows', 50))))

    extra = {}
    lat = request.args.get('lat', '')
    lon = request.args.get('lon', '')

    if lat and lon:
        try:
            lat_f, lon_f = float(lat), float(lon)
            extra['startLat'] = str(round(lat_f - 0.045, 6))
            extra['endLat'] = str(round(lat_f + 0.045, 6))
            extra['startLot'] = str(round(lon_f - 0.055, 6))
            extra['endLot'] = str(round(lon_f + 0.055, 6))
        except ValueError:
            lat, lon = '', ''

    data = _fetch_api('shelter', extra_params=extra if extra else None, page=page, rows=rows)
    items, total, error = parse_response(data)

    if lat and lon:
        for it in items:
            it_lat = it.get('LA') or it.get('YCORD', '')
            it_lon = it.get('LO') or it.get('XCORD', '')
            d = haversine_km(lat, lon, it_lat, it_lon)
            it['_distance'] = round(d, 2) if d is not None else None
        items.sort(key=lambda x: x.get('_distance') if x.get('_distance') is not None else 1e9)

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    total_pages = max(1, (total + rows - 1) // rows) if total > 0 else 1

    return render_template('shelters.html',
                           items=items,
                           total=total,
                           error=error,
                           page=page,
                           rows=rows,
                           total_pages=total_pages,
                           server_time=now,
                           lat=lat,
                           lon=lon,
                           active_tab='shelters')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Routes — JSON API (AJAX)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.route('/api/disaster')
def api_disaster():
    page = max(1, int(request.args.get('page', 1)))
    rows = min(100, max(1, int(request.args.get('rows', 20))))
    messages, total, error = _fetch_disaster_newest(page=page, rows=rows)
    return jsonify({'body': messages, 'totalCount': total, 'error': error})


@app.route('/api/shelters')
def api_shelters():
    page = max(1, int(request.args.get('page', 1)))
    rows = min(200, max(1, int(request.args.get('rows', 50))))
    extra = {}
    for k in ('startLat', 'endLat', 'startLot', 'endLot'):
        v = request.args.get(k)
        if v:
            extra[k] = v
    data = _fetch_api('shelter', extra_params=extra if extra else None, page=page, rows=rows)
    return jsonify(data)


@app.route('/api/debug/<api_name>')
def api_debug(api_name):
    """디버그용 — API 원본 응답 확인"""
    if api_name not in API_CONFIG:
        return jsonify({'error': 'Unknown API'}), 404
    data = _fetch_api(api_name, rows=3)
    return jsonify(data)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Run
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)

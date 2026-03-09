#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, Response
import json
from markupsafe import Markup
import os
import os.path
import xml.etree.ElementTree as ET
import requests
import time
import html as _html
from functools import lru_cache

app = Flask(__name__)

API_URL = 'http://apis.data.go.kr/B552657/ErmctInfoInqireService/getEmrrmRltmUsefulSckbdInfoInqire'
BASIC_INFO_URL = 'http://apis.data.go.kr/B552657/ErmctInfoInqireService/getEgytListInfoInqire'
DEFAULT_KEY = os.getenv('DATA_GO_KR_KEY', '82b5509f3ea200886192a50569efc50b480eda4a1458cd22349634edcc3bfbb0')
CACHE_TTL = int(os.getenv('CACHE_TTL', '20'))  # seconds
BASIC_INFO_TTL = 600  # 10 minutes — basic info changes rarely

# simple in-memory cache: key -> (timestamp, items, raw_xml)
_CACHE = {}
# basic info cache: hpid -> {dutyaddr, wgs84lat, wgs84lon, dutyname, ...}
_BASIC_INFO_CACHE = {}  # hpid -> dict
_BASIC_INFO_TS = {}     # region_key -> timestamp

# store last seen per hospital to detect changes: hpid -> {'hvec':int,'hvgc':int,'ts':timestamp}
LAST_SEEN = {}

# requests session for connection reuse
_SESSION = requests.Session()

KNOWN_FIELDS = [
    'rnum','hpid','phpid','hvidate','hvec','hvoc','hvcc','hvncc','hvccc','hvicc',
    'hvgc','hvdnm','hvctayn','hvmriayn','hvangioayn','hvventiayn','hvamyn','hv1',
    'hv2','hv3','hv4','hv5','hv6','hv7','hv8','hv9','hv10','hv11','hv12',
    'dutyname','dutytel3','dutyAddr','wgs84Lat','wgs84Lon'
]

# department label mapping (keys are lowercase)
DEPT_LABELS = {
    'hv2': '내과중환자실',
    'hv3': '외과중환자실',
    'hv4': '외과입원실(정형외과)',
    'hv5': '신경과입원실',
    'hv6': '신경외과중환자실',
    'hv7': '약물중환자',
    'hv8': '화상중환자',
    'hv9': '외상중환자',
    'hv10': 'VENTI(소아)',
    'hv11': '인큐베이터(보육기)'
}

NUMERIC_FIELDS = set(['hvec','hvoc','hvcc','hvncc','hvccc','hvicc','hvgc'] + list(DEPT_LABELS.keys()))

# Human-readable labels for ALL known API fields
FIELD_LABELS = {
    'rnum': '순번',
    'hpid': '기관코드',
    'phpid': '기관코드(구)',
    'hvidate': '데이터 기준일시',
    'hvidate_fmt': '최근 갱신 시각',
    'hvec': '응급실 가용 병상',
    'hvoc': '수술실 가용',
    'hvcc': '신경외과 중환자실',
    'hvncc': '신생아 중환자실',
    'hvccc': '흉부외과 중환자실',
    'hvicc': '일반 중환자실',
    'hvgc': '입원실 가용 병상',
    'hvdnm': '당직의 이름',
    'hvctayn': 'CT 보유',
    'hvmriayn': 'MRI 보유',
    'hvangioayn': '혈관촬영기 보유',
    'hvventiayn': '인공호흡기 보유',
    'hvamyn': '구급차 가용',
    'hv1': '소아 중환자실',
    'hv2': '내과 중환자실',
    'hv3': '외과 중환자실',
    'hv4': '정형외과 입원실',
    'hv5': '신경과 입원실',
    'hv6': '신경외과 중환자실',
    'hv7': '약물 중환자',
    'hv8': '화상 중환자',
    'hv9': '외상 중환자',
    'hv10': '소아 VENTI',
    'hv11': '인큐베이터(보육기)',
    'hv12': '소아당직의 직통 연락처',
    'hv17': '소아 음압 격리',
    'hv18': '음압 격리',
    'hv28': '외상소생실',
    'hv29': '소아 전용 입원실',
    'hv30': 'CRRT(소아)',
    'hv31': 'ECMO(소아)',
    'hv36': '일반 입원실(격리)',
    'hv42': '코호트 격리',
    'hvcrrtayn': 'CRRT 장비 보유',
    'hvecmoayn': 'ECMO 장비 보유',
    'hvhypoayn': '저체온요법 장비 보유',
    'hvincuayn': '인큐베이터 보유',
    'hvoxyayn': '고압산소치료기 보유',
    'hvventisoayn': '소아인공호흡기 보유',
    'dutyname': '기관명',
    'dutytel3': '응급실 전화번호',
    'dutyaddr': '주소',
    'wgs84lat': '위도',
    'wgs84lon': '경도',
    # hvs series — specialty availability counts
    'hvs01': '뇌출혈수술',
    'hvs02': '뇌경색 재관류',
    'hvs03': '심근경색 재관류',
    'hvs04': '복부손상 수술',
    'hvs05': '사지접합 수술',
    'hvs06': '응급내시경',
    'hvs07': '응급투석',
    'hvs08': '조산산모',
    'hvs09': '정신질환자',
    'hvs10': '신생아',
    'hvs11': '중증화상',
    'hvs19': '산부인과',
    'hvs22': '정형외과',
    'hvs26': '영상의학 해독 전문의',
    'hvs27': '소아 전용 중환자실 당직의',
    'hvs28': '소아 수술',
    'hvs29': '영상 중재 시술',
    'hvs30': '마취과',
    'hvs31': '일반외과',
    'hvs32': '정형외과',
    'hvs33': '신경외과',
    'hvs34': '흉부외과',
    'hvs35': '안과',
    'hvs37': '응급의학과',
    'hvs38': '입원실(일반)',
    'hvs50': '음압격리 진료',
    'hvs51': '감염 중환자 격리 병상',
}

# Fields to show in the "equipment" section
EQUIP_FIELDS = ['hvctayn','hvmriayn','hvangioayn','hvventiayn','hvamyn',
                'hvcrrtayn','hvecmoayn','hvhypoayn','hvincuayn','hvoxyayn','hvventisoayn']

# Fields to show in the "specialty beds" section
BED_FIELDS = ['hvec','hvgc','hvoc','hvcc','hvncc','hvccc','hvicc',
              'hv1','hv2','hv3','hv4','hv5','hv6','hv7','hv8','hv9','hv10','hv11',
              'hv17','hv18','hv28','hv29','hv30','hv31','hv36','hv42']

# Fields for specialty availability (hvs series)
SPEC_FIELDS = ['hvs01','hvs02','hvs03','hvs04','hvs05','hvs06','hvs07','hvs08',
               'hvs19','hvs22','hvs26','hvs27','hvs28','hvs29','hvs30','hvs31',
               'hvs32','hvs33','hvs34','hvs35','hvs37','hvs38','hvs50','hvs51']


def fetch_basic_info(sido=None, sigungu=None, numOfRows=500, timeout=15.0):
    """Fetch hospital basic info (address, coordinates) from the list API.
    Results are cached for BASIC_INFO_TTL seconds per region."""
    region_key = (sido or '', sigungu or '')
    now = time.time()
    ts = _BASIC_INFO_TS.get(region_key, 0)
    if now - ts < BASIC_INFO_TTL:
        return  # already fresh

    params = {
        'serviceKey': DEFAULT_KEY,
        'pageNo': '1',
        'numOfRows': str(numOfRows),
        '_type': 'xml',
    }
    if sido:
        params['Q0'] = sido
    if sigungu:
        params['Q1'] = sigungu
    try:
        r = _SESSION.get(BASIC_INFO_URL, params=params, timeout=timeout)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for it in root.findall('.//item'):
            obj = {}
            for child in it:
                tag = child.tag.split('}')[-1].lower()
                obj[tag] = (child.text or '').strip()
            hpid = obj.get('hpid', '')
            if not hpid:
                continue
            # decode strings
            for k, v in list(obj.items()):
                if isinstance(v, str) and v:
                    try:
                        obj[k] = _html.unescape(v)
                    except Exception:
                        pass
            _BASIC_INFO_CACHE[hpid] = obj
        _BASIC_INFO_TS[region_key] = now
    except Exception:
        pass  # non-critical — page still works without it


def merge_basic_info(items):
    """Merge address / coordinates from basic info cache into real-time items."""
    for it in items:
        hpid = it.get('hpid', '')
        info = _BASIC_INFO_CACHE.get(hpid)
        if not info:
            continue
        # fill missing address
        if not it.get('dutyaddr') or it['dutyaddr'].strip() == '':
            it['dutyaddr'] = info.get('dutyaddr', '') or info.get('dutyaddr1', '')
        # fill missing coordinates
        if not it.get('wgs84lat') or it['wgs84lat'].strip() == '':
            it['wgs84lat'] = info.get('wgs84lat', '') or info.get('latitude', '')
        if not it.get('wgs84lon') or it['wgs84lon'].strip() == '':
            it['wgs84lon'] = info.get('wgs84lon', '') or info.get('longitude', '')
        # fill missing name if needed
        if not it.get('dutyname') or it['dutyname'].strip() == '':
            it['dutyname'] = info.get('dutyname', '')


def build_params(sido=None, sigungu=None, pageNo=1, numOfRows=100):
    p = {
        'serviceKey': DEFAULT_KEY,
        'pageNo': str(pageNo),
        'numOfRows': str(numOfRows),
        '_type': 'xml'
    }
    if sido:
        p['STAGE1'] = sido
    if sigungu:
        p['STAGE2'] = sigungu
    return p


def haversine_km(lat1, lon1, lat2, lon2):
    # simple haversine formula (returns kilometers)
    from math import radians, sin, cos, sqrt, asin
    try:
        lat1 = float(lat1); lon1 = float(lon1); lat2 = float(lat2); lon2 = float(lon2)
    except Exception:
        return None
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(min(1, sqrt(a)))
    return R * c


def format_hvidate(s):
    # API gives YYYYMMDDhhmmss like 20260309153705
    if not s:
        return ''
    try:
        from datetime import datetime
        dt = datetime.strptime(s[:14], '%Y%m%d%H%M%S')
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return s


def fetch_items(sido=None, sigungu=None, pageNo=1, numOfRows=100, timeout=15.0):
    params = build_params(sido, sigungu, pageNo, numOfRows)
    # cache key by params that matter
    cache_key = (params.get('STAGE1',''), params.get('STAGE2',''), params.get('pageNo','1'), params.get('numOfRows','100'))
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached:
        ts, items_cached, raw_cached = cached
        if now - ts < CACHE_TTL:
            return items_cached, raw_cached

    r = _SESSION.get(API_URL, params=params, timeout=timeout)
    r.raise_for_status()
    txt = r.text
    root = ET.fromstring(txt)
    items = []
    for it in root.findall('.//item'):
        obj = {}
        # collect all child elements into a dict using lowercase local-names
        for child in it:
            tag = child.tag
            local = tag.split('}')[-1].lower()
            obj[local] = child.text.strip() if child is not None and child.text else ''
        # also include deeper nested elements if any
        for child in it.findall('.//*'):
            tag = child.tag
            local = tag.split('}')[-1].lower()
            if local not in obj or not obj[local]:
                obj[local] = child.text.strip() if child is not None and child.text else obj.get(local, '')

        # ensure known fields exist (lowercase keys)
        normalized = {}
        for k in KNOWN_FIELDS:
            normalized[k.lower()] = obj.get(k.lower(), '')
        # keep also any extra keys found
        for k, v in obj.items():
            if k not in normalized:
                normalized[k] = v

        # normalize coordinate keys
        if not normalized.get('wgs84lat'):
            for cand in ('latitude', 'lat'):
                if obj.get(cand):
                    normalized['wgs84lat'] = obj.get(cand)
                    break
        if not normalized.get('wgs84lon'):
            for cand in ('longitude', 'lon'):
                if obj.get(cand):
                    normalized['wgs84lon'] = obj.get(cand)
                    break

        # convert numeric fields to ints where possible
        for k in list(normalized.keys()):
            if k in NUMERIC_FIELDS and normalized.get(k):
                try:
                    iv = int(normalized[k])
                    # API may use negative numbers for special codes; treat negatives as missing
                    if iv < 0:
                        normalized[k] = None
                    else:
                        normalized[k] = iv
                except Exception:
                    # keep raw if cannot convert
                    pass

        # normalize equipment flags to uppercase Y/N or empty
        for eq in ('hvctayn','hvmriayn','hvangioayn','hvventiayn','hvamyn'):
            if eq in normalized and isinstance(normalized[eq], str):
                normalized[eq] = normalized[eq].upper()

        # decode HTML entities and unicode-escape sequences in string fields
        for k, v in list(normalized.items()):
            if isinstance(v, str) and v:
                try:
                    # unescape HTML entities first
                    vv = _html.unescape(v)
                    # if contains literal backslash-u sequences, decode them
                    if '\\u' in vv or '\\x' in vv:
                        try:
                            vv2 = vv.encode('utf-8').decode('unicode_escape')
                            vv = vv2
                        except Exception:
                            pass
                    normalized[k] = vv
                except Exception:
                    pass

        items.append(normalized)
    # detect changes vs LAST_SEEN and attach small diff metadata
    for it in items:
        hpid = it.get('hpid') or it.get('dutyname')
        prev = LAST_SEEN.get(hpid)
        # format hvidate
        it['hvidate_fmt'] = format_hvidate(it.get('hvidate') or '')
        # record previous values if any
        try:
            cur_hvgc = it.get('hvgc') if isinstance(it.get('hvgc'), int) else (int(it.get('hvgc')) if it.get('hvgc') else None)
        except Exception:
            cur_hvgc = None
        try:
            cur_hvec = it.get('hvec') if isinstance(it.get('hvec'), int) else (int(it.get('hvec')) if it.get('hvec') else None)
        except Exception:
            cur_hvec = None

        if prev:
            # detect change
            changes = {}
            if prev.get('hvgc') is not None and cur_hvgc is not None and prev.get('hvgc') != cur_hvgc:
                changes['hvgc'] = (prev.get('hvgc'), cur_hvgc)
            if prev.get('hvec') is not None and cur_hvec is not None and prev.get('hvec') != cur_hvec:
                changes['hvec'] = (prev.get('hvec'), cur_hvec)
            if changes:
                it['changes'] = changes
                it['last_seen_ts'] = prev.get('ts')
        else:
            it['changes'] = {}
            it['last_seen_ts'] = None

        # update LAST_SEEN
        LAST_SEEN[hpid] = {'hvgc': cur_hvgc, 'hvec': cur_hvec, 'ts': now}

    # store in cache
    _CACHE[cache_key] = (now, items, txt)
    return items, txt


@app.route('/')
def index():
    sido = request.args.get('sido', '')
    sigungu = request.args.get('sigungu', '')
    num = int(request.args.get('numOfRows', 50))
    user_lat_raw = request.args.get('lat')
    user_lon_raw = request.args.get('lon')
    user_lat = None
    user_lon = None
    try:
        if user_lat_raw:
            user_lat = float(user_lat_raw)
        if user_lon_raw:
            user_lon = float(user_lon_raw)
    except Exception:
        user_lat = None
        user_lon = None
    dept = request.args.get('dept','').strip()
    only_admit = request.args.get('only_admit', '') in ('1', 'true', 'on', 'yes')
    items, raw = [], ''
    error = None
    try:
        # fetch basic info first (address/coords) — cached for 10 min
        fetch_basic_info(sido or None, sigungu or None)
        items, raw = fetch_items(sido or None, sigungu or None, 1, num)
        # merge address / coordinates from basic info
        merge_basic_info(items)
    except Exception as e:
        error = str(e)

    # compute availability flags per item
    for it in items:
        # admission availability: 입원실 (hvgc) > 0 considered available
        try:
            hvgc = it.get('hvgc')
            it['admission_available'] = isinstance(hvgc, int) and hvgc > 0
        except Exception:
            it['admission_available'] = False
        # ER availability: 응급실 (hvec) > 0
        try:
            hvec = it.get('hvec')
            it['er_available'] = isinstance(hvec, int) and hvec > 0
        except Exception:
            it['er_available'] = False

        # compute distance if user location provided and hospital coords available
        try:
            lat = it.get('wgs84lat') or it.get('latitude') or it.get('lat')
            lon = it.get('wgs84lon') or it.get('longitude') or it.get('lon')
            if user_lat is not None and user_lon is not None and lat and lon:
                try:
                    d = haversine_km(user_lat, user_lon, float(lat), float(lon))
                    it['distance_km'] = round(d, 2) if d is not None else None
                except Exception:
                    it['distance_km'] = None
            else:
                it['distance_km'] = None
        except Exception:
            it['distance_km'] = None

    # optional filter: only show hospitals with admission available
    if only_admit:
        items = [it for it in items if it.get('admission_available')]

    # optional department filter (simple substring match across key fields)
    if dept:
        q = dept.lower()
        def match_dept(it):
            for k in ('dutyname','dutyaddr','dutytel3'):
                v = it.get(k)
                if isinstance(v, str) and q in v.lower():
                    return True
            # also scan all string fields
            for k, v in it.items():
                if isinstance(v, str) and q in v.lower():
                    return True
            return False
        items = [it for it in items if match_dept(it)]

    # sort: admission-available first
    # if user location provided, sort by distance first then admission availability
    if user_lat is not None and user_lon is not None:
        items.sort(key=lambda x: (not bool(x.get('admission_available')), x.get('distance_km') if x.get('distance_km') is not None else 1e9))
    else:
        items.sort(key=lambda x: (not bool(x.get('admission_available')),))

    # build map if coordinates exist
    map_html = ''
    try:
        coords = []
        for i in items:
            lat = i.get('wgs84lat') or i.get('latitude') or i.get('lat')
            lon = i.get('wgs84lon') or i.get('longitude') or i.get('lon')
            if lat and lon:
                try:
                    coords.append((float(lat), float(lon)))
                except Exception:
                    continue
    except Exception:
        coords = []

    # generate map only when coordinates exist and result set is reasonably small
    if coords and len(coords) <= 200:
        try:
            import folium
            avg_lat = sum(lat for lat,lon in coords)/len(coords)
            avg_lon = sum(lon for lat,lon in coords)/len(coords)
            m = folium.Map(location=[avg_lat, avg_lon], zoom_start=11)
            for it in items:
                try:
                    lat_key = it.get('wgs84lat') or it.get('latitude') or it.get('lat')
                    lon_key = it.get('wgs84lon') or it.get('longitude') or it.get('lon')
                    if lat_key and lon_key:
                        lat = float(lat_key)
                        lon = float(lon_key)
                        popup = f"{it.get('dutyname','') }<br/>{it.get('dutytel3','') }"
                        folium.Marker([lat, lon], popup=popup).add_to(m)
                except Exception:
                    continue
            map_html = m._repr_html_()
        except Exception:
            map_html = ''
    else:
        map_html = ''

    from datetime import datetime
    server_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return render_template('index.html', items=items, map_html=Markup(map_html),
                           sido=sido, sigungu=sigungu, num=num, error=error,
                           dept_labels=DEPT_LABELS, field_labels=FIELD_LABELS,
                           equip_fields=EQUIP_FIELDS, bed_fields=BED_FIELDS,
                           spec_fields=SPEC_FIELDS, server_time=server_time)


@app.route('/debug')
def debug_items():
    """Return raw JSON of fetched items for debugging (no template)."""
    sido = request.args.get('sido', '') or None
    sigungu = request.args.get('sigungu', '') or None
    num = int(request.args.get('numOfRows', 50))
    try:
        items, raw = fetch_items(sido, sigungu, 1, num)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    # if pretty=1 requested, return HTML-pretty JSON for browser
    if request.args.get('pretty') in ('1', 'true', 'on'):
        pretty = json.dumps({'count': len(items), 'items': items}, ensure_ascii=False, indent=2)
        return Response(f"<pre style='white-space:pre-wrap'>{pretty}</pre>", mimetype='text/html; charset=utf-8')
    return jsonify({'count': len(items), 'items': items})


@app.route('/export.csv')
def export_csv():
    from io import StringIO
    import csv
    sido = request.args.get('sido', '') or None
    sigungu = request.args.get('sigungu', '') or None
    num = int(request.args.get('numOfRows', 50))
    try:
        items, raw = fetch_items(sido, sigungu, 1, num)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    si = StringIO()
    # determine columns (common ones)
    cols = ['dutyname','dutyaddr','dutytel3','hvec','hvgc','hvctayn','hvmriayn']
    writer = csv.writer(si)
    writer.writerow(cols)
    for it in items:
        row = [it.get(c,'') for c in cols]
        writer.writerow(row)
    output = si.getvalue()
    return Response(output, mimetype='text/csv; charset=utf-8', headers={"Content-Disposition":"attachment; filename=er_beds.csv"})


def score_and_reason(it, user_lat=None, user_lon=None):
    """Deterministic scoring fallback used when no LLM key is available.
    Returns (score:int, reason:str)."""
    score = 0
    reasons = []
    # admission available is highest priority
    if it.get('admission_available'):
        score += 50
        reasons.append('입원실 여유 있음')
    # ER availability next
    if it.get('er_available'):
        score += 25
        reasons.append('응급실 여유 있음')
    # equipment
    if it.get('hvctayn') == 'Y':
        score += 8
        reasons.append('CT 보유')
    if it.get('hvmriayn') == 'Y':
        score += 7
        reasons.append('MRI 보유')
    # distance penalty
    try:
        if user_lat and user_lon and it.get('distance_km') is not None:
            d = float(it.get('distance_km'))
            # nearer hospitals get bonus up to +20 (very near)
            dist_bonus = max(0, 20 - min(20, d))
            score += int(dist_bonus)
            reasons.append(f'거리: {d}km')
    except Exception:
        pass
    # normalize and produce readable reason
    reason = '; '.join(reasons) if reasons else '기준에 따름'
    return score, reason


@app.route('/ai/query', methods=['GET','POST'])
def ai_query():
    """Return an AI-assisted recommendation JSON for current items.
    If OPENAI_API_KEY is set, this can be extended to call the LLM.
    For now we implement a safe deterministic fallback ranking suited for emergencies.
    """
    sido = request.values.get('sido', '') or None
    sigungu = request.values.get('sigungu', '') or None
    num = min(200, int(request.values.get('numOfRows', 100)))
    user_lat = request.values.get('lat')
    user_lon = request.values.get('lon')
    dept = request.values.get('dept','').strip()

    try:
        items, raw = fetch_items(sido, sigungu, 1, num)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # compute distances if coords exist
    for it in items:
        try:
            lat = it.get('wgs84lat') or it.get('latitude') or it.get('lat')
            lon = it.get('wgs84lon') or it.get('longitude') or it.get('lon')
            if user_lat and user_lon and lat and lon:
                d = haversine_km(user_lat, user_lon, lat, lon)
                it['distance_km'] = round(d, 2) if d is not None else None
            else:
                it['distance_km'] = None
        except Exception:
            it['distance_km'] = None

    # optional department filter
    if dept:
        q = dept.lower()
        def match_dept(it):
            for k, v in it.items():
                if isinstance(v, str) and q in v.lower():
                    return True
            return False
        items = [it for it in items if match_dept(it)]

    # prepare scored list
    scored = []
    for it in items:
        sc, reason = score_and_reason(it, user_lat, user_lon)
        scored.append({'hpid': it.get('hpid') or it.get('dutyname'),
                       'dutyname': it.get('dutyname',''),
                       'distance_km': it.get('distance_km'),
                       'hvec': it.get('hvec'),
                       'hvgc': it.get('hvgc'),
                       'dutytel3': it.get('dutytel3',''),
                       'score': sc,
                       'reason': reason})

    # sort by score desc then distance asc
    scored.sort(key=lambda x: (-x.get('score',0), x.get('distance_km') if x.get('distance_km') is not None else 1e9))

    # return top 10 concise summaries
    top = scored[:10]
    return jsonify({'count': len(scored), 'top': top, 'note': 'deterministic fallback ranking used'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

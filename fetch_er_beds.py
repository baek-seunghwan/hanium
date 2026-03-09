#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple fetcher for 응급실 가용병상 정보 (data.go.kr API).
Usage:
  - set env var `DATA_GO_KR_KEY` to override the embedded key
  - run: python fetch_er_beds.py --sido 서울특별시 --sigungu 강남구 --numOfRows 5
"""
import os
import sys
import argparse
import xml.etree.ElementTree as ET
try:
    import requests
except Exception:
    requests = None

API_URL = 'http://apis.data.go.kr/B552657/ErmctInfoInqireService/getEmrrmRltmUsefulSckbdInfoInqire'
# Provided key (will be used only if env var not set)
DEFAULT_KEY = '82b5509f3ea200886192a50569efc50b480eda4a1458cd22349634edcc3bfbb0'


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--sido', help='주소(시도) (STAGE1)')
    p.add_argument('--sigungu', help='주소(시군구) (STAGE2)')
    p.add_argument('--pageNo', type=int, default=1, help='페이지 번호')
    p.add_argument('--numOfRows', type=int, default=10, help='목록 건수')
    p.add_argument('--timeout', type=float, default=15.0)
    return p.parse_args()


def build_params(args, key):
    params = {
        'serviceKey': key,
        'pageNo': str(args.pageNo),
        'numOfRows': str(args.numOfRows),
        '_type': 'xml'
    }
    if args.sido:
        params['STAGE1'] = args.sido
    if args.sigungu:
        params['STAGE2'] = args.sigungu
    return params


def fetch_with_requests(url, params, timeout):
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.text


def fetch_with_urllib(url, params, timeout):
    from urllib import parse, request
    qs = parse.urlencode(params)
    full = url + '?' + qs
    with request.urlopen(full, timeout=timeout) as fh:
        return fh.read()


KNOWN_FIELDS = [
    'rnum','hpid','phpid','hvidate','hvec','hvoc','hvcc','hvncc','hvccc','hvicc',
    'hvgc','hvdnm','hvctayn','hvmriayn','hvangioayn','hvventiayn','hvamyn','hv1',
    'hv2','hv3','hv4','hv5','hv6','hv7','hv8','hv9','hv10','hv11','hv12',
    'dutyname','dutytel3'
]


def print_item(el):
    out = {}
    for f in KNOWN_FIELDS:
        child = el.find(f)
        if child is None:
            # try namespaced or uppercase variants
            child = el.find('.//'+f)
        out[f] = (child.text.strip() if child is not None and child.text else '')
    # print summary
    print('---')
    print('기관명:', out.get('dutyname') or out.get('hpid') or '')
    print('기관코드:', out.get('hpid'))
    print('응급실전화:', out.get('dutytel3'))
    # print some bed info succinctly
    print('응급실:', out.get('hvec'), '입원실:', out.get('hvgc'))
    print('CT 사용 가능:', out.get('hvctayn'), 'MRI 사용 가능:', out.get('hvmriayn'))


def main():
    args = parse_args()
    key = os.getenv('DATA_GO_KR_KEY') or DEFAULT_KEY
    params = build_params(args, key)

    try:
        if requests is not None:
            txt = fetch_with_requests(API_URL, params, args.timeout)
            if isinstance(txt, bytes):
                txt = txt.decode('utf-8')
        else:
            txt = fetch_with_urllib(API_URL, params, args.timeout)
            if isinstance(txt, bytes):
                txt = txt.decode('utf-8')
    except Exception as e:
        print('Request failed:', e)
        sys.exit(2)

    # parse XML
    try:
        root = ET.fromstring(txt)
    except Exception as e:
        print('Failed to parse response as XML:', e)
        print('Raw response preview:', txt[:400])
        sys.exit(3)

    # try to find resultCode / resultMsg
    rc = root.find('.//resultCode')
    rm = root.find('.//resultMsg')
    if rc is not None:
        print('resultCode:', rc.text if rc.text else '')
    if rm is not None:
        print('resultMsg:', rm.text if rm.text else '')

    # find items
    items = root.findall('.//item')
    if not items:
        # sometimes wrapped as items/item
        body_items = root.findall('.//items')
        for bi in body_items:
            items.extend(bi.findall('.//item'))

    if not items:
        print('No items found in response.')
        return

    for it in items:
        print_item(it)


if __name__ == '__main__':
    main()

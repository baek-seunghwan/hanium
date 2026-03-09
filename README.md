간단한 XML(RDF/DCAT) 파서 예제 및 응급실 가용병상 API 호출 예제

설치: Python 3 필요 (옵션으로 `requests` 패키지 권장)

로컬 메타데이터 파싱 예제:

```bash
python run.py
```

응급실 가용병상(API) 호출 예제 스크립트:

`fetch_er_beds.py` 사용법

- 환경 변수로 API 키를 설정 (권장):

```powershell
$env:DATA_GO_KR_KEY = "<your_key>"
python fetch_er_beds.py --sido "서울특별시" --sigungu "강남구" --numOfRows 5
```

또는 키를 직접 사용하려면 환경 변수를 설정하지 않아도 스크립트 내부의 기본 키가 사용됩니다.

파라미터:
- `--sido`: 주소(시도, STAGE1)
- `--sigungu`: 주소(시군구, STAGE2)
- `--pageNo`: 페이지 번호 (기본 1)
- `--numOfRows`: 목록 건수 (기본 10)

출력: 각 기관별로 `기관명`, `기관코드`, `응급실전화`, `응급실/입원실/CT/MRI` 요약을 출력합니다.

문제가 발생하면 `requests` 설치를 권장합니다:

```bash
pip install requests
```

웹(간단한 실시간 조회 UI)

`app.py`는 Flask 기반의 간단한 웹 인터페이스를 제공합니다. 좌표가 응답에 포함되어 있으면 지도(Leaflet via Folium)도 표시합니다.

필요 패키지 설치:

```bash
pip install -r requirements.txt
```

앱 실행(Windows PowerShell 예시):

```powershell
$env:DATA_GO_KR_KEY="82b5509f3ea200886192a50569efc50b480eda4a1458cd22349634edcc3bfbb0"
python app.py
```

브라우저에서 http://localhost:5000 접속 후 `시도`/`시군구`를 입력하면 실시간 결과를 확인할 수 있습니다.

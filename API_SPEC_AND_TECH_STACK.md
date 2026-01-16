# API 명세서 및 기술 스택 (인사담당자용)

## 개요
본 저장소는 키워드 분석/랭킹 수집 및 네이버 검색광고 연동을 위한 백엔드 유틸리티 모듈입니다. FastAPI 기반의 간단한 API와 스크립트형 배치 로직으로 구성되어 있으며, 데이터는 SSH 터널링을 통해 MySQL에 저장되고, 일부 결과는 FTP에 적재됩니다.

---

# 1) API 명세서

## 공통 사항
- **프로토콜**: HTTP
- **포맷**: JSON
- **인증**: 별도 인증 없음 (내부망/사내 용도 전제)
- **CORS**: 모든 도메인 허용(테스트용 설정)
- **서버 포트**: naver_searchad:8890, keyword_update:8891

### 공통 오류 응답
| 상태코드 | 의미 | 설명 |
|---|---|---|
| 400 | Bad Request | 입력 파라미터 누락/형식 오류 |
| 500 | Internal Server Error | 외부 API 호출 실패, DB/FTP 실패, 런타임 오류 등 |

---

## 1. 네이버 검색광고 키워드 조회
- **엔드포인트**: POST /s_ad/
- **설명**: 네이버 검색광고 API에 키워드 목록을 전달하여 광고 키워드 도구 결과를 반환합니다.
- **요청 바디**
  - `keywords`: string[] (선택, 빈 배열 또는 누락 시 의미 있는 결과 없음)

**요청 예시(개념)**
- keywords: ["키워드1", "키워드2"]

**응답**
- `keywordList` 중 요청 개수만큼의 결과 리스트 반환

**비고**
- `NAVER_API_KEY`, `NAVER_SECRET_KEY`, `NAVER_CUSTOMER_ID` 환경 변수 미설정 시 예외 발생

---

## 2. 네이버 블로그 검색 랭킹 수집
- **엔드포인트**: POST /NSR/
- **설명**: 입력한 키워드들의 블로그 검색 랭킹 정보를 수집하고 결과를 반환합니다. 검색 히스토리는 FTP 및 DB에 저장됩니다.
- **요청 바디**
  - `userId`: string (요청자 식별자)
  - `keywords`: string[] (필수)

**응답 구조**
- `keyword`: string[] (요청 키워드 리스트)
- `rank`: array (각 키워드에 대한 순위 결과)

**저장 동작**
- FTP: /TVNAS132/smart_service/search_history/{userId}/ 에 JSON 저장
- DB: Search_History 테이블에 기록 저장

---

## 3. 인플루언서 키워드 챌린지 랭킹 추출
- **엔드포인트**: POST /inkr/
- **설명**: 인플루언서 챌린지 페이지를 스크롤 크롤링하여 최근 5개월 이내 20등 이내 키워드를 추출합니다.
- **요청 바디**
  - `link`: string (인플루언서 블로그 URL)

**응답**
- 20등 이내 키워드/등수/일자 리스트

---

# 2) 모듈별 역할 요약

| 모듈 | 역할 |
|---|---|
| check_keyword.py | 키워드 챌린지 페이지 크롤링 및 참여자 수 변동 DB 업데이트 |
| keyword_update.py | 키워드 목록을 DB에 일괄 반영(삽입/갱신) |
| search_ranking.py | 키워드 기반 블로그 검색 랭킹 수집 및 저장 |
| naver_searchad.py | 네이버 검색광고 API 연동 및 실시간 랭킹/챌린지 API 제공 |
| infl_keyword_Information.py | 인플루언서/키워드 관련 정보 수집 및 가공 |
| key.py | DB/SSH/FTP/네이버 API 키 환경변수 로딩 |

---

# 3) 기술 스택 (상세)

## 언어/런타임
- **Python 3.x**

## 웹 프레임워크
- **FastAPI**: 비동기 API 서버 구축
- **Uvicorn**: ASGI 서버 런타임

## 크롤링/자동화
- **Selenium**: 브라우저 자동화 기반 스크롤/페이지 캡처
- **BeautifulSoup4**: HTML 파싱 및 데이터 추출
- **Requests**: HTTP 요청 처리

## 데이터 처리
- **Pandas**: 데이터 가공 및 분석

## 데이터베이스
- **MySQL** (PyMySQL 사용)
- **sshtunnel / open_tunnel**: SSH 터널을 통한 안전한 DB 접근

## 파일 전송/저장
- **FTP (ftplib)**: 결과 파일 업로드 및 이력 저장

## 보안/키 관리
- 민감정보는 **환경변수**로 주입 (key.py)
  - 예: DB, SSH, FTP, NAVER API 키

---

# 4) 환경 변수 목록

| 변수명 | 설명 |
|---|---|
| DB_ID | DB 사용자 ID |
| DB_PASSWORD | DB 비밀번호 |
| SSH_USER | SSH 사용자 |
| SSH_PASSWORD | SSH 비밀번호 |
| NAS_ID | FTP 계정 |
| NAS_PASSWORD | FTP 비밀번호 |
| FTP_SERVER | FTP 서버 주소 |
| NAVER_API_KEY | 네이버 검색광고 API 키 |
| NAVER_SECRET_KEY | 네이버 검색광고 시크릿 키 |
| NAVER_CUSTOMER_ID | 네이버 광고 고객 ID |

---

# 5) 운영 관점 요약
- 배치성 스크립트와 API가 결합된 구조
- 네이버 검색/광고 데이터 수집 및 내부 DB 적재
- 실시간 랭킹 조회와 이력 저장 지원
- 민감정보는 환경변수 기반으로 비식별 처리

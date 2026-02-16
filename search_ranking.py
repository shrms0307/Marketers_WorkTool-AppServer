# 검색 키워드 블로거 순위 추출 프로세스
## naver_searchad.py로 통합된 레거시 엔드포인트 (deprecated)

"""
이 모듈은 naver_searchad.py로 기능이 통합된 레거시 스텁입니다.
실제 API 호출은 /NSR, /s_ad 등 신규 엔드포인트를 사용하세요.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

origins = [
    "http://work.now-i.am",
    "https://work.now-i.am",
    "http://sys.now-i.am",
    "https://hanssemgaon.co.kr",
    "http://hanssemgaon.co.kr",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/search_ranking/deprecated")
async def main(requestor: str, serch: str):
    """호환성만 유지하는 Deprecated 엔드포인트."""
    raise HTTPException(
        status_code=410,
        detail="search_ranking.py는 naver_searchad.py로 통합되었습니다. /NSR 또는 /s_ad 엔드포인트를 사용하세요.",
    )
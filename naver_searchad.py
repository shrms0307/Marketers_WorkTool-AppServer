# 네이버 검색광고 API 연동하여 결과 전달 + 검색 키워드 블로거 순위 추출 프로세스
## 입력 받은 키워드를 검색광고 API를 사용하여 결과를 클라이언트에게 전달합니다
## 입력 받은 키워드를 검색하여 순위를 추출하고 검색 기록을 저장합니다
### port: 8812


import os
import sys
import urllib.request
import json
import logging
import pandas as pd
import matplotlib.pyplot as plt
import time
import random
import requests
from requests.adapters import HTTPAdapter, Retry
import httpx
from time import perf_counter
import re
from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST, generate_latest
DEFAULT_TIMEOUT = 10  # seconds for all outbound HTTP calls
MAX_KEYWORDS = 20
MAX_KEYWORD_LEN = 80
KEYWORD_PATTERN = re.compile(r"^[\w\s가-힣\-\.,+#/&()]+$")
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = 0.5

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("naver_searchad")

REQUEST_LATENCY = Histogram("naver_api_latency_seconds", "API latency seconds", ["endpoint"])
REQUEST_COUNT = Counter("naver_api_requests_total", "API request count", ["endpoint", "status"])
FTP_UPLOADS = Counter("naver_ftp_upload_total", "FTP upload attempts", ["status"])
DB_INSERTS = Counter("naver_db_insert_total", "DB insert attempts", ["status"])
EXTERNAL_CALL_LATENCY = Histogram("naver_external_call_seconds", "External call latency seconds", ["target"])


def _build_session():
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess = requests.Session()
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    return sess


http = _build_session()


async def http_get_with_retry(url, *, params=None, headers=None, timeout=DEFAULT_TIMEOUT):
    delay = RETRY_BACKOFF
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as exc:
            if attempt == RETRY_ATTEMPTS:
                logger.warning("httpx GET failed", extra={"url": url, "attempt": attempt, "error": str(exc)})
                raise HTTPException(status_code=502, detail="External API request failed") from exc
            await asyncio.sleep(delay)
            delay *= 2


import hashlib
import hmac
import base64


import asyncio
import uvicorn
from fastapi import (
    FastAPI,
    File,
    UploadFile,
    HTTPException,
    Request,
    Query,
    Form,
)
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AnyHttpUrl, BaseModel, conlist, validator
from typing import Union, List, Optional, AsyncGenerator

import pymysql
from sshtunnel import open_tunnel

from fastapi.responses import Response, JSONResponse, StreamingResponse


from ftplib import FTP
from ftplib import error_perm

from bs4 import BeautifulSoup
from datetime import datetime
from io import BytesIO


app = FastAPI()


origins = [
    "http://work.now-i.am",
    "https://work.now-i.am",
    "http://sys.now-i.am",
    "https://hanssemgaon.co.kr",
    "http://hanssemgaon.co.kr"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)




class Signature:
    @staticmethod
    def generate(timestamp, method, uri, secret_key):
        message = "{}.{}.{}".format(timestamp, method, uri)
        hash = hmac.new(bytes(secret_key, "utf-8"), bytes(message, "utf-8"), hashlib.sha256)
        
        hash.hexdigest()
        return base64.b64encode(hash.digest())

class Item(BaseModel):
    keywords: Optional[conlist(str, min_items=1, max_items=MAX_KEYWORDS)] = None

    @validator("keywords", each_item=True)
    def validate_keyword(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("키워드는 공백만 입력할 수 없습니다.")
        if len(v) > MAX_KEYWORD_LEN:
            raise ValueError(f"키워드는 최대 {MAX_KEYWORD_LEN}자까지만 허용합니다.")
        if not KEYWORD_PATTERN.match(v):
            raise ValueError("키워드는 한글, 영문, 숫자, 공백과 -._,+#/&()만 허용합니다.")
        return v


class KeywordListResponse(BaseModel):
    keywordList: List[dict]
    

def get_header(method, uri, api_key, secret_key, customer_id):
    timestamp = str(round(time.time() * 1000))
    signature = Signature.generate(timestamp, method, uri, secret_key)
    
    return {'Content-Type': 'application/json; charset=UTF-8', 'X-Timestamp': timestamp, 
            'X-API-KEY': api_key, 'X-Customer': str(customer_id), 'X-Signature': signature}


async def getresults(hintKeywords):

    BASE_URL = 'https://api.naver.com'
    API_KEY = NAVER_API_KEY
    SECRET_KEY = NAVER_SECRET_KEY
    CUSTOMER_ID = NAVER_CUSTOMER_ID

    if not API_KEY or not SECRET_KEY or not CUSTOMER_ID:
        raise ValueError("NAVER_API_KEY, NAVER_SECRET_KEY, NAVER_CUSTOMER_ID 환경 변수를 설정하세요.")

    uri = '/keywordstool'
    method = 'GET'

    params={}

    params['hintKeywords']=hintKeywords
    params['showDetail']='1'

    start = perf_counter()
    resp = await http_get_with_retry(
        BASE_URL + uri,
        params=params,
        headers=get_header(method, uri, API_KEY, SECRET_KEY, CUSTOMER_ID),
        timeout=DEFAULT_TIMEOUT,
    )

    EXTERNAL_CALL_LATENCY.labels("naver_keywordstool").observe(round(perf_counter() - start, 3))

    logger.info("Naver API success", extra={"status": resp.status_code, "keywords": hintKeywords})

    return resp


@app.post("/s_ad/", response_model=KeywordListResponse)
async def result(item: Item):
    if not item.keywords:
        raise HTTPException(status_code=400, detail="keywords는 최소 1개 이상이어야 합니다.")

    if len(item.keywords) > MAX_KEYWORDS:
        raise HTTPException(status_code=400, detail=f"keywords는 최대 {MAX_KEYWORDS}개까지 지원합니다.")

    too_long = [kw for kw in item.keywords if kw and len(kw) > MAX_KEYWORD_LEN]
    if too_long:
        raise HTTPException(status_code=400, detail=f"각 키워드는 최대 {MAX_KEYWORD_LEN}자까지만 허용합니다.")

    start = perf_counter()
    try:
        h_m_show = len(item.keywords)
        result = await getresults(item.keywords)
        payload = result.json().get('keywordList', [])[:h_m_show]
    except Exception:
        REQUEST_COUNT.labels(endpoint="/s_ad", status="failure").inc()
        raise

    elapsed = round(perf_counter() - start, 3)
    REQUEST_LATENCY.labels(endpoint="/s_ad").observe(elapsed)
    REQUEST_COUNT.labels(endpoint="/s_ad", status="success").inc()
    logger.info("/s_ad completed", extra={"keywords": item.keywords, "elapsed_s": elapsed, "payload_len": len(payload)})
    return {"keywordList": payload}



#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


### 여기서부터 네이버 실시간 순위 추출 

class secondItem(BaseModel):
    userId: str
    keywords: Optional[conlist(str, min_items=1, max_items=MAX_KEYWORDS)] = None

    @validator("keywords", each_item=True)
    def validate_keyword(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("키워드는 공백만 입력할 수 없습니다.")
        if len(v) > MAX_KEYWORD_LEN:
            raise ValueError(f"키워드는 최대 {MAX_KEYWORD_LEN}자까지만 허용합니다.")
        if not KEYWORD_PATTERN.match(v):
            raise ValueError("키워드는 한글, 영문, 숫자, 공백과 -._,+#/&()만 허용합니다.")
        return v


class BlogRank(BaseModel):
    name: str
    blog_url: Optional[str]
    sub: str
    post_title: str
    post_url: Optional[str]
    category: str
    neighbor: str


class InfluencerRank(BaseModel):
    name: str
    fan_count: str
    category: str
    date: str
    post_title: Optional[str]
    post_url: Optional[str]
    profile_url: Optional[str]
    blog_url: Optional[str]
    blog_name: Optional[str]
    blog_category: str
    blog_neighbor: str


class RankingResult(BaseModel):
    blog: List[BlogRank]
    influencer: List[InfluencerRank]


class NSRResponse(BaseModel):
    keyword: List[str]
    rank: List[RankingResult]


now = datetime.now()

def ago(w_t):
    today = datetime.now()
    if w_t.find("일 전"):
        w_t = int(w_t.replace("일 전", ""))
    elif w_t.find("주 전"):
        w_t = int(w_t.replace("주 전", ""))
    elif w_t.find("주 전"):
        w_t = int(w_t.replace("시간 전", ""))
        return today
    n_days_ago = today - timedelta(days=w_t)
    return str(n_days_ago.date())


# 접근 키 가져오기
try:
    import key  # type: ignore
except ImportError:
    key = None


def _get_setting(env_name, *, key_attr=None, default=None, required=True):
    """Resolve config from env first, then key.py, otherwise fallback or error."""
    value = os.getenv(env_name)
    if value:
        return value
    if key_attr and key and hasattr(key, key_attr):
        return getattr(key, key_attr)
    if default is not None:
        return default
    if required:
        raise RuntimeError(f"Missing required setting: {env_name} (or key.{key_attr or env_name.lower()})")
    return None


NAVER_API_KEY = _get_setting("NAVER_API_KEY", key_attr="NAVER_API_KEY")
NAVER_SECRET_KEY = _get_setting("NAVER_SECRET_KEY", key_attr="NAVER_SECRET_KEY")
NAVER_CUSTOMER_ID = _get_setting("NAVER_CUSTOMER_ID", key_attr="NAVER_CUSTOMER_ID")

SSH_HOST = _get_setting("SSH_HOST", key_attr="ssh_host")
SSH_PORT = int(_get_setting("SSH_PORT", key_attr="ssh_port", default="22"))
SSH_USER = _get_setting("SSH_USER", key_attr="ssh_user")
SSH_PASSWORD = _get_setting("SSH_PASSWORD", key_attr="ssh_passwd")
DB_HOST = _get_setting("DB_HOST", key_attr="db_host", default="127.0.0.1")
DB_PORT = int(_get_setting("DB_PORT", key_attr="db_port", default="3306"))
DB_NAME = _get_setting("DB_NAME", key_attr="db_name", default="smart_service_influencer")
DB_USER = _get_setting("DB_USER", key_attr="db_id")
DB_PASSWORD = _get_setting("DB_PASSWORD", key_attr="db_passwd")

FTP_SERVER = _get_setting("FTP_SERVER", key_attr="FTP_server")
FTP_USER = _get_setting("FTP_USER", key_attr="nas_id")
FTP_PASSWORD = _get_setting("FTP_PASSWORD", key_attr="nas_passwd")


from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse, urljoin


def blogger(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
        }
        start = perf_counter()
        response = http.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        EXTERNAL_CALL_LATENCY.labels("naver_blog_search").observe(round(perf_counter() - start, 3))

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select("ul.lst_view._fe_view_infinite_scroll_append_target li.bx")

        results = []

        for item in items:
            if "type_ad" in item.get("class", []):
                continue

            name_tag = item.select_one("a.name")
            b_link = None
            if name_tag and "href" in name_tag.attrs:
                b_link = name_tag["href"]
            else:
                for selector in ["a.user_thumb", "a.title_link"]:
                    link_tag = item.select_one(selector)
                    if link_tag and "href" in link_tag.attrs:
                        b_link = link_tag["href"]
                        break

            if not b_link:
                continue

            parsed_url = urlparse(b_link)
            if "blog" in parsed_url.netloc:
                b_link = b_link.replace("://blog", "://m.blog")
            elif "in" in parsed_url.netloc:
                b_link = b_link.replace("://in", "://m.blog")

            sub = item.select_one("span.sub").text.strip() if item.select_one("span.sub") else "N/A"
            post_title_tag = item.select_one("a.title_link")
            post_title = post_title_tag.text.strip() if post_title_tag else "N/A"
            href = post_title_tag["href"] if post_title_tag and "href" in post_title_tag.attrs else None

            if href and "https://post.naver.com/viewer" in href:
                continue

            category, neighbor = "N/A", "N/A"
            if b_link:
                try:
                    b_start = perf_counter()
                    b_response = http.get(b_link, headers=headers, timeout=DEFAULT_TIMEOUT)
                    b_response.raise_for_status()
                    EXTERNAL_CALL_LATENCY.labels("naver_blog_profile").observe(round(perf_counter() - b_start, 3))
                    b_soup = BeautifulSoup(b_response.text, "html.parser")
                    category = b_soup.select_one("span.subject__m4PT2").text.strip() if b_soup.select_one("span.subject__m4PT2") else "N/A"
                    neighbor = b_soup.select_one("span.buddy__fw6Uo").text.strip() if b_soup.select_one("span.buddy__fw6Uo") else "N/A"

                    if category == "N/A" and href:
                        post_parsed_url = urlparse(href)
                        href_base = f"https://m.blog.naver.com{post_parsed_url.path.rsplit('/', 1)[0]}/"
                        b_response = http.get(href_base, headers=headers, timeout=DEFAULT_TIMEOUT)
                        b_response.raise_for_status()
                        b_soup = BeautifulSoup(b_response.text, "html.parser")
                        category = b_soup.select_one("span.subject__m4PT2").text.strip() if b_soup.select_one("span.subject__m4PT2") else "N/A"
                        neighbor = b_soup.select_one("span.buddy__fw6Uo").text.strip() if b_soup.select_one("span.buddy__fw6Uo") else "N/A"
                except requests.exceptions.RequestException as e:
                    logger.warning("b_link request failed", extra={"error": str(e), "url": b_link})

            results.append({
                "name": name_tag.text.strip() if name_tag else "N/A",
                "blog_url": b_link,
                "sub": sub or "N/A",
                "post_title": post_title or "N/A",
                "post_url": href,
                "category": category or "N/A",
                "neighbor": neighbor or "N/A",
            })

        return results

    except requests.exceptions.RequestException as e:
        logger.warning("blogger request failed", extra={"error": str(e), "url": url})
    except Exception as e:
        logger.warning("blogger parse failed", extra={"error": str(e)})
    return []



def influencer(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
        }
        start = perf_counter()
        response = http.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        EXTERNAL_CALL_LATENCY.labels("naver_influencer_search").observe(round(perf_counter() - start, 3))

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select("ul.keyword_challenge_list._inf_contents li.keyword_bx._item._check_visible")

        results = []

        for item in items:
            name = item.select_one("a.name.elss span.txt").text.strip() if item.select_one("a.name.elss span.txt") else None
            fan_count = item.select_one("span.fan_count span._fan_count").text.strip() if item.select_one("span.fan_count span._fan_count") else None
            category = item.select_one("div.etc_area span.etc").text.strip() if item.select_one("div.etc_area span.etc") else None
            post_title = item.select_one("a.title_link").text.strip() if item.select_one("a.title_link") else None
            date_tag = item.select_one("span.date")
            date = date_tag.text.strip() if date_tag else "N/A"

            href_tag = item.select_one("a.dsc_link")
            href = href_tag["href"].replace("?areacode=ink*A&query=%EC%9E%90%EB%8F%99%EC%B0%A8", "") if href_tag and "href" in href_tag.attrs else None
            profile_url = None
            if href and "/contents" in href:
                profile_url = href.split("/contents", 1)[0]

            blog_url, blog_name, blog_category, blog_neighbor = None, None, "N/A", "N/A"

            if href:
                try:
                    href_start = perf_counter()
                    href_response = http.get(href, headers=headers, timeout=DEFAULT_TIMEOUT)
                    href_response.raise_for_status()
                    EXTERNAL_CALL_LATENCY.labels("naver_influencer_post").observe(round(perf_counter() - href_start, 3))
                    href_soup = BeautifulSoup(href_response.text, "html.parser")

                    script_tag = href_soup.find("script", text=lambda x: x and "blogId" in x and "blogURL" in x)
                    if script_tag:
                        script_content = script_tag.string or ""
                        blog_id_match = re.search(r"blogId\s*=\s*'(.*?)'", script_content)
                        blog_url_match = re.search(r"blogURL\s*=\s*'(.*?)'", script_content)

                        blog_id = blog_id_match.group(1) if blog_id_match else None
                        blog_url_val = blog_url_match.group(1) if blog_url_match else None

                        if blog_id and blog_url_val:
                            blog_url = f"https://m.blog.naver.com/{blog_id}"

                    if blog_url:
                        try:
                            b_start = perf_counter()
                            b_response = http.get(blog_url, headers=headers, timeout=DEFAULT_TIMEOUT)
                            b_response.raise_for_status()
                            EXTERNAL_CALL_LATENCY.labels("naver_influencer_blog").observe(round(perf_counter() - b_start, 3))
                            b_soup = BeautifulSoup(b_response.text, "html.parser")

                            blog_category = b_soup.select_one("span.subject__m4PT2").text.strip() if b_soup.select_one("span.subject__m4PT2") else "N/A"
                            blog_neighbor = b_soup.select_one("span.buddy__fw6Uo").text.strip() if b_soup.select_one("span.buddy__fw6Uo") else "N/A"
                            blog_name = b_soup.select_one("a.text__j6LKZ").text.strip() if b_soup.select_one("a.text__j6LKZ") else None

                        except requests.exceptions.RequestException as e:
                            logger.warning("blog_url request failed", extra={"error": str(e), "blog_url": blog_url})
                except requests.exceptions.RequestException as e:
                    logger.warning("href request failed", extra={"error": str(e), "href": href})

            if not all([name, fan_count, category, href]):
                continue

            results.append({
                "name": name,
                "fan_count": fan_count,
                "category": category,
                "date": date,
                "post_title": post_title,
                "post_url": href,
                "profile_url": profile_url,
                "blog_url": blog_url,
                "blog_name": blog_name,
                "blog_category": blog_category or "N/A",
                "blog_neighbor": blog_neighbor or "N/A",
            })

        return results

    except requests.exceptions.RequestException as e:
        logger.warning("influencer request failed", extra={"error": str(e), "url": url})
    except Exception as e:
        logger.warning("influencer parse failed", extra={"error": str(e)})
    return []



def Ranking(serch):
    result = {
        "blog" : [],
        "influencer" : []
    }
    b_url = "https://search.naver.com/search.naver?ssc=tab.blog.all&sm=tab_jum&query=" + serch
    i_url = "https://search.naver.com/search.naver?sm=tab_hty.top&where=influencer&?ssc=tab.influencer.chl&where=influencer&sm=tab_jum&query=" + serch

    result["blog"] = blogger(b_url)
    result["influencer"] = influencer(i_url)
    return result



# DB 연결
def get_connection():
    """데이터베이스 연결을 반환하는 함수"""
    try:
        server = open_tunnel(
            (SSH_HOST, SSH_PORT),
            ssh_username=SSH_USER,
            ssh_password=SSH_PASSWORD,
            remote_bind_address=(DB_HOST, DB_PORT)
        )
        server.start()

        # 데이터베이스 연결
        connection = pymysql.connect(
            host="127.0.0.1",
            port=server.local_bind_port,
            user=DB_USER,
            passwd=DB_PASSWORD ,
            db=DB_NAME,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection, server  # 두 객체를 반환
    except Exception as e:
        raise Exception(f"데이터베이스 연결 오류: {str(e)}")


def upload_history_to_ftp(requestor: str, serch: str, json_file: BytesIO) -> str:
    date = str(datetime.now().date())
    file_name = f"{serch}({date}).json"
    save_point = f"/TVNAS132/smart_service/search_history/{requestor}/{file_name}"

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            json_file.seek(0)
            with FTP(FTP_SERVER) as ftp:
                ftp.login(FTP_USER, FTP_PASSWORD)
                try:
                    ftp.mkd(f"/TVNAS132/smart_service/search_history/{requestor}/")
                except Exception:
                    pass
                ftp.cwd(f"/TVNAS132/smart_service/search_history/{requestor}/")
                ftp.storbinary(f"STOR {file_name}", json_file)
            FTP_UPLOADS.labels(status="success").inc()
            logger.info("FTP upload success", extra={"file": file_name, "attempt": attempt})
            return save_point
        except Exception as e:
            FTP_UPLOADS.labels(status="failure").inc()
            logger.warning("FTP upload failed", extra={"file": file_name, "attempt": attempt, "error": str(e)})
            if attempt == RETRY_ATTEMPTS:
                raise
            time.sleep(RETRY_BACKOFF * attempt)

    return save_point


def insert_history_with_retries(word: str, requestor: str, save_point: str) -> None:
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        conn, server = get_connection()
        try:
            with conn.cursor() as cur:
                query = """INSERT INTO Search_History (word, a_searcher, history_storage) VALUES (%s, %s, %s)"""
                cur.execute(query, (word, requestor, save_point))
                conn.commit()
                DB_INSERTS.labels(status="success").inc()
                logger.info("Search history DB insert success", extra={"word": word, "requestor": requestor, "attempt": attempt})
                return
        except Exception as e:
            DB_INSERTS.labels(status="failure").inc()
            logger.warning("DB insert failed", extra={"word": word, "attempt": attempt, "error": str(e)})
            if attempt == RETRY_ATTEMPTS:
                raise
            time.sleep(RETRY_BACKOFF * attempt)
        finally:
            conn.close()
            server.stop()


def Searcher_Manager(requestor,serch):
    serch = serch.strip()
    if not serch:
        raise ValueError("검색어는 공백일 수 없습니다.")

    data = Ranking(serch)

    if not data:
        return {"blog": [], "influencer": []}

    json_file = BytesIO(json.dumps(data, indent=4).encode('utf-8'))
    save_point = upload_history_to_ftp(requestor, serch, json_file)
    insert_history_with_retries(serch, requestor, save_point)

    return data


@app.post("/NSR/", response_model=NSRResponse)
async def main(item: secondItem):
    if not item.keywords:
        raise HTTPException(status_code=400, detail="keywords는 최소 1개 이상이어야 합니다.")
    if len(item.keywords) > MAX_KEYWORDS:
        raise HTTPException(status_code=400, detail=f"keywords는 최대 {MAX_KEYWORDS}개까지 지원합니다.")
    too_long = [kw for kw in item.keywords if kw and len(kw) > MAX_KEYWORD_LEN]
    if too_long:
        raise HTTPException(status_code=400, detail=f"각 키워드는 최대 {MAX_KEYWORD_LEN}자까지만 허용합니다.")

    requestor = item.userId
    serch = item.keywords

    start = perf_counter()
    result = {"keyword": [], "rank": []}

    try:
        for i in serch:
            data = Searcher_Manager(requestor, i)
            logger.info("NSR processed", extra={"keyword": i, "requestor": requestor})
            result["keyword"].append(i)
            result["rank"].append(data)
    except Exception:
        REQUEST_COUNT.labels(endpoint="/NSR", status="failure").inc()
        raise

    elapsed = round(perf_counter() - start, 3)
    REQUEST_LATENCY.labels(endpoint="/NSR").observe(elapsed)
    REQUEST_COUNT.labels(endpoint="/NSR", status="success").inc()
    logger.info("/NSR completed", extra={"requestor": requestor, "count": len(serch), "elapsed_s": elapsed, "payload_len": len(result.get('rank', []))})
    return result


#-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# 키워드 챌린지 등수 추출

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from datetime import datetime, timedelta
import time
from urllib.parse import urljoin

class thirdItem(BaseModel):
    link: AnyHttpUrl

    @validator("link")
    def validate_link(cls, v):
        if not str(v).lower().startswith(("http://", "https://")):
            raise ValueError("유효한 URL을 입력하세요.")
        return v

def parse_date(text):
    """
    '2024.12.05', '6일 전', '4시간 전' 형태의 날짜 문자열을 datetime 객체로 변환
    """
    now = datetime.now()

    if '전' in text:
        if '일' in text:
            days = int(text.split('일')[0])
            return now - timedelta(days=days)
        elif '시간' in text:
            hours = int(text.split('시간')[0])
            return now - timedelta(hours=hours)
        elif '분' in text:
            minutes = int(text.split('분')[0])
            return now - timedelta(minutes=minutes)
    else:
        return datetime.strptime(text, "%Y.%m.%d")
        


# 추후 확인
# 인자값 : 인플루언서 url 
@app.post("/inkr/")
async def scroll_and_crawl_top_20(item: thirdItem):
    input_url = str(item.link)
    url = input_url + "/challenge?sortType=LAST_UPDATE"
    print(f"생성된 URL: {url}")  # 디버깅용
    start = perf_counter()

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )

    driver = webdriver.Chrome(options=chrome_options)

    idx = 20  # 초기 인덱스
    try:
        driver.get(url)
        # 5개월 전 기준 날짜 계산
        five_months_ago = datetime.now() - timedelta(days=5 * 30)

        # JavaScript 로드 대기
        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "ChallengeHistory__item___BPUlN"))
        )

        print("요소 로드 성공")

        while True:
            # 현재 렌더링된 요소 가져오기
            items = driver.find_elements(By.CLASS_NAME, "ChallengeHistory__item___BPUlN")
            print(f"현재 요소 개수: {len(items)}")
        
            if len(items) > idx:
                print("뭔데 조건이 충족이 안돼", idx)
                
                target_item = items[idx]
                detail_item = target_item.find_element(By.CSS_SELECTOR, ".KeywordChallenge__detail_item___L9wek")
                target_text = detail_item.text
                print(f"{idx}번째 요소 텍스트(날짜): {target_text}")
            
                last_date = parse_date(target_text)
            
                if last_date <= five_months_ago:
                    print(f"5개월 이전 데이터 발견: {last_date}")
                    break  # 루프 종료
            else:
                print("요소가 아직 로드되지 않았습니다.")


            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(5)
            idx += 19

        print("5개월 이전 데이터 발견, 20등 이내 데이터 크롤링 시작...")
        result = []
        for i, item in enumerate(items):  # 인덱스를 함께 추적
            try:
                rank_element = item.find_element(By.CSS_SELECTOR, ".KeywordChallenge__rank___YBTPn")
                rank_text = rank_element.text.strip()
                rank = int(rank_text.replace("등", ""))  # 등수 숫자로 변환

                if rank <= 20:  # 순위 20등 이내 확인
                    try:
                        title_element = item.find_element(By.CSS_SELECTOR, ".KeywordChallenge__title_text___gHyYw span")
                        title = title_element.text.strip()
                    except NoSuchElementException:
                        continue  # 제목이 없으면 건너뜀

                    date_element = item.find_element(By.CSS_SELECTOR, ".ChallengeBlogPost__date___vCR4K")
                    date = date_element.text.strip()

                    # 결과 저장 및 출력
                    result.append({"keyword": title, "rank": rank, "date": date})
                    print(f"순위: {rank}, 제목: {title}, 날짜: {date}")
            except Exception as e:
                print(f"{i}번째 요소: 데이터 추출 중 오류 발생:", e)
        print("크롤링 결과:", result)
        elapsed = round(perf_counter() - start, 3)
        REQUEST_LATENCY.labels(endpoint="/inkr").observe(elapsed)
        REQUEST_COUNT.labels(endpoint="/inkr", status="success").inc()
        logger.info("/inkr completed", extra={"url": input_url, "count": len(result), "elapsed_s": elapsed})
        return result

    except Exception:
        REQUEST_COUNT.labels(endpoint="/inkr", status="failure").inc()
        raise

    finally:
        driver.quit()
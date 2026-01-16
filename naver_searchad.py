# 네이버 검색광고 API 연동하여 결과 전달 + 검색 키워드 블로거 순위 추출 프로세스
## 입력 받은 키워드를 검색광고 API를 사용하여 결과를 클라이언트에게 전달합니다
## 입력 받은 키워드를 검색하여 순위를 추출하고 검색 기록을 저장합니다
### port: 8812


import os
import sys
import urllib.request
import json
import pandas as pd
import matplotlib.pyplot as plt
import time
import random
import requests


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
    Form
)
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Union, List, Optional, AsyncGenerator

import pymysql
from sshtunnel import open_tunnel

from typing import Union, List, Optional, AsyncGenerator
from fastapi.responses import Response ,JSONResponse, StreamingResponse


from ftplib import FTP
from ftplib import error_perm

from bs4 import BeautifulSoup
from datetime import datetime
from io import BytesIO
import re


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
    allow_origins=["*"],  # 모든 도메인을 허용 (테스트용)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




class Signature:
    @staticmethod
    def generate(timestamp, method, uri, secret_key):
        message = "{}.{}.{}".format(timestamp, method, uri)
        hash = hmac.new(bytes(secret_key, "utf-8"), bytes(message, "utf-8"), hashlib.sha256)
        
        hash.hexdigest()
        return base64.b64encode(hash.digest())

class Item(BaseModel):
    keywords: Optional[List[str]] = None
    

def get_header(method, uri, api_key, secret_key, customer_id):
    timestamp = str(round(time.time() * 1000))
    signature = Signature.generate(timestamp, method, uri, secret_key)
    
    return {'Content-Type': 'application/json; charset=UTF-8', 'X-Timestamp': timestamp, 
            'X-API-KEY': api_key, 'X-Customer': str(customer_id), 'X-Signature': signature}


def getresults(hintKeywords):

    BASE_URL = 'https://api.naver.com'
    API_KEY = key.NAVER_API_KEY
    SECRET_KEY = key.NAVER_SECRET_KEY
    CUSTOMER_ID = key.NAVER_CUSTOMER_ID

    if not API_KEY or not SECRET_KEY or not CUSTOMER_ID:
        raise ValueError("NAVER_API_KEY, NAVER_SECRET_KEY, NAVER_CUSTOMER_ID 환경 변수를 설정하세요.")

    uri = '/keywordstool'
    method = 'GET'

    params={}

    params['hintKeywords']=hintKeywords
    params['showDetail']='1'

    r=requests.get(BASE_URL + uri, params=params, 
                 headers=get_header(method, uri, API_KEY, SECRET_KEY, CUSTOMER_ID))

    return r


@app.post("/s_ad/")
async def result(item: Item):
    keyword = item.keywords
    h_m_show = len(keyword)
    result = getresults(keyword)
    print("안녕",result.json()['keywordList'][0:h_m_show])
    return result.json()['keywordList'][0:h_m_show]



#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


### 여기서부터 네이버 실시간 순위 추출 

class secondItem(BaseModel):
    userId: str
    keywords: Optional[List[str]] = None


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
import key

db_id = key.db_id
db_passwd = key.db_passwd
ssh_user= key.ssh_user
ssh_passwd = key.ssh_passwd
nas_id = key.nas_id
nas_passwd = key.nas_passwd
FTP_server = key.FTP_server


from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse, urljoin


def blogger(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select("ul.lst_view._fe_view_infinite_scroll_append_target li.bx")

        results = []

        for item in items:
            # 광고 항목 건너뛰기
            if "type_ad" in item.get("class", []):
                continue

            # 블로거 이름과 메인 주소 추출
            name_tag = item.select_one("a.name")
            b_link = None
            if name_tag and "href" in name_tag.attrs:
                b_link = name_tag["href"]
            elif not b_link:
                for selector in ["a.user_thumb", "a.title_link"]:
                    link_tag = item.select_one(selector)
                    if link_tag and "href" in link_tag.attrs:
                        b_link = link_tag["href"]
                        break

            # 블로그 URL이 유효하지 않으면 건너뛰기
            if not b_link:
                continue

            # 모바일 URL로 변환
            parsed_url = urlparse(b_link)
            if "blog" in parsed_url.netloc:
                b_link = b_link.replace("://blog", "://m.blog")
            elif "in" in parsed_url.netloc:
                b_link = b_link.replace("://in", "://m.blog")

            # 데이터 추출
            sub = item.select_one("span.sub").text.strip() if item.select_one("span.sub") else "N/A"
            post_title_tag = item.select_one("a.title_link")
            post_title = post_title_tag.text.strip() if post_title_tag else "N/A"
            href = post_title_tag["href"] if post_title_tag and "href" in post_title_tag.attrs else None

            # href 값에 "https://post.naver.com/viewer"가 포함된 경우 건너뛰기
            if href and "https://post.naver.com/viewer" in href:
                print(f"패스된 href: {href}")
                continue

            # b_link에 접속하여 추가 데이터 추출
            category, neighbor = "N/A", "N/A"
            if b_link:
                try:
                    b_response = requests.get(b_link, headers=headers)
                    b_response.raise_for_status()
                    b_soup = BeautifulSoup(b_response.text, "html.parser")
                    category = b_soup.select_one("span.subject__m4PT2").text.strip() if b_soup.select_one("span.subject__m4PT2") else "N/A"
                    neighbor = b_soup.select_one("span.buddy__fw6Uo").text.strip() if b_soup.select_one("span.buddy__fw6Uo") else "N/A"
                    
                    # category가 "N/A"일 경우 href를 사용하여 URL 수정 후 다시 요청
                    if category == "N/A" and href:
                        # href 값 수정: 게시물 ID 제거하고 모바일 URL로 변환
                        post_parsed_url = urlparse(href)
                        href_base = f"https://m.blog.naver.com{post_parsed_url.path.rsplit('/', 1)[0]}/"
                        print(f"수정된 href로 요청: {href_base}")

                        b_response = requests.get(href_base, headers=headers)
                        b_response.raise_for_status()
                        b_soup = BeautifulSoup(b_response.text, "html.parser")
                        category = b_soup.select_one("span.subject__m4PT2").text.strip() if b_soup.select_one("span.subject__m4PT2") else "N/A"
                        neighbor = b_soup.select_one("span.buddy__fw6Uo").text.strip() if b_soup.select_one("span.buddy__fw6Uo") else "N/A"
                except requests.exceptions.RequestException as e:
                    print(f"b_link 요청 중 오류 발생: {e}")

            # 결과 저장
            results.append({
                "name": name_tag.text.strip() if name_tag else "N/A",
                "b_link": b_link,
                "sub": sub,
                "post_title": post_title,
                "href": href,
                "category": category,
                "Neighbor": neighbor,
            })

        return results

    except requests.exceptions.RequestException as e:
        print(f"요청 중 오류 발생: {e}")
    except Exception as e:
        print(f"데이터 추출 중 오류 발생: {e}")



def influencer(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # BeautifulSoup로 HTML 파싱
        soup = BeautifulSoup(response.text, "html.parser")

        # 모든 <li> 태그 선택
        items = soup.select("ul.keyword_challenge_list._inf_contents li.keyword_bx._item._check_visible")
        # print(f"Found {len(items)} items")

        results = []

        for item in items:
            # print(item.prettify())  # 각 item의 구조 디버깅
            name = item.select_one("a.name.elss span.txt").text.strip() if item.select_one("a.name.elss span.txt") else None  # 인플루언서명
            fan_count = item.select_one("span.fan_count span._fan_count").text.strip() if item.select_one("span.fan_count span._fan_count") else None  # 팬 수
            etc = item.select_one("div.etc_area span.etc").text.strip() if item.select_one("div.etc_area span.etc") else None  # 카테고리
            post_title = item.select_one("a.title_link").text.strip() if item.select_one("a.title_link") else None # 게시물 제목
            date_tag = item.select_one("span.date") # 업로드 날짜
            date = date_tag.text.strip() if date_tag else "N/A"
            # date = ago(date)

            href = item.select_one("a.dsc_link")
            href = href["href"] if href and "href" in href.attrs else None  # 포스트 링크
            href = href.replace("?areacode=ink*A&query=%EC%9E%90%EB%8F%99%EC%B0%A8","") # 이거 뭔가 자주 바뀌거 같음
            index = href.find('/contents')
            in_link = href[:index]
            
            
            # print(f"Processing href: {href}")

            b_link, b_name, b_category, b_neighbor = None, None, "N/A", "N/A"
            
            if href:
                try:
                    href_response = requests.get(href, headers=headers)
                    href_response.raise_for_status()
                    href_soup = BeautifulSoup(href_response.text, "html.parser")
                    
                    # blogId와 blogURL 추출
                    script_tag = href_soup.find("script", text=lambda x: x and "blogId" in x and "blogURL" in x)
                    if script_tag:
                        script_content = script_tag.string
                        blog_id = None
                        blog_url = None

                        # blogId 추출
                        blog_id_match = re.search(r"blogId\s*=\s*'(.*?)'", script_content)
                        if blog_id_match:
                            blog_id = blog_id_match.group(1)

                        # blogURL 추출
                        blog_url_match = re.search(r"blogURL\s*=\s*'(.*?)'", script_content)
                        if blog_url_match:
                            blog_url = blog_url_match.group(1)

                        # b_link 생성
                        if blog_id and blog_url:
                            b_link = f"https://m.blog.naver.com/{blog_id}"


                    
                    if b_link:
                        try:
                            b_response = requests.get(b_link, headers=headers)
                            print("최종 url 네이버 블로그 접속 완료",b_link)
                            b_response.raise_for_status()
                            b_soup = BeautifulSoup(b_response.text, "html.parser")
                            
                            b_category = b_soup.select_one("span.subject__m4PT2").text.strip() if b_soup.select_one("span.subject__m4PT2") else "N/A"
                            b_neighbor = b_soup.select_one("span.buddy__fw6Uo").text.strip() if b_soup.select_one("span.buddy__fw6Uo") else "N/A"
                            b_name = b_soup.select_one("a.text__j6LKZ").text.strip() if b_soup.select_one("a.text__j6LKZ") else None

                        except requests.exceptions.RequestException as e:
                            print(f"b_link 요청 중 오류 발생: {e}")
                except requests.exceptions.RequestException as e:
                    print(f"href 요청 중 오류 발생: {e}")

            if not all([name, fan_count, etc, href]):
                # print(f"Skipping item due to missing values: {name}, {fan_count}, {etc}, {href}")
                continue

            results.append({
                "name": name,
                "fan_count": fan_count,
                "etc": etc,
                "date": date,  # 게시물 업로드 일시
                "href": href,
                "in_link": in_link,
                "b_link": b_link,
                "b_name": b_name,
                "b_category": b_category,
                "b_Neighbor": b_neighbor,
                "post_title": post_title
            })

        return results

    except requests.exceptions.RequestException as e:
        print(f"요청 중 오류 발생: {e}")
    except Exception as e:
        print(f"데이터 추출 중 오류 발생: {e}")



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
            ('45.115.155.45', 22),
            ssh_username=ssh_user,
            ssh_password=ssh_passwd,
            remote_bind_address=('127.0.0.1', 3306)
        )
        server.start()

        # 데이터베이스 연결
        connection = pymysql.connect(
            host="127.0.0.1",
            port=server.local_bind_port,
            user=db_id,
            passwd=db_passwd ,
            db="smart_service_influencer",
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection, server  # 두 객체를 반환
    except Exception as e:
        raise Exception(f"데이터베이스 연결 오류: {str(e)}")



def Searcher_Manager(requestor,serch):
    
    data = Ranking(serch)  # 검색어 순위
    
    if data:
        ftp = FTP(FTP_server)
        ftp.login(nas_id, nas_passwd)
        
        try:
            ftp.mkd(f'/TVNAS132/smart_service/search_history/{requestor}/')
        except Exception:
            pass  # 디렉토리가 이미 존재하면 무시
        ftp.cwd(f'/TVNAS132/smart_service/search_history/{requestor}/')
        
        # JSON 데이터를 BytesIO 객체로 변환
        json_file = BytesIO(json.dumps(data, indent=4).encode('utf-8'))
        date = str(now.date())
        file_name = f"{serch}({date}).json"  # 확장자 추가
        
        try:
            ftp.storbinary(f'STOR {file_name}', json_file)
            print(f"검색 결과 '{file_name}' FTP 저장완료.")
        except Exception as e:
            print(f"Error uploading JSON file to FTP: {e}")
        finally:
            ftp.quit()
        
        
        save_point = f'/TVNAS132/smart_service/search_history/{requestor}/' + file_name
        conn, server = get_connection()
        try:
            with conn.cursor() as cur:
                # 쿼리 실행 - video_url과 일치하는 모든 data_type 가져오기
                query = """INSERT INTO Search_History (word, a_searcher, history_storage) VALUES (%s, %s, %s)"""
                cur.execute(query, (serch, requestor, save_point))
                conn.commit()
                print("검색 기록 db 저장 완료")
        finally:
            conn.close()  # 데이터베이스 연결 닫기
            server.stop()  # SSH 터널링 종료
        return data
    else:
        return False

# fastAPI 통신 구조는 추후 결정
@app.post("/NSR/")
async def main(item: secondItem):
    requestor = item.userId
    serch = item.keywords # 이거 리스트임 for문 돌려야함

    result = {
        "keyword": [],
        "rank": []
    }

    for i in serch:
        data = Searcher_Manager(requestor,i)
        result["keyword"].append(i)
        result["rank"].append(data)
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
    link: str

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
    input_url = item.link
    url = input_url + "/challenge?sortType=LAST_UPDATE"
    print(f"생성된 URL: {url}")  # 디버깅용
    
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
        return result

    finally:
        driver.quit()
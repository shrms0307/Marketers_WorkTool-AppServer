# 검색 키워드 블로거 순위 추출 프로세스
## 입력 받은 키워드를 검색하여 순위를 추출하고 검색 기록을 저장합니다
### 프론트 구현 해야함

"""naver_searchad 모듈과 병합됨"""

import pymysql
from sshtunnel import open_tunnel

from typing import Union, List, Optional, AsyncGenerator
from fastapi import FastAPI, Form, File, UploadFile, HTTPException
from fastapi.responses import Response ,JSONResponse, StreamingResponse

from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from ftplib import FTP
from ftplib import error_perm

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from io import BytesIO
import json
import re

from datetime import datetime

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

# FastAPI 실행
app = FastAPI()

# CORS 관련 --
origins = [
    "http://work.now-i.am",
    "https://work.now-i.am",
    "http://sys.now-i.am",
    "https://hanssemgaon.co.kr"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 접근 키 가져오기
import key

db_id = key.db_id
db_passwd = key.db_passwd
ssh_user= key.ssh_user
ssh_passwd = key.ssh_passwd
nas_id = key.nas_id
nas_passwd = key.nas_passwd
FTP_server = key.FTP_server


def blogger(url):
    try:
        # 요청 헤더 설정
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # BeautifulSoup로 HTML 파싱
        soup = BeautifulSoup(response.text, "html.parser")

        # <ul> 태그 내 모든 <li class="bx"> 태그 선택
        items = soup.select("ul.lst_view._fe_view_infinite_scroll_append_target li.bx")

        results = []

        for item in items:
            # 광고 항목 건너뛰기
            if "type_ad" in item.get("class", []):
                continue

            # 데이터 추출
            name = item.select_one("a.name").text.strip() if item.select_one("a.name") else None  # 블로거 이름
            b_link_tag = item.select_one("a.name")
            b_link = b_link_tag["href"] if b_link_tag and "href" in b_link_tag.attrs else None  # 블로거 메인 주소
            if b_link:
                b_link = b_link.replace("//blog", "//m.blog")
            sub = item.select_one("span.sub").text.strip() if item.select_one("span.sub") else None  # 업로드 시간
            post_title = item.select_one("a.title_link").text.strip() if item.select_one("a.title_link") else None  # 포스트 제목
            href = item.select_one("a.title_link")["href"] if item.select_one("a.title_link") else None  # 게시물 주소

            # None 값이 있는 항목 건너뛰기
            if not all([name, b_link, sub, post_title, href]):
                continue

            # b_link에 접속하여 추가 데이터 추출
            try:
                b_response = requests.get(b_link, headers=headers)
                b_response.raise_for_status()
                b_soup = BeautifulSoup(b_response.text, "html.parser")

                # 카테고리와 이웃 수 추출 (존재하지 않을 경우 "N/A"로 설정)
                category = b_soup.select_one("span.subject__m4PT2").text.strip() if b_soup.select_one("span.subject__m4PT2") else "N/A"
                neighbor = b_soup.select_one("span.buddy__fw6Uo").text.strip() if b_soup.select_one("span.buddy__fw6Uo") else "N/A"
            except requests.exceptions.RequestException as e:
                print(f"b_link 요청 중 오류 발생: {e}")
                category, neighbor = "N/A", "N/A"

            # 유효한 데이터만 추가
            results.append({
                "name": name,
                "b_link": b_link,
                "sub": sub,
                "post_title": post_title,
                "href": href,
                "category": category,
                "Neighbor": neighbor
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
            post_title = item.select_one("a.title_link._foryou_trigger").text.strip() if item.select_one("a.title_link._foryou_trigger") else None # 게시물 제목
            date_tag = item.select_one("span.date") # 업로드 날짜
            date = date_tag.text.strip() if date_tag else "N/A"
            # date = ago(date)


            
            href = item.select_one("a.dsc_link._foryou_trigger")
            href = href["href"] if href and "href" in href.attrs else None  # 포스트 링크
            href = href.replace("?areacode=ink*A&query=%EC%9E%90%EB%8F%99%EC%B0%A8","") # 이거 뭔가 자주 바뀌거 같음
            
            
            print(f"Processing href: {href}")

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
                            print("최종 url 네이버 블로그 접속 완료")
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

# fastAPI 통신 구조는 추후 결정
@app.post("//")
async def main(requestor, serch):
    data = Ranking(serch)  # 검색어 순위
    
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


# 4일 평균 방문자 수 : NVisitorgp4ajax api 사용 --> 조회수 관리 db 업데이트 시 한다고 함 (내가 해도 됨)
# 포스팅 제목도 추가로 크롤
# 이웃 수 / 카테고리 : https://m.blog.naver.com/아이디 통해 크롤링 
# 검색된 내용 db에 이미 보유한 사람이면 업데이트 없는 사람이면 승인 필요 테이블로 insert

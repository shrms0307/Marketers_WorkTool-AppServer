# 인플루언서의 키워드 챌린지 정보를 전달함
# 전달 정보 :  최근 5개월간 20등수 이내의 키워드/등수/업로드일
# naver_searchad 모듈과 통합됨


from fastapi import FastAPI, Query, Form, File, UploadFile, HTTPException
from fastapi.responses import Response ,JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from io import StringIO
from typing import Union, List, Optional, AsyncGenerator

app = FastAPI()

# CORS 관련 --
origins = [
    "http://work.now-i.am",
    "https://work.now-i.am",
    "http://sys.now-i.am",
    "https://hanssemgaon.co.kr",
    "https://smart-service.the-viral.co.kr/"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from selenium.common.exceptions import NoSuchElementException
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from datetime import datetime, timedelta
import time

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
async def scroll_and_crawl_top_20(url):
    url = url + "challenge?sortType=LAST_UPDATE"
    """
    주어진 URL에서 데이터를 크롤링하며, 5개월 이전 데이터를 발견하면 스크롤을 멈추고
    현재까지 렌더링된 요소 중 순위가 20등 이내인 데이터를 크롤링.
    """
    # Chrome 설정
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=chrome_options)

    idx = 20  # 초기 인덱스
    try:
        # URL 이동
        driver.get(url)
        time.sleep(3)

        # 5개월 전 기준 날짜 계산
        five_months_ago = datetime.now() - timedelta(days=5 * 30)

        while True:
            # 현재 렌더링된 요소 가져오기
            items = driver.find_elements(By.CLASS_NAME, "ChallengeHistory__item___BPUlN")
            # print(f"현재 요소 개수: {len(items)}")

            if len(items) > idx:
                target_item = items[idx]  # idx번째 요소
                detail_item = target_item.find_element(By.CSS_SELECTOR, ".KeywordChallenge__detail___tghF8 .KeywordChallenge__detail_item___L9wek")
                target_text = detail_item.text
                # print(f"{idx}번째 요소 텍스트(날짜): {target_text}")

                last_date = parse_date(target_text)

                if last_date <= five_months_ago:
                    print(f"5개월 이전 데이터 발견: {last_date}")
                    break
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
                        print(f"{i}번째 요소: 제목 요소가 없습니다. 건너뜁니다.")
                        continue  # 제목이 없으면 건너뜀

                    date_element = item.find_element(By.CSS_SELECTOR, ".ChallengeBlogPost__date___vCR4K")
                    date = date_element.text.strip()

                    # 결과 저장 및 출력
                    result.append({"keyword": title, "rank": rank, "date": date})

            except Exception as e:
                print(f"{i}번째 요소: 데이터 추출 중 오류 발생:", e)

        print("크롤링 결과:", result)
        return result

    finally:
        driver.quit()

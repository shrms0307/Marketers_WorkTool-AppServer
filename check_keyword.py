# 매일 오전 9시에 자동 실행됨
## 키워드 챌린지 페이지에 접속하여 키워드 수량 변화를 감지하여 db에 자동 업로드 + 참여자 수 업데이트
### 프론트 구현해야함
import os
import json
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains  # 추가된 부분
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys  
from selenium.common.exceptions import InvalidSessionIdException

import json
import time

import pymysql
from sshtunnel import open_tunnel

# 접근 키 가져오기
import key

db_id = key.db_id
db_passwd = key.db_passwd
ssh_user= key.ssh_user
ssh_passwd = key.ssh_passwd
nas_id = key.nas_id
nas_passwd = key.nas_passwd
FTP_server = key.FTP_server



# DB 연결 함수
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
            passwd=db_passwd,
            db="smart_service_influencer",
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection, server
    except Exception as e:
        raise Exception(f"데이터베이스 연결 오류: {str(e)}")


# 카테고리 딕셔너리
category_dict = {
    "travel": '여행',
    "game": '게임',
    "book": '컬쳐(도서)',
    "prosports": '스포츠(프로스포츠)',
    "broadcast": '엔터테인먼트(방송-연예)',
    "biz": '경제-비즈니스',
    "beauty": '스타일(뷰티)',
    "art": '컬쳐(공연-전시-예술)',
    "edu": '어학-교육',
    "technology": '테크(IT테크)',
    "health": '라이프(생활건강)',
    "pet": '동물-펫',
    "fashion": '스타일(패션)',
    "living": '라이프(리빙)',
    "movie": '엔터테인먼트(영화)',
    "sports": '스포츠(운동-레저)',
    "food": '푸드',
    "parenting": '라이프(육아)',
    "car": '테크(자동차)',
    "music": '엔터테인먼트(대중음악)'
}

# JSON 파일 읽기 및 데이터 처리 함수
def load_data_from_json(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    formatted_data = []
    for category, items in data.items():
        for item in items:
            title = item.get("title", "").strip()
            participant = item.get("participant", "").strip()
            formatted_data.append({
                "keyword": title,
                "participation": participant,
                "category": category_dict.get(category, "Unknown")  # 벨류 사용
            })
    return formatted_data

# 키워드 삽입 또는 업데이트 함수
def insert_or_update_keywords(file_path):
    try:
        # DB 연결
        connection, server = get_connection()
        cursor = connection.cursor()

        # JSON 데이터 불러오기
        data = load_data_from_json(file_path)

        for item in data:
            keyword = item["keyword"]
            raw_participation = item["participation"]
            category = item["category"]

            # participation 숫자만 추출
            participation = int(re.sub(r"[^\d]", "", raw_participation))

            # 키워드 존재 확인
            check_sql = """
                SELECT COUNT(*) AS count FROM test_infl_keyword 
                WHERE keyword = %s AND category = %s
            """
            cursor.execute(check_sql, (keyword, category))
            result = cursor.fetchone()

            if result["count"] > 0:
                # participation 업데이트
                update_sql = """
                    UPDATE test_infl_keyword 
                    SET participation = %s 
                    WHERE keyword = %s AND category = %s
                """
                cursor.execute(update_sql, (participation, keyword, category))
                print(f"[INFO] Updated: {keyword}, Category: {category}, Participation: {participation}")
            else:
                # 새 데이터 삽입
                insert_sql = """
                    INSERT INTO test_infl_keyword (keyword, participation, category)
                    VALUES (%s, %s, %s)
                """
                cursor.execute(insert_sql, (keyword, participation, category))
                print(f"[INFO] Inserted: {keyword}, Category: {category}, Participation: {participation}")

        # 커밋
        connection.commit()
        print("[INFO] 데이터베이스 업로드 완료")

        # JSON 파일 삭제
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[INFO] JSON 파일이 삭제되었습니다: {file_path}")

    except Exception as e:
        print(f"[ERROR] 데이터 처리 중 오류 발생: {e}")
        connection.rollback()
    finally:
        cursor.close()
        connection.close()
        server.stop()
        print("[INFO] 데이터베이스 연결 종료")



# 카테고리와 해당 ID를 매핑한 변수
CATEGORY_IDS = {
    "travel": 173983334400000,
    "fashion": 173983338496000,
    "beauty": 173983338496000,
    "food": 173983342592000,
    "technology": 173983346688000,
    "car": 173983346688000,
    "living": 173983350784000,
    "parenting": 173983350784000,
    "health": 173983350784000,
    "game": 173983354880000,
    "pet": 173983358976000,
    "sports": 173983363072000,
    "prosports": 173983363072000,
    "broadcast": 173983367168000,
    "music": 173983367168000,
    "movie": 173983367168000,
    "art": 173983371264000,
    "book": 173983371264000,
    "biz": 173983375360000,
    "edu": 173983379456000
}

def load_existing_counts(json_path):
    """JSON 파일에서 기존 키워드 수와 업데이트 날짜를 로드"""
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"{json_path} not found.")
    
    with open(json_path, 'r') as file:
        data = json.load(file)
    
    # 기존 키워드 데이터와 업데이트 날짜 분리
    last_updated = data.get("last_updated", "Unknown")
    keyword_counts = {key: value for key, value in data.items() if key != "last_updated"}
    return keyword_counts, last_updated

def save_updated_counts(json_path, updated_counts):
    """JSON 파일에 업데이트된 키워드 수와 업데이트 날짜 저장"""
    updated_counts["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 현재 시간 기록
    with open(json_path, 'w') as file:
        json.dump(updated_counts, file, indent=4, ensure_ascii=False)
    print(f"[INFO] JSON 파일이 업데이트되었습니다: {json_path}")

def get_keyword_counts(url):
    """네이버 키워드 페이지에서 현재 키워드 수를 크롤링"""
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch the page: {response.status_code}")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    script_tag = soup.find('script', id='initialState')
    if not script_tag:
        raise Exception("Script tag with id='initialState' not found")
    
    script_content = script_tag.string.strip()
    match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});', script_content, re.DOTALL)
    if not match:
        raise Exception("Preloaded state not found in the script content")
    
    raw_json = match.group(1).strip()
    end_index = raw_json.rfind('}')
    clean_json = raw_json[:end_index + 1]
    data = json.loads(clean_json)
    
    categories = data.get("keyword", {}).get("categoryGroups", {}).get("data", [])
    if not categories:
        raise Exception("No category data found")

    # 현재 키워드 수 추출
    extracted_counts = {}
    for group in categories:
        for category in group["categories"]:
            code = category["code"]
            keyword_count = category["keywordCount"]
            extracted_counts[code] = keyword_count

    return extracted_counts

def compare_and_update_counts(existing_counts, new_counts):
    """수량 변화 확인 및 업데이트"""
    changed_categories = {}
    for category, existing_count in existing_counts.items():
        new_count = new_counts.get(category, 0)
        if existing_count < new_count:
            changed_categories[category] = {
                "old": existing_count,
                "new": new_count,
                "change": new_count - existing_count
            }
            # 기존 데이터 업데이트
            existing_counts[category] = new_count
    return changed_categories, existing_counts

def get_category_ids_with_names(changed_categories):
    """업데이트된 카테고리에 대한 이름과 ID 반환"""
    updated_category_data = []
    for category in changed_categories:
        category_id = CATEGORY_IDS.get(category)
        if category_id:
            updated_category_data.append({"name": category, "id": category_id})
    return updated_category_data

def check_keyword(json_path="keyword/count_history.json", url="https://in.naver.com/keywords"):
    try:
        # 기존 키워드 수 로드
        existing_counts, last_updated = load_existing_counts(json_path)
        print(f"[INFO] 마지막 업데이트: {last_updated}")
        
        # 현재 키워드 수 크롤링
        new_counts = get_keyword_counts(url)
        
        # 변화 확인 및 업데이트
        changed_categories, updated_counts = compare_and_update_counts(existing_counts, new_counts)
        
        if changed_categories:
            print("[INFO] 수량 변화가 감지되었습니다:")
            for category, details in changed_categories.items():
                print(f"{category}: Old = {details['old']}, New = {details['new']}, Change = {details['change']}")
            
            # JSON 파일 업데이트
            save_updated_counts(json_path, updated_counts)
            
            # 업데이트된 카테고리 이름과 ID 반환
            updated_category_data = get_category_ids_with_names(changed_categories)
            print("[INFO] 업데이트된 카테고리 데이터:")
            print(updated_category_data)
            
            return updated_category_data
        
        else:
            print("[INFO] 수량 변화가 없습니다.")
            return []

    except Exception as e:
        print(f"[ERROR] {e}")
        return []



def scrape_dynamic_tabs(updated_categories, output_file="output.json"):
    """
    특정 카테고리만 크롤링하는 함수 (세션 만료 시 자동 재시작 포함)
    """
    def restart_driver():
        """WebDriver를 재시작하는 함수"""
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(options=options)
        driver.maximize_window()  # 최대화로 스크롤 처리 최적화
        return driver

    def click_tab(driver, tab):
        """탭 클릭 함수"""
        try:
            driver.execute_script("arguments[0].click();", tab)  # JavaScript 강제 클릭
            time.sleep(2)  # 클릭 후 안정화 대기
        except Exception as e:
            raise Exception(f"[ERROR] Failed to click tab: {e}")

    def perform_full_scroll(driver):
        """스크롤을 끝까지 진행"""
        previous_scroll_position = -1
        while True:
            current_scroll_position = driver.execute_script("return window.scrollY;")
            if current_scroll_position == previous_scroll_position:
                print("[INFO] Scrolling stopped as no new content is loaded.")
                break
            previous_scroll_position = current_scroll_position
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(1)

    driver = restart_driver()  # 드라이버 시작
    driver.get("https://in.naver.com/keywords")
    results = {}

    try:
        # 상위 탭 탐색
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".CategoryTabList__item___Vp0WS"))
        )
        tabs = driver.find_elements(By.CSS_SELECTOR, ".CategoryTabList__item___Vp0WS")

        for tab in tabs:
            tab_id = int(tab.get_attribute("id"))
            tab_name = tab.text.strip()

            # 업데이트된 카테고리 필터링
            matching_categories = [cat for cat in updated_categories if cat["id"] == tab_id]
            if not matching_categories:
                print(f"[INFO] Skipping tab: {tab_name} (ID: {tab_id})")
                continue

            print(f"[INFO] Switching to tab: {tab_name} (ID: {tab_id})")
            try:
                # 탭 클릭
                click_tab(driver, tab)

                # 하위 버튼 또는 단순 탭 처리
                for category in matching_categories:
                    if tab_id in CATEGORY_BUTTON_MAPPING:  # 하위 버튼이 있는 탭
                        process_subcategory(driver, category, results)
                    else:  # 하위 버튼이 없는 탭
                        perform_full_scroll(driver)
                        results[category["name"]] = scrape_keywords(driver)

            except Exception as e:
                print(f"[ERROR] Failed to process tab: {tab_name} (ID: {tab_id}). Error: {e}")
                continue

    except InvalidSessionIdException:
        print("[ERROR] WebDriver session expired. Restarting the driver...")
        driver.quit()
        driver = restart_driver()
        driver.get("https://in.naver.com/keywords")
        scrape_dynamic_tabs(updated_categories, output_file)  # 재귀 호출

    finally:
        driver.quit()

    # 결과 저장
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    if not results:
        print("[WARNING] 크롤링 결과가 비어 있습니다. 확인이 필요합니다.")
    else:
        print(f"[INFO] Data has been saved to {output_file}")

    return results




# 상위 탭 ID와 하위 버튼 매핑
CATEGORY_BUTTON_MAPPING = {
    # 여행 (ID: 173983334400000)
    173983334400000: {
        "travel": 1  # 하위 버튼 없음
    },

    # 스타일 (ID: 173983338496000)
    173983338496000: {
        "fashion": 1,  # 패션
        "beauty": 2    # 뷰티
    },

    # 푸드 (ID: 173983342592000)
    173983342592000: {
        "food": 1  # 하위 버튼 없음
    },

    # 테크 (ID: 173983346688000)
    173983346688000: {
        "technology": 1,  # IT테크
        "car": 2          # 자동차
    },

    # 라이프 (ID: 173983350784000)
    173983350784000: {
        "living": 1,    # 리빙
        "parenting": 2, # 육아
        "health": 3     # 생활건강
    },

    # 게임 (ID: 173983354880000)
    173983354880000: {
        "game": 1  # 하위 버튼 없음
    },

    # 동물/펫 (ID: 173983358976000)
    173983358976000: {
        "pet": 1  # 하위 버튼 없음
    },

    # 스포츠 (ID: 173983363072000)
    173983363072000: {
        "sports": 1,    # 운동/레저
        "prosports": 2  # 프로스포츠
    },

    # 엔터테인먼트 (ID: 173983367168000)
    173983367168000: {
        "broadcast": 1,  # 방송/연예
        "music": 2,      # 대중음악
        "movie": 3       # 영화
    },

    # 컬쳐 (ID: 173983371264000)
    173983371264000: {
        "art": 1,  # 공연/전시/예술
        "book": 2  # 도서
    },

    # 경제/비즈니스 (ID: 173983375360000)
    173983375360000: {
        "biz": 1  # 경제/비즈니스
    },

    # 어학/교육 (ID: 173983379456000)
    173983379456000: {
        "edu": 1  # 어학/교육
    }
}


def process_subcategory(driver, category, results):
    """
    하위 버튼이 있는 카테고리 처리
    """
    buttons = driver.find_elements(By.CSS_SELECTOR, ".IntroCategoryGroup__keyword_item___q8W96")
    button_index = CATEGORY_BUTTON_MAPPING[category["id"]].get(category["name"])

    if button_index is None or button_index > len(buttons):
        print(f"[ERROR] No matching button found for category: {category['name']}")
        return

    try:
        # 버튼 선택
        button = buttons[button_index - 1]  # 버튼은 1-based index로 매핑됨

        # JavaScript로 클릭 시도
        driver.execute_script("arguments[0].click();", button)
        time.sleep(2)  # 클릭 후 안정화 대기
        print(f"[INFO] Clicked button for category: {category['name']} using JavaScript")

        # 키워드 크롤링
        perform_full_scroll(driver)
        results[category["name"]] = scrape_keywords(driver)
    except Exception as e:
        print(f"[ERROR] Failed to process subcategory: {category['name']}. Error: {e}")




def process_simple_tab(driver, category, results):
    """
    하위 버튼이 없는 단순 탭에서 데이터를 크롤링
    :param driver: WebDriver 객체
    :param category: 카테고리 정보
    :param results: 결과를 저장할 딕셔너리
    """
    print(f"Processing simple tab: {category['name']} (ID: {category['id']})")

    # 스크롤 끝까지 진행
    perform_full_scroll(driver)

    # 스크롤 완료 후 데이터 수집
    data = scrape_keywords(driver)

    # 결과 저장
    results[category["name"]] = data



def click_tab(driver, tab):
    """ 탭 클릭 함수 """
    try:
        ActionChains(driver).move_to_element(tab).click().perform()
        time.sleep(2)  # 클릭 후 페이지 안정화 대기
    except Exception as e:
        raise Exception(f"Failed to click tab. Error: {e}")


def perform_full_scroll(driver):
    """
    스크롤을 끝까지 진행 (기존 방식 유지)
    """
    total_scroll_distance = 0
    previous_scroll_position = -1
    scroll_count = 0
    print("스크롤 다운을 시작합니다")
    while True:
        # 현재 스크롤 위치 확인
        current_scroll_position = driver.execute_script("return window.scrollY;")
        if current_scroll_position == previous_scroll_position:
            print("[INFO] Scrolling stopped as Total px is unchanged.")
            break
        previous_scroll_position = current_scroll_position

        # 스크롤 다운 (자동 계산)
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
        scroll_count += 1
        time.sleep(1)

        new_scroll_position = driver.execute_script("return window.scrollY;")
        scroll_distance = new_scroll_position - current_scroll_position
        total_scroll_distance += scroll_distance

    print(f"[DEBUG] Scrolled {scroll_count} times, Total: {total_scroll_distance}px")



def scrape_keywords(driver):
    """
    현재 페이지에서 키워드 데이터를 크롤링
    """
    data = []
    items = driver.find_elements(By.CLASS_NAME, "TotalKeywordList__item___POENl")

    for item in items:
        try:
            title = item.find_element(By.CLASS_NAME, "TotalKeywordList__ell___vlm0r").text
            participant = item.find_element(By.CLASS_NAME, "TotalKeywordList__participant___tQbm5").text
            data.append({"title": title, "participant": participant})
        except Exception:
            continue

    print(f"[INFO] Collected {len(data)} keywords from current tab.")
    return data


def main():
    # 키워드 수 변화 확인 및 업데이트된 카테고리 반환
    result = check_keyword(json_path="keyword/count_history.json", url="https://in.naver.com/keywords")
    
    if not result:
        print("[INFO] 업데이트된 카테고리가 없습니다. 크롤링을 중단합니다.")
        return

    # 업데이트된 카테고리를 대상으로 크롤링 실행    
    scrape_result = scrape_dynamic_tabs(updated_categories=result, output_file="keyword/filtered_output.json")

    if scrape_result:
        print("[INFO] 크롤링 완료. 결과:")
        for category, data in scrape_result.items():
            print(f"- {category}: {len(data)} keywords collected")
        db_up = "keyword/filtered_output.json"
        return db_up
    else:
        print("[WARNING] 크롤링 결과가 비어 있습니다. 확인이 필요합니다.")

if __name__ == "__main__":
    toss_db = main()
    insert_or_update_keywords(toss_db)
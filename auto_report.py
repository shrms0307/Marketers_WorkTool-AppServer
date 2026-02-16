# 보고서 첨부자료 자동 생성
## projects 테이블에서 현재 진행중인 프로잭트를 확인하고 자동으로 해당 키워드에 대한 노출 순위를 가져옴

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os
from bs4 import BeautifulSoup
import requests

import pymysql
from sshtunnel import open_tunnel

from ftplib import FTP
from ftplib import error_perm

from datetime import datetime


try:
    import key  # type: ignore
except ImportError:
    key = None


def _get_setting(env_name, *, key_attr=None, default=None, required=True):
    """Fetch a setting from env first, then key.py, otherwise fallback or raise."""
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


# 블로거 순위체크 
def check_blogger_in_list(url, bloggers):
    try:
        
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 검색 결과에서 블로거 리스트 추출(파싱)
        blogger_elements = soup.select('ul.lst_view > li.bx:not(.sp_nblog) .user_info .name')[:10]
        blogger_names = [element.text.strip() for element in blogger_elements]

        # 블로거 점유 순위 체크
        positions = []
        for blogger in bloggers:
            if blogger in blogger_names:
                index = blogger_names.index(blogger) + 1  
                positions.append(index)

        
        return str(tuple(positions))

    except Exception as e:
        print(f"Error checking bloggers: {e}")
        return "()"


def capture(idx, keywords, blogger):
    """
    <인자값>
    idx : str
    keyword : str
    blogger : list
    """
    for keyword in keywords:
        now = datetime.now().strftime("%Y%m%d")
        url = "https://m.search.naver.com/search.naver?ssc=tab.m_blog.all&sm=mtb_jum&query=" + keyword
        add_name = check_blogger_in_list(url, blogger)  # 순위 추출
        local_save_path = f"/tmp/{idx}_{keyword}_{now}{add_name}.jpg"  # 이미지 임시 저장소
        save_path = f"/TVNAS132/smart_service/Project_Report/{idx}/{keyword}/{now}{add_name}.jpg"  # FTP 저장 경로

        # 임시 저장소 생성
        local_dir = os.path.dirname(local_save_path)
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)

        # 셀레니움 세팅
        options = Options()
        options.add_argument("--headless")  # 브라우저 출력 유무
        options.add_argument("--disable-gpu")  
        options.add_argument("--window-size=375,812")  # 모바일 모드
        options.add_argument("--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 13_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0 Mobile/15E148 Safari/604.1")

        #  캡쳐
        try:
            driver = webdriver.Chrome(options=options)

            # 접속
            driver.get(url)

            
            driver.execute_script("document.body.style.overflow = 'hidden';")

            # 캡쳐 길이 지정
            total_height = driver.execute_script("return document.body.scrollHeight")
            driver.set_window_size(750, total_height / 2.5)

            
            driver.save_screenshot(local_save_path)
            print(f"Full page screenshot saved as: {local_save_path}")

            # FTP upload
            with FTP(FTP_SERVER) as ftp:
                ftp.login(FTP_USER, FTP_PASSWORD)
        
        
                # 저장경로 체크22
                remote_dir = os.path.dirname(save_path)
                path_parts = remote_dir.split("/")
                for folder in path_parts:
                    if folder:
                        try:
                            ftp.cwd(folder)
                        except Exception:
                            ftp.mkd(folder)
                            ftp.cwd(folder)

                # FTP 저장
                with open(local_save_path, 'rb') as f:
                    ftp.storbinary(f'STOR {os.path.basename(save_path)}', f)
                print(f"Uploaded {save_path} to FTP.")

        except Exception as e:
            print(f"Error: {e}")

        finally:
            driver.quit()

            
            if os.path.exists(local_save_path):
                os.remove(local_save_path)
                print(f"Temporary file removed: {local_save_path}")


# 진행중인 프로잭트 FTP 저장 폴더 유무 확인
## fetch_project_data 함수 retrun 값을 그대로 인자로 받음
def ftp_folder_ck(project_data):

    try:
        ftp = FTP(FTP_SERVER)
        ftp.login(FTP_USER, FTP_PASSWORD)

        base_path = "/TVNAS132/smart_service/Project_Report"

        for project in project_data:
            project_id = str(project['ID'])
            keywords = project['keyword']

            # 프로잭트 id 폴더 유무 확인
            project_path = os.path.join(base_path, project_id)
            try:
                ftp.cwd(project_path)
            except Exception:
                print(f"프로잭트-{project_id} 폴더가 존재하지 않아 새롭게 생성: {project_path}")
                ftp.mkd(project_path)

            # 키워드 폴더 확인
            for keyword in keywords:
                keyword_path = os.path.join(project_path, keyword)
                try:
                    ftp.cwd(keyword_path)
                except Exception:
                    print(f"{keywords}키워드 폴더가 존재하지 않아 새롭게 생성: {keyword_path}")
                    ftp.mkd(keyword_path)

        ftp.quit()
        return True

    except Exception as e:
        return False



# 현재 진행중인 프로잭트 확인
def fetch_project_data():
    try:
        
        connection, server = get_connection()
        try:
            with connection.cursor() as cursor:
                # 진행중인 프로잭트 id 가져오기
                query_projects = """
                    SELECT id FROM projects WHERE end_date >= CURDATE();
                """
                cursor.execute(query_projects)
                project_ids = [row['id'] for row in cursor.fetchall()]

                if not project_ids:
                    print("No ongoing projects found.")
                    return

                # 프로젝트 진행 정보 가져오기 : 키워드
                project_keywords = {}
                query_keywords = """
                    SELECT project_id, keyword FROM project_keywords WHERE project_id IN (%s);
                """ % ','.join(['%s'] * len(project_ids))
                cursor.execute(query_keywords, project_ids)
                for row in cursor.fetchall():
                    project_id = row['project_id']
                    keyword = row['keyword']
                    if project_id not in project_keywords:
                        project_keywords[project_id] = []
                    project_keywords[project_id].append(keyword)

                # 프로젝트 진행 정보 가져오기 : 블로거
                project_bloggers = {}
                query_bloggers = """
                    SELECT pb.project_id, bd.inf_blogname 
                    FROM project_bloggers pb
                    JOIN 1090_blogdata bd ON pb.blogger_id = bd.inf_blogid
                    WHERE pb.project_id IN (%s);
                """ % ','.join(['%s'] * len(project_ids))
                cursor.execute(query_bloggers, project_ids)
                for row in cursor.fetchall():
                    project_id = row['project_id']
                    inf_blogname = row['inf_blogname']
                    if project_id not in project_bloggers:
                        project_bloggers[project_id] = []
                    project_bloggers[project_id].append(inf_blogname)

                # 결과
                results = []
                for project_id in project_ids:
                    result = {
                        "ID": project_id,
                        "keyword": project_keywords.get(project_id, []),
                        "blogger": project_bloggers.get(project_id, [])
                    }
                    results.append(result)

                return results

        finally:
            
            connection.close()
            server.stop()

    except Exception as e:
        print(f"Error fetching project data: {e}")


if __name__ == "__main__":
    project_information = fetch_project_data()
    for_ready = ftp_folder_ck(project_information)
    if for_ready:
        for i in project_information:
            idx = str(i["ID"])
            kw = i["keyword"]
            if len(kw)==0:
                continue
            blog = i["blogger"]
            capture(idx,kw,blog)
    else:
        print("문제가 있다")
        
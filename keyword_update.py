## 수동으로 수집한 키워드가 담긴 txt파일을 입력 받아 db에 업로드합니다.
# 동일한 키워드가 존재하는지 확인하여 일치하는 키워드 존재 시 참 해당 릴레이션의 participation 만 업데이트


import os
import pymysql
from sshtunnel import open_tunnel

try:
    import key  # type: ignore
except ImportError:
    key = None


def _get_setting(env_name, *, key_attr=None, default=None, required=True):
    """환경 변수 우선, 없으면 key.py, 없으면 기본값/에러."""
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


# 카테고리 딕셔너리
category_dict = {
    0: '여행',
    1: '게임',
    2: '컬쳐(도서)',
    3: '스포츠(프로스포츠)',
    4: '엔터테인먼트(방송-연예)',
    5: '경제-비즈니스',
    6: '스타일(뷰티)',
    7: '컬쳐(공연-전시-예술)',
    8: '어학-교육',
    9: '테크(IT테크)',
    10: '라이프(생활건강)',
    11: '동물-펫',
    12: '스타일(패션)',
    13: '라이프(리빙)',
    14: '엔터테인먼트(영화)',
    15: '스포츠(운동-레저)',
    16: '푸드',
    17: '라이프(육아)',
    18: '테크(자동차)',
    19: '엔터테인먼트(대중음악)'
}


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


def data_refine(file_content):
    upload_data = {
        "kw": [],
        "cnt": []
    }

    file = StringIO(file_content)
    line_number = 0

    for line in file:
        line_number += 1
        parts = line.strip().split('참여')
        if len(parts) == 2:
            del(parts[0])
            parts = parts[0].lstrip()
            try:
                # 쉼표 제거 후 숫자로 변환
                parts = int(parts.replace(",", "").replace("명", ""))
                upload_data["cnt"].append(parts)
            except ValueError as e:
                print(f"[ERROR] Value error in line {line_number}: {line.strip()} | Error: {e}")
                continue
        elif parts[0] == "":
            continue
        else:
            upload_data["kw"].append(parts[0])

    print(f"[DEBUG] Parsed keywords: {upload_data['kw']}")
    print(f"[DEBUG] Parsed participation counts: {upload_data['cnt']}")
    return upload_data


def upsert_keywords_in_db(file_content, category_id):
    upload_data = data_refine(file_content)

    if not upload_data["kw"] or not upload_data["cnt"]:
        print("[WARNING] No keywords or participation counts parsed from the file.")
        return []

    category = category_dict.get(category_id)
    if category is None:
        raise HTTPException(status_code=400, detail="Invalid category ID")

    result_status = []

    # 데이터베이스 연결
    connection, server = get_connection()
    try:
        cursor = connection.cursor()

        for keyword, participation in zip(upload_data["kw"], upload_data["cnt"]):
            print(f"[DEBUG] Processing keyword: {keyword}, participation: {participation}, category: {category}")

            # 키워드와 카테고리 존재 여부 확인
            check_sql = """
                SELECT COUNT(*) FROM infl_keyword 
                WHERE keyword = %s AND category = %s
            """
            cursor.execute(check_sql, (keyword, category))
            result = cursor.fetchone()

            count = result.get('COUNT(*)', 0) if isinstance(result, dict) else result[0]
            print(f"[DEBUG] Query count result: {count}")

            if count > 0:
                # 존재하면 participation 업데이트
                update_sql = """
                    UPDATE infl_keyword 
                    SET participation = %s 
                    WHERE keyword = %s AND category = %s
                """
                print(f"[DEBUG] Updating participation for keyword: {keyword}, category: {category}")
                cursor.execute(update_sql, (participation, keyword, category))
                result_status.append({
                    "keyword": keyword,
                    "category": category,
                    "status": "updated",
                    "participation": participation
                })
            else:
                # 존재하지 않으면 삽입
                insert_sql = """
                    INSERT INTO infl_keyword (keyword, participation, category) 
                    VALUES (%s, %s, %s)
                """
                print(f"[DEBUG] Inserting new keyword: {keyword}, category: {category}")
                cursor.execute(insert_sql, (keyword, participation, category))
                result_status.append({
                    "keyword": keyword,
                    "category": category,
                    "status": "inserted",
                    "participation": participation
                })

            connection.commit()

    except Exception as e:
        print(f"[ERROR] Error while inserting or updating data in the database: {e}")
        connection.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred.")
    finally:
        cursor.close()
        connection.close()
        server.stop()

    print(f"[DEBUG] Final result status: {result_status}")
    return result_status




@app.post("/k_u/")
async def upload_file(category_id: int = Form(...), file: UploadFile = File(...)):
    print("카테고리 : ", category_id)
    try:
        # 파일 내용 읽기
        file_content = await file.read()
        file_content_str = file_content.decode("utf-8")
        print(file_content_str)

        # 데이터베이스 삽입 및 업데이트
        result_status = upsert_keywords_in_db(file_content_str, category_id)

        return {
            "filename": file.filename,
            "category_id": category_id,
            "message": "File processed successfully.",
            "results": result_status  # 작업 결과 반환
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing the file: {str(e)}")




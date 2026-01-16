import os

db_id = os.getenv("DB_ID", "")
db_passwd = os.getenv("DB_PASSWORD", "")
ssh_user = os.getenv("SSH_USER", "")
ssh_passwd = os.getenv("SSH_PASSWORD", "")
nas_id = os.getenv("NAS_ID", "")
nas_passwd = os.getenv("NAS_PASSWORD", "")
FTP_server = os.getenv("FTP_SERVER", "")

NAVER_API_KEY = os.getenv("NAVER_API_KEY", "")
NAVER_SECRET_KEY = os.getenv("NAVER_SECRET_KEY", "")
NAVER_CUSTOMER_ID = os.getenv("NAVER_CUSTOMER_ID", "")
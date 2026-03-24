import os
import sys
import pickle
import argparse
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ===================== [0. 환경 설정] =====================
BASE_DIR = r"D:\AI Porject\shorts_factory"
CLIENT_SECRETS_FILE = os.path.join(BASE_DIR, "dopamin_labs_key.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.pickle") # pickle이 token.json보다 인증 객체 저장에 유리함

# 이 Scope은 업로드 권한을 포함함
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

def get_authenticated_service():
    """인증 서비스 캐싱 및 갱신 로직"""
    credentials = None
    # 1. 기존 토큰파일 확인 (token.pickle)
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            credentials = pickle.load(token)
    
    # 2. 토큰이 없거나 만료된 경우 처리
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("[YouTube] 기존 토큰 만료됨, 갱신 중...")
            credentials.refresh(Request())
        else:
            print("[YouTube] 새로운 인증 세션 시작 (아래 링크를 복사하여 브라우저에 붙여넣으세요)...")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0, open_browser=False)
        
        # 3. 새로운 또는 갱신된 토큰 저장
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(credentials, token)

    return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

def upload_video(file_path, title, description, tags, category_id="24", privacy="private"):
    """
    YouTube 비디오 업로드 실행
    - Category ID 24: Entertainment (엔터테인먼트)
    """
    if not os.path.exists(file_path):
        print(f"[YouTube 오류] 파일을 찾을 수 없습니다: {file_path}")
        return

    youtube = get_authenticated_service()

    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': category_id
        },
        'status': {
            'privacyStatus': privacy,
            'selfDeclaredMadeForKids': False
        }
    }

    # 업로드할 미디어 파일 설정
    media = MediaFileUpload(
        file_path,
        chunksize=-1,
        resumable=True
    )

    request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )

    print(f"[YouTube] 업로드 중...: {title}")
    
    response = None
    try:
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"    진행률: {int(status.progress() * 100)}%")
        
        print(f"    [성공] 유튜브 업로드 완료! Video ID: {response.get('id')}")
        return response.get('id')
    
    except HttpError as e:
        print(f"    [오류] HTTP 에러 발생: {e.content}")
        return None
    except Exception as e:
        print(f"    [오류] 일반 에러 발생: {e}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="도파민연구소 유튜브 자동 업로드")
    parser.add_argument("--file", required=True, help="업로드할 영상 파일 경로")
    parser.add_argument("--title", required=True, help="영상 제목")
    parser.add_argument("--desc", default="도파민연구소가 선사하는 최고의 즐거움! #shorts", help="영상 설명")
    parser.add_argument("--tags", default="도파민,숏츠,재미,shorts", help="콤마로 구분된 태그")
    parser.add_argument("--privacy", default="unlisted", choices=["private", "public", "unlisted"], help="공개 범위")
    
    args = parser.parse_args()
    
    # 태그를 리스트로 분리
    tag_list = [t.strip() for t in args.tags.split(",")]
    
    upload_video(
        file_path=args.file,
        title=args.title,
        description=args.desc,
        tags=tag_list,
        privacy=args.privacy
    )

import os
import datetime
import yt_dlp
import sys
import json
import re

BASE_DIR = r"D:\AI Porject\shorts_factory\original"
os.makedirs(BASE_DIR, exist_ok=True)

def clean_filename(title):
    # 특수문자 및 이모지(cp949 에러 방지용) 완전 제거
    import string
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    cleaned = ''.join(c for c in title if c in valid_chars)
    cleaned = cleaned.replace(" ", "_").strip()
    return cleaned if cleaned else "Trending_Video"

def download_video(query):
    print("=" * 60)
    print(f"[기대리] 바이럴 트렌드 영상 실시간 발굴 시작!")
    print(f"   검색/키워드: '{query}'")
    print("=" * 60)
    
    # 1단계: 검색 및 메타데이터 추출
    search_query = f"ytsearch1:{query} shorts"
    ydl_opts_info = {
        'format': 'best',
        'noplaylist': True,
        'quiet': True,
        'extract_flat': True,
        'match_filter': yt_dlp.utils.match_filter_func("duration <= 60")
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            print("  [SYSTEM] YouTube 검색 및 저작권/링크 스캔 중...")
            info = ydl.extract_info(search_query, download=False)
            
            if 'entries' in info and len(info['entries']) > 0:
                video_info = info['entries'][0]
            else:
                video_info = info
                
            # URL 추출 (웹페이지 URL)
            video_url = video_info.get('url') or video_info.get('webpage_url')
            if not video_url:
                # 추출된 id로 url 조합
                video_url = f"https://www.youtube.com/watch?v={video_info.get('id')}"
                
            raw_title = video_info.get('title', 'Unknown_Video')
            
            # 2단계: 파일명 생성 (영상제목_날짜_시간)
            safe_title = clean_filename(raw_title)
            # 너무 길면 자르기
            if len(safe_title) > 30:
                safe_title = safe_title[:30]
                
            now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
            base_filename = f"{safe_title}_{now}"
            
            video_filepath = os.path.join(BASE_DIR, f"{base_filename}.mp4")
            meta_filepath = os.path.join(BASE_DIR, f"{base_filename}.json")
            
            print(f"  [확인 완료] 유튜브 원본 링크: {video_url}")
            print(f"  [다운로드] 목적지: original 폴더 진행 중...")
            
            # 3단계: 실제 다운로드
            dl_opts = {
                'format': 'best',
                'outtmpl': video_filepath,
                'quiet': True,
                'match_filter': yt_dlp.utils.match_filter_func("duration <= 60")
            }
            with yt_dlp.YoutubeDL(dl_opts) as dl_ydl:
                dl_ydl.download([video_url])
                
            # 4단계: 링크 및 메타데이터 저장
            metadata = {
                "original_title": raw_title,
                "youtube_url": video_url,
                "download_time": datetime.datetime.now().isoformat(),
                "search_keyword": query
            }
            with open(meta_filepath, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=4)
                
            print(f"\n  [기대리 작업 완료] 영상과 메타데이터 확보가 끝났습니다!")
            print(f"     비디오: {base_filename}.mp4")
            print(f"     링크정보: {base_filename}.json")
            print("=" * 60)
            
    except Exception as e:
        print(f"  [오류] 영상 다운로드 실패: {e}")

if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "unbelievable nature moments"
    download_video(q)

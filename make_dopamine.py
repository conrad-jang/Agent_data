"""
[도파민연구소] YouTube Shorts 자동 영상 제작 스크립트
- MoviePy 2.x 호환
- 배경 프레임 자동 리사이즈 (1080x1920)
- frame_config.json 기반 정밀 좌표 배치
- Pillow 기반 한국어 텍스트 렌더링 (ImageMagick 불요)
"""
import os
import json
import re
import cv2
import numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from moviepy import (VideoFileClip, ImageClip, AudioFileClip,
                     CompositeVideoClip, CompositeAudioClip)
import moviepy.video.fx as vfx
from gtts import gTTS
import yt_dlp
import requests

# ===================== [0. 환경 설정] =====================
BASE_DIR   = r"D:\AI Porject\shorts_factory"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
FONT_PATH  = os.path.join(BASE_DIR, "assets", "fonts", "런드리고딕OTF Regular.otf")
CONFIG_PATH = os.path.join(BASE_DIR, "assets", "frame_config.json")

# YouTube Shorts 표준 해상도
SHORTS_W, SHORTS_H = 1080, 1920

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===================== [1. 유틸리티 함수들] =====================

def load_config():
    """frame_config.json 로드"""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def prepare_frame(config):
    """
    배경 프레임(PNG)을 YouTube Shorts 사이즈(1080x1920)로 자동 리사이즈.
    원본이 1536x2752여도 정확히 1080x1920으로 변환.
    """
    frame_path = os.path.join(BASE_DIR, "assets", config['frame_info']['file_name'])
    print(f"[1] 배경 프레임 로드: {frame_path}")
    
    # Pillow로 리사이즈 후 numpy 배열로 변환
    frame_img = Image.open(frame_path).convert('RGBA')
    frame_img = frame_img.resize((SHORTS_W, SHORTS_H), Image.LANCZOS)
    print(f"    리사이즈 완료: {frame_img.size}")
    
    return ImageClip(np.array(frame_img))

def make_text_image(text, size=(1080, 150), font_size=65,
                    color='white', stroke_color='black', stroke_width=4):
    """Pillow 기반 한국어 텍스트 이미지 생성 (ImageMagick 불요)"""
    # 마크다운 기호 & 이스케이프 정리
    text = text.replace("**", "").replace("__", "")
    text = text.replace("\\n", " ").replace("\n", " ").strip()
    
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        print(f"    ⚠ 폰트 로드 실패, 기본 폰트 사용")
        font = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    tx = (size[0] - w) // 2
    ty = (size[1] - h) // 2
    
    # 외곽선(Stroke) 그리기
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            draw.text((tx + dx, ty + dy), text, font=font, fill=stroke_color)
    # 본문
    draw.text((tx, ty), text, font=font, fill=color)
    
    return ImageClip(np.array(img))

def make_title_image(full_title, size=(1000, 150), base_font_size=70,
                     stroke_width=5):
    """
    [모든 숏츠 공통] 두 파트 제목 렌더링 + 글자수 자동 폰트 조정.
    14자 이상이면 폰트 사이즈를 자동 축소하여 제목이 잘리지 않도록 함.
    """
    # 제목을 ':' 기준으로 분리
    if ':' in full_title or '：' in full_title:
        sep = ':' if ':' in full_title else '：'
        parts = full_title.split(sep, 1)
        sub_text = parts[0].strip() + sep.strip()
        main_text = parts[1].strip()
    else:
        sub_text = ""
        main_text = full_title
    
    # ★ 핵심: 글자 수에 따른 폰트 사이즈 자동 조정
    total_chars = len(sub_text) + len(main_text)
    if total_chars >= 20:
        scale_factor = 0.65
    elif total_chars >= 17:
        scale_factor = 0.75
    elif total_chars >= 14:
        scale_factor = 0.85
    else:
        scale_factor = 1.0
    
    adjusted_base = int(base_font_size * scale_factor)
    sub_size  = adjusted_base - 3   # 서브타이틀: 3pt 작게
    main_size = adjusted_base + 2   # 메인타이틀: 2pt 크게
    
    print(f"    제목: '{full_title}' ({total_chars}자) → 폰트: sub={sub_size}, main={main_size}")
    
    sub_color  = '#B0C4DE'           # 밝은 회푸른색 (라이트스틸블루)
    main_color = '#00FFFF'           # 시안 (네온 느낌)
    
    # 폰트 로드 + 캔버스 너비 초과 시 재축소 루프
    max_attempts = 5
    for attempt in range(max_attempts):
        img = Image.new('RGBA', size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        try:
            sub_font  = ImageFont.truetype(FONT_PATH, sub_size)
            main_font = ImageFont.truetype(FONT_PATH, main_size)
        except:
            sub_font = main_font = ImageFont.load_default()
        
        # 전체 폭 계산
        gap = 12
        if sub_text:
            sub_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
            sub_w = sub_bbox[2] - sub_bbox[0]
            sub_h = sub_bbox[3] - sub_bbox[1]
        else:
            sub_w = sub_h = 0
        
        main_bbox = draw.textbbox((0, 0), main_text, font=main_font)
        main_w = main_bbox[2] - main_bbox[0]
        main_h = main_bbox[3] - main_bbox[1]
        
        total_w = sub_w + gap + main_w if sub_text else main_w
        
        # 캔버스 너비의 95% 이내면 OK, 아니면 축소 반복
        if total_w <= size[0] * 0.95:
            break
        sub_size  = int(sub_size * 0.9)
        main_size = int(main_size * 0.9)
        print(f"    → 폰트 재축소 (시도 {attempt+1}): sub={sub_size}, main={main_size}")
    
    max_h = max(sub_h, main_h) if sub_text else main_h
    
    # 중앙 정렬 좌표
    start_x = (size[0] - total_w) // 2
    cy = (size[1] - max_h) // 2
    
    def draw_stroked(x, y, text, font, color):
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                draw.text((x + dx, y + dy), text, font=font, fill='black')
        draw.text((x, y), text, font=font, fill=color)
    
    # 서브타이틀 그리기
    if sub_text:
        draw_stroked(start_x, cy, sub_text, sub_font, sub_color)
        draw_stroked(start_x + sub_w + gap, cy, main_text, main_font, main_color)
    else:
        draw_stroked(start_x, cy, main_text, main_font, main_color)
    
    return ImageClip(np.array(img))

def load_script(script_path):
    """범용 대본 로더: 지정된 마크다운 파일에서 제목 + 대본 데이터 추출"""
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 제목 추출: # [SCRIPT] 서브타이틀: 메인타이틀 (...)
    m = re.search(r'# \[SCRIPT\]\s*(.+?)(?:\n|$)', content)
    title = m.group(1).split('(')[0].strip() if m else "도파민 연구소"
    
    # 테이블 행 추출
    pattern = r'\| \*\*(\d+:\d+-\d+:\d+)\*\* \| (.*?) \| (.*?) \| (.*?) \|'
    rows = re.findall(pattern, content)
    
    script_data = []
    for time_range, audio, visual, caption in rows:
        s_str, e_str = time_range.split('-')
        start = int(s_str.split(':')[0]) * 60 + int(s_str.split(':')[1])
        end   = int(e_str.split(':')[0]) * 60 + int(e_str.split(':')[1])
        script_data.append({
            "start": start, "end": end,
            "audio": audio, "caption": caption
        })
    
    print(f"[2] 대본 로드 완료: '{title}', 구간: {len(script_data)}개")
    return title, script_data

def create_dopamine_shorts(video_path, script_path, use_typecast=False):
    print("=" * 60)
    print(f"  [도파민연구소] YouTube Shorts 제작 (동적 자동화 모드)")
    print(f"  원본 영상: {os.path.basename(video_path).encode('ascii', 'ignore').decode('utf-8')}")
    print(f"  대본 파일: {os.path.basename(script_path).encode('ascii', 'ignore').decode('utf-8')}")
    if use_typecast:
        print(f"  음성 합성: 프리미엄 [타입캐스트 API] 사용")
    else:
        print(f"  음성 합성: 기본 [gTTS 무료] 사용")
    print("=" * 60)
    
    # 데이터 로드
    config = load_config()
    
    # 파일 존재 확인
    if not os.path.exists(video_path):
        print(f"  ⚠ 원본 영상을 찾을 수 없습니다: {video_path}")
        return
    if not os.path.exists(script_path):
        print(f"  ⚠ 대본 파일을 찾을 수 없습니다: {script_path}")
        return
    
    title, script_data = load_script(script_path)
    source_path = video_path
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    
    # ─── Layer 1: 배경 프레임 (dopamine_frame_re.png 사용, 자동 리사이즈) ───
    # 새 프레임 파일명을 직접 지정 (config 오버라이드)
    config['frame_info']['file_name'] = 'dopamine_frame_re.png'
    frame_clip = prepare_frame(config)
    
    # ─── Layer 2: 원본 영상 (Mute + 리사이즈 + 좌표 배치) ───
    print("[4] 원본 영상 편집 중...")
    vid = VideoFileClip(source_path)
    vid = vid.without_audio()                           # 핵심1: 원본 사운드 제거
    if vid.duration > 59.0:
        vid = vid.subclipped(0, 59.0)                   # 원본 롱폼 영상일 경우 강제 59초 크롭
    vid = vfx.MirrorX().apply(vid)                      # 좌우반전(저작권)
    vid = vfx.MultiplySpeed(factor=1.1).apply(vid)      # 미세 속도 조절
    
    # JSON 좌표 기반 + 대표님 수동 조정값 반영
    vc = config['areas']['video_content']
    vid_w = vc['width']         # 900
    vid_h = vc['height'] - 50   # 1400 → 1350
    vid_left = vc['left'] + 80  # 90 → 170 (대표님 수동 조정)
    vid_top  = vc['top'] + 40   # 250 → 290 (대표님 수동 조정)
    print(f"    ★ DEBUG: 영상크기=({vid_w}x{vid_h}), 위치=({vid_left}, {vid_top})")
    vid = vid.resized(width=vid_w, height=vid_h)
    vid = vid.with_position((vid_left, vid_top))
    
    # 프레임 길이를 영상 길이에 맞춤
    frame_clip = frame_clip.with_duration(vid.duration)
    
    # ─── Layer 3: 상단 제목 (서브+메인 2색 렌더링, 모든 숏츠 공통) ───
    tb = config['areas']['title_bar']
    title_top = tb['top'] + 30  # 50 → 80
    title_clip = make_title_image(
        title,
        size=(tb['width'], tb['height']),
        base_font_size=tb['font_size'],
        stroke_width=5
    ).with_duration(vid.duration).with_position((tb['left'], title_top))
    
    # ─── 하단 채널명: 프레임에 이미 있으므로 추가 텍스트 없음 ───
    
    # ─── Layer 4: TTS 오디오 + 자막 캡션 ───
    print("[5] TTS 음성 생성 및 자막 합성 중...")
    audio_segments = []
    caption_clips  = []
    t_cursor = 0  # 음성 공백 제거용 커서
    
    for i, row in enumerate(script_data):
        # TTS 생성 (캐싱)
        tts_ext = "wav" if use_typecast else "mp3"
        tts_path = os.path.join(OUTPUT_DIR, f"tts_{base_name}_{i}.{tts_ext}")
        
        if not os.path.exists(tts_path):
            if use_typecast:
                print(f"    [TTS] Typecast API 생성 중 (1.2배속 시도)... ({i+1}/{len(script_data)})")
                
                prev_text = script_data[i-1]['audio'] if i > 0 else ""
                next_text = script_data[i+1]['audio'] if i < len(script_data) - 1 else ""
                
                url = "https://api.typecast.ai/v1/text-to-speech"
                headers = {"X-API-KEY": "__plt89e4ikksPd6MGmUcwySFQpk8usndoWggJe566tYy", "Content-Type": "application/json"}
                
                # 1. 속도 파라미터를 API에 직접 전달 (정상 속도로 변경)
                payload = {
                    "text": row['audio'],
                    "model": "ssfm-v21",
                    "voice_id": "tc_65c47f4f7e237f1cb0a80380",
                    "prompt": {"emotion_type": "smart", "previous_text": prev_text, "next_text": next_text},
                    "tempo": 1.0
                }
                
                resp = requests.post(url, headers=headers, json=payload)
                if resp.status_code == 400 or resp.status_code == 422 or resp.status_code == 404: # 파라미터 또는 모델 오류시 재시도
                    if "tempo" in payload: del payload["tempo"]
                    if "prompt" in payload: del payload["prompt"]
                    resp = requests.post(url, headers=headers, json=payload)
                
                if resp.status_code == 200:
                    with open(tts_path, 'wb') as f:
                        f.write(resp.content)
                else:
                    print(f"    [오류] Typecast 실패 ({resp.status_code}): {resp.text}, gTTS로 대체합니다.")
                    tts_path_gtts = tts_path.replace(".wav", ".mp3")
                    gTTS(text=row['audio'], lang='ko').save(tts_path_gtts)
                    tts_path = tts_path_gtts
            else:
                gTTS(text=row['audio'], lang='ko').save(tts_path)
        
        # 오디오 로드 및 배속 조절 (사용자 요청: 1.0배속 정상화)
        if not os.path.exists(tts_path):
             seg = AudioFileClip(None, duration=1).with_fps(44100) # 임시
        else:
            seg = AudioFileClip(tts_path)
        
        # '잠시 감상' 구간이라면 3초간 정적 유지
        is_quiet_moment = "잠시 감상" in row['audio']
        
        speed_factor = 1.0 if use_typecast else 1.3
        seg = vfx.MultiplySpeed(factor=speed_factor).apply(seg)
        
        seg = seg.with_start(t_cursor)
        audio_segments.append(seg)
        
        # 자막 시작 시점은 현재 t_cursor
        start_t = t_cursor
        
        t_cursor += seg.duration
        if is_quiet_moment:
            t_cursor += 3.0 # 조용히 감상하는 3초 추가
        
        # 자막
        cap = make_text_image(
            row['caption'],
            size=(1000, 200),
            color='#FFD700', stroke_width=8
        ).with_start(start_t).with_duration(seg.duration).with_position(('center', 1400))
        caption_clips.append(cap)
        
    
    # ─── 최종 합성 (레이어 순서: 영상 → 프레임 → 제목 → 자막) ───
    # 영상이 프레임 뒤에 깔리고, 프레임의 투명 영역을 통해 영상이 보임
    print("[6] 최종 레이어 합성 중...")
    final_video = CompositeVideoClip(
        [vid, frame_clip, title_clip] + caption_clips,
        size=(SHORTS_W, SHORTS_H)
    )
    
    # 오디오 믹싱
    final_audio = CompositeAudioClip(audio_segments)
    final_video = final_video.with_audio(final_audio)
    
    # ─── 렌더링 (사용자 요청: [오늘날짜_시간]_제목.mp4) ───
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    # 파일명 특수문자 안전 처리 (마크다운에서 추출한 title 변수 사용)
    clean_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
    output_name = f"[{timestamp}]_{clean_title}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_name)
    duration = min(vid.duration, t_cursor, 60)  # 최대 60초
    print(f"[7] 렌더링 시작 (길이: {duration:.1f}초)...")
    
    final_video.with_duration(duration).write_videofile(
        output_path, fps=30,
        codec='libx264', audio_codec='aac',
        temp_audiofile='temp-audio.m4a'
    )
    
    print("=" * 60)
    print(f"  [오류 방지 완료] 렌더링 결과물: {output_path}")
    print("=" * 60)

# ===================== [실행] =====================
import sys

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("사용법: python make_dopamine.py <원본영상경로> <대본파일경로> [--typecast]")
        sys.exit(1)
        
    v_path = sys.argv[1]
    s_path = sys.argv[2]
    use_typecast = "--typecast" in sys.argv
    create_dopamine_shorts(video_path=v_path, script_path=s_path, use_typecast=use_typecast)

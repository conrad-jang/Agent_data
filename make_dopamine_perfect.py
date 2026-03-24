"""
[도파민연구소] YouTube Shorts 자동 영상 제작 + 유튜브 업로드 통합 스크립트 (Perfect Edition)
- MoviePy 2.x 호환
- 배경 프레임 자동 리사이즈 (1080x1920)
- Typecast AI 및 gTTS 선택 지원
- 유튜브 자동 업로드 연동
"""
import os
import sys
import json
import re
import cv2
import numpy as np
import subprocess
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
UPLOAD_SCRIPT = os.path.join(BASE_DIR, "upload_to_youtube.py")

# YouTube Shorts 표준 해상도
SHORTS_W, SHORTS_H = 1080, 1920

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===================== [1. 유틸리티 함수들] =====================

def load_config():
    """frame_config.json 로드"""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def prepare_frame(config):
    frame_path = os.path.join(BASE_DIR, "assets", config['frame_info']['file_name'])
    frame_img = Image.open(frame_path).convert('RGBA')
    frame_img = frame_img.resize((SHORTS_W, SHORTS_H), Image.LANCZOS)
    return ImageClip(np.array(frame_img))

def make_text_image(text, size=(1080, 150), font_size=65,
                    color='white', stroke_color='black', stroke_width=4):
    text = text.replace("**", "").replace("__", "")
    text = text.replace("\\n", " ").replace("\n", " ").strip()
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = (size[0] - w) // 2, (size[1] - h) // 2
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            draw.text((tx + dx, ty + dy), text, font=font, fill=stroke_color)
    draw.text((tx, ty), text, font=font, fill=color)
    return ImageClip(np.array(img))

def make_title_image(full_title, size=(1000, 150), base_font_size=70, stroke_width=5):
    if ':' in full_title or '：' in full_title:
        sep = ':' if ':' in full_title else '：'
        parts = full_title.split(sep, 1)
        sub_text, main_text = parts[0].strip() + sep.strip(), parts[1].strip()
    else:
        sub_text, main_text = "", full_title
    
    total_chars = len(sub_text) + len(main_text)
    scale_factor = 0.65 if total_chars >= 20 else 0.75 if total_chars >= 17 else 0.85 if total_chars >= 14 else 1.0
    adjusted_base = int(base_font_size * scale_factor)
    sub_size, main_size = adjusted_base - 3, adjusted_base + 2
    
    sub_color, main_color = '#B0C4DE', '#00FFFF'
    
    max_attempts = 5
    for attempt in range(max_attempts):
        img = Image.new('RGBA', size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        try:
            sub_font, main_font = ImageFont.truetype(FONT_PATH, sub_size), ImageFont.truetype(FONT_PATH, main_size)
        except:
            sub_font = main_font = ImageFont.load_default()
        
        gap = 12
        sub_w = draw.textbbox((0, 0), sub_text, font=sub_font)[2] if sub_text else 0
        main_w = draw.textbbox((0, 0), main_text, font=main_font)[2]
        total_w = sub_w + gap + main_w if sub_text else main_w
        if total_w <= size[0] * 0.95: break
        sub_size, main_size = int(sub_size * 0.9), int(main_size * 0.9)
    
    start_x = (size[0] - total_w) // 2
    cy = (size[1] - max(sub_size, main_size)) // 2
    
    def draw_stroked(x, y, text, font, color):
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                draw.text((x + dx, y + dy), text, font=font, fill='black')
        draw.text((x, y), text, font=font, fill=color)
    
    if sub_text:
        draw_stroked(start_x, cy, sub_text, sub_font, sub_color)
        draw_stroked(start_x + sub_w + gap, cy, main_text, main_font, main_color)
    else:
        draw_stroked(start_x, cy, main_text, main_font, main_color)
    return ImageClip(np.array(img))

def load_script(script_path):
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 제목 추출
    m = re.search(r'# \[SCRIPT\]\s*(.+?)(?:\n|$)', content)
    title = m.group(1).split('(')[0].strip() if m else "도파민 연구소"
    
    # 상세 설명 추출 (> Description: (...) 형태)
    desc_m = re.search(r'> Description:\s*(.+?)(?:\n|>|$)', content, re.DOTALL)
    description = desc_m.group(1).strip() if desc_m else ""
    
    # 해시태그 추출 (> Hashtags: #태그 ... 형태)
    hash_m = re.search(r'> Hashtags:\s*(.+?)(?:\n|$)', content)
    hashtags = hash_m.group(1).strip() if hash_m else ""

    pattern = r'\| \*\*(\d+:\d+-\d+:\d+)\*\* \| (.*?) \| (.*?) \| (.*?) \|'
    rows = re.findall(pattern, content)
    script_data = [{"start": int(s.split(':')[0])*60 + int(s.split(':')[1]), 
                    "end": int(e.split(':')[0])*60 + int(e.split(':')[1]),
                    "audio": a, "caption": c} for (tr, a, v, c) in rows for s, e in [tr.split('-')]]
    
    return title, description, hashtags, script_data

def create_dopamine_shorts(video_path, script_path, use_typecast=False, upload=False, privacy="unlisted"):
    print("=" * 60)
    print(f"  [도파민연구소] YouTube Shorts 제작 (Perfect Edition)")
    print(f"  - 원본: {os.path.basename(video_path)}")
    print(f"  - 대본: {os.path.basename(script_path)}")
    print(f"  - TTS: {'Typecast' if use_typecast else 'gTTS'}")
    print(f"  - 업로드 예정: {'YES (' + privacy + ')' if upload else 'NO'}")
    print("=" * 60)
    
    title, script_desc, script_tags, script_data = load_script(script_path)
    config = load_config()
    config['frame_info']['file_name'] = 'dopamine_frame_re.png'
    frame_clip = prepare_frame(config)
    
    vid = VideoFileClip(video_path).without_audio()
    if vid.duration > 59.0: vid = vid.subclipped(0, 59.0)
    vid = vfx.MirrorX().apply(vid)
    vid = vfx.MultiplySpeed(factor=1.1).apply(vid)
    
    vc = config['areas']['video_content']
    vid = vid.resized(width=vc['width'], height=vc['height'] - 50).with_position((vc['left'] + 80, vc['top'] + 40))
    frame_clip = frame_clip.with_duration(vid.duration)
    
    tb = config['areas']['title_bar']
    title_clip = make_title_image(title, size=(tb['width'], tb['height']), base_font_size=tb['font_size']).with_duration(vid.duration).with_position((tb['left'], tb['top'] + 30))
    
    audio_segments, caption_clips, t_cursor = [], [], 0
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    
    for i, row in enumerate(script_data):
        tts_ext = "wav" if use_typecast else "mp3"
        tts_path = os.path.join(OUTPUT_DIR, f"tts_{base_name}_{i}.{tts_ext}")
        
        if not os.path.exists(tts_path):
            if use_typecast:
                url = "https://api.typecast.ai/v1/text-to-speech"
                headers = {"X-API-KEY": "__plt89e4ikksPd6MGmUcwySFQpk8usndoWggJe566tYy", "Content-Type": "application/json"}
                payload = {"text": row['audio'], "model": "ssfm-v21", "voice_id": "tc_65c47f4f7e237f1cb0a80380", "prompt": {"emotion_type": "smart"}, "tempo": 1.0}
                resp = requests.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    with open(tts_path, 'wb') as f: f.write(resp.content)
                else: gTTS(text=row['audio'], lang='ko').save(tts_path.replace(".wav", ".mp3")); tts_path = tts_path.replace(".wav", ".mp3")
            else: gTTS(text=row['audio'], lang='ko').save(tts_path)
        
        seg = AudioFileClip(tts_path) if os.path.exists(tts_path) else AudioFileClip(None, duration=1).with_fps(44100)
        is_quiet = "잠시 감상" in row['audio']
        seg = vfx.MultiplySpeed(factor=1.0 if use_typecast else 1.3).apply(seg)
        seg = seg.with_start(t_cursor)
        audio_segments.append(seg)
        
        start_t = t_cursor
        t_cursor += seg.duration
        if is_quiet: t_cursor += 3.0
        
        cap = make_text_image(row['caption'], size=(1000, 200), color='#FFD700', stroke_width=8).with_start(start_t).with_duration(seg.duration).with_position(('center', 1400))
        caption_clips.append(cap)
        
    final_video = CompositeVideoClip([vid, frame_clip, title_clip] + caption_clips, size=(SHORTS_W, SHORTS_H)).with_audio(CompositeAudioClip(audio_segments))
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    clean_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
    output_name = f"[{timestamp}]_{clean_title}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_name)
    duration = min(vid.duration, t_cursor, 60)
    
    final_video.with_duration(duration).write_videofile(output_path, fps=30, codec='libx264', audio_codec='aac')
    print(f"\n[성공] 영상 제작 완료: {output_path}")

    # ─── YouTube 업로드 연동 ───
    if upload:
        print(f"\n[YouTube] 업로드 프로세스 시작...")
        cmd = [
            sys.executable, UPLOAD_SCRIPT,
            "--file", output_path,
            "--title", title,
            "--desc", f"{script_desc}\n\n도파민연구소가 선사하는 최고의 즐거움! #shorts #도파민연구소",
            "--tags", f"{script_tags},도파민연구소,shorts",
            "--privacy", privacy
        ]
        try:
            subprocess.run(cmd, check=True)
            print("[YouTube] 모든 프로세스가 성공적으로 완료되었습니다.")
        except Exception as e:
            print(f"[YouTube 오류] 업로드 중 문제가 발생했습니다: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="원본 영상 경로")
    parser.add_argument("script", help="대본 파일 경로")
    parser.add_argument("--typecast", action="store_true", help="타입캐스트 사용")
    parser.add_argument("--upload", action="store_true", help="유튜브 자동 업로드")
    parser.add_argument("--privacy", default="unlisted", help="개인 정보 보호 설정 (private/unlisted/public)")
    
    args = parser.parse_args()
    create_dopamine_shorts(args.video, args.script, use_typecast=args.typecast, upload=args.upload, privacy=args.privacy)

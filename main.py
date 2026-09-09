import os
import uuid
import subprocess
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="AliPiano Shorts Engine V2 - Ultra Simple")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Request(BaseModel):
    input_type: str  # "youtube" or "text"
    content: str     # YouTube URL or text
    brand_text: str = "AliPiano.ir | One Hand, One Dream"

jobs = {}

def generate_thumbnail(video_path: str, output_path: str):
    """ساخت thumbnail از بهترین فریم ویدیو (ثانیه ۱۰)"""
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-ss", "10",  # فریم ثانیه ۱۰
        "-vframes", "1",
        "-vf", "scale=1280:720",
        output_path
    ], capture_output=True)

def generate_caption_template(brand: str) -> str:
    """تولید کپشن آماده با هشتگ‌های مرتبط"""
    return f"""🎹 {brand}

اگر از این ویدیو لذت بردی، لایک و سابسکرایب یادت نره! ❤️

#پیانو #موسیقی #آموزش_پیانو #دست_چپ #AliPiano #OneHandOneDream #Piano #LeftHandPiano #Music #PianoTutorial
"""

def process_video(req: Request, job_id: str):
    try:
        jobs[job_id]["status"] = "downloading"
        
        # مسیرهای موقت
        temp_dir = f"/tmp/{job_id}"
        os.makedirs(temp_dir, exist_ok=True)
        video_path = os.path.join(temp_dir, "input.mp4")
        final_path = os.path.join(temp_dir, "final.mp4")
        thumb_path = os.path.join(temp_dir, "thumbnail.jpg")

        # ۱. دانلود هوشمند (فقط ۶۰ ثانیه اول)
        import yt_dlp
        ydl_opts = {
            "format": "mp4[height<=720]/best[height<=720]",
            "outtmpl": video_path,
            "noplaylist": True,
            "quiet": True,
            "max_filesize": 50 * 1024 * 1024,  # حداکثر ۵۰ مگابایت
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.content, download=False)
            duration = info.get("duration", 60)
            
            # انتخاب هوشمند نقطه شروع
            if duration > 120:
                # اگر ویدیو طولانی است، از وسط شروع کن
                start_time = duration // 2 - 30
            else:
                # اگر کوتاه است، از اول
                start_time = 0
            
            ydl_opts["download_ranges"] = lambda info, ydl: [{"start_time": start_time, "end_time": start_time + 60}]
            ydl.download([req.content])

        jobs[job_id]["status"] = "processing"

        # ۲. برش ۹:۱۶ + واترمارک با FFmpeg (فوق‌ساده)
        brand = req.brand_text.replace("'", "\\'")
        
        # فیلتر FFmpeg:
        # - crop: برش به نسبت ۹:۱۶ (عمودی)
        # - scale: تغییر اندازه به ۱۰۸۰x۱۹۲۰
        # - drawtext: اضافه کردن واترمارک
        vf = (
            "crop=ih*9/16:ih,"
            "scale=1080:1920,"
            f"drawtext=text='{brand}':"
            "fontsize=32:fontcolor=#FFB800:"
            "x=40:y=40:"
            "borderw=2:bordercolor=black"
        )

        subprocess.run([
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf,
            "-t", "30",  # فقط ۳۰ ثانیه خروجی
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", "128k",
            final_path
        ], capture_output=True, timeout=120)

        jobs[job_id]["status"] = "generating_extras"

        # ۳. ساخت thumbnail
        generate_thumbnail(video_path, thumb_path)

        # ۴. تولید کپشن
        caption = generate_caption_template(req.brand_text)

        jobs[job_id]["status"] = "done"
        jobs[job_id]["video"] = final_path
        jobs[job_id]["thumbnail"] = thumb_path
        jobs[job_id]["caption"] = caption

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)

@app.post("/generate")
async def generate(req: Request, bg: BackgroundTasks):
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {"status": "queued"}
    bg.add_task(process_video, req, job_id)
    return {"job_id": job_id, "status": "queued"}

@app.get("/status/{job_id}")
async def status(job_id: str):
    if job_id not in jobs:
        return {"error": "not found"}
    return jobs[job_id]

@app.get("/health")
async def health():
    return {"status": "alive", "engine": "AliPiano Shorts V2"}

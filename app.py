import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl

import yt_dlp

app = FastAPI(title="YT to MP3 API", version="1.0.0")

# App (Flutter) calls are not blocked by browser CORS, but enabling CORS
# makes it easier if you later add a Web frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConvertRequest(BaseModel):
    url: HttpUrl


def _safe_filename(name: str) -> str:
    # Remove characters that are invalid on Windows/macOS/Linux
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] if len(name) > 180 else name


def _cleanup_dir(path: str) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/youtube/mp3")
def youtube_to_mp3(req: ConvertRequest, bg: BackgroundTasks):
    # Create an isolated temp folder per request
    job_id = str(uuid.uuid4())
    workdir = Path(tempfile.gettempdir()) / f"ytmp3_{job_id}"
    workdir.mkdir(parents=True, exist_ok=True)

    # Ensure temp folder is cleaned after response is sent
    bg.add_task(_cleanup_dir, str(workdir))

    # yt-dlp settings
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(workdir / "%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(str(req.url), download=True)

        # Find the produced mp3
        mp3_files = list(workdir.glob("*.mp3"))
        if not mp3_files:
            # Sometimes title is nested; do a broader search just in case
            mp3_files = list(workdir.rglob("*.mp3"))
        if not mp3_files:
            raise RuntimeError("MP3 not generated (ffmpeg missing or conversion failed).")

        mp3_path = mp3_files[0]

        title = info.get("title") or mp3_path.stem
        filename = _safe_filename(f"{title}.mp3")

        return FileResponse(
            path=str(mp3_path),
            media_type="audio/mpeg",
            filename=filename,
            background=bg,
        )

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"yt-dlp download error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)

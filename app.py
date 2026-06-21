import base64
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

app = FastAPI(title="YT to MP3 API", version="1.1.0")

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


def _get_cookie_file() -> str | None:
    """
    Return a cookies.txt file path for yt-dlp.

    Railway cannot use --cookies-from-browser because there is no real browser profile
    inside the container. The safest deployment flow is:
      1. Export YouTube cookies as a Netscape cookies.txt file locally.
      2. Base64 encode the file.
      3. Put the encoded string in Railway variable YTDLP_COOKIES_BASE64.

    Also supported:
      - YTDLP_COOKIES_FILE: an existing file path inside the container
      - YTDLP_COOKIES: raw cookies.txt content, useful locally
    """
    cookie_file = os.getenv("YTDLP_COOKIES_FILE")
    if cookie_file and Path(cookie_file).is_file():
        return cookie_file

    cookies_base64 = os.getenv("YTDLP_COOKIES_BASE64")
    cookies_raw = os.getenv("YTDLP_COOKIES")

    if not cookies_base64 and not cookies_raw:
        return None

    try:
        if cookies_base64:
            content = base64.b64decode(cookies_base64).decode("utf-8")
        else:
            # Allows either real newlines or escaped \n in environment variables.
            content = cookies_raw.replace("\\n", "\n")
    except Exception as exc:
        raise RuntimeError("Invalid YouTube cookies env. Check YTDLP_COOKIES_BASE64/YTDLP_COOKIES.") from exc

    cookie_path = Path(tempfile.gettempdir()) / "yt_dlp_youtube_cookies.txt"
    cookie_path.write_text(content, encoding="utf-8")

    try:
        cookie_path.chmod(0o600)
    except Exception:
        pass

    return str(cookie_path)


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
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7",
        },
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    try:
        cookie_file = _get_cookie_file()
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file

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
        msg = str(e)
        if "Sign in to confirm" in msg or "not a bot" in msg:
            msg = (
                "YouTube is requiring authentication/cookies for this video or server IP. "
                "Set Railway variable YTDLP_COOKIES_BASE64 with a valid Netscape cookies.txt file. "
                f"Original yt-dlp error: {e}"
            )
        raise HTTPException(status_code=400, detail=f"yt-dlp download error: {msg}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)

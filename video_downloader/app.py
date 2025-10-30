import os
import re
import tempfile
import shutil
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app = Flask(__name__, template_folder=TEMPLATES_DIR)

TMP_ROOT = Path(tempfile.gettempdir()) / "flask_video_downloader"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

YOUTUBE_URL_RE = re.compile(r"(youtube\.com|youtu\.be)")

# --- Helpers ------------------------------------------------------

def _safe_filename(name: str) -> str:
    name = secure_filename(name or "video")
    if not name.lower().endswith(".mp4"):
        name += ".mp4"
    return name

def _download_youtube(url: str, out_path: Path, quality: str = "best") -> Path:
    quality_map = {
        "2160": "bestvideo[height<=2160]+bestaudio/best",
        "1440": "bestvideo[height<=1440]+bestaudio/best",
        "1080": "bestvideo[height<=1080]+bestaudio/best",
        "720":  "bestvideo[height<=720]+bestaudio/best",
        "480":  "bestvideo[height<=480]+bestaudio/best",
        "best": "bestvideo+bestaudio/best",
    }
    fmt = quality_map.get(quality, "bestvideo+bestaudio/best")

    output_file = out_path / "%(title)s.%(ext)s"
    cmd = [
        "yt-dlp",
        "-f", fmt,
        "--merge-output-format", "mp4",
        "-o", str(output_file.as_posix()),  # use forward slashes
        url
    ]

    # run yt-dlp and capture errors
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp failed")

    files = list(out_path.glob("*.mp4"))
    if not files:
        raise RuntimeError("No mp4 file found after download.")
    return files[0]

def _download_direct(url: str, out_path: Path) -> Path:
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    ext = Path(url.split("?")[0]).suffix or ".mp4"
    filename = out_path / f"downloaded_video{ext}"
    with open(filename, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return filename

# --- Routes ------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url", "").strip()
    custom_name = request.form.get("filename", "").strip()
    quality = request.form.get("quality", "best")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    tmpdir = Path(tempfile.mkdtemp(prefix="vd__", dir=TMP_ROOT))
    try:
        if YOUTUBE_URL_RE.search(url):
            downloaded_path = _download_youtube(url, tmpdir, quality)
        else:
            downloaded_path = _download_direct(url, tmpdir)

        user_filename = _safe_filename(custom_name or downloaded_path.stem)
        final_path = tmpdir / user_filename
        downloaded_path.rename(final_path)

        return send_file(
            str(final_path),
            as_attachment=True,
            download_name=user_filename,
            mimetype="application/octet-stream"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass

# --- Run ---------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

import sys
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OCR_DIR = BASE_DIR / "assets" / "models" / "ocr"
FACE_DIR = BASE_DIR / "assets" / "models" / "face"
VIDEO_DIR = BASE_DIR / "assets" / "models" / "video"

OCR_DIR.mkdir(parents=True, exist_ok=True)
FACE_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

MODELS = [
    # 1. OCR Models
    (
        OCR_DIR / "ara.traineddata",
        "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/ara.traineddata"
    ),
    (
        OCR_DIR / "arabic_rec.onnx",
        "https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/arabic/rec.onnx"
    ),
    (
        OCR_DIR / "arabic_dict.txt",
        "https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/arabic/dict.txt"
    ),
    # 2. Face Recognition (MobileFaceNet / Buffalo_s)
    (
        FACE_DIR / "mobilefacenet.onnx",
        "https://huggingface.co/immich-app/buffalo_s/resolve/main/recognition/model.onnx"
    ),
    # 3. Video Visual Classifier (MobileNetV2)
    (
        VIDEO_DIR / "mobilenetv2_video.onnx",
        "https://huggingface.co/onnx-community/mobilenet_v2_1.0_224/resolve/main/onnx/model_int8.onnx"
    )
]


def download_file(dest_path: Path, url: str, max_retries: int = 5, min_size: int | None = None) -> bool:
    if min_size is None:
        min_size = 50 if dest_path.suffix.lower() in [".txt", ".json", ".csv"] else 1000

    if dest_path.exists() and dest_path.stat().st_size >= min_size:
        print(f"ALREADY EXISTS: {dest_path.name} ({dest_path.stat().st_size} bytes)")
        return True

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_error = ""
    for attempt in range(1, max_retries + 1):
        print(f"DOWNLOADING: {dest_path.name} from {url}... (attempt {attempt}/{max_retries})")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                content = resp.read()
                with open(dest_path, "wb") as f:
                    f.write(content)
            size = dest_path.stat().st_size
            if size < min_size:
                raise ValueError(f"downloaded file suspiciously small ({size} bytes, expected >= {min_size})")
            print(f"SAVED: {dest_path.name} ({size} bytes)")
            return True
        except Exception as exc:
            last_error = str(exc)
            print(f"ERROR downloading {dest_path.name} (attempt {attempt}): {exc}")
            if dest_path.exists():
                dest_path.unlink()
            if attempt < max_retries:
                wait_seconds = 10 * attempt
                print(f"Retrying in {wait_seconds}s...")
                time.sleep(wait_seconds)
    print(f"FAILED to download {dest_path.name} after {max_retries} attempts. Last error: {last_error}")
    return False


if __name__ == "__main__":
    success = True
    for dest, url in MODELS:
        ok = download_file(dest, url)
        if not ok:
            success = False
    print("Download finished with status:", success)
    if not success:
        sys.exit(1)

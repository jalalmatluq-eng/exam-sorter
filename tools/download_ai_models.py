import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
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

def download_file(dest_path: Path, url: str) -> bool:
    if dest_path.exists() and dest_path.stat().st_size > 1000:
        print(f"ALREADY EXISTS: {dest_path.name} ({dest_path.stat().st_size} bytes)")
        return True
    
    print(f"DOWNLOADING: {dest_path.name} from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = resp.read()
            with open(dest_path, "wb") as f:
                f.write(content)
        print(f"SAVED: {dest_path.name} ({dest_path.stat().st_size} bytes)")
        return True
    except Exception as exc:
        print(f"ERROR downloading {dest_path.name}: {exc}")
        if dest_path.exists():
            dest_path.unlink()
        return False

if __name__ == "__main__":
    success = True
    for dest, url in MODELS:
        ok = download_file(dest, url)
        if not ok:
            success = False
    print("Download finished with status:", success)

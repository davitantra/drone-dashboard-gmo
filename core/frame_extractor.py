import os, subprocess, glob
from config import FFMPEG_PATH

def extract_frames(video_path: str, output_dir: str, fps: float = 0.5) -> list:
    """
    Ekstrak frame dari video MP4 menggunakan ffmpeg.
    Return list path file JPG yang berhasil diekstrak.
    """
    os.makedirs(output_dir, exist_ok=True)
    pattern = os.path.join(output_dir, "frame_%04d.jpg")
    cmd = [
        FFMPEG_PATH, "-y", "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",
        pattern
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr[-500:]}")
    frames = sorted(glob.glob(os.path.join(output_dir, "frame_*.jpg")))
    return frames

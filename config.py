import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "drone_dashboard.db")

FFMPEG_PATH = r"C:\Users\davi.tantra\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"

# DJI Air3s
IMG_W = 1920
IMG_H = 1080
HFOV_DEG = 84.0
VFOV_DEG = 63.0

# Planting grid
HOLE_SPACING_M = 4.0

# UTM Zone 50N
UTM_CENTRAL_MERIDIAN = 117.0

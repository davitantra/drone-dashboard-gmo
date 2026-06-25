import cv2
import math
import numpy as np
from core.gps_projection import pixel_to_gps, footprint_meters
from core.canopy_classifier import classify_canopy
from config import IMG_W, IMG_H, HOLE_SPACING_M

# HSV range untuk hijau
HSV_LOW  = np.array([22,  12,  20])
HSV_HIGH = np.array([95, 255, 255])

def _green_blob_diameter_px(img_bgr, cx, cy, search_r=40):
    """Ukur diameter blob hijau di sekitar titik (cx, cy) dalam pixel."""
    x1, x2 = max(0, cx-search_r), min(img_bgr.shape[1], cx+search_r)
    y1, y2 = max(0, cy-search_r), min(img_bgr.shape[0], cy+search_r)
    roi = img_bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    hsv  = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, HSV_LOW, HSV_HIGH)
    # Hitung bounding box blob hijau
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < 4:
        return 0.0
    # Diameter dari area (asumsi lingkaran)
    return 2 * math.sqrt(area / math.pi)

def detect_holes(img_path: str, drone_lat: float, drone_lon: float, alt: float,
                 usia_bulan: int, thresholds: list) -> list:
    """
    Deteksi lubang tanam dalam satu frame gambar.
    Return list of dict: {lat, lon, status_tanam, diameter_tajuk_m, kategori_tajuk}
    """
    img = cv2.imread(img_path)
    if img is None:
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 4
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    morph  = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    morph  = cv2.morphologyEx(morph,  cv2.MORPH_OPEN,  kernel, iterations=1)

    contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Estimasi px_per_meter dari footprint kamera
    fp_w, _ = footprint_meters(alt)
    px_per_meter = IMG_W / fp_w

    holes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 80 or area > 8000:
            continue
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circularity = 4 * math.pi * area / (perimeter ** 2)
        if circularity < 0.25:
            continue

        M  = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        lat, lon = pixel_to_gps(cx, cy, drone_lat, drone_lon, alt)

        # Ukur tajuk
        blob_px = _green_blob_diameter_px(img, cx, cy)
        diameter_m = (blob_px / px_per_meter) if blob_px > 0 else None

        # Klasifikasi ditanam/kosong
        n_green = int(cv2.countNonZero(
            cv2.inRange(
                cv2.cvtColor(
                    img[max(0,cy-22):cy+22, max(0,cx-22):cx+22],
                    cv2.COLOR_BGR2HSV
                ), HSV_LOW, HSV_HIGH
            )
        ))
        total_px = 44 * 44
        green_pct = n_green / max(total_px, 1)
        status = "ditanam" if (green_pct >= 0.01 or n_green >= 3) else "kosong"

        kategori = classify_canopy(diameter_m, usia_bulan, thresholds)

        holes.append({
            "lat": lat, "lon": lon,
            "status_tanam": status,
            "diameter_tajuk_m": diameter_m,
            "kategori_tajuk": kategori,
        })
    return holes

# Drone Dashboard GMO

Dashboard berbasis web untuk tim lapangan revegetasi (GMO/General Management Office) yang memproses video drone, mendeteksi lubang tanam, dan menganalisis kesehatan kanopi tanaman.

Berjalan di **LAN server lokal** — tidak membutuhkan koneksi internet.

---

## Fitur Utama

### 🗺️ Peta & Analisis
- Visualisasi hasil deteksi lubang tanam di peta Leaflet
- Ringkasan per blok: total lubang, hijau/oranye/merah, coverage
- Export data ke CSV dan Excel

### 📁 Boundary
- Upload shapefile area kerja (.zip: shp + dbf + prj + shx)
- Konversi UTM Zone 50N → WGS84 otomatis (EPSG:32650)
- Manajemen blok revegetasi: luas, bulan tanam, target lubang

### 📹 Sesi Drone
- Upload video MP4 + file SRT (GPS telemetry DJI)
- Pipeline otomatis: ekstrak frame → parse GPS → deteksi lubang → deduplication → analisis kanopi
- Progress real-time via SSE

### 🔍 Review Frame
- Grid semua frame yang diproses per sesi
- Modal per frame: lihat lubang terdeteksi overlay di atas gambar
- Klik lubang → tandai **Ditanam** / **Kosong** / **Hapus**
- Tambah lubang manual dengan klik di area kosong
- "Hapus Semua Frame Ini" untuk bersihkan per frame

### 🤖 Auto-tune
- **Auto-tune Parameter**: grid search 36 kombinasi (circularity × area scale) menggunakan reviewed frames sebagai ground truth; rejected holes sebagai explicit FP penalty
- **Auto-tune HSV**: analisis threshold green pixel % dari lubang berlabel ditanam/kosong untuk mengoptimalkan deteksi vegetasi

---

## Arsitektur

```
drone-dashboard/
├── app.py                  # Flask entry point
├── config.py               # Paths & settings
├── database.py             # SQLite schema + migrations
├── requirements.txt
├── api/
│   ├── boundaries.py       # CRUD boundary & blok
│   ├── sessions.py         # Session + pipeline + review endpoints
│   ├── map_data.py         # GeoJSON lubang + blok
│   └── export.py           # CSV / Excel export
├── core/
│   ├── hole_detector.py    # OpenCV: adaptive threshold + Hough circles + HSV masking
│   ├── deduplicator.py     # Deduplikasi lubang 2×2m grid majority vote
│   ├── frame_extractor.py  # ffmpeg: ekstrak frame 0.5 fps
│   ├── srt_parser.py       # Parse GPS telemetry dari SRT DJI
│   ├── gps_projection.py   # Pixel → GPS (pyproj EPSG:32650)
│   ├── shapefile_manager.py# Shapefile loader + point-in-polygon
│   └── canopy_classifier.py# Klasifikasi hijau/oranye/merah berdasarkan usia
├── templates/
│   └── index.html          # SPA utama
└── static/
    ├── css/style.css
    └── js/
        ├── app.js          # UI logic + review modal + auto-tune
        └── map.js          # Leaflet map + layer management
```

## Database Schema

| Tabel | Deskripsi |
|---|---|
| `boundaries` | Area kerja shapefile |
| `bloks` | Sub-area per boundary |
| `drone_sessions` | Sesi penerbangan drone |
| `lubang_deteksi` | Lubang terdeteksi (auto/manual), dengan `frame_video`, `frame_filename`, `source`, `status_tanam` |
| `reviewed_frames` | Frame yang sudah direview |
| `rejected_holes` | Lubang yang dihapus manual (dipakai auto-tune sebagai negative examples) |
| `canopy_thresholds` | Threshold diameter tajuk per usia tanaman |

---

## Instalasi

### Prasyarat
- Python 3.10+
- ffmpeg (tersedia di PATH)

### Setup

```bash
git clone <repo-url>
cd drone-dashboard
pip install -r requirements.txt
python app.py
```

Buka browser: `http://localhost:5000`

---

## Alur Penggunaan

1. **Upload Boundary** — tab Boundary → upload .zip shapefile
2. **Buat Sesi Drone** — tab Sesi → upload MP4 + SRT → klik proses
3. **Lihat di Peta** — tab Peta → pilih sesi → lubang tampil di peta
4. **Review Frame** — tab Review → pilih sesi → klik frame → tandai lubang
5. **Auto-tune** — setelah review beberapa frame → klik "Auto-tune Parameter"

---

## Stack Teknologi

| Layer | Teknologi |
|---|---|
| Backend | Flask, SQLite, pyproj |
| Computer Vision | OpenCV (adaptive threshold, Hough circles, HSV masking) |
| Frontend | Vanilla JS, Leaflet.js |
| Video processing | ffmpeg via subprocess |
| Shapefile | shapefile (pyshp) |

---

## Development History

Dibangun secara iteratif dalam 17 task:

- **Task 1–5**: Scaffold, SRT parser, GPS projection, canopy classifier, hole detector, frame extractor, shapefile manager
- **Task 6–8**: REST API (boundaries, sessions, map data, export)
- **Task 9–10**: Frontend SPA + integrasi end-to-end
- **Task 11–13**: Peta boundary + blok, session management UI
- **Task 14**: Review tab — frame grid
- **Task 15**: Canvas overlay: klik tambah/hapus lubang, pixel-to-GPS
- **Task 16**: Hole detector improvements — Hough circles, HSV green mask, dynamic area bounds, auto-tune dari reviewed frames
- **Task 17**: `rejected_holes` tracking, auto-tune HSV, label ditanam/kosong, hapus per frame

---

*Dikembangkan untuk tim revegetasi GMO — BerauCoal, Kalimantan Timur*

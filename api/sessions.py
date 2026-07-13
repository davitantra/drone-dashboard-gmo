import os, json, math, threading, time, glob, shutil
from datetime import datetime
from flask import Blueprint, request, jsonify, Response
from database import get_db
from core.srt_parser import parse_srt
from core.frame_extractor import extract_frames
from core.hole_detector import detect_holes
from core.deduplicator import deduplicate
from core.shapefile_manager import load_shapefile, find_blok_for_point
from core.gps_projection import wgs84_to_utm50n
from core.canopy_classifier import get_usia_bulan
from config import UPLOAD_DIR

bp = Blueprint("sessions", __name__)
_progress = {}  # session_id -> {pct, msg, done}


def _now():
    return datetime.utcnow().isoformat()


# ──────────────────────────────────────────────
# GET /api/sessions
# ──────────────────────────────────────────────
@bp.route("", methods=["GET"])
def list_sessions():
    db = get_db()
    rows = db.execute(
        "SELECT id, nama, tanggal_terbang, boundary_id, status, created_at "
        "FROM drone_sessions ORDER BY created_at DESC"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


# ──────────────────────────────────────────────
# POST /api/sessions
# ──────────────────────────────────────────────
@bp.route("", methods=["POST"])
def create_session():
    nama        = request.form.get("nama", "Sesi Drone")
    tgl         = request.form.get("tanggal_terbang", datetime.utcnow().strftime("%Y-%m-%d"))
    boundary_id = request.form.get("boundary_id")
    videos      = request.files.getlist("videos")
    if not videos:
        return jsonify({"error": "Upload minimal 1 file video"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO drone_sessions (nama, tanggal_terbang, boundary_id, status, video_files, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (nama, tgl, boundary_id, "pending", "[]", _now())
    )
    sid = cur.lastrowid
    db.commit()
    db.close()

    sess_dir = os.path.join(UPLOAD_DIR, f"session_{sid}")
    vid_dir  = os.path.join(sess_dir, "videos")
    os.makedirs(vid_dir, exist_ok=True)

    saved = []
    for v in videos:
        dst = os.path.join(vid_dir, v.filename)
        v.save(dst)
        saved.append(v.filename)

    # SRT files uploaded alongside videos
    srts = request.files.getlist("srts")
    for s in srts:
        s.save(os.path.join(vid_dir, s.filename))

    db = get_db()
    db.execute("UPDATE drone_sessions SET video_files=? WHERE id=?", (json.dumps(saved), sid))
    db.commit()
    db.close()

    return jsonify({"id": sid, "nama": nama, "status": "pending"}), 201


# ──────────────────────────────────────────────
# DELETE /api/sessions/<sid>
# ──────────────────────────────────────────────
@bp.route("/<int:sid>", methods=["DELETE"])
def delete_session(sid):
    from config import UPLOAD_DIR
    db = get_db()
    row = db.execute("SELECT id FROM drone_sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Not found"}), 404
    sess_dir = os.path.join(UPLOAD_DIR, f"session_{sid}")
    shutil.rmtree(sess_dir, ignore_errors=True)
    db.execute("DELETE FROM drone_sessions WHERE id=?", (sid,))
    db.commit()
    db.close()
    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# POST /api/sessions/<sid>/process
# ──────────────────────────────────────────────
@bp.route("/<int:sid>/process", methods=["POST"])
def process_session(sid):
    db = get_db()
    row = db.execute("SELECT status FROM drone_sessions WHERE id=?", (sid,)).fetchone()
    db.close()
    if row is None:
        return jsonify({"error": "Not found"}), 404
    if row["status"] not in ("pending", "error"):
        return jsonify({"error": "Session sudah diproses atau sedang diproses"}), 409
    thread = threading.Thread(target=_run_pipeline, args=(sid,), daemon=True)
    thread.start()
    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# GET /api/sessions/<sid>/status  (SSE)
# ──────────────────────────────────────────────
@bp.route("/<int:sid>/status", methods=["GET"])
def session_status(sid):
    def generate():
        while True:
            prog = _progress.get(sid, {"pct": 0, "msg": "Menunggu...", "done": False})
            yield f"data: {json.dumps(prog)}\n\n"
            if prog.get("done"):
                break
            time.sleep(1)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _set_progress(sid, pct, msg, done=False):
    _progress[sid] = {"pct": pct, "msg": msg, "done": done}


def _run_pipeline(sid: int):
    db = get_db()
    try:
        row = db.execute(
            "SELECT tanggal_terbang, boundary_id, video_files FROM drone_sessions WHERE id=?", (sid,)
        ).fetchone()
        if row is None:
            _set_progress(sid, 0, f"Session {sid} tidak ditemukan.", done=True)
            return

        tanggal     = row["tanggal_terbang"]
        boundary_id = row["boundary_id"]
        video_files = json.loads(row["video_files"] or "[]")

        db.execute("UPDATE drone_sessions SET status='processing' WHERE id=?", (sid,))
        db.commit()

        # Load boundary bloks (geometry list for spatial lookup + DB rows for metadata)
        bloks_geom = []
        bloks_db   = []
        if boundary_id:
            shp_row = db.execute(
                "SELECT shp_dir FROM boundaries WHERE id=?", (boundary_id,)
            ).fetchone()
            if shp_row:
                try:
                    bloks_geom = load_shapefile(shp_row["shp_dir"])
                except Exception:
                    bloks_geom = []
            bloks_db = db.execute(
                "SELECT id, nama_area, bulan_tanam, tahun_tanam FROM bloks WHERE boundary_id=?",
                (boundary_id,)
            ).fetchall()

        # Load canopy thresholds
        thresh_rows = db.execute(
            "SELECT usia_min_bulan, usia_max_bulan, diameter_min_m "
            "FROM canopy_thresholds WHERE jenis_tanaman='default' ORDER BY usia_min_bulan"
        ).fetchall()
        thresholds = [dict(t) for t in thresh_rows]
    finally:
        db.close()

    # Build name-keyed dict so spatial lookup by geometry name maps correctly to DB row
    bloks_db_by_name = {row["nama_area"]: row for row in bloks_db}

    sess_dir  = os.path.join(UPLOAD_DIR, f"session_{sid}")
    vid_dir   = os.path.join(sess_dir, "videos")
    frame_dir = os.path.join(sess_dir, "frames")
    all_holes = []
    gps_index = {}

    try:
        mp4_files = (
            glob.glob(os.path.join(vid_dir, "*.MP4")) +
            glob.glob(os.path.join(vid_dir, "*.mp4"))
        )

        for vi, mp4 in enumerate(mp4_files):
            _set_progress(sid, int(vi / max(len(mp4_files), 1) * 40),
                          f"Ekstrak frame video {vi+1}/{len(mp4_files)}...")
            vname  = os.path.splitext(os.path.basename(mp4))[0]
            fdir   = os.path.join(frame_dir, vname)
            frames = extract_frames(mp4, fdir, fps=0.5)

            # Find matching SRT (case-insensitive extension swap)
            srt_path = mp4.rsplit(".", 1)[0] + ".SRT"
            if not os.path.exists(srt_path):
                srt_path = mp4.rsplit(".", 1)[0] + ".srt"
            gps_data = parse_srt(srt_path) if os.path.exists(srt_path) else []
            fps_src  = 47.95  # typical DJI sensor fps

            prev_gps = None
            for fi, fpath in enumerate(frames):
                pct = 40 + int(
                    (vi * len(frames) + fi) / max(len(mp4_files) * max(len(frames), 1), 1) * 50
                )
                _set_progress(sid, pct,
                              f"Deteksi frame {fi+1}/{len(frames)} (video {vi+1})...")

                # Map extracted-frame index to source frame number
                target_frame = int(fi * (1 / 0.5) * fps_src)
                gps = (
                    min(gps_data, key=lambda g: abs(g["frame"] - target_frame))
                    if gps_data else None
                )
                if gps is None:
                    continue

                # Skip if GPS coordinates haven't changed from previous frame (GPS freeze artifact)
                if prev_gps is not None and gps["lat"] == prev_gps["lat"] and gps["lon"] == prev_gps["lon"]:
                    continue
                prev_gps = gps

                # Save GPS index for this frame
                rel_key = f"session_{sid}/frames/{vname}/{os.path.basename(fpath)}"
                gps_index[rel_key] = {
                    "lat": gps["lat"],
                    "lon": gps["lon"],
                    "alt": float(gps.get("alt", 30)),
                }

                # Default usia from first blok; refined per-hole after dedup
                usia = 0
                if bloks_db_by_name:
                    b0   = next(iter(bloks_db_by_name.values()))
                    usia = get_usia_bulan(
                        b0["bulan_tanam"] or "JANUARI",
                        b0["tahun_tanam"] or 2026,
                        tanggal,
                    )

                holes = detect_holes(fpath, gps["lat"], gps["lon"], gps["alt"], usia, thresholds)
                all_holes.extend(holes)

        # Save GPS index for all processed frames
        gps_index_path = os.path.join(sess_dir, "gps_index.json")
        with open(gps_index_path, "w") as gf:
            json.dump(gps_index, gf)

        _set_progress(sid, 92, "Deduplikasi lubang...")
        deduped = deduplicate(all_holes, cell_m=2.0)

        # Assign each deduped hole to its nearest frame in gps_index
        def _nearest_frame(hole_lat, hole_lon):
            best_key, best_d = None, float("inf")
            for key, g in gps_index.items():
                d = (hole_lat - g["lat"]) ** 2 + (hole_lon - g["lon"]) ** 2
                if d < best_d:
                    best_d, best_key = d, key
            if best_key is None:
                return None, None
            parts = best_key.split("/")  # session_N/frames/vname/fname
            return parts[-2], parts[-1]

        _set_progress(sid, 95, "Simpan ke database...")
        db2 = get_db()
        try:
            db2.execute("DELETE FROM lubang_deteksi WHERE session_id=?", (sid,))

            for h in deduped:
                blok_id = None
                usia_b  = 0
                e, n = wgs84_to_utm50n(h["lat"], h["lon"])
                idx = find_blok_for_point(e, n, bloks_geom)
                if idx is not None:
                    geom_blok = bloks_geom[idx]
                    brow = bloks_db_by_name.get(geom_blok["nama_area"])
                    if brow:
                        blok_id = brow["id"]
                        usia_b  = get_usia_bulan(
                            brow["bulan_tanam"] or "JANUARI",
                            brow["tahun_tanam"] or 2026,
                            tanggal,
                        )

                fvideo, ffname = _nearest_frame(h["lat"], h["lon"])

                db2.execute(
                    "INSERT INTO lubang_deteksi "
                    "(session_id, blok_id, latitude, longitude, status_tanam, "
                    " diameter_tajuk_m, kategori_tajuk, usia_bulan, frame_video, frame_filename) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        sid, blok_id,
                        h["lat"], h["lon"],
                        h["status_tanam"],
                        h["diameter_tajuk_m"],
                        h["kategori_tajuk"],
                        usia_b,
                        fvideo, ffname,
                    ),
                )

            db2.execute("UPDATE drone_sessions SET status='done' WHERE id=?", (sid,))
            db2.commit()
            _set_progress(sid, 100, f"Selesai! {len(deduped)} lubang terdeteksi.", done=True)
        finally:
            db2.close()

    except Exception as ex:
        try:
            db3 = get_db()
            db3.execute("UPDATE drone_sessions SET status='error' WHERE id=?", (sid,))
            db3.commit()
            db3.close()
        except Exception:
            pass
        _set_progress(sid, 0, f"Error: {str(ex)}", done=True)


# ──────────────────────────────────────────────
# GET /api/sessions/<sid>/frames
# ──────────────────────────────────────────────
@bp.route("/<int:sid>/frames", methods=["GET"])
def list_frames(sid):
    from config import UPLOAD_DIR
    import glob as glob_mod
    sess_dir = os.path.join(UPLOAD_DIR, f"session_{sid}")
    frame_dir = os.path.join(sess_dir, "frames")
    result = []
    if os.path.isdir(frame_dir):
        for vdir in sorted(os.listdir(frame_dir)):
            vpath = os.path.join(frame_dir, vdir)
            if os.path.isdir(vpath):
                for fname in sorted(os.listdir(vpath)):
                    if fname.lower().endswith('.jpg'):
                        result.append({
                            "url": f"/data/uploads/session_{sid}/frames/{vdir}/{fname}",
                            "video": vdir,
                            "filename": fname,
                        })

    gps_index_path = os.path.join(sess_dir, "gps_index.json")
    gps_index = {}
    if os.path.exists(gps_index_path):
        with open(gps_index_path) as gf:
            gps_index = json.load(gf)

    for item in result:
        key = f"session_{sid}/frames/{item['video']}/{item['filename']}"
        gps_data = gps_index.get(key, {})
        item["lat"] = gps_data.get("lat")
        item["lon"] = gps_data.get("lon")
        item["alt"] = gps_data.get("alt", 30.0)

    return jsonify(result)


# ──────────────────────────────────────────────
# GET  /api/sessions/<sid>/frame-holes?video=X&filename=Y
# DELETE /api/sessions/<sid>/frame-holes?video=X&filename=Y
# ──────────────────────────────────────────────
@bp.route("/<int:sid>/frame-holes", methods=["GET", "DELETE"])
def frame_holes(sid):
    video    = request.args.get("video", "")
    filename = request.args.get("filename", "")
    if not video or not filename:
        return jsonify({"error": "video and filename required"}), 400

    db = get_db()
    if request.method == "DELETE":
        result = db.execute(
            "DELETE FROM lubang_deteksi WHERE session_id=? AND frame_video=? AND frame_filename=?",
            (sid, video, filename)
        )
        db.commit()
        db.close()
        return jsonify({"ok": True, "deleted": result.rowcount})

    # GET — return holes for this frame as GeoJSON
    rows = db.execute(
        "SELECT id, latitude, longitude, status_tanam, diameter_tajuk_m, "
        "       kategori_tajuk, usia_bulan, blok_id, source "
        "FROM lubang_deteksi "
        "WHERE session_id=? AND frame_video=? AND frame_filename=?",
        (sid, video, filename)
    ).fetchall()
    db.close()
    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
            "properties": {
                "id": r["id"],
                "status_tanam": r["status_tanam"],
                "diameter_tajuk_m": r["diameter_tajuk_m"],
                "kategori_tajuk": r["kategori_tajuk"],
                "usia_bulan": r["usia_bulan"],
                "blok_id": r["blok_id"],
                "source": r["source"],
            }
        })
    return jsonify({"type": "FeatureCollection", "features": features})


# ──────────────────────────────────────────────
# PATCH /api/sessions/<sid>/holes/<hole_id>
# ──────────────────────────────────────────────
@bp.route("/<int:sid>/holes/<int:hole_id>", methods=["PATCH"])
def update_hole(sid, hole_id):
    data = request.get_json() or {}
    status = data.get("status_tanam")
    if status not in ("ditanam", "kosong"):
        return jsonify({"error": "status_tanam must be 'ditanam' or 'kosong'"}), 400
    db = get_db()
    row = db.execute("SELECT id FROM lubang_deteksi WHERE id=? AND session_id=?", (hole_id, sid)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Not found"}), 404
    db.execute("UPDATE lubang_deteksi SET status_tanam=?, source='manual' WHERE id=?", (status, hole_id))
    db.commit()
    db.close()
    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# DELETE /api/sessions/<sid>/holes/<hole_id>
# ──────────────────────────────────────────────
@bp.route("/<int:sid>/holes/<int:hole_id>", methods=["DELETE"])
def delete_hole(sid, hole_id):
    db = get_db()
    row = db.execute("SELECT id FROM lubang_deteksi WHERE id=? AND session_id=?", (hole_id, sid)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Not found"}), 404
    db.execute("DELETE FROM lubang_deteksi WHERE id=?", (hole_id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# POST /api/sessions/<sid>/holes/from_pixel
# ──────────────────────────────────────────────
@bp.route("/<int:sid>/holes/from_pixel", methods=["POST"])
def add_hole_from_pixel(sid):
    from core.gps_projection import pixel_to_gps, wgs84_to_utm50n as _wgs84_to_utm50n
    from core.canopy_classifier import classify_canopy, get_usia_bulan as _get_usia_bulan
    data = request.get_json() or {}
    pixel_x    = data.get("pixel_x", 0)
    pixel_y    = data.get("pixel_y", 0)
    img_w      = data.get("img_w", 1920)
    img_h      = data.get("img_h", 1080)
    drone_lat  = data.get("lat")
    drone_lon  = data.get("lon")
    alt        = data.get("alt", 30.0)
    frame_video    = data.get("frame_video")
    frame_filename = data.get("frame_filename")

    if drone_lat is None or drone_lon is None:
        return jsonify({"error": "GPS tidak tersedia untuk frame ini"}), 400

    hole_lat, hole_lon = pixel_to_gps(pixel_x, pixel_y, drone_lat, drone_lon, alt)

    db = get_db()
    sess = db.execute(
        "SELECT tanggal_terbang, boundary_id FROM drone_sessions WHERE id=?", (sid,)
    ).fetchone()
    if not sess:
        db.close()
        return jsonify({"error": "Session tidak ditemukan"}), 404

    blok_id = None
    usia_b  = 0
    if sess["boundary_id"]:
        bloks_db = db.execute(
            "SELECT id, nama_area, bulan_tanam, tahun_tanam FROM bloks WHERE boundary_id=?",
            (sess["boundary_id"],)
        ).fetchall()
        if bloks_db:
            from core.shapefile_manager import find_blok_for_point
            shp_row = db.execute(
                "SELECT shp_dir FROM boundaries WHERE id=?", (sess["boundary_id"],)
            ).fetchone()
            if shp_row:
                try:
                    from core.shapefile_manager import load_shapefile
                    bloks_geom = load_shapefile(shp_row["shp_dir"])
                    bloks_db_by_name = {r["nama_area"]: r for r in bloks_db}
                    e, n = _wgs84_to_utm50n(hole_lat, hole_lon)
                    idx = find_blok_for_point(e, n, bloks_geom)
                    if idx is not None:
                        geom_blok = bloks_geom[idx]
                        brow = bloks_db_by_name.get(geom_blok["nama_area"])
                        if brow:
                            blok_id = brow["id"]
                            usia_b = _get_usia_bulan(
                                brow["bulan_tanam"] or "JANUARI",
                                brow["tahun_tanam"] or 2026,
                                sess["tanggal_terbang"]
                            )
                except Exception:
                    pass

    thresh_rows = db.execute(
        "SELECT usia_min_bulan, usia_max_bulan, diameter_min_m FROM canopy_thresholds "
        "WHERE jenis_tanaman='default' ORDER BY usia_min_bulan"
    ).fetchall()
    thresholds = [dict(t) for t in thresh_rows]
    kategori = classify_canopy(0.0, usia_b, thresholds) if thresholds else "merah"

    cur = db.execute(
        "INSERT INTO lubang_deteksi (session_id, blok_id, latitude, longitude, "
        "status_tanam, diameter_tajuk_m, kategori_tajuk, usia_bulan, source, frame_video, frame_filename) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (sid, blok_id, hole_lat, hole_lon, "ditanam", None, kategori, usia_b, "manual",
         frame_video, frame_filename)
    )
    new_id = cur.lastrowid
    db.commit()
    db.close()
    return jsonify({
        "id": new_id, "lat": hole_lat, "lon": hole_lon,
        "blok_id": blok_id, "kategori_tajuk": kategori, "usia_bulan": usia_b
    }), 201


# ──────────────────────────────────────────────
# POST /api/sessions/<sid>/reviewed-frames
# ──────────────────────────────────────────────
@bp.route("/<int:sid>/reviewed-frames", methods=["POST"])
def mark_frame_reviewed(sid):
    from datetime import datetime as dt
    data = request.get_json() or {}
    video    = data.get("video", "")
    filename = data.get("filename", "")
    if not video or not filename:
        return jsonify({"error": "video and filename required"}), 400
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO reviewed_frames (session_id, video, filename, reviewed_at) "
        "VALUES (?,?,?,?)",
        (sid, video, filename, dt.utcnow().isoformat())
    )
    db.commit()
    db.close()
    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# GET /api/sessions/<sid>/review-stats
# ──────────────────────────────────────────────
@bp.route("/<int:sid>/review-stats", methods=["GET"])
def review_stats(sid):
    db = get_db()
    auto_count   = db.execute("SELECT COUNT(*) FROM lubang_deteksi WHERE session_id=? AND (source IS NULL OR source='auto')", (sid,)).fetchone()[0]
    manual_count = db.execute("SELECT COUNT(*) FROM lubang_deteksi WHERE session_id=? AND source='manual'", (sid,)).fetchone()[0]
    reviewed_count = db.execute("SELECT COUNT(*) FROM reviewed_frames WHERE session_id=?", (sid,)).fetchone()[0]
    db.close()
    return jsonify({
        "auto": auto_count,
        "manual": manual_count,
        "total": auto_count + manual_count,
        "reviewed_frames": reviewed_count
    })


# ──────────────────────────────────────────────
# POST /api/sessions/<sid>/auto-tune
# ──────────────────────────────────────────────
@bp.route("/<int:sid>/auto-tune", methods=["POST"])
def auto_tune(sid):
    """Run grid search on reviewed frames. Returns best params."""
    import itertools
    from core.hole_detector import detect_holes as _detect

    db = get_db()
    sess = db.execute("SELECT tanggal_terbang, boundary_id FROM drone_sessions WHERE id=?", (sid,)).fetchone()
    if not sess:
        db.close()
        return jsonify({"error": "Not found"}), 404

    reviewed = db.execute(
        "SELECT video, filename FROM reviewed_frames WHERE session_id=?", (sid,)
    ).fetchall()
    if not reviewed:
        db.close()
        return jsonify({"error": "Belum ada frame yang di-review. Buka tab Review, review beberapa frame lalu coba lagi."}), 400

    gps_index_path = os.path.join(UPLOAD_DIR, f"session_{sid}", "gps_index.json")
    if not os.path.exists(gps_index_path):
        db.close()
        return jsonify({"error": "GPS index tidak ditemukan. Re-proses sesi terlebih dahulu."}), 400

    with open(gps_index_path) as gf:
        gps_index = json.load(gf)

    all_holes_db = db.execute(
        "SELECT latitude, longitude FROM lubang_deteksi WHERE session_id=?", (sid,)
    ).fetchall()
    thresh_rows = db.execute(
        "SELECT usia_min_bulan, usia_max_bulan, diameter_min_m FROM canopy_thresholds "
        "WHERE jenis_tanaman='default' ORDER BY usia_min_bulan"
    ).fetchall()
    thresholds = [dict(t) for t in thresh_rows]
    db.close()

    gt_points = [(r["latitude"], r["longitude"]) for r in all_holes_db]

    # Build per-reviewed-frame ground truth (holes within ~50m of frame GPS)
    frame_data = []
    for rv in reviewed:
        key = f"session_{sid}/frames/{rv['video']}/{rv['filename']}"
        gps = gps_index.get(key)
        if not gps:
            continue
        fpath = os.path.join(UPLOAD_DIR, f"session_{sid}", "frames", rv["video"], rv["filename"])
        if not os.path.exists(fpath):
            continue
        mPerDegLat = 111320
        mPerDegLon = 111320 * math.cos(math.radians(gps["lat"]))
        nearby = [
            (lat, lon) for lat, lon in gt_points
            if abs(lat - gps["lat"]) * mPerDegLat < 50 and abs(lon - gps["lon"]) * mPerDegLon < 50
        ]
        frame_data.append({"fpath": fpath, "gps": gps, "gt": nearby})

    if not frame_data:
        return jsonify({"error": "Frame yang di-review tidak memiliki GPS atau file gambar tidak ditemukan."}), 400

    # Grid search
    circ_values  = [0.35, 0.45, 0.55, 0.65]
    scale_mins   = [0.3, 0.5, 0.8]
    scale_maxs   = [2.0, 3.0, 4.5]

    MATCH_RADIUS_M = 2.0
    best_f1, best_params = -1, {}

    for circ, sc_min, sc_max in itertools.product(circ_values, scale_mins, scale_maxs):
        tp = fp = fn = 0
        for fd in frame_data:
            gps = fd["gps"]
            detected = _detect(fd["fpath"], gps["lat"], gps["lon"], gps["alt"],
                               0, thresholds,
                               circularity_min=circ,
                               area_scale_min=sc_min,
                               area_scale_max=sc_max)
            mLat = 111320
            mLon = 111320 * math.cos(math.radians(gps["lat"]))
            matched_gt = set()
            for d in detected:
                hit = False
                for i, (gt_lat, gt_lon) in enumerate(fd["gt"]):
                    dist = math.sqrt(((d["lat"]-gt_lat)*mLat)**2 + ((d["lon"]-gt_lon)*mLon)**2)
                    if dist <= MATCH_RADIUS_M and i not in matched_gt:
                        matched_gt.add(i)
                        hit = True
                        break
                if hit:
                    tp += 1
                else:
                    fp += 1
            fn += len(fd["gt"]) - len(matched_gt)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        if f1 > best_f1:
            best_f1 = f1
            best_params = {"circularity_min": circ, "area_scale_min": sc_min, "area_scale_max": sc_max,
                           "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
                           "frames_tested": len(frame_data)}

    return jsonify(best_params)

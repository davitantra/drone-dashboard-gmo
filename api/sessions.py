import os, json, threading, time, glob, shutil
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

        _set_progress(sid, 92, "Deduplikasi lubang...")
        deduped = deduplicate(all_holes, cell_m=2.0)

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

                db2.execute(
                    "INSERT INTO lubang_deteksi "
                    "(session_id, blok_id, latitude, longitude, status_tanam, "
                    " diameter_tajuk_m, kategori_tajuk, usia_bulan) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        sid, blok_id,
                        h["lat"], h["lon"],
                        h["status_tanam"],
                        h["diameter_tajuk_m"],
                        h["kategori_tajuk"],
                        usia_b,
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
    return jsonify(result)

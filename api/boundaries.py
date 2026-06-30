import os, zipfile, shutil
from datetime import datetime
from flask import Blueprint, request, jsonify
from database import get_db
from core.shapefile_manager import load_shapefile
from config import UPLOAD_DIR

bp = Blueprint("boundaries", __name__)

def _now():
    return datetime.utcnow().isoformat()

@bp.route("", methods=["GET"])
def list_boundaries():
    db = get_db()
    rows = db.execute(
        "SELECT id, nama, deskripsi, luas_ha, jumlah_blok, uploaded_at FROM boundaries ORDER BY uploaded_at DESC"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@bp.route("", methods=["POST"])
def create_boundary():
    nama      = request.form.get("nama", "Boundary Baru")
    deskripsi = request.form.get("deskripsi", "")
    if "file" not in request.files:
        return jsonify({"error": "File zip diperlukan"}), 400

    f = request.files["file"]
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    shp_dir = os.path.join(UPLOAD_DIR, f"shp_{ts}")
    os.makedirs(shp_dir, exist_ok=True)

    zip_path = os.path.join(shp_dir, "upload.zip")
    f.save(zip_path)
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            for member in z.namelist():
                member_path = os.path.realpath(os.path.join(shp_dir, member))
                if not member_path.startswith(os.path.realpath(shp_dir)):
                    shutil.rmtree(shp_dir, ignore_errors=True)
                    return jsonify({"error": "File zip tidak valid (path traversal)"}), 400
            z.extractall(shp_dir)
        os.remove(zip_path)
        bloks = load_shapefile(shp_dir)
    except Exception as e:
        shutil.rmtree(shp_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 422

    total_luas = sum(b["luas_ha"] for b in bloks)
    db = get_db()
    cur = db.execute(
        "INSERT INTO boundaries (nama, deskripsi, shp_dir, luas_ha, jumlah_blok, uploaded_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (nama, deskripsi, shp_dir, total_luas, len(bloks), _now(), _now())
    )
    boundary_id = cur.lastrowid
    for b in bloks:
        db.execute(
            "INSERT INTO bloks (boundary_id, nama_area, elevasi, bulan_tanam, tahun_tanam, luas_ha, target_lubang, geom_wkt) VALUES (?,?,?,?,?,?,?,?)",
            (boundary_id, b["nama_area"], b["elevasi"], b["bulan_tanam"], b["tahun_tanam"], b["luas_ha"], b["target_lubang"], b["geom_wkt"])
        )
    db.commit()
    db.close()
    return jsonify({"id": boundary_id, "nama": nama, "jumlah_blok": len(bloks)}), 201

@bp.route("/<int:bid>", methods=["PUT"])
def update_boundary(bid):
    data = request.get_json() or {}
    db = get_db()
    cur = db.execute(
        "UPDATE boundaries SET nama=COALESCE(?,nama), deskripsi=COALESCE(?,deskripsi), updated_at=? WHERE id=?",
        (data.get("nama"), data.get("deskripsi"), _now(), bid)
    )
    db.commit()
    db.close()
    if cur.rowcount == 0:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"ok": True})

@bp.route("/<int:bid>", methods=["DELETE"])
def delete_boundary(bid):
    db = get_db()
    row = db.execute("SELECT shp_dir FROM boundaries WHERE id=?", (bid,)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Not found"}), 404
    shutil.rmtree(row["shp_dir"], ignore_errors=True)
    db.execute("DELETE FROM boundaries WHERE id=?", (bid,))
    db.commit()
    db.close()
    return jsonify({"ok": True})

@bp.route("/<int:bid>/bloks", methods=["GET"])
def list_bloks(bid):
    db = get_db()
    rows = db.execute(
        "SELECT id, nama_area, luas_ha, target_lubang, bulan_tanam, tahun_tanam, elevasi FROM bloks WHERE boundary_id=?",
        (bid,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

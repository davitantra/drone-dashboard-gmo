"""
Map Data API
- GET /api/map/<session_id>       → GeoJSON FeatureCollection titik lubang
- GET /api/map/bloks/<boundary_id> → GeoJSON FeatureCollection polygon blok
"""
import math
from flask import Blueprint, jsonify
from database import get_db

try:
    from shapely import wkt as shapely_wkt
except ImportError:
    shapely_wkt = None

bp = Blueprint("map_data", __name__)


# ---------------------------------------------------------------------------
# Route: titik lubang per sesi
# ---------------------------------------------------------------------------

@bp.route("/all", methods=["GET"])
def holes_all():
    db = get_db()
    rows = db.execute(
        "SELECT ld.id, ld.session_id, ld.blok_id, ld.latitude, ld.longitude, "
        "ld.status_tanam, ld.diameter_tajuk_m, ld.kategori_tajuk, ld.usia_bulan, "
        "ds.nama AS session_nama, ds.tanggal_terbang "
        "FROM lubang_deteksi ld "
        "JOIN drone_sessions ds ON ld.session_id = ds.id "
        "WHERE (ds.boundary_id IS NULL OR ld.blok_id IS NOT NULL)"
    ).fetchall()
    db.close()
    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
            "properties": {
                "id": r["id"],
                "session_id": r["session_id"],
                "session_nama": r["session_nama"],
                "tanggal_terbang": r["tanggal_terbang"],
                "status_tanam": r["status_tanam"],
                "kategori_tajuk": r["kategori_tajuk"],
                "diameter_tajuk_m": r["diameter_tajuk_m"],
                "usia_bulan": r["usia_bulan"],
                "blok_id": r["blok_id"],
            }
        })
    return jsonify({"type": "FeatureCollection", "features": features})


@bp.route("/<int:sid>", methods=["GET"])
def holes_geojson(sid):
    db = get_db()
    sess = db.execute(
        "SELECT boundary_id FROM drone_sessions WHERE id=?", (sid,)
    ).fetchone()
    has_boundary = sess and sess["boundary_id"] is not None

    query = (
        "SELECT id, latitude, longitude, status_tanam, diameter_tajuk_m, "
        "       kategori_tajuk, usia_bulan, blok_id "
        "FROM lubang_deteksi WHERE session_id=?"
        + (" AND blok_id IS NOT NULL" if has_boundary else "")
    )
    rows = db.execute(query, (sid,)).fetchall()
    db.close()

    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["longitude"], r["latitude"]],
            },
            "properties": {
                "id": r["id"],
                "status_tanam": r["status_tanam"],
                "diameter_tajuk_m": r["diameter_tajuk_m"],
                "kategori_tajuk": r["kategori_tajuk"],
                "usia_bulan": r["usia_bulan"],
                "blok_id": r["blok_id"],
            },
        })

    return jsonify({"type": "FeatureCollection", "features": features})


# ---------------------------------------------------------------------------
# Route: polygon blok per boundary
# ---------------------------------------------------------------------------

@bp.route("/bloks/<int:bid>", methods=["GET"])
def bloks_geojson(bid):
    db = get_db()
    blok_rows = db.execute(
        "SELECT b.id, b.nama_area, b.luas_ha, b.target_lubang, "
        "       b.bulan_tanam, b.tahun_tanam, b.geom_wkt "
        "FROM bloks b WHERE b.boundary_id=?",
        (bid,)
    ).fetchall()

    # Hitung warna tiap blok berdasarkan % hijau di semua sesi
    blok_ids = [r["id"] for r in blok_rows]
    blok_color = {}
    if blok_ids:
        placeholders = ",".join("?" * len(blok_ids))
        hole_rows = db.execute(
            f"SELECT blok_id, kategori_tajuk FROM lubang_deteksi "
            f"WHERE blok_id IN ({placeholders})",
            blok_ids,
        ).fetchall()
        # Aggregate per blok
        counts = {}  # blok_id -> {"total": int, "hijau": int}
        for hr in hole_rows:
            bid_h = hr["blok_id"]
            if bid_h not in counts:
                counts[bid_h] = {"total": 0, "hijau": 0}
            counts[bid_h]["total"] += 1
            if hr["kategori_tajuk"] == "hijau":
                counts[bid_h]["hijau"] += 1

        for blok_id, c in counts.items():
            pct = c["hijau"] / c["total"] if c["total"] > 0 else 0
            if pct >= 0.80:
                blok_color[blok_id] = "hijau"
            elif pct >= 0.50:
                blok_color[blok_id] = "oranye"
            else:
                blok_color[blok_id] = "merah"

    db.close()

    features = []
    for r in blok_rows:
        if not r["geom_wkt"]:
            continue
        try:
            if shapely_wkt is None:
                raise ImportError("shapely not available")
            geom = shapely_wkt.loads(r["geom_wkt"])
            coords = _utm_polygon_to_latlon(geom)
        except Exception:
            coords = None
        if coords is None:
            continue

        color = blok_color.get(r["id"], "merah")
        features.append({
            "type": "Feature",
            "geometry": coords,
            "properties": {
                "id": r["id"],
                "nama_area": r["nama_area"],
                "luas_ha": r["luas_ha"],
                "target_lubang": r["target_lubang"],
                "bulan_tanam": r["bulan_tanam"],
                "tahun_tanam": r["tahun_tanam"],
                "color": color,
            },
        })

    return jsonify({"type": "FeatureCollection", "features": features})


# ---------------------------------------------------------------------------
# UTM Zone 50N → WGS84 helper (pyproj, dengan koreksi southern hemisphere)
# ---------------------------------------------------------------------------

try:
    from pyproj import Transformer
    _transformer = Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True)

    def _utm_to_wgs84(easting: float, northing: float):
        """Konversi UTM 50N → (lon, lat) WGS84 via pyproj EPSG:32650."""
        lon, lat = _transformer.transform(easting, northing)
        return lon, lat

except ImportError:
    # Fallback: manual inverse UTM (tanpa pyproj)
    _a  = 6378137.0
    _f  = 1 / 298.257223563
    _b  = _a * (1 - _f)
    _e2 = 1 - (_b / _a) ** 2
    _k0 = 0.9996
    _lon0 = math.radians(117.0)

    def _utm_to_wgs84(easting: float, northing: float):
        M  = northing / _k0
        e1 = (1 - math.sqrt(1 - _e2)) / (1 + math.sqrt(1 - _e2))
        mu = M / (_a * (1 - _e2 / 4 - 3 * _e2 ** 2 / 64 - 5 * _e2 ** 3 / 256))
        phi1 = (
            mu
            + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
        )
        N1 = _a / math.sqrt(1 - _e2 * math.sin(phi1) ** 2)
        T1 = math.tan(phi1) ** 2
        C1 = (_e2 / (1 - _e2)) * math.cos(phi1) ** 2
        R1 = _a * (1 - _e2) / (1 - _e2 * math.sin(phi1) ** 2) ** 1.5
        D  = (easting - 500000) / (N1 * _k0)
        lat = phi1 - (N1 * math.tan(phi1) / R1) * (
            D ** 2 / 2
            - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * (_e2 / (1 - _e2))) * D ** 4 / 24
            + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * (_e2 / (1 - _e2)) - 3 * C1 ** 2) * D ** 6 / 720
        )
        lon = _lon0 + (
            D
            - (1 + 2 * T1 + C1) * D ** 3 / 6
            + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * (_e2 / (1 - _e2)) + 24 * T1 ** 2) * D ** 5 / 120
        ) / math.cos(phi1)
        lon_deg = math.degrees(lon)
        lat_deg = math.degrees(lat)
        return lon_deg, lat_deg


def _utm_polygon_to_latlon(geom):
    """Konversi polygon/multipolygon Shapely (UTM 50N) → GeoJSON koordinat WGS84."""
    from shapely.geometry import Polygon, MultiPolygon

    def convert_ring(coords):
        return [_utm_to_wgs84(x, y) for x, y in coords]

    if isinstance(geom, Polygon):
        ext = convert_ring(geom.exterior.coords)
        holes = [convert_ring(ring.coords) for ring in geom.interiors]
        return {"type": "Polygon", "coordinates": [ext] + holes}
    elif isinstance(geom, MultiPolygon):
        polys = []
        for p in geom.geoms:
            ext = convert_ring(p.exterior.coords)
            holes = [convert_ring(ring.coords) for ring in p.interiors]
            polys.append([ext] + holes)
        return {"type": "MultiPolygon", "coordinates": polys}
    return None

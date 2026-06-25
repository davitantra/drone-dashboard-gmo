import math, shapefile
from shapely.geometry import shape, Point
from config import HOLE_SPACING_M

def load_shapefile(shp_dir: str) -> list:
    """
    Load semua polygon dari folder shapefile.
    Return list of dict: {nama_area, elevasi, bulan_tanam, tahun_tanam,
                          luas_ha, target_lubang, geom_wkt, geom (shapely)}

    NOTE: The GMO shapefile (rvg_gmo_kum_2605.shp) has a known hemisphere error —
    southern-hemisphere coordinates (~-2.13°S) were stored as positive UTM Zone 50N
    northing values (~237,500 m instead of the expected negative value). This is a
    shapefile data error. load_shapefile returns geometry as-is; callers must use
    wgs84_to_utm50n() from core/gps_projection.py (which applies abs(lat)) so that
    drone GPS coordinates are converted to the same positive-northing convention.
    A residual ~2 km northing offset may remain near polygon boundaries — known limitation.
    """
    import glob, os
    shp_files = glob.glob(os.path.join(shp_dir, "*.shp"))
    if not shp_files:
        raise FileNotFoundError(f"Tidak ada file .shp di {shp_dir}")

    sf = shapefile.Reader(shp_files[0])
    fields = [f[0] for f in sf.fields[1:]]
    bloks = []
    for sr in sf.shapeRecords():
        rec  = dict(zip(fields, sr.record))
        geom = shape(sr.shape.__geo_interface__)
        area_m2 = geom.area
        bloks.append({
            "nama_area":    rec.get("NAMA_AREA", ""),
            "elevasi":      _parse_elevasi(rec.get("NAMA_AREA", "")),
            "bulan_tanam":  rec.get("BULAN_TANA", ""),
            "tahun_tanam":  int(rec.get("TAHUN_TANA", 2026) or 2026),
            "luas_ha":      round(area_m2 / 10000, 4),
            "target_lubang": int(area_m2 / (HOLE_SPACING_M ** 2)),
            "geom_wkt":     geom.wkt,
            "geom":         geom,
        })
    return bloks

def find_blok_for_point(easting: float, northing: float, bloks: list):
    """
    Cari blok (dict dari load_shapefile) yang mengandung titik UTM (easting, northing).
    Return index dalam list bloks, atau None jika tidak ada.

    PENTING: easting/northing harus dihitung dengan wgs84_to_utm50n() dari
    core/gps_projection.py agar konsisten dengan konvensi positif shapefile GMO.
    """
    pt = Point(easting, northing)
    for i, b in enumerate(bloks):
        if b["geom"].contains(pt):
            return i
    return None

def _parse_elevasi(nama_area: str) -> float:
    """Ekstrak angka elevasi dari string seperti 'OPD_WEST ELV +50.0'."""
    import re
    m = re.search(r"[+-]?\d+\.?\d*", nama_area.split("ELV")[-1] if "ELV" in nama_area else "")
    return float(m.group()) if m else 0.0

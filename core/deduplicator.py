import math
from collections import defaultdict

def _gps_to_cell(lat, lon, cell_m=2.0):
    """Konversi GPS ke grid cell ID (integer tuple)."""
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat))
    return (int(lat * m_per_deg_lat / cell_m), int(lon * m_per_deg_lon / cell_m))

def deduplicate(holes: list, cell_m: float = 2.0) -> list:
    """
    Deduplikasi lubang yang sama terdeteksi di beberapa frame.
    Gunakan majority vote per cell 2×2m untuk status dan kategori.
    Return list of dict dengan field yang sama seperti input.
    """
    cells = defaultdict(list)
    for h in holes:
        cid = _gps_to_cell(h["lat"], h["lon"], cell_m)
        cells[cid].append(h)

    result = []
    for cid, group in cells.items():
        # Rata-rata koordinat
        avg_lat = sum(h["lat"] for h in group) / len(group)
        avg_lon = sum(h["lon"] for h in group) / len(group)

        # Majority vote status
        status_votes = {}
        for h in group:
            status_votes[h["status_tanam"]] = status_votes.get(h["status_tanam"], 0) + 1
        status = max(status_votes, key=status_votes.get)

        # Majority vote kategori
        kat_votes = {}
        for h in group:
            kat_votes[h["kategori_tajuk"]] = kat_votes.get(h["kategori_tajuk"], 0) + 1
        kategori = max(kat_votes, key=kat_votes.get)

        # Median diameter (ignore None)
        diameters = [h["diameter_tajuk_m"] for h in group if h["diameter_tajuk_m"] is not None]
        avg_diam = sum(diameters) / len(diameters) if diameters else None

        result.append({
            "lat": avg_lat, "lon": avg_lon,
            "status_tanam": status,
            "diameter_tajuk_m": avg_diam,
            "kategori_tajuk": kategori,
        })
    return result

from datetime import date

BULAN_MAP = {
    "JANUARI":1,"FEBRUARI":2,"MARET":3,"APRIL":4,
    "MEI":5,"JUNI":6,"JULI":7,"AGUSTUS":8,
    "SEPTEMBER":9,"OKTOBER":10,"NOVEMBER":11,"DESEMBER":12
}

def get_usia_bulan(bulan_tanam: str, tahun_tanam: int, tanggal_terbang: str) -> int:
    """Hitung selisih bulan antara tanggal tanam dan tanggal terbang drone."""
    bulan = BULAN_MAP.get(bulan_tanam.upper(), 1)
    tanam = date(tahun_tanam, bulan, 1)
    terbang_parts = tanggal_terbang[:10].split("-")
    terbang = date(int(terbang_parts[0]), int(terbang_parts[1]), int(terbang_parts[2]))
    delta = (terbang.year - tanam.year) * 12 + (terbang.month - tanam.month)
    return max(0, delta)

def classify_canopy(diameter_m, usia_bulan: int, thresholds: list) -> str:
    """
    Kategorikan kondisi tajuk berdasarkan diameter terukur vs threshold usia.
    thresholds: list of dict dengan keys usia_min_bulan, usia_max_bulan, diameter_min_m
    Return: 'hijau' | 'oranye' | 'merah'
    """
    if diameter_m is None or diameter_m <= 0:
        return "merah"
    threshold = None
    for t in sorted(thresholds, key=lambda x: x["usia_min_bulan"]):
        if usia_bulan >= t["usia_min_bulan"]:
            if t["usia_max_bulan"] is None or usia_bulan <= t["usia_max_bulan"]:
                threshold = t["diameter_min_m"]
                break
    if threshold is None:
        # Ambil threshold tertinggi jika usia melebihi semua range
        threshold = max(t["diameter_min_m"] for t in thresholds)
    return "hijau" if diameter_m >= threshold else "oranye"

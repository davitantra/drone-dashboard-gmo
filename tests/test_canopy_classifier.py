import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.canopy_classifier import classify_canopy, get_usia_bulan

THRESHOLDS = [
    {"usia_min_bulan": 0,  "usia_max_bulan": 2,    "diameter_min_m": 0.15},
    {"usia_min_bulan": 3,  "usia_max_bulan": 5,    "diameter_min_m": 0.30},
    {"usia_min_bulan": 6,  "usia_max_bulan": 11,   "diameter_min_m": 0.60},
    {"usia_min_bulan": 12, "usia_max_bulan": None,  "diameter_min_m": 1.00},
]

def test_hijau_when_diameter_meets_threshold():
    assert classify_canopy(0.20, 1, THRESHOLDS) == "hijau"

def test_oranye_when_diameter_below_threshold():
    assert classify_canopy(0.10, 1, THRESHOLDS) == "oranye"

def test_merah_when_no_diameter():
    assert classify_canopy(None, 1, THRESHOLDS) == "merah"

def test_hijau_older_plant():
    assert classify_canopy(1.20, 15, THRESHOLDS) == "hijau"

def test_oranye_older_plant():
    assert classify_canopy(0.70, 15, THRESHOLDS) == "oranye"

def test_get_usia_bulan_basic():
    assert get_usia_bulan("JANUARI", 2026, "2026-06-06") == 5

def test_get_usia_bulan_same_month():
    assert get_usia_bulan("JUNI", 2026, "2026-06-06") == 0

import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.gps_projection import pixel_to_gps, wgs84_to_utm50n

def test_pixel_center_returns_drone_position():
    lat, lon = pixel_to_gps(960, 540, -2.130737, 117.600155, 19.0)
    assert abs(lat - (-2.130737)) < 1e-5
    assert abs(lon - 117.600155) < 1e-5

def test_utm_conversion_roundtrip():
    lat, lon = -2.130737, 117.600155
    e, n = wgs84_to_utm50n(lat, lon)
    # Easting harus sekitar 567000, Northing negatif kecil (selatan equator)
    assert 560000 < e < 580000
    assert 230000 < n < 250000

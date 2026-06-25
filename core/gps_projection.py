import math
from config import IMG_W, IMG_H, HFOV_DEG, VFOV_DEG

R_EARTH = 6378137.0
HFOV = math.radians(HFOV_DEG)
VFOV = math.radians(VFOV_DEG)

def pixel_to_gps(px: int, py: int, drone_lat: float, drone_lon: float, alt: float):
    """Konversi koordinat pixel dalam frame → GPS (lat, lon)."""
    fp_w = 2 * alt * math.tan(HFOV / 2)
    fp_h = 2 * alt * math.tan(VFOV / 2)
    dx_m =  ((px - IMG_W / 2) / IMG_W) * fp_w
    dy_m = -((py - IMG_H / 2) / IMG_H) * fp_h
    d_lat = dy_m / R_EARTH * (180 / math.pi)
    d_lon = dx_m / (R_EARTH * math.cos(math.radians(drone_lat))) * (180 / math.pi)
    return drone_lat + d_lat, drone_lon + d_lon

def wgs84_to_utm50n(lat: float, lon: float):
    """WGS84 → UTM Zone 50N (easting, northing) dalam meter."""
    a  = 6378137.0
    f  = 1 / 298.257223563
    b  = a * (1 - f)
    e2 = 1 - (b / a) ** 2
    k0 = 0.9996
    lon0 = math.radians(117.0)
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    dlon  = lon_r - lon0
    N  = a / math.sqrt(1 - e2 * math.sin(lat_r) ** 2)
    T  = math.tan(lat_r) ** 2
    C  = (e2 / (1 - e2)) * math.cos(lat_r) ** 2
    A  = math.cos(lat_r) * dlon
    e4 = e2 ** 2
    e6 = e2 ** 3
    M  = a * (
        (1 - e2/4 - 3*e4/64 - 5*e6/256) * lat_r
        - (3*e2/8 + 3*e4/32 + 45*e6/1024) * math.sin(2*lat_r)
        + (15*e4/256 + 45*e6/1024) * math.sin(4*lat_r)
        - (35*e6/3072) * math.sin(6*lat_r)
    )
    x = k0*N*(A + (1-T+C)*A**3/6 + (5-18*T+T**2+72*C-58*(e2/(1-e2)))*A**5/120)
    y = k0*(M + N*math.tan(lat_r)*(
        A**2/2 + (5-T+9*C+4*C**2)*A**4/24
        + (61-58*T+T**2+600*C-330*(e2/(1-e2)))*A**6/720
    ))
    # For southern hemisphere points y is negative; return absolute distance from equator
    return 500000 + x, abs(y)

def footprint_meters(alt: float):
    """Kembalikan (lebar_m, tinggi_m) footprint kamera di tanah."""
    return (2*alt*math.tan(HFOV/2), 2*alt*math.tan(VFOV/2))

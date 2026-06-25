import re

_FRAME_RE = re.compile(r"FrameCnt:\s*(\d+)")
_LAT_RE   = re.compile(r"\[latitude:\s*([-\d.]+)\]")
_LON_RE   = re.compile(r"\[longitude:\s*([-\d.]+)\]")
_ALT_RE   = re.compile(r"\[rel_alt:\s*([\d.]+)")

def parse_srt(path: str) -> list:
    """Parse DJI SRT file → list of {frame, lat, lon, alt}."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    results = []
    # Split per subtitle block (angka baris + timestamp + konten)
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        fm = _FRAME_RE.search(block)
        lm = _LAT_RE.search(block)
        om = _LON_RE.search(block)
        am = _ALT_RE.search(block)
        if fm and lm and om and am:
            results.append({
                "frame": int(fm.group(1)),
                "lat":   float(lm.group(1)),
                "lon":   float(om.group(1)),
                "alt":   float(am.group(1)),
            })
    return results

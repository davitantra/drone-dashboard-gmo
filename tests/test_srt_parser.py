import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.srt_parser import parse_srt

SRT_SAMPLE = """\
1
00:00:00,000 --> 00:00:00,033
<font size="28">FrameCnt: 1, DiffTime: 33ms
2026-06-06 14:10:52.123
[latitude: -2.130125] [longitude: 117.598456] [rel_alt: 18.200 abs_alt: 68.200] [iso: 100] [shutter: 1/1000.0] [fnum: 280] [ev: 0] [focal_len: 24.00] [dzoom_ratio: 10000, delta:0] [color_md : default] [focal_len35: 24.00] [latitude_str: 2.130125S] [longitude_str: 117.598456E]
</font>

2
00:00:00,033 --> 00:00:00,066
<font size="28">FrameCnt: 2, DiffTime: 33ms
2026-06-06 14:10:52.156
[latitude: -2.130200] [longitude: 117.598500] [rel_alt: 18.300 abs_alt: 68.300] [iso: 100] [shutter: 1/1000.0] [fnum: 280] [ev: 0] [focal_len: 24.00] [dzoom_ratio: 10000, delta:0] [color_md : default] [focal_len35: 24.00] [latitude_str: 2.130200S] [longitude_str: 117.598500E]
</font>
"""

def test_parse_srt_count():
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8") as f:
        f.write(SRT_SAMPLE)
        path = f.name
    result = parse_srt(path)
    assert len(result) == 2

def test_parse_srt_fields():
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8") as f:
        f.write(SRT_SAMPLE)
        path = f.name
    result = parse_srt(path)
    r = result[0]
    assert r["frame"] == 1
    assert abs(r["lat"] - (-2.130125)) < 1e-6
    assert abs(r["lon"] - 117.598456) < 1e-6
    assert abs(r["alt"] - 18.2) < 0.01

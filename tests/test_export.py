"""
Unit tests untuk fungsi _build_csv dan _build_excel di api/export.py.
Tidak memerlukan Flask app atau database — hanya menguji logika output.
"""
import csv
import io
import sys
import os

# Tambahkan project root ke sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.export import _build_csv, _build_excel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakeRow(dict):
    """dict yang mendukung akses atribut (meniru sqlite3.Row)."""
    def __getitem__(self, key):
        return super().__getitem__(key)


def make_rows():
    return [
        FakeRow({
            "id": 1, "latitude": -2.1300, "longitude": 117.4500,
            "status_tanam": "ditanam", "diameter_tajuk_m": 1.2,
            "kategori_tajuk": "hijau", "usia_bulan": 14, "blok_id": 3,
        }),
        FakeRow({
            "id": 2, "latitude": -2.1310, "longitude": 117.4510,
            "status_tanam": "tidak_tanam", "diameter_tajuk_m": None,
            "kategori_tajuk": "merah", "usia_bulan": None, "blok_id": None,
        }),
    ]


# ---------------------------------------------------------------------------
# CSV tests
# ---------------------------------------------------------------------------

def test_csv_header():
    csv_str = _build_csv(make_rows())
    reader = csv.reader(io.StringIO(csv_str))
    header = next(reader)
    assert header == [
        "id", "latitude", "longitude", "status_tanam",
        "diameter_tajuk_m", "kategori_tajuk", "usia_bulan", "blok_id",
    ]


def test_csv_row_count():
    csv_str = _build_csv(make_rows())
    reader = csv.reader(io.StringIO(csv_str))
    rows = list(reader)
    assert len(rows) == 3  # header + 2 data rows


def test_csv_first_row_values():
    csv_str = _build_csv(make_rows())
    reader = csv.reader(io.StringIO(csv_str))
    next(reader)  # skip header
    row = next(reader)
    assert row[0] == "1"
    assert float(row[1]) == -2.13
    assert row[4] == "1.2"
    assert row[6] == "14"
    assert row[7] == "3"


def test_csv_null_values_become_empty():
    csv_str = _build_csv(make_rows())
    reader = csv.reader(io.StringIO(csv_str))
    next(reader)  # header
    next(reader)  # row 1
    row = next(reader)  # row 2 (nulls)
    assert row[4] == ""   # diameter_tajuk_m None
    assert row[6] == ""   # usia_bulan None
    assert row[7] == ""   # blok_id None


def test_csv_empty_rows():
    csv_str = _build_csv([])
    reader = csv.reader(io.StringIO(csv_str))
    rows = list(reader)
    assert len(rows) == 1  # header only


# ---------------------------------------------------------------------------
# Excel tests
# ---------------------------------------------------------------------------

def test_excel_returns_bytes():
    result = _build_excel(make_rows())
    assert isinstance(result, bytes)
    # XLSX magic bytes (PK)
    assert result[:2] == b"PK"


def test_excel_sheet_name():
    import openpyxl
    result = _build_excel(make_rows())
    wb = openpyxl.load_workbook(io.BytesIO(result))
    assert "Lubang Deteksi" in wb.sheetnames


def test_excel_header_row():
    import openpyxl
    result = _build_excel(make_rows())
    wb = openpyxl.load_workbook(io.BytesIO(result))
    ws = wb["Lubang Deteksi"]
    headers = [ws.cell(1, c).value for c in range(1, 9)]
    assert headers == [
        "id", "latitude", "longitude", "status_tanam",
        "diameter_tajuk_m", "kategori_tajuk", "usia_bulan", "blok_id",
    ]


def test_excel_data_values():
    import openpyxl
    result = _build_excel(make_rows())
    wb = openpyxl.load_workbook(io.BytesIO(result))
    ws = wb["Lubang Deteksi"]
    assert ws.cell(2, 1).value == 1          # id
    assert ws.cell(2, 2).value == -2.13      # latitude
    assert ws.cell(2, 6).value == "hijau"    # kategori_tajuk
    assert ws.cell(3, 5).value is None       # diameter None stays None in xlsx


def test_excel_empty_rows():
    import openpyxl
    result = _build_excel([])
    wb = openpyxl.load_workbook(io.BytesIO(result))
    ws = wb["Lubang Deteksi"]
    assert ws.max_row == 1  # header only


# ---------------------------------------------------------------------------
# Runner (optional direct execution)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_csv_header, test_csv_row_count, test_csv_first_row_values,
        test_csv_null_values_become_empty, test_csv_empty_rows,
        test_excel_returns_bytes, test_excel_sheet_name, test_excel_header_row,
        test_excel_data_values, test_excel_empty_rows,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")

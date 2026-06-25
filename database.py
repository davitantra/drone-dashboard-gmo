import sqlite3, os
from config import DB_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS boundaries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nama        TEXT NOT NULL,
            deskripsi   TEXT DEFAULT '',
            shp_dir     TEXT NOT NULL,
            luas_ha     REAL DEFAULT 0,
            jumlah_blok INTEGER DEFAULT 0,
            uploaded_at TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bloks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            boundary_id  INTEGER NOT NULL REFERENCES boundaries(id) ON DELETE CASCADE,
            nama_area    TEXT NOT NULL,
            elevasi      REAL,
            bulan_tanam  TEXT,
            tahun_tanam  INTEGER,
            luas_ha      REAL,
            target_lubang INTEGER,
            geom_wkt     TEXT
        );

        CREATE TABLE IF NOT EXISTS canopy_thresholds (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            jenis_tanaman   TEXT NOT NULL DEFAULT 'default',
            usia_min_bulan  INTEGER NOT NULL,
            usia_max_bulan  INTEGER,
            diameter_min_m  REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS drone_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nama            TEXT NOT NULL,
            tanggal_terbang TEXT NOT NULL,
            boundary_id     INTEGER REFERENCES boundaries(id),
            status          TEXT NOT NULL DEFAULT 'pending',
            video_files     TEXT DEFAULT '[]',
            created_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lubang_deteksi (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id       INTEGER NOT NULL REFERENCES drone_sessions(id) ON DELETE CASCADE,
            blok_id          INTEGER REFERENCES bloks(id),
            latitude         REAL NOT NULL,
            longitude        REAL NOT NULL,
            status_tanam     TEXT NOT NULL,
            diameter_tajuk_m REAL,
            kategori_tajuk   TEXT NOT NULL DEFAULT 'merah',
            usia_bulan       INTEGER
        );
    """)
    # Seed default thresholds jika belum ada
    cur = conn.execute("SELECT COUNT(*) FROM canopy_thresholds WHERE jenis_tanaman='default'")
    if cur.fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO canopy_thresholds (jenis_tanaman, usia_min_bulan, usia_max_bulan, diameter_min_m) VALUES (?,?,?,?)",
            [
                ("default", 0,  2,    0.15),
                ("default", 3,  5,    0.30),
                ("default", 6,  11,   0.60),
                ("default", 12, None, 1.00),
            ]
        )
    conn.commit()
    conn.close()

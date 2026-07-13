// app.js - Tab switching, upload, CRUD boundary, SSE progress
let currentSessionId = null;
let currentBoundaryId = null;

// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-tab').forEach(function(tab) {
  tab.addEventListener('click', function() {
    document.querySelectorAll('.nav-tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'peta') { setTimeout(function() { map.invalidateSize(); }, 100); }
    if (tab.dataset.tab === 'review') { loadReviewSessions(); }
  });
});

// ── Load awal ─────────────────────────────────────────────────────────────────
async function loadSessions() {
  try {
    const res = await fetch('/api/sessions');
    const sessions = await res.json();
    const sel = document.getElementById('session-select');
    sel.innerHTML = '<option value="">-- Pilih sesi --</option>';
    const allOpt = document.createElement('option');
    allOpt.value = 'all';
    allOpt.textContent = '-- Semua Sesi --';
    sel.appendChild(allOpt);
    sessions.forEach(function(s) {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = s.nama + ' (' + s.tanggal_terbang + ') — ' + s.status;
      sel.appendChild(opt);
    });
    renderSessionList(sessions);
  } catch(e) { console.warn('loadSessions error:', e); }
}

async function loadBoundaries() {
  try {
    const res = await fetch('/api/boundaries');
    const bounds = await res.json();
    ['sesi-boundary', 'boundary-map-select'].forEach(function(id) {
      const sel = document.getElementById(id);
      if (!sel) return;
      sel.innerHTML = '<option value="">-- Pilih boundary --</option>';
      bounds.forEach(function(b) {
        const opt = document.createElement('option');
        opt.value = b.id;
        opt.textContent = b.nama + ' (' + b.jumlah_blok + ' blok, ' + (b.luas_ha ? parseFloat(b.luas_ha).toFixed(2) : '0') + ' ha)';
        sel.appendChild(opt);
      });
    });
    renderBoundaryList(bounds);
  } catch(e) { console.warn('loadBoundaries error:', e); }
}

// ── Peta session & boundary select ───────────────────────────────────────────
document.getElementById('session-select').addEventListener('change', function(e) {
  currentSessionId = e.target.value;
  if (currentSessionId === 'all') loadHoles('all');
  else if (currentSessionId) loadHoles(currentSessionId);
  else document.getElementById('stats-panel').style.display = 'none';
});

document.getElementById('boundary-map-select').addEventListener('change', function(e) {
  currentBoundaryId = e.target.value;
  if (currentBoundaryId) {
    loadBloks(currentBoundaryId);
    loadBlokTable(currentBoundaryId, currentSessionId);
  } else {
    document.getElementById('bottom-table').style.display = 'none';
  }
});

// ── Sesi Tab ──────────────────────────────────────────────────────────────────
document.getElementById('btn-new-session').addEventListener('click', function() {
  document.getElementById('upload-panel').style.display = '';
  document.getElementById('sesi-tanggal').value = new Date().toISOString().slice(0, 10);
});

document.getElementById('btn-cancel-upload').addEventListener('click', function() {
  document.getElementById('upload-panel').style.display = 'none';
});

// File upload drag & drop
const videoInput = document.getElementById('video-input');
document.getElementById('video-drop').addEventListener('click', function() { videoInput.click(); });
videoInput.addEventListener('change', function() {
  const list = document.getElementById('video-list');
  list.innerHTML = '';
  Array.from(videoInput.files).forEach(function(f) {
    const div = document.createElement('div');
    div.style.cssText = 'font-size:11px;color:#555;padding:2px 0';
    div.textContent = '📄 ' + f.name;
    list.appendChild(div);
  });
});

document.getElementById('btn-upload').addEventListener('click', async function() {
  const nama  = document.getElementById('sesi-nama').value || 'Sesi Drone';
  const tgl   = document.getElementById('sesi-tanggal').value;
  const bid   = document.getElementById('sesi-boundary').value;
  const files = videoInput.files;
  if (!files.length) { alert('Pilih file video terlebih dahulu'); return; }

  const fd = new FormData();
  fd.append('nama', nama);
  fd.append('tanggal_terbang', tgl);
  if (bid) fd.append('boundary_id', bid);
  Array.from(files).forEach(function(f) {
    if (f.name.match(/\.mp4$/i)) fd.append('videos', f);
    else if (f.name.match(/\.srt$/i)) fd.append('srts', f);
  });

  document.getElementById('upload-panel').style.display = 'none';
  document.getElementById('progress-panel').style.display = '';

  try {
    const res  = await fetch('/api/sessions', { method: 'POST', body: fd });
    const sess = await res.json();
    if (!res.ok) { alert('Error: ' + (sess.error || 'Upload gagal')); document.getElementById('progress-panel').style.display = 'none'; return; }
    currentSessionId = sess.id;

    await fetch('/api/sessions/' + sess.id + '/process', { method: 'POST' });
    listenProgress(sess.id);
    loadSessions();
  } catch(e) {
    console.error('upload error:', e);
    alert('Upload gagal: ' + e.message);
    document.getElementById('progress-panel').style.display = 'none';
  }
});

function listenProgress(sid) {
  const es = new EventSource('/api/sessions/' + sid + '/status');
  es.onmessage = function(e) {
    try {
      const data = JSON.parse(e.data);
      document.getElementById('progress-fill').style.width = (data.pct || 0) + '%';
      document.getElementById('progress-msg').textContent = data.msg || '';
      if (data.done) {
        es.close();
        document.getElementById('progress-panel').style.display = 'none';
        loadHoles(sid);
        loadSessions();
        if (currentBoundaryId) loadBlokTable(currentBoundaryId, sid);
      }
    } catch(err) { console.warn('SSE parse error:', err); }
  };
  es.onerror = function() { es.close(); document.getElementById('progress-panel').style.display = 'none'; };
}

// ── Session list render ───────────────────────────────────────────────────────
function renderSessionList(sessions) {
  const container = document.getElementById('session-list');
  if (!container) return;
  container.innerHTML = '';
  if (!sessions.length) {
    container.innerHTML = '<p style="color:#888;font-size:12px;padding:12px">Belum ada sesi. Klik "+ Sesi Baru" untuk upload video drone.</p>';
    return;
  }
  sessions.forEach(function(s) {
    const statusClass = 'status-' + (s.status || 'pending');
    const card = document.createElement('div');
    card.className = 'session-card';
    card.innerHTML =
      '<div class="session-card-info">' +
        '<h4>' + s.nama + ' <span class="status-badge ' + statusClass + '">' + s.status + '</span></h4>' +
        '<p>' + s.tanggal_terbang + (s.boundary_id ? ' · Boundary #' + s.boundary_id : '') + '</p>' +
      '</div>' +
      '<div class="session-card-actions">' +
        (s.status === 'pending' ? '<button class="btn btn-sm" onclick="processSession(' + s.id + ')">▶ Proses</button>' : '') +
        (s.status === 'done' ? '<button class="btn btn-sm btn-outline" onclick="viewSession(' + s.id + ')">🗺️ Lihat</button>' : '') +
        '<button class="btn btn-sm btn-danger" onclick="deleteSession(' + s.id + ')" title="Hapus sesi">🗑</button>' +
      '</div>';
    container.appendChild(card);
  });
}

function processSession(id) {
  fetch('/api/sessions/' + id + '/process', { method: 'POST' })
    .then(function(res) {
      if (!res.ok) {
        return res.json().catch(function() { return {}; }).then(function(err) {
          alert('Gagal memproses: ' + (err.error || res.status));
        });
      }
      document.getElementById('progress-panel').style.display = '';
      listenProgress(id);
    });
}

function viewSession(id) {
  currentSessionId = id;
  document.getElementById('session-select').value = id;
  // Switch to peta tab
  document.querySelectorAll('.nav-tab').forEach(function(t) { t.classList.remove('active'); });
  document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
  document.querySelector('.nav-tab[data-tab="peta"]').classList.add('active');
  document.getElementById('tab-peta').classList.add('active');
  setTimeout(function() { map.invalidateSize(); loadHoles(id); }, 100);
}

// ── Blok table ────────────────────────────────────────────────────────────────
async function loadBlokTable(boundaryId, sessionId) {
  if (!boundaryId) return;
  try {
    const bloks = await (await fetch('/api/boundaries/' + boundaryId + '/bloks')).json();
    let holes = [];
    if (sessionId) {
      const gj = await (await fetch('/api/map/' + sessionId)).json();
      holes = gj.features || [];
    }

    const tbody = document.querySelector('#blok-table tbody');
    tbody.innerHTML = '';
    bloks.forEach(function(b) {
      const bHoles = holes.filter(function(h) { return h.properties.blok_id === b.id; });
      const hijau  = bHoles.filter(function(h) { return h.properties.kategori_tajuk === 'hijau'; }).length;
      const oranye = bHoles.filter(function(h) { return h.properties.kategori_tajuk === 'oranye'; }).length;
      const merah  = bHoles.filter(function(h) { return h.properties.kategori_tajuk === 'merah'; }).length;
      const total  = bHoles.length;
      const cov    = b.target_lubang ? (total / b.target_lubang * 100).toFixed(1) : '—';
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + b.nama_area + '</td>' +
        '<td>' + b.luas_ha + ' ha</td>' +
        '<td>' + b.target_lubang + '</td>' +
        '<td>' + total + '</td>' +
        '<td><span class="badge badge-hijau">' + hijau + '</span></td>' +
        '<td><span class="badge badge-oranye">' + oranye + '</span></td>' +
        '<td><span class="badge badge-merah">' + merah + '</span></td>' +
        '<td>' + cov + '%</td>';
      tbody.appendChild(tr);
    });
    document.getElementById('bottom-table').style.display = '';
  } catch(e) { console.warn('loadBlokTable error:', e); }
}

// ── Export ────────────────────────────────────────────────────────────────────
document.getElementById('btn-export-csv').addEventListener('click', function() {
  if (currentSessionId) window.location = '/api/export/' + currentSessionId + '/csv';
});
document.getElementById('btn-export-excel').addEventListener('click', function() {
  if (currentSessionId) window.location = '/api/export/' + currentSessionId + '/excel';
});

// ── Boundary CRUD ─────────────────────────────────────────────────────────────
document.getElementById('btn-add-boundary').addEventListener('click', function() {
  document.getElementById('add-boundary-form').style.display = '';
});
document.getElementById('btn-cancel-boundary').addEventListener('click', function() {
  document.getElementById('add-boundary-form').style.display = 'none';
});

const bndFile = document.getElementById('bnd-file');
document.getElementById('bnd-drop').addEventListener('click', function() { bndFile.click(); });
bndFile.addEventListener('change', function() {
  document.getElementById('bnd-filename').textContent = bndFile.files[0] ? bndFile.files[0].name : '';
});

document.getElementById('btn-save-boundary').addEventListener('click', async function() {
  const nama = document.getElementById('bnd-nama').value;
  const desc = document.getElementById('bnd-desc').value;
  const file = bndFile.files[0];
  if (!file) { alert('Pilih file .zip'); return; }
  const fd = new FormData();
  fd.append('nama', nama);
  fd.append('deskripsi', desc);
  fd.append('file', file);
  const res = await fetch('/api/boundaries', { method: 'POST', body: fd });
  if (res.ok) {
    const data = await res.json();
    document.getElementById('add-boundary-form').style.display = 'none';
    document.getElementById('bnd-nama').value = '';
    document.getElementById('bnd-desc').value = '';
    document.getElementById('bnd-filename').textContent = '';
    loadBoundaries();
    // Switch to Peta tab and load the new boundary onto the map
    document.querySelectorAll('.nav-tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
    document.querySelector('.nav-tab[data-tab="peta"]').classList.add('active');
    document.getElementById('tab-peta').classList.add('active');
    setTimeout(function() { map.invalidateSize(); loadBloks(data.id); }, 100);
  } else {
    const err = await res.json();
    alert('Error: ' + (err.error || 'Upload gagal'));
  }
});

function renderBoundaryList(bounds) {
  const container = document.getElementById('boundary-list');
  container.innerHTML = '';
  if (!bounds.length) {
    container.innerHTML = '<p style="color:#888;font-size:12px;padding:12px">Belum ada boundary. Klik "+ Tambah Boundary" untuk upload shapefile.</p>';
    return;
  }
  bounds.forEach(function(b) {
    const card = document.createElement('div');
    card.className = 'boundary-card';
    card.innerHTML =
      '<div class="boundary-card-info">' +
        '<h4>' + b.nama + '</h4>' +
        '<p>' + b.jumlah_blok + ' blok · ' + parseFloat(b.luas_ha || 0).toFixed(2) + ' ha · Diupload ' + (b.uploaded_at ? b.uploaded_at.slice(0, 10) : '—') + '</p>' +
        (b.deskripsi ? '<p style="color:#aaa">' + b.deskripsi + '</p>' : '') +
      '</div>' +
      '<div class="boundary-card-actions">' +
        '<button class="btn btn-sm btn-outline" onclick="toggleBlokPanel(' + b.id + ')">📋 Blok</button>' +
        '<button class="btn btn-sm btn-outline" onclick="editBoundary(' + b.id + ', \'' + (b.nama || '').replace(/'/g, "\\'") + '\', \'' + (b.deskripsi || '').replace(/'/g, "\\'") + '\')">✏️ Edit</button>' +
        '<button class="btn btn-sm btn-danger" onclick="deleteBoundary(' + b.id + ')">🗑️ Hapus</button>' +
      '</div>';
    const blokPanel = document.createElement('div');
    blokPanel.id = 'blok-panel-' + b.id;
    blokPanel.style.display = 'none';
    blokPanel.style.cssText = 'padding:8px 16px 12px;border-top:1px solid #f0f0f0';
    blokPanel.innerHTML = '<div id="blok-panel-content-' + b.id + '" style="font-size:12px;color:#888">Memuat...</div>';
    card.style.flexWrap = 'wrap';
    card.appendChild(blokPanel);
    container.appendChild(card);
  });
}

async function toggleBlokPanel(bid) {
  const panel = document.getElementById('blok-panel-' + bid);
  if (!panel) return;
  if (panel.style.display !== 'none') { panel.style.display = 'none'; return; }
  panel.style.display = 'block';
  const content = document.getElementById('blok-panel-content-' + bid);
  try {
    const bloks = await (await fetch('/api/boundaries/' + bid + '/bloks')).json();
    if (!bloks.length) { content.innerHTML = '<em>Tidak ada blok.</em>'; return; }
    content.innerHTML = '<table style="width:100%;font-size:11px;border-collapse:collapse">' +
      '<thead><tr><th style="text-align:left;padding:4px 8px;background:#f5f7fa">Nama Area</th><th style="text-align:left;padding:4px 8px;background:#f5f7fa">Luas (ha)</th><th style="text-align:left;padding:4px 8px;background:#f5f7fa">Target Lubang</th><th style="padding:4px 8px;background:#f5f7fa"></th></tr></thead>' +
      '<tbody>' + bloks.map(function(blok) {
        return '<tr>' +
          '<td style="padding:4px 8px;border-bottom:1px solid #f0f0f0">' + blok.nama_area + '</td>' +
          '<td style="padding:4px 8px;border-bottom:1px solid #f0f0f0">' + blok.luas_ha + '</td>' +
          '<td style="padding:4px 8px;border-bottom:1px solid #f0f0f0">' + blok.target_lubang + '</td>' +
          '<td style="padding:4px 8px;border-bottom:1px solid #f0f0f0"><button class="btn btn-sm btn-danger" onclick="deleteBlok(' + bid + ',' + blok.id + ')">🗑 Hapus Blok</button></td>' +
          '</tr>';
      }).join('') + '</tbody></table>';
  } catch(e) { content.innerHTML = '<em>Gagal memuat blok.</em>'; }
}

async function editBoundary(id, nama, desc) {
  const newNama = prompt('Nama baru:', nama);
  if (newNama === null) return;
  const newDesc = prompt('Deskripsi:', desc);
  await fetch('/api/boundaries/' + id, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nama: newNama, deskripsi: newDesc })
  });
  loadBoundaries();
}

async function deleteBoundary(id) {
  if (!confirm('Hapus boundary ini? Semua data blok akan ikut terhapus.')) return;
  try {
    const res = await fetch('/api/boundaries/' + id, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json().catch(function() { return {}; });
      alert('Gagal menghapus: ' + (err.error || res.status));
      return;
    }
    if (currentBoundaryId == id) {
      currentBoundaryId = null;
      bloksLayer.clearLayers();
      document.getElementById('bottom-table').style.display = 'none';
    }
    loadBoundaries();
  } catch(e) {
    alert('Gagal menghapus boundary: ' + e.message);
  }
}

async function deleteSession(id) {
  if (!confirm('Hapus sesi ini beserta semua data deteksi lubang? Tindakan ini tidak dapat dibatalkan.')) return;
  try {
    const res = await fetch('/api/sessions/' + id, { method: 'DELETE' });
    if (!res.ok) { alert('Gagal menghapus sesi'); return; }
    loadSessions();
    if (currentSessionId == id) {
      currentSessionId = null;
      holesLayer.clearLayers();
      document.getElementById('stats-panel').style.display = 'none';
    }
  } catch(e) { console.error('deleteSession error:', e); }
}

async function deleteBlok(boundaryId, blokId) {
  if (!confirm('Hapus blok ini dari database? Shapefile asli tidak berubah.')) return;
  const res = await fetch('/api/boundaries/' + boundaryId + '/bloks/' + blokId, { method: 'DELETE' });
  if (res.ok) {
    loadBoundaries();
    if (currentBoundaryId == boundaryId) loadBloks(currentBoundaryId);
  }
}

// ── Settings ──────────────────────────────────────────────────────────────────
document.getElementById('btn-save-settings').addEventListener('click', function() {
  alert('Pengaturan disimpan (belum ada API settings).');
});

// ── Review Tab ────────────────────────────────────────────────────────────────
async function loadReviewSessions() {
  try {
    const res = await fetch('/api/sessions');
    const sessions = await res.json();
    const sel = document.getElementById('review-session-select');
    sel.innerHTML = '<option value="">-- Pilih Sesi --</option>';
    sessions.filter(s => s.status === 'done').forEach(function(s) {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = s.nama + ' (' + s.tanggal_terbang + ')';
      sel.appendChild(opt);
    });
  } catch(e) { console.warn('loadReviewSessions error:', e); }
}

document.getElementById('review-session-select').addEventListener('change', async function(e) {
  const sid = e.target.value;
  const grid = document.getElementById('frame-grid');
  const status = document.getElementById('review-status');
  grid.innerHTML = '';
  document.getElementById('review-stats-panel').style.display = 'none';
  if (!sid) return;
  status.textContent = 'Memuat frame...';
  try {
    const [framesRes, holesRes] = await Promise.all([
      fetch('/api/sessions/' + sid + '/frames'),
      fetch('/api/map/' + sid)
    ]);
    const frames = await framesRes.json();
    const holesGeoJSON = await holesRes.json();
    const holes = holesGeoJSON.features || [];
    status.textContent = frames.length + ' frame, ' + holes.length + ' lubang terdeteksi';
    renderFrameGrid(frames, holes, sid);
    // Fetch review stats
    fetch('/api/sessions/' + sid + '/review-stats')
      .then(r => r.json())
      .then(function(stats) {
        const panel = document.getElementById('review-stats-panel');
        panel.style.display = '';
        document.getElementById('review-stats-text').textContent =
          stats.reviewed_frames + ' frame di-review · ' + stats.total + ' lubang total (' +
          stats.auto + ' otomatis, ' + stats.manual + ' manual)';
        document.getElementById('auto-tune-result').style.display = 'none';
      });
  } catch(e) {
    console.warn('review load error:', e);
    status.textContent = 'Error memuat data';
  }
});

function renderFrameGrid(frames, holes, sid) {
  const grid = document.getElementById('frame-grid');
  grid.innerHTML = '';
  if (!frames.length) {
    grid.innerHTML = '<p style="color:#888;font-size:12px">Tidak ada frame tersimpan untuk sesi ini.</p>';
    return;
  }
  frames.forEach(function(frame, idx) {
    const card = document.createElement('div');
    card.style.cssText = 'border:1px solid #e0e0e0;border-radius:6px;overflow:hidden;cursor:pointer;background:#fff';
    card.innerHTML =
      '<img src="' + frame.url + '" style="width:100%;height:140px;object-fit:cover;display:block" ' +
      'onerror="this.style.background=\'#f5f5f5\';this.alt=\'Frame tidak tersedia\'" ' +
      'loading="lazy">' +
      '<div style="padding:6px 8px;font-size:11px;color:#555">' +
        '<b>Frame ' + (idx + 1) + '</b><br>' +
        frame.video.substring(0, 20) + (frame.video.length > 20 ? '…' : '') +
      '</div>';
    card.addEventListener('click', function() {
      openFrameModal(frames, holes, idx, sid);
    });
    grid.appendChild(card);
  });
}

// ── Review tab frame modal state ──────────────────────────────────────────────
let _modalFrames  = [];
let _modalHoles   = [];
let _modalSid     = null;
let _modalIdx     = 0;
let _modalChanged = false;

function openFrameModal(frames, holes, idx, sid) {
  _modalFrames = frames;
  _modalHoles  = holes;
  _modalSid    = sid;
  _modalIdx    = idx;
  document.getElementById('frame-modal').style.display = '';
  _renderModalFrame();
}

function _renderModalFrame() {
  const frame   = _modalFrames[_modalIdx];
  const img     = document.getElementById('modal-img');
  const counter = document.getElementById('modal-frame-counter');
  counter.textContent = 'Frame ' + (_modalIdx + 1) + ' / ' + _modalFrames.length +
    (frame.lat ? ' · GPS: ' + frame.lat.toFixed(5) + ', ' + frame.lon.toFixed(5) : ' · GPS tidak tersedia');
  document.getElementById('modal-info').textContent =
    _modalHoles.length + ' lubang terdeteksi total dalam sesi ini';
  img.src = frame.url;
  img.onload = function() { _drawCanvasOverlay(frame); };
  if (img.complete && img.naturalWidth) { _drawCanvasOverlay(frame); }
}

function navigateFrame(dir) {
  _modalIdx = Math.max(0, Math.min(_modalFrames.length - 1, _modalIdx + dir));
  _renderModalFrame();
}

function closeFrameModal() {
  if (_modalChanged && _modalSid && _modalFrames[_modalIdx]) {
    const f = _modalFrames[_modalIdx];
    fetch('/api/sessions/' + _modalSid + '/reviewed-frames', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video: f.video, filename: f.filename })
    });
  }
  _modalChanged = false;
  document.getElementById('frame-modal').style.display = 'none';
  document.getElementById('modal-img').src = '';
}

function _drawCanvasOverlay(frame) {
  const img    = document.getElementById('modal-img');
  const canvas = document.getElementById('modal-canvas');
  canvas.width  = img.offsetWidth  || img.naturalWidth;
  canvas.height = img.offsetHeight || img.naturalHeight;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (!frame.lat || !frame.lon || !frame.alt) return;

  const HFOV = 84 * Math.PI / 180;
  const VFOV = 63 * Math.PI / 180;
  const alt = frame.alt || 30;
  const fw = 2 * Math.tan(HFOV / 2) * alt;
  const fh = 2 * Math.tan(VFOV / 2) * alt;
  const mPerDegLat = 111320;
  const mPerDegLon = 111320 * Math.cos(frame.lat * Math.PI / 180);

  canvas._visibleHoles = [];

  _modalHoles.forEach(function(f) {
    const hLat = f.geometry.coordinates[1];
    const hLon = f.geometry.coordinates[0];
    const dLat = (hLat - frame.lat) * mPerDegLat;
    const dLon = (hLon - frame.lon) * mPerDegLon;
    const px = canvas.width  / 2 + (dLon / fw) * canvas.width;
    const py = canvas.height / 2 - (dLat / fh) * canvas.height;
    if (px < 0 || px > canvas.width || py < 0 || py > canvas.height) return;

    const kat = f.properties.kategori_tajuk || 'merah';
    const color = { hijau: '#27ae60', oranye: '#e67e22', merah: '#e74c3c' }[kat] || '#e74c3c';
    const r = 10;
    ctx.beginPath();
    ctx.arc(px, py, r, 0, 2 * Math.PI);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = color + '55';
    ctx.fill();
    canvas._visibleHoles.push({ id: f.properties.id, px: px, py: py, r: r, kat: kat });
  });

  canvas.onclick = function(e) {
    const rect = canvas.getBoundingClientRect();
    const cx = (e.clientX - rect.left) * (canvas.width  / rect.width);
    const cy = (e.clientY - rect.top)  * (canvas.height / rect.height);

    const hit = (canvas._visibleHoles || []).find(function(h) {
      return Math.hypot(cx - h.px, cy - h.py) <= h.r + 8;
    });

    if (hit) {
      if (!confirm('Hapus lubang ini dari analisis?')) return;
      fetch('/api/sessions/' + _modalSid + '/holes/' + hit.id, { method: 'DELETE' })
        .then(function(res) {
          if (res.ok) {
            _modalChanged = true;
            _modalHoles = _modalHoles.filter(function(f) { return f.properties.id !== hit.id; });
            _drawCanvasOverlay(frame);
            document.getElementById('modal-info').textContent =
              _modalHoles.length + ' lubang terdeteksi total dalam sesi ini';
          }
        });
    } else {
      if (!frame.lat || !frame.lon) { alert('GPS tidak tersedia untuk frame ini'); return; }
      const dLonM = (cx - canvas.width  / 2) / canvas.width  * fw;
      const dLatM = (canvas.height / 2 - cy) / canvas.height * fh;
      const mPerDegLat2 = 111320;
      const mPerDegLon2 = 111320 * Math.cos(frame.lat * Math.PI / 180);
      const newLat = frame.lat + dLatM / mPerDegLat2;
      const newLon = frame.lon + dLonM / mPerDegLon2;

      // Scale canvas display coords → source image coords (1920×1080) for pixel_to_gps
      const img2 = document.getElementById('modal-img');
      const srcX = cx / canvas.width  * (img2.naturalWidth  || 1920);
      const srcY = cy / canvas.height * (img2.naturalHeight || 1080);
      fetch('/api/sessions/' + _modalSid + '/holes/from_pixel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat: frame.lat, lon: frame.lon, alt: frame.alt,
          pixel_x: srcX, pixel_y: srcY,
          img_w: img2.naturalWidth || 1920, img_h: img2.naturalHeight || 1080
        })
      })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.id) {
          _modalChanged = true;
          _modalHoles.push({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [data.lon, data.lat] },
            properties: { id: data.id, kategori_tajuk: data.kategori_tajuk }
          });
          _drawCanvasOverlay(frame);
          document.getElementById('modal-info').textContent =
            _modalHoles.length + ' lubang terdeteksi total dalam sesi ini';
        }
      });
    }
  };
}

document.getElementById('frame-modal').addEventListener('click', function(e) {
  if (e.target === this) closeFrameModal();
});

async function deleteAllHoles() {
  const sid = document.getElementById('review-session-select').value;
  if (!sid) return;
  if (!confirm('Hapus SEMUA lubang untuk sesi ini? Tindakan ini tidak dapat dibatalkan.')) return;
  try {
    const res = await fetch('/api/sessions/' + sid + '/holes', { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) { alert('Gagal: ' + (data.error || res.status)); return; }
    _modalHoles = [];
    alert(data.deleted + ' lubang dihapus.');
    // Refresh review status and map
    document.getElementById('review-session-select').dispatchEvent(new Event('change'));
    if (currentSessionId == sid) loadHoles(sid);
  } catch(e) { alert('Gagal: ' + e.message); }
}

async function runAutoTune() {
  const sid = document.getElementById('review-session-select').value;
  if (!sid) return;
  const btn = document.getElementById('btn-auto-tune');
  const result = document.getElementById('auto-tune-result');
  btn.textContent = '⏳ Menghitung...';
  btn.disabled = true;
  result.style.display = 'none';
  try {
    const res = await fetch('/api/sessions/' + sid + '/auto-tune', { method: 'POST' });
    const data = await res.json();
    btn.textContent = '🔧 Auto-tune Parameter';
    btn.disabled = false;
    if (data.error) { result.textContent = 'Error: ' + data.error; result.style.display = ''; return; }
    result.innerHTML =
      '<b>Parameter terbaik ditemukan:</b> ' +
      'Circularity min: <b>' + data.circularity_min + '</b> · ' +
      'Area scale min: <b>' + data.area_scale_min + '</b> · ' +
      'Area scale max: <b>' + data.area_scale_max + '</b><br>' +
      'F1 score: <b>' + data.f1 + '</b> · Precision: ' + data.precision + ' · Recall: ' + data.recall +
      ' · Diuji pada ' + data.frames_tested + ' frame<br>' +
      '<em>Untuk menerapkan, re-proses sesi menggunakan parameter ini (fitur apply akan ditambahkan kemudian).</em>';
    result.style.display = '';
  } catch(e) {
    btn.textContent = '🔧 Auto-tune Parameter';
    btn.disabled = false;
    result.textContent = 'Gagal: ' + e.message;
    result.style.display = '';
  }
}

// ── Load awal ─────────────────────────────────────────────────────────────────
loadSessions();
loadBoundaries();

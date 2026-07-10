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
  });
});

// ── Load awal ─────────────────────────────────────────────────────────────────
async function loadSessions() {
  try {
    const res = await fetch('/api/sessions');
    const sessions = await res.json();
    const sel = document.getElementById('session-select');
    sel.innerHTML = '<option value="">-- Pilih sesi --</option>';
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
  if (currentSessionId) loadHoles(currentSessionId);
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
  await fetch('/api/boundaries/' + id, { method: 'DELETE' });
  loadBoundaries();
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

// ── Load awal ─────────────────────────────────────────────────────────────────
loadSessions();
loadBoundaries();

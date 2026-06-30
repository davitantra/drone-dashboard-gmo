// map.js - Leaflet map initialization dan layer management
let map, tileOnline, holesLayer, bloksLayer;

function initMap() {
  map = L.map('map').setView([-2.130737, 117.600155], 16);

  // Online tile (OSM)
  tileOnline = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap',
    maxZoom: 20
  });

  // Try to load OSM, silently ignore tile errors (offline fallback = blank map)
  tileOnline.addTo(map);
  tileOnline.on('tileerror', function() {
    // offline — blank map is fine
  });

  holesLayer = L.layerGroup().addTo(map);
  bloksLayer = L.layerGroup().addTo(map);
}

const WARNA = {
  hijau:  '#27ae60',
  oranye: '#e67e22',
  merah:  '#e74c3c'
};

const WARNA_FILL = {
  hijau:  'rgba(39,174,96,0.25)',
  oranye: 'rgba(230,126,34,0.25)',
  merah:  'rgba(231,76,60,0.25)'
};

function loadHoles(sessionId) {
  holesLayer.clearLayers();
  if (!sessionId) return;
  fetch('/api/map/' + sessionId)
    .then(function(r) { return r.json(); })
    .then(function(geojson) {
      const counts = { hijau: 0, oranye: 0, merah: 0 };
      if (!geojson.features) return;
      geojson.features.forEach(function(f) {
        const p = f.properties;
        const kat = p.kategori_tajuk || 'merah';
        counts[kat] = (counts[kat] || 0) + 1;
        const marker = L.circleMarker(
          [f.geometry.coordinates[1], f.geometry.coordinates[0]],
          { radius: 5, fillColor: WARNA[kat] || '#888', color: '#fff', weight: 1, fillOpacity: 0.85 }
        );
        marker.bindPopup(
          '<b>' + kat.toUpperCase() + '</b><br>' +
          'Status: ' + (p.status_tanam || '—') + '<br>' +
          'Tajuk: ' + (p.diameter_tajuk_m ? parseFloat(p.diameter_tajuk_m).toFixed(2) + ' m' : 'tidak terdeteksi') + '<br>' +
          'Usia: ' + (p.usia_bulan !== null && p.usia_bulan !== undefined ? p.usia_bulan : '—') + ' bulan<br>' +
          '<a href="https://maps.google.com/?q=' + f.geometry.coordinates[1] + ',' + f.geometry.coordinates[0] + '" target="_blank">Google Maps</a>'
        );
        holesLayer.addLayer(marker);
      });
      // Update stats
      document.getElementById('stat-total').textContent = geojson.features.length;
      document.getElementById('stat-hijau').textContent = counts.hijau;
      document.getElementById('stat-oranye').textContent = counts.oranye;
      document.getElementById('stat-merah').textContent = counts.merah;
      document.getElementById('stats-panel').style.display = '';
      if (geojson.features.length > 0) {
        const lats = geojson.features.map(function(f) { return f.geometry.coordinates[1]; });
        const lons = geojson.features.map(function(f) { return f.geometry.coordinates[0]; });
        map.fitBounds([[Math.min.apply(null, lats), Math.min.apply(null, lons)], [Math.max.apply(null, lats), Math.max.apply(null, lons)]]);
      }
    })
    .catch(function(err) { console.warn('loadHoles error:', err); });
}

function loadBloks(boundaryId) {
  bloksLayer.clearLayers();
  if (!boundaryId) return;
  fetch('/api/map/bloks/' + boundaryId)
    .then(function(r) { return r.json(); })
    .then(function(geojson) {
      L.geoJSON(geojson, {
        style: function(f) {
          var c = f.properties.color || 'merah';
          return { color: WARNA[c] || '#888', weight: 2, fillOpacity: 0.35, fillColor: WARNA_FILL[c] || WARNA_FILL.merah };
        },
        onEachFeature: function(f, layer) {
          const p = f.properties;
          layer.bindPopup(
            '<b>' + (p.nama_area || '—') + '</b><br>' +
            'Luas: ' + (p.luas_ha || '—') + ' ha<br>' +
            'Target: ' + (p.target_lubang || '—') + ' lubang<br>' +
            'Tanam: ' + (p.bulan_tanam || '—') + ' ' + (p.tahun_tanam || '')
          );
        }
      }).addTo(bloksLayer);
    })
    .catch(function(err) { console.warn('loadBloks error:', err); });
}

initMap();

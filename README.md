# ha-laadpaal-road 🚗⚡

Dit project hangt aan elkaar met pure vibes. Geen garanties, geen aansprakelijkheid en geen idee waarom het onder water werkt. Gebruik op eigen risico.

---

## Stap 1: De Location ID Finder (Hosting)

Zonder de juiste `location_id` doet de integratie niets. Omdat de Road API browser-beveiliging (CORS) heeft, moet je de bijgevoegde `index.html` hosten via een Nginx-server die fungeert als reverse proxy. Niet aan te raden om op het grote boze internet te hosten. 

Je vraagt je misschien af, kan dit makkelijker? 

Het antwoord is waarschijnlijk "ja" 

In my defense: I have no idea what I'm doing 

### 1.1 De Finder Tool (index.html)
Sla deze code op als `index.html` op je server.

```html
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>EV Config Tool 3.1 - Raw ID Edition</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body { font-family: 'Segoe UI', sans-serif; display: flex; height: 100vh; margin: 0; background: #121212; color: #ececec; }
        #map { flex: 1; border-right: 2px solid #333; }
        #sidebar { width: 480px; padding: 20px; overflow-y: auto; background: #1e1e1e; display: flex; flex-direction: column; }
        
        .search-box { display: flex; gap: 8px; margin-bottom: 20px; }
        input[type="text"] { flex: 1; padding: 10px; background: #2a2a2a; border: 1px solid #444; color: #fff; border-radius: 4px; }
        
        button { padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; transition: 0.2s; }
        .btn-search { background: #4caf50; color: white; }
        .btn-copy { background: #03a9f4; color: white; margin-top: 10px; width: 100%; }
        
        .result-item { 
            background: #2a2a2a; border: 1px solid #3d3d3d; border-radius: 6px; padding: 15px; margin-bottom: 10px; 
            cursor: pointer; transition: transform 0.1s; position: relative;
        }
        .result-item:hover { transform: scale(1.01); border-color: #03a9f4; background: #333; }
        .result-item h4 { margin: 0 0 8px 0; color: #fff; padding-right: 60px; }
        
        .dist-badge { position: absolute; top: 15px; right: 15px; font-size: 0.8em; color: #03a9f4; font-weight: bold; }
        
        pre { background: #000; padding: 15px; border-radius: 6px; font-size: 14px; color: #a6e22e; border: 1px solid #333; overflow-x: auto; text-align: center; font-weight: bold; }
        .status-tag { display: inline-block; padding: 2px 6px; border-radius: 3px; background: #444; font-size: 0.75em; margin-right: 5px; }
        
        #id-section { margin-top: 20px; border-top: 1px solid #333; padding-top: 20px; display: none; }
    </style>
</head>
<body>

<div id="map"></div>

<div id="sidebar">
    <h2>EV Scouter</h2>
    
    <div class="search-box">
        <input type="text" id="addrInput" placeholder="Zoek adres...">
        <button class="btn-search" onclick="searchAddress()">Zoek</button>
    </div>

    <div id="results-list">
        <p style="color: #888;">Klik op de kaart of zoek een adres om palen te vinden.</p>
    </div>

    <div id="id-section">
        <h3>Location ID</h3>
        <p style="font-size: 0.85em; color: #aaa; margin-top: 0;">Klaar voor gebruik in je REST payload</p>
        <pre id="rawIdDisplay"></pre>
        <button class="btn-copy" onclick="copyRawId()">Kopieer ID</button>
    </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
    const map = L.map('map').setView([52.195, 5.967], 15);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

    function getDistance(lat1, lon1, lat2, lon2) {
        const R = 6371e3; 
        const φ1 = lat1 * Math.PI/180;
        const φ2 = lat2 * Math.PI/180;
        const Δφ = (lat2-lat1) * Math.PI/180;
        const Δλ = (lon2-lon1) * Math.PI/180;

        const a = Math.sin(Δφ/2) * Math.sin(Δφ/2) +
                  Math.cos(φ1) * Math.cos(φ2) *
                  Math.sin(Δλ/2) * Math.sin(Δλ/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));

        return R * c; 
    }

    async function searchAddress() {
        const query = document.getElementById('addrInput').value;
        if (!query) return;
        try {
            const resp = await fetch(`/osm-proxy/search?q=${encodeURIComponent(query)}&format=json&limit=1`);
            const data = await resp.json();
            if (data.length > 0) {
                const lat = parseFloat(data[0].lat), lon = parseFloat(data[0].lon);
                map.setView([lat, lon], 17);
                triggerSearch(lat, lon);
            }
        } catch (e) { alert("Adres zoeken mislukt."); }
    }

    map.on('click', e => triggerSearch(e.latlng.lat, e.latlng.lng));

    async function triggerSearch(lat, lon) {
        const list = document.getElementById('results-list');
        list.innerHTML = "Palen ophalen en sorteren...";
        document.getElementById('id-section').style.display = 'none';

        const bbox = {
            nwLat: lat + 0.005, nwLng: lon - 0.005,
            seLat: lat - 0.005, seLng: lon + 0.005
        };

        try {
            const searchResp = await fetch('/road-proxy/1/map/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ gridPrecision: 8, bbox })
            });
            const searchJson = await searchResp.json();
            
            if (searchJson.data && searchJson.data.length > 0) {
                const allIds = searchJson.data.map(item => item.ids[0]);
                
                const locResp = await fetch('/road-proxy/1/map/locations', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: allIds })
                });
                const locJson = await locResp.json();
                
                locJson.data.forEach(station => {
                    const sLat = station.geoLocation.coordinates[1];
                    const sLon = station.geoLocation.coordinates[0];
                    station.calculatedDistance = getDistance(lat, lon, sLat, sLon);
                });

                locJson.data.sort((a, b) => a.calculatedDistance - b.calculatedDistance);
                
                list.innerHTML = "";
                locJson.data.forEach(station => {
                    const div = document.createElement('div');
                    div.className = 'result-item';
                    const available = station.evses.filter(e => e.status === 'AVAILABLE').length;
                    const distStr = station.calculatedDistance > 1000 
                        ? (station.calculatedDistance / 1000).toFixed(1) + " km" 
                        : Math.round(station.calculatedDistance) + " m";
                    
                    div.innerHTML = `
                        <div class="dist-badge">${distStr}</div>
                        <h4>${station.address || 'Onbekend adres'}, ${station.city || ''}</h4>
                        <span class="status-tag">Vrij: ${available}/${station.evses.length}</span>
                        <span class="status-tag" style="background:#222">${station.operator.name || 'CPO'}</span>
                    `;
                    div.onclick = () => selectStation(station);
                    list.appendChild(div);
                });
            } else {
                list.innerHTML = "Geen palen gevonden in dit gebied.";
            }
        } catch (e) { list.innerHTML = "Fout bij ophalen van paalgegevens."; }
    }

    function selectStation(station) {
        document.getElementById('id-section').style.display = 'block';
        
        // Alleen het kale ID in het codeblokje zetten
        document.getElementById('rawIdDisplay').innerText = station.id;
    }

    function copyRawId() {
        const text = document.getElementById('rawIdDisplay').innerText;
        navigator.clipboard.writeText(text).then(() => alert("Location ID gekopieerd!"));
    }
</script>
</body>
</html>


### 1.2 Nginx Configuratie
Voeg de volgende `location` block toe aan je bestaande Nginx `server` configuratie om de browser-beveiliging te omzeilen:

```nginx
# Proxy pad voor de Road API
location /road-proxy/ {
    proxy_pass [https://api.road.io/](https://api.road.io/);
    proxy_set_header Host api.road.io;
    proxy_set_header Origin [https://www.e-flux.io](https://www.e-flux.io);
    proxy_set_header Referer [https://www.e-flux.io/](https://www.e-flux.io/);
    proxy_ssl_server_name on;

    # Browser CORS headers om toegang te verlenen aan je lokale script
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Content-Type' always;

    # Afhandeling van preflight verzoeken
    if ($request_method = 'OPTIONS') {
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Max-Age' 1728000;
        add_header 'Content-Type' 'text/plain; charset=utf-8';
        add_header 'Content-Length' 0;
        return 204;
    }
}
```

---

## Stap 2: Installatie via HACS

1. Ga in Home Assistant naar **HACS** > **Integrations**.
2. Klik op de drie puntjes rechtsboven > **Custom repositories**.
3. Plak de URL van deze GitHub repo erin en kies bij Category voor **Integration**.
4. Installeer de integratie en herstart Home Assistant.
5. Ga naar **Settings** > **Devices & Services** > **Add Integration** en zoek naar **"Road.io"** om je palen toe te voegen met de ID's uit Stap 1.

---

## Stap 3: Dichtstbijzijnde vrije paal (Template Sensor)

De integratie haalt de data op. Deze sensor berekent automatisch de dichtstbijzijnde vrije paal op basis van de coördinaten uit de integratie. Plak dit in je `configuration.yaml`:

"Maar waarom splits je die coordinaten in de sensor en niet in de integratie met python?"

Ja goeie vraag

```yaml
template:
  - sensor:
      - name: "Road Dichtstbijzijnde Paal"
        icon: "mdi:map-marker-distance"
        unique_id: road_closest_charger_final
        state: >
          {% set palen = states.sensor | selectattr('attributes.vrije_plekken', 'defined') | selectattr('attributes.vrije_plekken', '>', 0) | list %}
          {% set ns = namespace(distances=[]) %}
          {% for paal in palen %}
            {% set base_id = paal.entity_id | replace('_beschikbaarheid', '') %}
            {% set coord_id = base_id ~ '_coordinaten' %}
            {% set coord_state = states(coord_id) %}
            {% if coord_state and ',' in coord_state %}
              {% set lat = coord_state.split(',')[0] | trim | float(0) %}
              {% set lon = coord_state.split(',')[1] | trim | float(0) %}
              {% set dist = distance(lat, lon) %}
              {% if dist != None %}
                {% set ns.distances = ns.distances + [{"naam": paal.name | replace(" Beschikbaarheid", ""), "afstand": (dist * 1000) | round(0)}] %}
              {% endif %}
            {% endif %}
          {% endfor %}
          {% set gesorteerd = ns.distances | sort(attribute='afstand') %}
          {{ gesorteerd[0].naam ~ ' (' ~ gesorteerd[0].afstand ~ 'm)' if gesorteerd | length > 0 else 'Geen paal vrij' }}
        attributes:
          palen_lijst: >
            {% set palen = states.sensor | selectattr('attributes.vrije_plekken', 'defined') | selectattr('attributes.vrije_plekken', '>', 0) | list %}
            {% set ns = namespace(distances=[]) %}
            {% for paal in palen %}
              {% set base_id = paal.entity_id | replace('_beschikbaarheid', '') %}
              {% set coord_id = base_id ~ '_coordinaten' %}
              {% set coord_state = states(coord_id) %}
              {% if coord_state and ',' in coord_state %}
                {% set lat = coord_state.split(',')[0] | trim | float(0) %}
                {% set lon = coord_state.split(',')[1] | trim | float(0) %}
                {% set dist = distance(lat, lon) %}
                {% if dist != None %}
                  {% set ns.distances = ns.distances + [{"naam": paal.name | replace(" Beschikbaarheid", ""), "afstand_m": (dist * 1000) | round(0), "vrije_sockets": paal.attributes.vrije_plekken}] %}
                {% endif %}
              {% endif %}
            {% endfor %}
            {{ ns.distances | sort(attribute='afstand_m') }}
```

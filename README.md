#ha-laadpaal-road 🚗⚡

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
    <title>E-flux Location ID Finder</title>
    <link rel="stylesheet" href="[https://unpkg.com/leaflet@1.9.4/dist/leaflet.css](https://unpkg.com/leaflet@1.9.4/dist/leaflet.css)" />
    <style>
        body { font-family: sans-serif; display: flex; height: 100vh; margin: 0; background: #1a1a1a; color: #e0e0e0; }
        #map { flex: 1; z-index: 1; }
        #sidebar { width: 400px; padding: 25px; overflow-y: auto; background: #2d2d2d; border-left: 1px solid #444; }
        .card { background: #3d3d3d; padding: 15px; border-radius: 8px; margin-bottom: 15px; }
        .id-box { background: #000; color: #a6e22e; padding: 12px; border-radius: 4px; font-family: monospace; word-break: break-all; }
        button { background: #03a9f4; border: none; color: white; padding: 12px; border-radius: 4px; cursor: pointer; width: 100%; font-weight: bold; margin-bottom: 10px; }
        .copy-btn { background: #4caf50; font-size: 13px; }
        h2 { color: #03a9f4; }
    </style>
</head>
<body>
<div id="map"></div>
<div id="sidebar">
    <h2>E-flux ID Finder</h2>
    <div id="results">Klik op de kaart om te zoeken...</div>
    <div id="detail-area" style="display:none; margin-top: 20px;">
        <div class="card">
            <strong id="displayName">Naam</strong><br>
            <div class="id-box" id="locationID">ID laden...</div>
            <button class="copy-btn" id="copyBtn" onclick="copyId()">Kopieer ID</button>
        </div>
    </div>
</div>
<script src="[https://unpkg.com/leaflet@1.9.4/dist/leaflet.js](https://unpkg.com/leaflet@1.9.4/dist/leaflet.js)"></script>
<script>
    const map = L.map('map').setView([52.211, 5.965], 14);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
    map.on('click', async function(e) {
        const res = document.getElementById('results');
        res.innerHTML = "Zoeken...";
        try {
            const response = await fetch('/road-proxy/1/map/clusters', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Origin': '[https://www.e-flux.io](https://www.e-flux.io)', 'Referer': '[https://www.e-flux.io/](https://www.e-flux.io/)' },
                body: JSON.stringify({ lat: e.latlng.lat, lng: e.latlng.lng, zoom: 15 })
            });
            const data = await response.json();
            res.innerHTML = "";
            if (data.locations) {
                data.locations.forEach(loc => {
                    const btn = document.createElement('button');
                    btn.innerText = `${loc.name || 'Onbekend'} (${loc.evses.length} poorten)`;
                    btn.onclick = () => {
                        document.getElementById('detail-area').style.display = 'block';
                        document.getElementById('displayName').innerText = loc.name;
                        document.getElementById('locationID').innerText = loc.id;
                    };
                    res.appendChild(btn);
                });
            }
        } catch (err) { res.innerHTML = "Proxy fout. Controleer Nginx configuratie."; }
    });
    function copyId() {
        navigator.clipboard.writeText(document.getElementById('locationID').innerText);
        document.getElementById('copyBtn').innerText = "Gekopieerd!";
        setTimeout(() => { document.getElementById('copyBtn').innerText = "Kopieer ID"; }, 2000);
    }
</script>
</body>
</html>
```

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

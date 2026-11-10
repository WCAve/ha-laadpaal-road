# EV Location Radar

Dit project hangt aan elkaar met pure vibes. Geen garanties, geen aansprakelijkheid en geen idee waarom het onder water werkt. Gebruik op eigen risico. Zelfs deze readme is pure ai slop. Bij mij werkt het, geen idee of het bij jou ook werkt als je deze stappen volgt. Succes met zelf vibecoden.

---

## Stap 1: De Location ID Finder

Zonder de juiste Location ID doet de integratie niets. Omdat de Road.io API browser-beveiliging (CORS) heeft, moet je de bijgevoegde `index.html` (te vinden in de `web_tool` map) hosten via een Nginx-server die fungeert als reverse proxy. Het adres zoeken gaat rechtstreeks via OpenStreetMap (Nominatim) en heeft geen proxy nodig.

Je vraagt je misschien af: kan dit makkelijker? Het antwoord is waarschijnlijk "ja". In my defense: I have no idea what I'm doing.

### Nginx Configuration
Zet `index.html` in de root van je Nginx site en voeg dit block toe aan dezelfde `server { ... }`. Het pad `/road-proxy/` moet precies zo heten, want de webtool roept dat aan.

```nginx
location /road-proxy/ {
    proxy_pass https://api.road.io/;
    proxy_set_header Host api.road.io;
    proxy_set_header Origin https://www.e-flux.io;
    proxy_set_header Referer https://www.e-flux.io/;
    proxy_ssl_server_name on;

    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Content-Type' always;

    if ($request_method = 'OPTIONS') {
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Max-Age' 1728000;
        add_header 'Content-Type' 'text/plain; charset=utf-8';
        add_header 'Content-Length' 0;
        return 204;
    }
}
```

1. Open je gehoste `index.html` in de browser.
2. Klik op de kaart of zoek een adres; rechts verschijnen de laadpalen in de buurt, gesorteerd op afstand.
3. Klik op een paal in de lijst en kopieer de Location ID.

---

## Stap 2: Installatie via HACS

1. Ga in Home Assistant naar **HACS** > **Integrations**.
2. Klik op de drie puntjes rechtsboven > **Custom repositories**.
3. Plak de URL van deze GitHub repo erin en kies bij Category voor **Integration**.
4. Installeer de integratie en herstart Home Assistant.
5. Ga naar **Settings** > **Devices & Services** > **Add Integration** en zoek naar **Road.io (E-flux) EV Charger** om je locaties toe te voegen met de ID's uit Stap 1. Het ID wordt direct gecontroleerd bij Road.io, en dezelfde locatie kan maar één keer worden toegevoegd.

Vereist Home Assistant 2025.1 of nieuwer.

---

## Stap 3: De Radar (Template Sensor)

De integratie haalt de data op, deze sensor doet het rekenwerk. Hij vindt automatisch de dichtstbijzijnde vrije locatie op basis van de coördinaten in de diagnostic sensor. Plak dit in je `configuration.yaml` (dezelfde code staat ook in `templates/sensor_closest_available_charger.txt`):

> De template zoekt naar sensoren die eindigen op `_beschikbaarheid` en `_coordinaten`. Hernoem die entiteiten dus niet.

```yaml
template:
  - sensor:
      - name: "Dichtstbijzijnde Laadpunt"
        icon: "mdi:map-marker-distance"
        unique_id: ev_radar_closest_charger
        state: >
          {% set palen = states.sensor | selectattr('attributes.vrije_plekken', 'defined') | selectattr('attributes.vrije_plekken', '>', 0) | list %}
          {% set ns = namespace(distances=[]) %}
          {% for paal in palen %}
            {% set base_id = paal.entity_id | replace('_beschikbaarheid', '') %}
            {% set coord_state = states(base_id ~ '_coordinaten') %}
            {% if ',' in coord_state %}
              {% set lat = coord_state.split(',')[0] | trim | float(0) %}
              {% set lon = coord_state.split(',')[1] | trim | float(0) %}
              {% set dist = distance(lat, lon) if lat != 0 and lon != 0 else None %}
              {% if dist is not none %}
                {% set ns.distances = ns.distances + [{"naam": paal.name | replace(" Beschikbaarheid", ""), "afstand": (dist * 1000) | round(0)}] %}
              {% endif %}
            {% endif %}
          {% endfor %}
          {% set gesorteerd = ns.distances | sort(attribute='afstand') %}
          {{ gesorteerd[0].naam ~ ' (' ~ gesorteerd[0].afstand ~ 'm)' if gesorteerd | length > 0 else 'Geen punt vrij' }}
        attributes:
          palen_lijst: >
            {% set palen = states.sensor | selectattr('attributes.vrije_plekken', 'defined') | selectattr('attributes.vrije_plekken', '>', 0) | list %}
            {% set ns = namespace(distances=[]) %}
            {% for paal in palen %}
              {% set base_id = paal.entity_id | replace('_beschikbaarheid', '') %}
              {% set coord_state = states(base_id ~ '_coordinaten') %}
              {% if ',' in coord_state %}
                {% set lat = coord_state.split(',')[0] | trim | float(0) %}
                {% set lon = coord_state.split(',')[1] | trim | float(0) %}
                {% set dist = distance(lat, lon) if lat != 0 and lon != 0 else None %}
                {% if dist is not none %}
                  {% set ns.distances = ns.distances + [{"naam": paal.name | replace(" Beschikbaarheid", ""), "afstand_m": (dist * 1000) | round(0), "vrije_sockets": paal.attributes.vrije_plekken}] %}
                {% endif %}
              {% endif %}
            {% endfor %}
            {{ ns.distances | sort(attribute='afstand_m') }}
```

---


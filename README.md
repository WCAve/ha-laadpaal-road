# EV Location Radar

Dit project hangt aan elkaar met pure vibes. Geen garanties, geen aansprakelijkheid en geen idee waarom het onder water werkt. Gebruik op eigen risico. Zelfs deze readme is pure ai slop. Bij mij werkt het, geen idee of het bij jou ook werkt als je deze stappen volgt. Succes met zelf vibecoden.

---

## Stap 1: De Location ID Finder

Zonder de juiste Location ID doet de integratie niets. Omdat de API van de provider browser-beveiliging (CORS) heeft, moet je de bijgevoegde `index.html` (te vinden in de `web_tool` map) hosten via een Nginx-server die fungeert als reverse proxy. 

Je vraagt je misschien af: kan dit makkelijker? Het antwoord is waarschijnlijk "ja". In my defense: I have no idea what I'm doing.

### Nginx Configuration
Voeg dit block toe aan je Nginx server config om de API bereikbaar te maken voor het script. Vervang de placeholders door de daadwerkelijke URL's van de provider (zoek deze op in de netwerk-tab van je browser als je hun officiële kaart gebruikt):

```nginx
location /provider-proxy/ {
    proxy_pass https://[API_ENDPOINT_HIER]/;
    proxy_set_header Host [API_HOST_HIER];
    proxy_set_header Origin https://[PROVIDER_URL_HIER];
    proxy_set_header Referer https://[PROVIDER_URL_HIER]/;
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
2. Zoek je gewenste locatie op de kaart.
3. Klik op de markering en kopieer de Location ID.

---

## Stap 2: Installatie via HACS

1. Ga in Home Assistant naar **HACS** > **Integrations**.
2. Klik op de drie puntjes rechtsboven > **Custom repositories**.
3. Plak de URL van deze GitHub repo erin en kies bij Category voor **Integration**.
4. Installeer de integratie en herstart Home Assistant.
5. Ga naar **Settings** > **Devices & Services** > **Add Integration** en zoek naar de betreffende integratie om je locaties toe te voegen met de ID's uit Stap 1.

---

## Stap 3: De Radar (Template Sensor)

De integratie haalt de data op, deze sensor doet het rekenwerk. Hij vindt automatisch de dichtstbijzijnde vrije locatie op basis van de coördinaten in de diagnostic sensor. Plak dit in je `configuration.yaml`:

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
          {{ gesorteerd[0].naam ~ ' (' ~ gesorteerd[0].afstand ~ 'm)' if gesorteerd | length > 0 else 'Geen punt vrij' }}
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

---

## Stap 4: Dashboard

Gebruik een **Markdown card** op je dashboard voor het resultaat:

```yaml
type: markdown
content: >
  **Beschikbare punten in de buurt:**
  {% set palen = state_attr('sensor.dichtstbijzijnde_laadpunt', 'palen_lijst') %}
  {% if palen %}
    {% for paal in palen %}
    {{ loop.index }}. **{{ paal.naam }}** ({{ paal.afstand_m }}m) - *{{ paal.vrije_sockets }} vrij*
    {% endfor %}
  {% else %}
    Alles bezet. Succes met lopen.
  {% endif %}
```

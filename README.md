# Road.io Radar

Dit project hangt aan elkaar met pure vibes. Geen garanties, geen aansprakelijkheid en geen idee waarom het onder water werkt. Gebruik op eigen risico.

---

## Stap 1: Vind Location IDs
Zonder ID doet de integratie niets. Gebruik de bijgevoegde webtool om ze binnen 10 seconden te vinden.
1. Open `index.html` in je browser.
2. Zoek je paal op de kaart.
3. Klik op de paal en kopieer de Location ID.

---

## Stap 2: Installatie via HACS
1. Ga in Home Assistant naar **HACS** > **Integrations**.
2. Klik op de drie puntjes rechtsboven > **Custom repositories**.
3. Plak de URL van deze GitHub repo erin en kies bij Category voor **Integration**.
4. Installeer de integratie en herstart Home Assistant.
5. Ga naar **Settings** > **Devices & Services** > **Add Integration** en zoek naar "Road.io" om je palen toe te voegen met de ID's uit Stap 1.

---

## Stap 3: De Radar (Template Sensor)
De integratie haalt de data op, deze sensor doet het rekenwerk. Hij vindt automatisch de dichtstbijzijnde vrije paal op basis van de coördinaten in de diagnostic sensor. Plak dit in je `configuration.yaml`:

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

# Road.io Home Assistant Project ⚡️

## ⚠️ Belangrijke Disclaimer (The Vibecode Clause)
Deze volledige repository is **100% vibecode**. Er worden absoluut **geen garanties** gegeven en er is **geen enkele aansprakelijkheid** voor gesmolten laadpalen, ontplofte Home Assistant databases of andere digitale of fysieke schade. De auteur heeft bovendien **geen flauw idee** hoe dit onderwater daadwerkelijk werkt; het functioneert momenteel puur op goede hoop en positieve energie.

---

## 1. Road.io Custom Integration (`road_ev`)

Deze integratie haalt de ruwe data op van specifieke laadlocaties via de Road.io API[cite: 1].

### Installatie
*   Plaats de map `road_ev` in de `custom_components` map van je Home Assistant installatie.
*   Herstart Home Assistant.
*   Voeg de integratie toe via de interface en vul de `Location ID` in van de paal die je wilt volgen.

### Beschikbare Entiteiten
Per laadlocatie worden de volgende sensoren aangemaakt[cite: 1]:
*   **Socket Status:** Geeft aan of een socket `Vrij`, `Bezet` of `Niet beschikbaar` is.
*   **Max Vermogen:** Het maximale laadvermogen per socket in kW.
*   **Prijs:** De actuele prijs in EUR/kWh inclusief BTW.
*   **Beschikbaarheid:** Toont de status als "X van de Y vrij".
    *   *Attributen:* `vrije_plekken`, `totale_plekken`.
*   **Diagnostiek:** Sensoren voor de `Aanbieder` en de `Coördinaten` (als tekststring).

---

## 2. Road Radar Template Sensor

Deze sensor fungeert als een "laadpaal-radar". Hij zoekt automatisch naar alle Road.io sensoren in je systeem, berekent de afstand tot je huis en toont de dichtstbijzijnde vrije optie.

### Configuratie (`configuration.yaml`)
Plak de volgende code onder je `template:` sectie:
```yaml
- sensor:
    - name: "Road Dichtstbijzijnde Paal"
      icon: "mdi:map-marker-distance"
      unique_id: road_closest_charger_final
      state: >
        {% set palen = states.sensor 
          | selectattr('attributes.vrije_plekken', 'defined') 
          | selectattr('attributes.vrije_plekken', '>', 0) 
          | list %}
        {% set ns = namespace(distances=[]) %}
        
        {% for paal in palen %}
          {% set base_id = paal.entity_id | replace('_beschikbaarheid', '') %}
          {% set coord_id = base_id ~ '_coordinaten' %}
          {% set coord_state = states(coord_id) %}
          
          {% if coord_state and ',' in coord_state %}
            {% set lat = coord_state.split(',')[0] | trim | float(0) %}
            {% set lon = coord_state.split(',')[1] | trim | float(0) %}
            
            {% if lat != 0 and lon != 0 %}
              {% set dist = distance(lat, lon) %}
              {% if dist != None %}
                {% set ns.distances = ns.distances + [{"naam": paal.name | replace(" Beschikbaarheid", ""), "afstand": (dist * 1000) | round(0)}] %}
              {% endif %}
            {% endif %}
          {% endif %}
        {% endfor %}
        
        {% set gesorteerd = ns.distances | sort(attribute='afstand') %}
        {% if gesorteerd | length > 0 %}
          {{ gesorteerd[0].naam }} ({{ gesorteerd[0].afstand }}m)
        {% else %}
          Geen paal vrij
        {% endif %}
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

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


## Stap 4: De kaart

De integratie brengt zijn eigen dashboardkaart mee; je hoeft niets los te installeren. Na een update één keer de browser verversen (eventueel cache legen), daarna:

1. Open een dashboard > **Bewerken** > **Kaart toevoegen**.
2. Zoek naar **Road.io laadpalen**.

De kaart toont al je laadpalen met status, prijs en afstand tot je thuislocatie, gesorteerd op afstand. Tik op een paal voor de details, of op de 🔔 om een laadwens aan te zetten. In de visuele editor kies je welke palen je wilt zien en of prijs en afstand getoond worden.

In YAML:

```yaml
type: custom:road-ev-card
title: Laadpalen        # leeg = geen titel
devices: []             # leeg = alle Road.io laadpalen
show_price: true
show_distance: true
sort: distance          # of: name
```

---

## Stap 5: Laadwens (melding als er plek is)

Zet de 🔔 aan bij een paal (op de kaart of met `switch.<paal>_laadwens`) en je krijgt een melding zodra er een socket vrij is. Geen automations nodig.

**Instellen:** Instellingen > Apparaten & diensten > Road.io > **Configureren** bij een laadpaal.

| Instelling | Standaard | Wat het doet |
|---|---|---|
| Meldingen sturen naar | – | Je telefoon(s) met de Home Assistant app, en/of de meldingen in Home Assistant zelf |
| Laadwens uitzetten na de melding | aan | Eén melding per keer dat je de bel aanzet |
| Melden als de paal weer bezet raakt | aan | Tot 30 minuten na een "vrij"-melding |
| Persoon | – | Ben jij binnen 200 m als de paal bezet raakt, dan ben jij het: geen "weer bezet"-melding |
| Laadwens automatisch uitzetten na | 0 (nooit) | Je krijgt dan een melding dat er geen plek vrijkwam |
| Pas melden als hij minstens zo lang vrij is | 0 min | Tegen valse meldingen bij een korte wissel |

Een nieuwe laadpaal neemt de instellingen van je vorige paal over. Met de knop **Testmelding** op het apparaat check je of alles werkt.

**De melding** toont hoeveel sockets vrij zijn en de prijs, met de knoppen **Navigeer** (route in Maps) en **Stop** (bel uit). Is de paal al vrij als je de bel aanzet, dan krijg je meteen een melding. Een "weer bezet"-melding vervangt de eerdere melding op je telefoon.

Goed om te weten: Road.io wordt elke minuut gecontroleerd, dus een melding kan tot een minuut na het vrijkomen binnenkomen.

**Nieuwe entiteiten per laadpaal:**

- `switch.<paal>_laadwens`: de bel; blijft bewaard na een herstart
- `binary_sensor.<paal>_vrij`: aan als er minstens één socket vrij is
- `button.<paal>_testmelding`: stuurt een testmelding

---

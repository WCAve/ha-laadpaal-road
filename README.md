# EV Location Radar

Dit project hangt aan elkaar met pure vibes. Geen garanties, geen aansprakelijkheid en geen idee waarom het onder water werkt. Gebruik op eigen risico. Zelfs deze readme is pure ai slop. Bij mij werkt het, geen idee of het bij jou ook werkt als je deze stappen volgt. Succes met zelf vibecoden.

> Niet gelieerd aan Road.io of E-flux. Deze integratie praat met hun onofficiële kaart-API, dezelfde die hun eigen kaart op de website gebruikt. Het werkt tot ze daar iets aan veranderen. Daarna werkt het niet meer.

---

## Wat doet het

- Laat per laadpaal zien hoeveel sockets vrij zijn, wat het kost en hoeveel vermogen erop zit.
- Zoekt laadpalen voor je op een kaart, gewoon in Home Assistant.
- Een dashboardkaart met al je palen, gesorteerd op afstand.
- Een **Laadwens**: druk op de bel en je krijgt een melding op je telefoon zodra er plek is. Geen automations nodig.
- Meerdere palen tegelijk volgen: één melding voor de eerste die vrij komt.
- Een weekoverzicht per paal van wanneer hij meestal vrij is.

---

## Installatie

1. Ga in Home Assistant naar **HACS** > **Integrations**.
2. Klik op de drie puntjes rechtsboven > **Custom repositories**.
3. Plak de URL van deze repo erin en kies bij Category voor **Integration**.
4. Installeer **Road.io (E-flux) EV Charger** en herstart Home Assistant.

Vereist Home Assistant 2025.1 of nieuwer. Ouder kan werken, maar dat heeft niemand geprobeerd.

---

## Laadpalen toevoegen

1. Ga naar **Instellingen** > **Apparaten & diensten** > **Integratie toevoegen** en zoek naar **Road.io (E-flux) EV Charger**.
2. Kies **Zoeken op de kaart**.
3. Typ een adres of plaats en klik op **Verzenden**: de kaart springt erheen. Klopt de pin? Klik nog een keer op **Verzenden**. Je kunt de pin ook gewoon zelf verslepen (standaard staat hij op je thuislocatie), en met de cirkel bepaal je hoe ver er gezocht wordt, tot maximaal 3 km.
4. Kies een paal uit de lijst: adres, aanbieder, hoeveel sockets er nu vrij zijn en de afstand. Laat de naam leeg om het adres als naam te gebruiken.

Herhaal dit voor elke paal die je wilt volgen. Palen die je al hebt staan niet meer in de lijst.

Heb je al een Location ID, bijvoorbeeld van een eerdere installatie? Kies dan **Ik heb al een Location ID**. Het ID wordt meteen gecontroleerd bij Road.io.

> Vroeger moest je hiervoor een losse webtool achter een eigen Nginx reverse proxy hosten, omdat de API in de browser door CORS werd tegengehouden. Kon dat makkelijker? Ja. In my defense: I have no idea what I'm doing. Die tool is nu weg.

---

## De kaart

De integratie brengt zijn eigen dashboardkaart mee; er hoeft niets los geïnstalleerd te worden. Na een update één keer de browser verversen (en als dat niet helpt: cache legen, het blijft een webbrowser).

1. Open een dashboard > **Bewerken** > **Kaart toevoegen**.
2. Zoek naar **Road.io laadpalen**.

De kaart toont al je palen met status, prijs en afstand tot thuis. Tik op een paal voor de details, of op de 🔔 voor een laadwens. In de visuele editor kies je welke palen je ziet en wat er getoond wordt.

- **Eerste vrije** (rechtsboven): zet de bel aan op alle palen op de kaart. De eerste die vrij komt stuurt een melding en de rest gaat uit. Voor als het je niet uitmaakt wáár je laadt, als het maar ergens kan.
- **📊 per paal**: een weekoverzicht van wanneer die paal meestal vrij is, per uur, op basis van de afgelopen 4 weken. Home Assistant begint pas met tellen na deze update, dus de eerste dagen is dat overzicht nog wat leeg. Geduld.

Of in YAML, voor wie dat leuk vindt:

```yaml
type: custom:road-ev-card
title: Laadpalen        # leeg = geen titel
devices: []             # leeg = alle Road.io laadpalen
show_price: true
show_distance: true
show_group_button: true # de "Eerste vrije" knop
show_stats: true        # de 📊 knop
sort: distance          # of: name
```

---

## Laadwens (melding als er plek is)

Zet de 🔔 aan bij een paal, op de kaart of met `switch.<paal>_laadwens`, en je krijgt een melding zodra er een socket vrij is.

**Instellen:** Instellingen > Apparaten & diensten > Road.io > **Configureren** bij een paal.

| Instelling | Standaard | Wat het doet |
|---|---|---|
| Meldingen sturen naar | – | Je telefoon(s) met de Home Assistant app, en/of de meldingen in Home Assistant zelf |
| Laadwens uitzetten na de melding | aan | Eén melding per keer dat je de bel aanzet |
| Melden als de paal weer bezet raakt | aan | Tot 30 minuten na een "vrij"-melding, voor als iemand je voor is |
| Persoon | – | Ben jij binnen 200 m als de paal bezet raakt, dan ben jij het zelf: geen "weer bezet"-melding |
| Laadwens automatisch uitzetten na | 0 (nooit) | Je krijgt dan een melding dat er niks vrijkwam |
| Pas melden als hij minstens zo lang vrij is | 0 min | Tegen valse hoop als iemand alleen even van auto wisselt |
| Mijn andere laadwensen uitzetten zodra deze paal vrij is | aan | Volg je meerdere palen, dan krijg je één melding voor de eerste die vrij komt |

Een nieuwe paal neemt de instellingen van je vorige paal over. Met de knop **Testmelding** op het apparaat check je of alles werkt, in plaats van te wachten tot er echt een plek vrijkomt.

De melding toont hoeveel sockets vrij zijn en de prijs, met de knoppen **Navigeer** (route in Maps) en **Stop** (bel uit). Is de paal al vrij als je de bel aanzet, dan krijg je meteen een melding. Een "weer bezet"-melding vervangt de vorige op je telefoon, zodat je niet bedolven wordt.

---

## Entiteiten per laadpaal

| Entiteit | Wat |
|---|---|
| `sensor.<paal>_beschikbaarheid` | De hoofdsensor: "1 van de 2 vrij", met attributen `vrije_plekken` en `totale_plekken`. Heet gewoon zoals de paal (zie hieronder). Bij nieuw toegevoegde palen is het entity ID `sensor.<paal>` |
| `sensor.<paal>_prijs` | Prijs per kWh incl. btw |
| `sensor.<paal>_socket_<n>` | Status per socket (Vrij, Bezet, Buiten gebruik, …) |
| `sensor.<paal>_socket_<n>_max_vermogen` | Maximaal vermogen per socket in kW |
| `sensor.<paal>_aanbieder` | Aanbieder (diagnostisch) |
| `sensor.<paal>_coordinaten` | "lat, lon" (diagnostisch) |
| `sensor.<paal>_vrije_sockets` | Aantal vrije sockets als getal; hier bewaart Home Assistant de statistiek van voor het weekoverzicht |
| `binary_sensor.<paal>_vrij` | Aan als er minstens één socket vrij is |
| `switch.<paal>_laadwens` | De bel; blijft bewaard na een herstart |
| `button.<paal>_testmelding` | Stuurt een testmelding |

Komen er sockets bij, dan verschijnen die vanzelf.

**Waarom heet de beschikbaarheid gewoon "Eksterweg"?** Sinds Home Assistant 2026.11 zet HA de naam van het apparaat áchter de naam van de entiteit. "Beschikbaarheid" werd daardoor "Beschikbaarheid Eksterweg", en Android Auto kapte dat lekker af tot "Beschikbaarh…". Nu is de beschikbaarheid de hoofdsensor van de paal en heeft hij geen eigen naam meer, dus zie je overal gewoon de naam van de paal met "1 van de 2 vrij" erachter. Wil je een andere naam? Hernoem de paal (het apparaat), niet de sensor.

---

## Extra: de radar (template sensor)

Uit de tijd van vóór de kaart: een template sensor die de dichtstbijzijnde paal met een vrije socket zoekt. De kaart doet grotendeels hetzelfde, maar als je het als sensor wilt hebben (voor automations bijvoorbeeld), plak dan dit in je `configuration.yaml`. Dezelfde code staat in `templates/sensor_closest_available_charger.txt`.

> De template vindt de palen via het attribuut `vrije_plekken` en zoekt daar de bijbehorende `_coordinaten` sensor bij. Verander dus geen entity ID's, anders vindt hij niks.

<details>
<summary>Template tonen</summary>

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

</details>

---

## Als het stuk gaat

En dat gaat het een keer, want: onofficiële API.

- **Reparaties.** Onder **Instellingen** > **Systeem** > **Reparaties** verschijnt een melding als Road.io langer dan een half uur niet reageert, als hun API ineens iets anders terugstuurt dan verwacht, of als een paal niet meer bestaat. Die meldingen verdwijnen vanzelf zodra het weer werkt.
- **Diagnostiek.** Bij een laadpaal: **Instellingen** > **Apparaten & diensten** > **Road.io** > ⋮ > **Diagnostiek downloaden**. Daarin staat de ruwe data die Road.io over die paal stuurt, plus de toestand van de laadwens. Je meldingsdoelen en de gekozen persoon worden eruit gelaten. Handig om aan een issue (of een AI) te hangen.

---

## Goed om te weten

- **Onofficiële API.** Zie hierboven: als Road.io iets verandert, ligt dit plat tot iemand het fixt. Die iemand is waarschijnlijk een AI.
- **Eén keer per minuut.** De status wordt elke minuut opgehaald. Een melding kan dus tot een minuut na het vrijkomen binnenkomen. Vaker vragen kan, maar dan is de kans groter dat Road.io ons eruit gooit.
- **Geen sleutels of accounts.** De kaart-API heeft geen login nodig; er staan nergens wachtwoorden of API keys in deze repo.
- **Wat er naar Road.io gaat.** Elke minuut alleen de Location ID's van je palen. Tijdens het zoeken bij het toevoegen ook een vak rond de plek die je kiest, standaard je thuislocatie, net als wanneer je over hun kaart scrollt.
- **Wat er naar OpenStreetMap gaat.** Alleen als je bij het toevoegen een adres typt: dat adres, één keer, om het op de kaart te zetten. Je thuislocatie staat al op de kaart, dus die hoef je nergens te typen.

---

## Licentie

MIT. Doe ermee wat je wilt, maar klaag niet als het stuk gaat.

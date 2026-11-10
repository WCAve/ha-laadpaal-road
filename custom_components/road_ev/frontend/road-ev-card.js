/*
 * Road.io laadpalen kaart
 * Wordt automatisch geladen door de road_ev integratie; geen losse installatie nodig.
 *
 * Config (alles optioneel):
 *   type: custom:road-ev-card
 *   title: Laadpalen
 *   devices: [<device_id>, ...]   # leeg = alle Road.io laadpalen
 *   show_price: true
 *   show_distance: true
 *   sort: distance | name
 */

const DOMAIN = "road_ev";
const CARD_VERSION = "2.3.0";

const DEFAULTS = {
  title: "Laadpalen",
  devices: [],
  show_price: true,
  show_distance: true,
  sort: "distance",
};

const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);

function distanceMeters(lat1, lon1, lat2, lon2) {
  const rad = (d) => (d * Math.PI) / 180;
  const a =
    Math.sin(rad(lat2 - lat1) / 2) ** 2 +
    Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lon2 - lon1) / 2) ** 2;
  return 6371e3 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

const formatDistance = (m) =>
  m >= 1000 ? `${(m / 1000).toFixed(1).replace(".", ",")} km` : `${Math.round(m)} m`;

const formatPrice = (value) => `€${Number(value).toFixed(2).replace(".", ",")}/kWh`;

function formatRemaining(iso) {
  if (!iso) return "";
  const ms = new Date(iso).getTime() - Date.now();
  if (!(ms > 0)) return "";
  const totalMin = Math.ceil(ms / 60000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h > 0 ? `nog ${h}u ${String(m).padStart(2, "0")}m` : `nog ${m} min`;
}

const isUnavailable = (state) =>
  !state || state.state === "unavailable" || state.state === "unknown";

/** Zoek alle Road.io laadpalen (één per apparaat) en hun entiteiten. */
function findChargers(hass) {
  const byDevice = new Map();
  for (const entry of Object.values(hass.entities || {})) {
    if (entry.platform !== DOMAIN || !entry.device_id) continue;
    if (!byDevice.has(entry.device_id)) byDevice.set(entry.device_id, {});
    const roles = byDevice.get(entry.device_id);
    const id = entry.entity_id;
    let role = entry.translation_key;
    // Terugval voor als translation_key ontbreekt.
    if (!role) {
      const attrs = hass.states[id]?.attributes || {};
      if (id.startsWith("switch.")) role = "charge_wish";
      else if (id.startsWith("binary_sensor.")) role = "free";
      else if ("vrije_plekken" in attrs) role = "availability";
      else if (attrs.unit_of_measurement === "EUR/kWh") role = "price";
      else if (id.endsWith("_coordinaten")) role = "coordinates";
    }
    if (role) roles[role] = id;
  }

  const chargers = [];
  for (const [deviceId, roles] of byDevice) {
    if (!roles.availability) continue;
    const device = hass.devices?.[deviceId];
    chargers.push({
      deviceId,
      name: device?.name_by_user || device?.name || hass.states[roles.availability]?.attributes.friendly_name || "Laadpaal",
      ...roles,
    });
  }
  return chargers;
}

class RoadEvCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("road-ev-card-editor");
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = { ...DEFAULTS, ...(config || {}) };
    this._lastKey = undefined;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    // Aftellen van de laadwens elke 30 s bijwerken.
    this._timer = setInterval(() => {
      this._lastKey = undefined;
      this._render();
    }, 30000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  getCardSize() {
    return 1 + (this._rows?.length || 1);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  _collect() {
    const hass = this._hass;
    const cfg = this._config;
    let chargers = findChargers(hass);
    if (cfg.devices?.length) {
      chargers = chargers.filter((c) => cfg.devices.includes(c.deviceId));
    }

    const home = hass.config || {};
    const rows = chargers.map((c) => {
      const avail = hass.states[c.availability];
      const wish = c.charge_wish ? hass.states[c.charge_wish] : undefined;
      const price = c.price ? hass.states[c.price] : undefined;
      const coords = c.coordinates ? hass.states[c.coordinates] : undefined;

      let distance = null;
      if (coords && coords.state.includes(",") && home.latitude != null) {
        const [lat, lon] = coords.state.split(",").map((v) => parseFloat(v));
        if (!Number.isNaN(lat) && !Number.isNaN(lon) && (lat || lon)) {
          distance = distanceMeters(home.latitude, home.longitude, lat, lon);
        }
      }

      const unavailable = isUnavailable(avail);
      const free = unavailable ? null : Number(avail.attributes.vrije_plekken ?? 0);
      return {
        ...c,
        unavailable,
        free,
        statusText: unavailable ? "Niet bereikbaar" : avail.state,
        price: price && !isUnavailable(price) ? Number(price.state) : null,
        distance,
        wishOn: wish?.state === "on",
        remaining: wish?.state === "on" ? formatRemaining(wish.attributes.verloopt_om) : "",
      };
    });

    rows.sort((a, b) => {
      if (cfg.sort === "distance" && a.distance != null && b.distance != null) {
        return a.distance - b.distance;
      }
      return a.name.localeCompare(b.name, "nl");
    });
    return rows;
  }

  _render() {
    if (!this._config || !this._hass) return;
    const rows = this._collect();
    const key = JSON.stringify([this._config, rows]);
    if (key === this._lastKey) return;
    this._lastKey = key;
    this._rows = rows;

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
      this.shadowRoot.addEventListener("keydown", (ev) => {
        if ((ev.key === "Enter" || ev.key === " ") && ev.target.dataset?.action === "more-info") {
          ev.preventDefault();
          this._onClick(ev);
        }
      });
    }

    const cfg = this._config;
    const body = rows.length
      ? rows.map((r, i) => this._rowHtml(r, i)).join("")
      : `<div class="empty">Geen Road.io laadpalen gevonden.</div>`;

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        ${cfg.title ? `<h1 class="card-header">${escapeHtml(cfg.title)}</h1>` : ""}
        <div class="list ${cfg.title ? "" : "no-title"}">${body}</div>
      </ha-card>`;
  }

  _rowHtml(r, index) {
    const cfg = this._config;
    const state = r.unavailable ? "unavailable" : r.free > 0 ? "free" : "busy";
    const details = [`<span class="status">${escapeHtml(r.statusText)}</span>`];
    if (cfg.show_price && r.price != null) details.push(escapeHtml(formatPrice(r.price)));
    if (cfg.show_distance && r.distance != null) details.push(escapeHtml(formatDistance(r.distance)));

    let wishLine = "";
    if (r.wishOn) {
      const text = r.free > 0 ? "Laadwens aan" : "Wacht op een vrije plek";
      wishLine = `<div class="wish-line">${escapeHtml(text)}${r.remaining ? ` · ${escapeHtml(r.remaining)}` : ""}</div>`;
    }

    const bell = r.charge_wish
      ? `<button class="bell ${r.wishOn ? "on" : ""}" data-action="bell" data-index="${index}"
           title="${r.wishOn ? "Laadwens uitzetten" : "Meld als hier plek is"}"
           aria-label="${r.wishOn ? "Laadwens uitzetten" : "Laadwens aanzetten"}" aria-pressed="${r.wishOn}">
           <ha-icon icon="${r.wishOn ? "mdi:bell-ring" : "mdi:bell-outline"}"></ha-icon>
         </button>`
      : "";

    return `
      <div class="row ${state} ${r.wishOn ? "wishing" : ""}" data-action="more-info" data-index="${index}" role="button" tabindex="0">
        <div class="icon"><ha-icon icon="${state === "free" ? "mdi:ev-station" : "mdi:ev-plug-type2"}"></ha-icon></div>
        <div class="info">
          <div class="name">${escapeHtml(r.name)}</div>
          <div class="details">${details.join('<span class="sep">·</span>')}</div>
          ${wishLine}
        </div>
        ${bell}
      </div>`;
  }

  _onClick(ev) {
    const target = ev.target.closest("[data-action]");
    if (!target) return;
    const row = this._rows?.[Number(target.dataset.index)];
    if (!row) return;

    if (target.dataset.action === "bell") {
      ev.stopPropagation();
      this._hass.callService("switch", row.wishOn ? "turn_off" : "turn_on", {
        entity_id: row.charge_wish,
      });
      return;
    }
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId: row.availability },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

const STYLE = `
  .card-header { margin: 0; padding: 16px 16px 4px; font-size: var(--ha-card-header-font-size, 1.5em); font-weight: normal; color: var(--ha-card-header-color, var(--primary-text-color)); }
  .list { padding: 4px 8px 8px; }
  .list.no-title { padding-top: 8px; }
  .empty { padding: 12px 8px; color: var(--secondary-text-color); }
  .row { display: flex; align-items: center; gap: 12px; padding: 8px; border-radius: 12px; cursor: pointer; }
  .row:hover { background: var(--secondary-background-color); }
  .row.wishing { background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.08); }
  .icon { flex: none; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
  .free .icon { color: var(--success-color, #43a047); background: rgba(67, 160, 71, 0.15); }
  .busy .icon { color: var(--error-color, #db4437); background: rgba(219, 68, 55, 0.15); }
  .unavailable .icon { color: var(--disabled-text-color, #9e9e9e); background: var(--secondary-background-color); }
  .info { flex: 1; min-width: 0; }
  .name { font-weight: 500; color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .details { font-size: 0.9em; color: var(--secondary-text-color); }
  .free .status { color: var(--success-color, #43a047); font-weight: 500; }
  .busy .status { color: var(--error-color, #db4437); font-weight: 500; }
  .sep { margin: 0 6px; }
  .wish-line { margin-top: 2px; font-size: 0.85em; color: var(--primary-color); display: flex; align-items: center; gap: 4px; }
  .bell { flex: none; width: 40px; height: 40px; border: none; border-radius: 50%; background: none; cursor: pointer; color: var(--secondary-text-color); display: flex; align-items: center; justify-content: center; }
  .bell:hover { background: var(--secondary-background-color); }
  .bell.on { color: var(--primary-color); background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.15); }
`;

/* ------------------------------------------------------------------ editor */

const EDITOR_SCHEMA = [
  { name: "title", selector: { text: {} } },
  { name: "devices", selector: { device: { integration: DOMAIN, multiple: true } } },
  {
    type: "grid",
    name: "",
    schema: [
      { name: "show_price", selector: { boolean: {} } },
      { name: "show_distance", selector: { boolean: {} } },
    ],
  },
  {
    name: "sort",
    selector: {
      select: {
        mode: "dropdown",
        options: [
          { value: "distance", label: "Afstand tot thuis" },
          { value: "name", label: "Naam" },
        ],
      },
    },
  },
];

const EDITOR_LABELS = {
  title: "Titel",
  devices: "Laadpalen (leeg = allemaal)",
  show_price: "Prijs tonen",
  show_distance: "Afstand tonen",
  sort: "Sorteren op",
};

class RoadEvCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) => EDITOR_LABELS[schema.name] ?? schema.name;
      this._form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        // Standaardwaarden niet in de YAML zetten.
        const config = { ...ev.detail.value };
        for (const [key, value] of Object.entries(DEFAULTS)) {
          if (key !== "title" && JSON.stringify(config[key]) === JSON.stringify(value)) delete config[key];
        }
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config },
            bubbles: true,
            composed: true,
          }),
        );
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = EDITOR_SCHEMA;
    this._form.data = { ...DEFAULTS, ...this._config };
  }
}

if (!customElements.get("road-ev-card")) {
  customElements.define("road-ev-card", RoadEvCard);
  customElements.define("road-ev-card-editor", RoadEvCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "road-ev-card",
    name: "Road.io laadpalen",
    description: "Status, prijs en afstand van je Road.io laadpalen, met een bel voor meldingen.",
    preview: true,
    documentationURL: "https://github.com/WCAve/ha-laadpaal-road",
  });
  console.info(`%c ROAD-EV-CARD %c ${CARD_VERSION} `, "background:#03a9f4;color:#fff", "");
}

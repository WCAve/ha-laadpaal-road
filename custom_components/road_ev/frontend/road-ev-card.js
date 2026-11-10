/*
 * Laadpalen kaart (EV Location Radar)
 * Wordt automatisch geladen door de road_ev integratie; geen losse installatie nodig.
 *
 * Config (alles optioneel):
 *   type: custom:road-ev-card
 *   title: Laadpalen
 *   devices: [<device_id>, ...]   # leeg = alle laadpalen van deze integratie
 *   show_price: true
 *   show_distance: true
 *   show_group_button: true       # "Alle palen" bel in de kop
 *   show_stats: true              # knop voor "meestal vrij" per paal
 *   estimate_kwh: 20              # kostenschatting voor zoveel kWh (0 = uit)
 *   car_kw: 11                    # laadvermogen van je auto (voor tijdtarieven)
 *   sort: distance | price | name
 */

const DOMAIN = "road_ev";
const CARD_VERSION = "2.9.0";

const DEFAULTS = {
  title: "Laadpalen",
  devices: [],
  show_price: true,
  show_distance: true,
  show_group_button: true,
  show_stats: true,
  estimate_kwh: 20,
  car_kw: 11,
  sort: "distance",
};

const WEEKDAYS = ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"];
const STATS_DAYS = 28;
const STATS_MAX_AGE_MS = 30 * 60 * 1000;

/** Uurstatistiek -> gemiddeld aantal vrije sockets per weekdag x uur. */
function buildHeatmap(points) {
  const sum = Array.from({ length: 7 }, () => new Array(24).fill(0));
  const count = Array.from({ length: 7 }, () => new Array(24).fill(0));
  const days = new Set();
  for (const p of points || []) {
    if (p.mean == null) continue;
    const start = new Date(typeof p.start === "number" ? p.start : Date.parse(p.start));
    if (Number.isNaN(start.getTime())) continue;
    const wd = (start.getDay() + 6) % 7; // maandag = 0
    const h = start.getHours();
    sum[wd][h] += Number(p.mean);
    count[wd][h] += 1;
    days.add(start.toDateString());
  }
  const grid = sum.map((row, wd) => row.map((v, h) => (count[wd][h] ? v / count[wd][h] : null)));
  return { grid, days: days.size };
}

/** Rood (0 vrij) via oranje naar groen (gemiddeld 1 of meer vrij). */
function heatColor(mean) {
  const hue = Math.round(Math.min(Math.max(mean, 0), 1) * 120);
  return `hsl(${hue}, 60%, 45%)`;
}

const formatMean = (v) => v.toFixed(1).replace(".", ",");

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
const formatEuro = (value) => `€${Number(value).toFixed(2).replace(".", ",")}`;

/** Geschatte kosten voor `kwh` kWh: energie + starttarief + eventueel tijdtarief
 *  vanaf de start, bij het laagste van paal- en autovermogen. */
function estimateCost({ price, startFee, timeFee, maxKw }, kwh, carKw) {
  if (price == null || !(kwh > 0)) return null;
  const kw = Math.min(maxKw > 0 ? maxKw : carKw, carKw > 0 ? carKw : 11);
  const hours = kw > 0 ? kwh / kw : 0;
  return price * kwh + (startFee || 0) + (timeFee || 0) * hours;
}

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

/** Zoek alle laadpalen van deze integratie (één per apparaat) en hun entiteiten. */
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
      else if (id.endsWith("_vrije_sockets")) role = "free_sockets";
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

  constructor() {
    super();
    this._expanded = new Set(); // device_id's met open statistiek
    this._stats = {}; // entity_id -> { status, fetchedAt, heatmap, error }
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
        startFee: Number(price?.attributes?.starttarief || 0),
        timeFee: Number(price?.attributes?.tijdtarief_bij_start || 0),
        maxKw: Number(price?.attributes?.max_vermogen_kw || 0),
        blockingFee: price?.attributes?.blokkeertarief || null,
        distance,
        wishOn: wish?.state === "on",
        remaining: wish?.state === "on" ? formatRemaining(wish.attributes.verloopt_om) : "",
      };
    });

    for (const r of rows) {
      r.estimate = r.unavailable ? null : estimateCost(r, Number(cfg.estimate_kwh), Number(cfg.car_kw));
    }

    rows.sort((a, b) => {
      if (cfg.sort === "distance" && a.distance != null && b.distance != null) {
        return a.distance - b.distance;
      }
      if (cfg.sort === "price") {
        // Goedkoopste eerst (op schatting als die aan staat); zonder prijs achteraan.
        const pa = a.estimate ?? a.price;
        const pb = b.estimate ?? b.price;
        if (pa != null && pb != null && pa !== pb) return pa - pb;
        if ((pa == null) !== (pb == null)) return pa == null ? 1 : -1;
      }
      return a.name.localeCompare(b.name, "nl");
    });
    return rows;
  }

  _render() {
    if (!this._config || !this._hass) return;
    const rows = this._collect();
    const key = JSON.stringify([this._config, rows, [...this._expanded], this._statsVersion || 0]);
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
      : `<div class="empty">Geen laadpalen gevonden.</div>`;

    // "Alle palen": één bel voor alle getoonde palen; de eerste die vrij komt meldt zich.
    const wishRows = rows.filter((r) => r.charge_wish);
    let groupButton = "";
    if (cfg.show_group_button && wishRows.length >= 2) {
      const allOn = wishRows.every((r) => r.wishOn);
      groupButton = `<button class="group ${allOn ? "on" : ""}" data-action="group"
          title="${allOn ? "Alle laadwensen uitzetten" : "Meld de eerste paal die vrij komt"}">
          <ha-icon icon="${allOn ? "mdi:bell-off-outline" : "mdi:bell-plus-outline"}"></ha-icon>
          <span>${allOn ? "Alle uit" : "Eerste vrije"}</span>
        </button>`;
    }
    const header = cfg.title || groupButton
      ? `<div class="header ${cfg.title ? "" : "no-title"}">
           ${cfg.title ? `<h1 class="card-header">${escapeHtml(cfg.title)}</h1>` : "<span></span>"}
           ${groupButton}
         </div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        ${header}
        <div class="list ${header ? "" : "no-title"}">${body}</div>
      </ha-card>`;
  }

  _rowHtml(r, index) {
    const cfg = this._config;
    const state = r.unavailable ? "unavailable" : r.free > 0 ? "free" : "busy";
    const details = [`<span class="status">${escapeHtml(r.statusText)}</span>`];
    if (cfg.show_price && r.price != null) {
      const start = r.startFee > 0 ? ` + €${r.startFee.toFixed(2).replace(".", ",")} start` : "";
      details.push(escapeHtml(formatPrice(r.price) + start));
    }
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

    const expanded = this._expanded.has(r.deviceId);
    const statsButton = cfg.show_stats && r.free_sockets
      ? `<button class="stats-btn ${expanded ? "on" : ""}" data-action="stats" data-index="${index}"
           title="Wanneer is deze paal meestal vrij?" aria-expanded="${expanded}">
           <ha-icon icon="mdi:chart-box-outline"></ha-icon>
         </button>`
      : "";

    return `
      <div class="row ${state} ${r.wishOn ? "wishing" : ""}" data-action="more-info" data-index="${index}" role="button" tabindex="0">
        <div class="icon"><ha-icon icon="${state === "free" ? "mdi:ev-station" : "mdi:ev-plug-type2"}"></ha-icon></div>
        <div class="info">
          <div class="name">${escapeHtml(r.name)}</div>
          <div class="details">${details.join('<span class="sep">·</span>')}</div>
          ${cfg.show_price && r.estimate != null
            ? `<div class="estimate-line" title="Schatting: ${escapeHtml(cfg.estimate_kwh)} kWh × kWh-prijs${r.startFee > 0 ? " + starttarief" : ""}${r.timeFee > 0 ? " + tijdtarief tijdens het laden" : ""}">≈ ${escapeHtml(formatEuro(r.estimate))} voor ${escapeHtml(cfg.estimate_kwh)} kWh</div>`
            : ""}
          ${cfg.show_price && r.blockingFee
            ? `<div class="fee-line" title="Blokkeertarief: vanaf de start van je sessie"><ha-icon icon="mdi:timer-alert-outline"></ha-icon>${escapeHtml(r.blockingFee)}</div>`
            : ""}
          ${wishLine}
        </div>
        ${statsButton}
        ${bell}
      </div>
      ${expanded ? this._statsHtml(r) : ""}`;
  }

  _statsHtml(r) {
    const entry = this._stats[r.free_sockets];
    if (!entry || entry.status === "loading") {
      return `<div class="stats muted">Statistiek laden…</div>`;
    }
    if (entry.status === "error") {
      return `<div class="stats muted">Kon de statistiek niet laden (${escapeHtml(entry.error)}).</div>`;
    }
    const { grid, days } = entry.heatmap;
    if (!days) {
      return `<div class="stats muted">Nog geen statistiek. Home Assistant houdt vanaf nu per uur bij hoeveel sockets vrij zijn; na een paar dagen zie je hier wanneer deze paal meestal vrij is.</div>`;
    }
    const now = new Date();
    const nowWd = (now.getDay() + 6) % 7;
    const nowH = now.getHours();
    const nowMean = grid[nowWd][nowH];
    const summary = nowMean == null
      ? "Voor dit uur is nog geen statistiek."
      : `Rond deze tijd meestal <b>${formatMean(nowMean)}</b> vrij.`;

    const hours = Array.from({ length: 24 }, (_, h) =>
      `<div class="hh">${h % 6 === 0 ? h : ""}</div>`).join("");
    const rowsHtml = grid.map((cells, wd) => {
      const tds = cells.map((mean, h) => {
        const now = wd === nowWd && h === nowH ? " now" : "";
        if (mean == null) return `<div class="cell empty-cell${now}" title="${WEEKDAYS[wd]} ${h}:00 · geen gegevens"></div>`;
        return `<div class="cell${now}" style="background:${heatColor(mean)}"
          title="${WEEKDAYS[wd]} ${h}:00 · gemiddeld ${formatMean(mean)} vrij"></div>`;
      }).join("");
      return `<div class="wd">${WEEKDAYS[wd]}</div>${tds}`;
    }).join("");

    return `
      <div class="stats">
        <div class="stats-summary">${summary} <span class="muted">Op basis van ${days} ${days === 1 ? "dag" : "dagen"}.</span></div>
        <div class="heatmap"><div></div>${hours}${rowsHtml}</div>
        <div class="legend muted">
          <span class="swatch" style="background:${heatColor(0)}"></span>vol
          <span class="swatch" style="background:${heatColor(0.5)}"></span>soms
          <span class="swatch" style="background:${heatColor(1)}"></span>meestal plek
        </div>
      </div>`;
  }

  async _loadStats(entityId) {
    const cached = this._stats[entityId];
    if (cached && (cached.status === "loading" || (cached.status === "ok" && Date.now() - cached.fetchedAt < STATS_MAX_AGE_MS))) {
      return;
    }
    this._stats[entityId] = { status: "loading" };
    this._bumpStats();
    const end = new Date();
    const start = new Date(end.getTime() - STATS_DAYS * 24 * 3600 * 1000);
    try {
      const result = await this._hass.callWS({
        type: "recorder/statistics_during_period",
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        statistic_ids: [entityId],
        period: "hour",
        types: ["mean"],
      });
      this._stats[entityId] = {
        status: "ok",
        fetchedAt: Date.now(),
        heatmap: buildHeatmap(result?.[entityId]),
      };
    } catch (err) {
      this._stats[entityId] = { status: "error", error: err?.message || String(err) };
    }
    this._bumpStats();
  }

  /** Bellen één voor één aanzetten, dichtstbijzijnde eerst: is er al een paal
   *  vrij, dan meldt die zich en worden de rest niet meer aangezet. */
  async _armInOrder(entityIds) {
    for (const entityId of entityIds) {
      try {
        await this._hass.callService("switch", "turn_on", { entity_id: entityId });
      } catch (err) {
        console.warn("road-ev-card: kon laadwens niet aanzetten", entityId, err);
      }
    }
  }

  _bumpStats() {
    this._statsVersion = (this._statsVersion || 0) + 1;
    this._render();
  }

  _onClick(ev) {
    const target = ev.target.closest("[data-action]");
    if (!target) return;

    if (target.dataset.action === "group") {
      ev.stopPropagation();
      const wishRows = (this._rows || []).filter((r) => r.charge_wish);
      const allOn = wishRows.every((r) => r.wishOn);
      if (allOn) {
        this._hass.callService("switch", "turn_off", { entity_id: wishRows.map((r) => r.charge_wish) });
      } else {
        this._armInOrder(wishRows.filter((r) => !r.wishOn).map((r) => r.charge_wish));
      }
      return;
    }

    const row = this._rows?.[Number(target.dataset.index)];
    if (!row) return;

    if (target.dataset.action === "bell") {
      ev.stopPropagation();
      this._hass.callService("switch", row.wishOn ? "turn_off" : "turn_on", {
        entity_id: row.charge_wish,
      });
      return;
    }
    if (target.dataset.action === "stats") {
      ev.stopPropagation();
      if (this._expanded.has(row.deviceId)) {
        this._expanded.delete(row.deviceId);
        this._render();
      } else {
        this._expanded.add(row.deviceId);
        this._render();
        this._loadStats(row.free_sockets);
      }
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
  .header { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-right: 12px; }
  .header.no-title { padding-top: 8px; }
  .group { display: flex; align-items: center; gap: 6px; border: 1px solid var(--divider-color, rgba(0,0,0,.12)); border-radius: 18px; padding: 6px 12px; background: none; cursor: pointer; color: var(--primary-text-color); font: inherit; font-size: 0.9em; white-space: nowrap; }
  .group:hover { background: var(--secondary-background-color); }
  .group.on { color: var(--primary-color); border-color: var(--primary-color); }
  .group ha-icon { --mdc-icon-size: 18px; }
  .stats-btn { flex: none; width: 40px; height: 40px; border: none; border-radius: 50%; background: none; cursor: pointer; color: var(--secondary-text-color); display: flex; align-items: center; justify-content: center; }
  .stats-btn:hover { background: var(--secondary-background-color); }
  .stats-btn.on { color: var(--primary-color); }
  .stats { margin: 0 8px 8px 60px; font-size: 0.85em; color: var(--primary-text-color); }
  .muted { color: var(--secondary-text-color); }
  .stats-summary { margin-bottom: 6px; }
  .heatmap { display: grid; grid-template-columns: 22px repeat(24, 1fr); gap: 2px; align-items: center; }
  .hh { font-size: 0.75em; color: var(--secondary-text-color); height: 12px; line-height: 12px; }
  .wd { font-size: 0.8em; color: var(--secondary-text-color); }
  .cell { height: 12px; border-radius: 2px; }
  .cell.empty-cell { background: var(--secondary-background-color); }
  .cell.now { outline: 2px solid var(--primary-text-color); outline-offset: -1px; }
  .legend { display: flex; align-items: center; gap: 4px; margin-top: 6px; font-size: 0.85em; }
  .swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-left: 6px; }
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
  .estimate-line { margin-top: 2px; font-size: 0.85em; color: var(--secondary-text-color); }
  .fee-line { margin-top: 2px; font-size: 0.85em; color: var(--warning-color, #ffa600); display: flex; align-items: center; gap: 4px; }
  .fee-line ha-icon { --mdc-icon-size: 16px; }
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
      { name: "show_group_button", selector: { boolean: {} } },
      { name: "show_stats", selector: { boolean: {} } },
    ],
  },
  {
    type: "grid",
    name: "",
    schema: [
      { name: "estimate_kwh", selector: { number: { min: 0, max: 150, step: 5, mode: "box", unit_of_measurement: "kWh" } } },
      { name: "car_kw", selector: { number: { min: 1, max: 350, step: 0.1, mode: "box", unit_of_measurement: "kW" } } },
    ],
  },
  {
    name: "sort",
    selector: {
      select: {
        mode: "dropdown",
        options: [
          { value: "distance", label: "Afstand tot thuis" },
          { value: "price", label: "Prijs (goedkoopste eerst)" },
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
  show_group_button: "Knop \"Eerste vrije\" tonen",
  show_stats: "Statistiek-knop tonen",
  estimate_kwh: "Kostenschatting voor (0 = uit)",
  car_kw: "Laadvermogen van je auto",
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
    name: "Laadpalen (EV Location Radar)",
    description: "Status, prijs en afstand van je laadpalen, met een bel voor meldingen.",
    preview: true,
    documentationURL: "https://github.com/WCAve/ha-laadpaal-road",
  });
  console.info(`%c ROAD-EV-CARD %c ${CARD_VERSION} `, "background:#03a9f4;color:#fff", "");
}

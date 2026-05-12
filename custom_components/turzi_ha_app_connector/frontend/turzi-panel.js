/**
 * Turzi Panel — Home Assistant sidebar panel
 * Entity exposure managed via a simple on/off set (no labels).
 */

const STYLES = `
  :host {
    display: block; height: 100%;
    background: var(--primary-background-color);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
    --accent: var(--primary-color, #03a9f4);
    --card: var(--card-background-color, #fff);
    --divider: var(--divider-color, rgba(0,0,0,.12));
    --text: var(--primary-text-color, #212121);
    --sub: var(--secondary-text-color, #727272);
  }
  * { box-sizing: border-box; }
  .layout { display: flex; flex-direction: column; height: 100%; }

  /* Header */
  .header {
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, #fff);
    padding: 0 16px; display: flex; align-items: center; gap: 12px;
    height: 64px; flex-shrink: 0; box-shadow: 0 2px 6px rgba(0,0,0,.25);
  }
  .header h1 { margin: 0; font-size: 20px; font-weight: 400; flex: 1; letter-spacing: .3px; }

  /* Tabs */
  .tabs {
    display: flex;
    background: var(--app-header-background-color, var(--primary-color));
    padding: 0 16px; flex-shrink: 0; border-bottom: 1px solid rgba(255,255,255,.1);
  }
  .tab {
    padding: 12px 20px; cursor: pointer; font-size: 13px; font-weight: 500;
    color: rgba(255,255,255,.65); border-bottom: 3px solid transparent;
    transition: all .2s; letter-spacing: .5px; text-transform: uppercase; user-select: none;
  }
  .tab.active { color: #fff; border-bottom-color: #fff; }

  /* Content area */
  .content { flex: 1; overflow-y: auto; padding: 16px; }

  /* Toolbar */
  .toolbar {
    display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;
  }
  .search-wrap { position: relative; flex: 1; min-width: 160px; }
  .search-wrap ha-icon {
    position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
    --mdc-icon-size: 18px; color: var(--sub);
  }
  .search-input {
    width: 100%; padding: 9px 12px 9px 36px;
    border-radius: 8px; border: 1px solid var(--divider);
    background: var(--card); color: var(--text); font-size: 14px; outline: none;
  }
  .search-input:focus { border-color: var(--accent); }
  .btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 8px 14px; border-radius: 8px; border: none; cursor: pointer;
    font-size: 13px; font-weight: 500; transition: opacity .15s; white-space: nowrap;
  }
  .btn:disabled { opacity: .4; cursor: default; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-primary:hover:not(:disabled) { opacity: .88; }
  .btn-outline { background: transparent; border: 1.5px solid var(--divider); color: var(--text); }
  .btn-outline:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
  .btn-danger { background: transparent; border: 1.5px solid #ef5350; color: #ef5350; }
  .btn-danger:hover:not(:disabled) { background: rgba(239,83,80,.08); }

  /* Domain chips */
  .domain-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .chip {
    padding: 4px 12px; border-radius: 16px; font-size: 12px; cursor: pointer;
    border: 1.5px solid var(--divider); background: var(--card);
    color: var(--sub); transition: all .15s; user-select: none;
  }
  .chip.active { background: var(--accent); color: #fff; border-color: var(--accent); }

  /* Stats bar */
  .stats {
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 10px; font-size: 13px; color: var(--sub);
  }
  .stats strong { color: var(--accent); }
  .stats .sel-label { margin-left: auto; font-weight: 500; color: var(--accent); }

  /* Batch action bar */
  .batch-bar {
    display: none; align-items: center; gap: 8px; padding: 10px 14px;
    background: var(--card); border-radius: 10px; margin-bottom: 10px;
    border: 1.5px solid var(--accent); flex-wrap: wrap;
  }
  .batch-bar.visible { display: flex; }
  .batch-bar span { font-size: 13px; color: var(--text); font-weight: 500; flex: 1; }

  /* Entity list */
  .entity-list { display: flex; flex-direction: column; gap: 1px; }
  .entity-row {
    display: flex; align-items: center; gap: 10px;
    padding: 9px 12px; border-radius: 8px;
    background: var(--card); transition: background .12s; cursor: pointer;
  }
  .entity-row:hover { background: var(--secondary-background-color, #f0f0f0); }
  .entity-row.selected { background: rgba(3,169,244,.08); }
  .row-checkbox { flex-shrink: 0; width: 18px; height: 18px; accent-color: var(--accent); cursor: pointer; }
  .entity-icon { width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .entity-icon ha-icon { --mdc-icon-size: 20px; color: var(--sub); }
  .entity-icon ha-icon.on { color: var(--accent); }
  .entity-info { flex: 1; min-width: 0; }
  .entity-name { font-size: 14px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .entity-id { font-size: 11px; color: var(--sub); font-family: monospace; }
  .entity-state { font-size: 12px; color: var(--sub); flex-shrink: 0; min-width: 50px; text-align: right; }
  .domain-dot {
    width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
    background: var(--accent); opacity: 0;
  }
  .domain-dot.in-domain { opacity: 1; }
  ha-switch { flex-shrink: 0; }

  /* Select-all row */
  .select-all-row {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 12px; font-size: 13px; color: var(--sub);
    border-bottom: 1px solid var(--divider); margin-bottom: 4px;
  }

  /* Empty state */
  .empty { text-align: center; padding: 48px 16px; color: var(--sub); font-size: 14px; }
  .empty ha-icon { --mdc-icon-size: 48px; display: block; margin-bottom: 12px; opacity: .3; }

  /* Loading */
  .loading {
    display: flex; align-items: center; justify-content: center;
    height: 200px; flex-direction: column; gap: 16px; color: var(--sub); font-size: 14px;
  }
  .spinner {
    width: 36px; height: 36px; border: 3px solid var(--divider);
    border-top-color: var(--accent); border-radius: 50%; animation: spin 1s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Settings */
  .settings-section {
    background: var(--card); border-radius: 12px; padding: 20px; margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,.07);
  }
  .settings-section h3 { margin: 0 0 4px; font-size: 15px; font-weight: 500; color: var(--text); }
  .settings-section p { margin: 0 0 14px; font-size: 13px; color: var(--sub); line-height: 1.5; }
  .toggle-row { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; }
  .toggle-label { font-size: 14px; color: var(--text); }
  .toggle-sub { font-size: 12px; color: var(--sub); margin-top: 2px; }
  .domain-grid { display: flex; flex-wrap: wrap; gap: 8px; }
  .domain-pill {
    display: flex; align-items: center; gap: 5px; padding: 6px 14px;
    border-radius: 20px; cursor: pointer; font-size: 13px;
    border: 1.5px solid var(--divider); color: var(--sub);
    transition: all .15s; user-select: none;
  }
  .domain-pill.selected { background: var(--accent); color: #fff; border-color: var(--accent); }
  .save-btn {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 10px 22px; border-radius: 8px; border: none; cursor: pointer;
    background: var(--accent); color: #fff; font-size: 14px; font-weight: 500;
    letter-spacing: .3px; transition: opacity .15s; margin-top: 8px;
  }
  .save-btn:disabled { opacity: .5; cursor: default; }
  .save-btn:hover:not(:disabled) { opacity: .88; }
  .save-spinner { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite; }
`;

const ALL_DOMAINS = [
  "alarm_control_panel","automation","binary_sensor","button","camera","climate",
  "cover","device_tracker","fan","group","humidifier","input_boolean","input_button",
  "input_number","input_select","light","lock","media_player","person","remote",
  "scene","script","sensor","siren","switch","vacuum","valve","water_heater","weather",
];

class TurziPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._config = null;
    this._entities = [];
    this._activeTab = "entities";
    this._search = "";
    this._domainFilter = null;
    this._selected = new Set();
    this._loading = true;
    this._saving = false;
    this._unsub = null;
    this._draft = null;
    this.attachShadow({ mode: "open" });
    this._renderShell();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._init();
  }
  set panel(_) {}

  async _init() {
    await this._fetchData();
    this._subscribeUpdates();
    this._render();
  }

  async _fetchData() {
    try {
      const [cfg, ents] = await Promise.all([
        this._hass.connection.sendMessagePromise({ type: "turzi/config" }),
        this._hass.connection.sendMessagePromise({ type: "turzi/entities" }),
      ]);
      this._config = cfg;
      this._entities = ents.sort((a, b) => a.entity_id.localeCompare(b.entity_id));
      if (!this._draft) {
        this._draft = {
          included_domains: [...(cfg.included_domains || [])],
          auto_add_new: cfg.auto_add_new !== false,
        };
      }
    } catch (e) { console.error("[Turzi]", e); }
    this._loading = false;
  }

  async _subscribeUpdates() {
    if (this._unsub) { try { this._unsub(); } catch (_) {} }
    this._unsub = await this._hass.connection.subscribeMessage(
      async () => {
        const prevSelected = new Set(this._selected);
        this._draft = null; // let settings tab re-read from fresh config
        await this._fetchData();
        this._selected = new Set([...prevSelected].filter(id => this._entities.some(e => e.entity_id === id)));
        this._render();
      },
      { type: "turzi/subscribe" }
    );
  }

  async _setExpose(entityIds, expose) {
    try {
      await this._hass.callApi("POST", "turzi/entities/update", {
        entry_id: this._config.entry_id,
        entity_ids: Array.isArray(entityIds) ? entityIds : [entityIds],
        expose,
      });
    } catch (e) { console.error("[Turzi] entity update failed", e); }
  }

  async _saveSettings() {
    if (this._saving) return;
    this._saving = true;
    this._render();
    try {
      await this._hass.callApi("POST", "turzi/config", {
        entry_id: this._config.entry_id,
        included_domains: this._draft.included_domains,
        auto_add_new: this._draft.auto_add_new,
      });
      this._draft = null; // will be re-seeded from fresh config on subscribe push
    } catch (e) { console.error("[Turzi] save failed", e); }
    this._saving = false;
    this._render();
  }

  _filtered() {
    const q = this._search.toLowerCase();
    return this._entities.filter(e => {
      if (this._domainFilter && e.domain !== this._domainFilter) return false;
      if (q) return e.entity_id.includes(q) || (e.name || "").toLowerCase().includes(q);
      return true;
    });
  }

  _domains() {
    return [...new Set(this._entities.map(e => e.domain))].sort();
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>
      <div class="layout">
        <div class="header"><h1>Turzi</h1></div>
        <div class="tabs">
          <div class="tab active" data-tab="entities">Entities</div>
          <div class="tab" data-tab="settings">Settings</div>
        </div>
        <div class="content" id="content"></div>
      </div>`;
    this.shadowRoot.querySelectorAll(".tab").forEach(t =>
      t.addEventListener("click", () => {
        this._activeTab = t.dataset.tab;
        this._selected.clear();
        this.shadowRoot.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x === t));
        this._renderContent();
      })
    );
  }

  _render() { this._renderContent(); }

  _renderContent() {
    const c = this.shadowRoot.getElementById("content");
    if (!c) return;
    if (this._loading) {
      c.innerHTML = `<div class="loading"><div class="spinner"></div><span>Loading…</span></div>`;
      return;
    }
    if (this._activeTab === "entities") this._renderEntities(c);
    else this._renderSettings(c);
  }

  _renderEntities(c) {
    const filtered = this._filtered();
    const exposed = this._entities.filter(e => e.is_exposed).length;
    const selCount = this._selected.size;
    const selFiltered = filtered.filter(e => this._selected.has(e.entity_id));
    const allFilteredSelected = filtered.length > 0 && filtered.every(e => this._selected.has(e.entity_id));

    const domainChips = this._domains().map(d =>
      `<div class="chip${this._domainFilter === d ? " active" : ""}" data-domain="${d}">${d}</div>`
    ).join("");

    const rows = filtered.map(e => {
      const sel = this._selected.has(e.entity_id);
      return `<div class="entity-row${sel ? " selected" : ""}" data-id="${e.entity_id}">
        <input type="checkbox" class="row-checkbox" ${sel ? "checked" : ""} data-id="${e.entity_id}">
        <div class="entity-icon">
          <ha-icon class="${e.is_exposed ? "on" : ""}" icon="${e.icon || "mdi:help-circle-outline"}"></ha-icon>
        </div>
        <div class="entity-info">
          <div class="entity-name">${e.name || e.entity_id}</div>
          <div class="entity-id">${e.entity_id}</div>
        </div>
        <div class="domain-dot${e.in_domain ? " in-domain" : ""}" title="${e.in_domain ? "In included domain" : ""}"></div>
        <div class="entity-state">${e.state}</div>
        <ha-switch ${e.is_exposed ? "checked" : ""} data-id="${e.entity_id}" data-expose="${e.is_exposed ? "false" : "true"}"></ha-switch>
      </div>`;
    }).join("") || `<div class="empty"><ha-icon icon="mdi:magnify"></ha-icon>No entities match.</div>`;

    c.innerHTML = `
      <div class="toolbar">
        <div class="search-wrap">
          <ha-icon icon="mdi:magnify"></ha-icon>
          <input class="search-input" id="search" type="text" placeholder="Search entities…" value="${this._search}">
        </div>
      </div>
      <div class="domain-chips">
        <div class="chip${!this._domainFilter ? " active" : ""}" data-domain="">All</div>
        ${domainChips}
      </div>
      <div class="stats">
        <span><strong>${exposed}</strong> of ${this._entities.length} exposed</span>
        <span>·</span>
        <span>${filtered.length} shown</span>
        ${selCount ? `<span class="sel-label">${selCount} selected</span>` : ""}
      </div>
      <div class="batch-bar${selCount ? " visible" : ""}" id="batch-bar">
        <span>${selCount} selected</span>
        <button class="btn btn-primary" id="batch-enable">Enable</button>
        <button class="btn btn-danger" id="batch-disable">Disable</button>
        <button class="btn btn-outline" id="batch-clear">Clear</button>
      </div>
      <div class="select-all-row">
        <input type="checkbox" id="select-all" ${allFilteredSelected ? "checked" : ""}>
        <label for="select-all" style="cursor:pointer;font-size:13px;">Select all visible (${filtered.length})</label>
      </div>
      <div class="entity-list">${rows}</div>`;

    // Search
    c.querySelector("#search").addEventListener("input", e => { this._search = e.target.value; this._renderContent(); });

    // Domain chips
    c.querySelectorAll(".chip").forEach(ch =>
      ch.addEventListener("click", () => { this._domainFilter = ch.dataset.domain || null; this._renderContent(); })
    );

    // Select all
    c.querySelector("#select-all").addEventListener("change", ev => {
      if (ev.target.checked) filtered.forEach(e => this._selected.add(e.entity_id));
      else filtered.forEach(e => this._selected.delete(e.entity_id));
      this._renderContent();
    });

    // Row checkboxes
    c.querySelectorAll(".row-checkbox").forEach(cb =>
      cb.addEventListener("change", ev => {
        ev.stopPropagation();
        const id = cb.dataset.id;
        if (cb.checked) this._selected.add(id); else this._selected.delete(id);
        this._renderContent();
      })
    );

    // Individual switches
    c.querySelectorAll("ha-switch").forEach(sw =>
      sw.addEventListener("change", async ev => {
        ev.stopPropagation();
        const id = sw.dataset.id;
        const expose = sw.dataset.expose === "true";
        await this._setExpose([id], expose);
      })
    );

    // Batch actions
    if (selCount) {
      const selIds = [...this._selected];
      c.querySelector("#batch-enable").addEventListener("click", async () => {
        await this._setExpose(selIds, true);
        this._selected.clear();
      });
      c.querySelector("#batch-disable").addEventListener("click", async () => {
        await this._setExpose(selIds, false);
        this._selected.clear();
      });
      c.querySelector("#batch-clear").addEventListener("click", () => {
        this._selected.clear(); this._renderContent();
      });
    }
  }

  _renderSettings(c) {
    if (!this._draft) return;
    const d = this._draft;

    const domainPills = ALL_DOMAINS.map(dom =>
      `<div class="domain-pill${d.included_domains.includes(dom) ? " selected" : ""}" data-domain="${dom}">${dom}</div>`
    ).join("");

    c.innerHTML = `
      <div class="settings-section">
        <h3>Automatic exposure</h3>
        <p>When enabled, newly discovered entities from the included domains are automatically exposed.</p>
        <div class="toggle-row">
          <div>
            <div class="toggle-label">Auto-add new entities</div>
            <div class="toggle-sub">Automatically expose new entities from included domains</div>
          </div>
          <ha-switch id="auto-add" ${d.auto_add_new ? "checked" : ""}></ha-switch>
        </div>
      </div>
      <div class="settings-section">
        <h3>Included domains</h3>
        <p>Entities from selected domains are exposed by default. Adding a domain immediately exposes all its existing entities. Removing a domain does <em>not</em> hide entities — use the Entities tab for fine control.</p>
        <div class="domain-grid" id="domain-grid">${domainPills}</div>
      </div>
      <button class="save-btn" id="save-btn" ${this._saving ? "disabled" : ""}>
        ${this._saving
          ? '<div class="save-spinner"></div> Saving…'
          : '<ha-icon icon="mdi:content-save"></ha-icon> Save settings'}
      </button>`;

    c.querySelector("#auto-add").addEventListener("change", ev => {
      this._draft.auto_add_new = ev.target.checked;
    });
    c.querySelectorAll(".domain-pill").forEach(p =>
      p.addEventListener("click", () => {
        const dom = p.dataset.domain;
        if (this._draft.included_domains.includes(dom)) {
          this._draft.included_domains = this._draft.included_domains.filter(d => d !== dom);
          p.classList.remove("selected");
        } else {
          this._draft.included_domains.push(dom);
          p.classList.add("selected");
        }
      })
    );
    c.querySelector("#save-btn").addEventListener("click", () => this._saveSettings());
  }
}

customElements.define("turzi-panel", TurziPanel);

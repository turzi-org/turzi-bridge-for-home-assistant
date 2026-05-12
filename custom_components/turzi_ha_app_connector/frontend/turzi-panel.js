/**
 * Turzi Panel — Home Assistant custom sidebar panel
 * Manages entity exposure via HA labels.
 */

const LABEL_MODE_OPTIONS = [
  { value: "seed", label: "Seed (one-time)", description: "Label matching entities now, then manage manually" },
  { value: "automatic", label: "Automatic", description: "Labels kept in sync with domain rules at all times" },
  { value: "mixed", label: "Mixed", description: "Automatic sync + manually-added labels protected" },
];

const STYLES = `
  :host {
    display: block;
    height: 100%;
    background: var(--primary-background-color);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
    --turzi-accent: var(--primary-color, #03a9f4);
    --turzi-card-bg: var(--card-background-color, #fff);
    --turzi-divider: var(--divider-color, rgba(0,0,0,.12));
    --turzi-text: var(--primary-text-color, #212121);
    --turzi-secondary: var(--secondary-text-color, #727272);
  }
  .layout { display: flex; flex-direction: column; height: 100%; }
  .header {
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, #fff);
    padding: 0 16px;
    display: flex; align-items: center; gap: 12px;
    height: 64px; flex-shrink: 0;
    box-shadow: 0 2px 4px rgba(0,0,0,.2);
  }
  .header img { width: 32px; height: 32px; border-radius: 6px; }
  .header h1 { margin: 0; font-size: 20px; font-weight: 400; flex: 1; }
  .tabs {
    display: flex;
    background: var(--app-header-background-color, var(--primary-color));
    padding: 0 16px;
    flex-shrink: 0;
  }
  .tab {
    padding: 12px 20px; cursor: pointer; font-size: 14px; font-weight: 500;
    color: rgba(255,255,255,.7); border-bottom: 3px solid transparent;
    transition: all .2s; letter-spacing: .5px; text-transform: uppercase;
  }
  .tab.active { color: #fff; border-bottom-color: #fff; }
  .content { flex: 1; overflow-y: auto; padding: 16px; box-sizing: border-box; }

  /* --- Entity list --- */
  .search-bar {
    display: flex; gap: 8px; margin-bottom: 12px; align-items: center;
  }
  .search-bar input {
    flex: 1; padding: 10px 14px; border-radius: 8px;
    border: 1px solid var(--turzi-divider);
    background: var(--turzi-card-bg);
    color: var(--turzi-text);
    font-size: 14px; outline: none;
  }
  .search-bar input:focus { border-color: var(--turzi-accent); }
  .domain-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .chip {
    padding: 4px 12px; border-radius: 16px; font-size: 12px; cursor: pointer;
    border: 1px solid var(--turzi-divider);
    background: var(--turzi-card-bg); color: var(--turzi-secondary);
    transition: all .15s; user-select: none;
  }
  .chip.active { background: var(--turzi-accent); color: #fff; border-color: var(--turzi-accent); }
  .entity-list { display: flex; flex-direction: column; gap: 2px; }
  .entity-row {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 14px; border-radius: 8px;
    background: var(--turzi-card-bg);
    transition: background .15s;
  }
  .entity-row:hover { background: var(--secondary-background-color, #f5f5f5); }
  .entity-icon { width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .entity-icon ha-icon { --mdc-icon-size: 22px; color: var(--turzi-secondary); }
  .entity-icon ha-icon.exposed { color: var(--turzi-accent); }
  .entity-info { flex: 1; min-width: 0; }
  .entity-name { font-size: 14px; color: var(--turzi-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .entity-id { font-size: 11px; color: var(--turzi-secondary); font-family: monospace; }
  .entity-badges { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 2px; }
  .badge {
    font-size: 10px; padding: 1px 6px; border-radius: 10px;
    background: var(--turzi-divider); color: var(--turzi-secondary);
  }
  .badge.auto { background: rgba(3,169,244,.15); color: var(--turzi-accent); }
  .badge.manual { background: rgba(76,175,80,.15); color: #4caf50; }
  .badge.additional { background: rgba(156,39,176,.15); color: #9c27b0; }
  .entity-state { font-size: 12px; color: var(--turzi-secondary); flex-shrink: 0; min-width: 60px; text-align: right; }
  ha-switch { flex-shrink: 0; }
  .section-header {
    font-size: 11px; font-weight: 600; color: var(--turzi-secondary);
    letter-spacing: 1px; text-transform: uppercase;
    padding: 16px 0 6px 4px;
  }
  .count-badge {
    display: inline-block; margin-left: 6px; padding: 1px 7px;
    border-radius: 10px; background: var(--turzi-accent); color: #fff;
    font-size: 11px; font-weight: 600;
  }

  /* --- Settings --- */
  .settings-card {
    background: var(--turzi-card-bg); border-radius: 12px;
    padding: 20px; margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
  }
  .settings-card h3 { margin: 0 0 4px; font-size: 16px; font-weight: 500; color: var(--turzi-text); }
  .settings-card p { margin: 0 0 16px; font-size: 13px; color: var(--turzi-secondary); }
  .field-label { font-size: 13px; font-weight: 500; color: var(--turzi-text); margin-bottom: 6px; }
  .field-hint { font-size: 12px; color: var(--turzi-secondary); margin-top: 4px; margin-bottom: 16px; }
  .text-input {
    width: 100%; padding: 10px 12px; border-radius: 8px; box-sizing: border-box;
    border: 1px solid var(--turzi-divider);
    background: var(--primary-background-color);
    color: var(--turzi-text); font-size: 14px; outline: none;
  }
  .text-input:focus { border-color: var(--turzi-accent); }
  .mode-options { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
  .mode-option {
    display: flex; align-items: flex-start; gap: 12px; padding: 12px;
    border-radius: 8px; border: 2px solid var(--turzi-divider);
    cursor: pointer; transition: all .15s;
  }
  .mode-option.selected { border-color: var(--turzi-accent); background: rgba(3,169,244,.05); }
  .mode-option input[type=radio] { margin-top: 2px; accent-color: var(--turzi-accent); }
  .mode-option-text .title { font-size: 14px; font-weight: 500; color: var(--turzi-text); }
  .mode-option-text .desc { font-size: 12px; color: var(--turzi-secondary); margin-top: 2px; }
  .domain-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
  .domain-toggle {
    display: flex; align-items: center; gap: 6px; padding: 6px 12px;
    border-radius: 20px; cursor: pointer; font-size: 13px;
    border: 1.5px solid var(--turzi-divider);
    background: var(--primary-background-color);
    color: var(--turzi-secondary); transition: all .15s; user-select: none;
  }
  .domain-toggle.selected { background: var(--turzi-accent); color: #fff; border-color: var(--turzi-accent); }
  .domain-toggle input { display: none; }
  .save-btn {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 10px 24px; border-radius: 8px; border: none; cursor: pointer;
    background: var(--turzi-accent); color: #fff;
    font-size: 14px; font-weight: 500; letter-spacing: .3px;
    transition: opacity .15s; margin-top: 4px;
  }
  .save-btn:disabled { opacity: .5; cursor: default; }
  .save-btn:hover:not(:disabled) { opacity: .9; }
  .spinner {
    width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.4);
    border-top-color: #fff; border-radius: 50%;
    animation: spin .8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Loading */
  .loading {
    display: flex; align-items: center; justify-content: center;
    height: 200px; flex-direction: column; gap: 16px;
    color: var(--turzi-secondary); font-size: 14px;
  }
  .loading .big-spinner {
    width: 40px; height: 40px; border: 3px solid var(--turzi-divider);
    border-top-color: var(--turzi-accent); border-radius: 50%;
    animation: spin 1s linear infinite;
  }
  .empty { text-align: center; padding: 40px; color: var(--turzi-secondary); font-size: 14px; }
`;

class TurziPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._config = null;
    this._entities = [];
    this._activeTab = "entities";
    this._search = "";
    this._domainFilter = null;
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
          expose_label: cfg.expose_label || "",
          label_mode: cfg.label_mode || "seed",
          included_domains: [...(cfg.included_domains || [])],
        };
      }
    } catch (e) {
      console.error("[Turzi] fetch error", e);
    }
    this._loading = false;
  }

  async _subscribeUpdates() {
    if (this._unsub) { try { this._unsub(); } catch (_) {} }
    this._unsub = await this._hass.connection.subscribeMessage(
      async () => { await this._fetchData(); this._render(); },
      { type: "turzi/subscribe" }
    );
  }

  async _toggleEntity(entityId, expose) {
    await this._hass.callApi("POST", "turzi/entities/toggle", {
      entry_id: this._config.entry_id, entity_id: entityId, expose,
    });
  }

  async _saveSettings() {
    if (this._saving) return;
    this._saving = true;
    this._render();
    try {
      await this._hass.callApi("POST", "turzi/config", {
        entry_id: this._config.entry_id, ...this._draft,
      });
    } catch (e) { console.error("[Turzi] save error", e); }
    this._saving = false;
  }

  _domains() {
    return [...new Set(this._entities.map(e => e.domain))].sort();
  }

  _filtered() {
    const q = this._search.toLowerCase();
    return this._entities.filter(e => {
      if (this._domainFilter && e.domain !== this._domainFilter) return false;
      if (q) return e.entity_id.includes(q) || (e.name || "").toLowerCase().includes(q);
      return true;
    });
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>
      <div class="layout">
        <div class="header">
          <div class="header-logo"></div>
          <h1>Turzi</h1>
        </div>
        <div class="tabs">
          <div class="tab active" data-tab="entities">Entities</div>
          <div class="tab" data-tab="settings">Settings</div>
        </div>
        <div class="content" id="content"></div>
      </div>`;
    this.shadowRoot.querySelectorAll(".tab").forEach(t =>
      t.addEventListener("click", () => {
        this._activeTab = t.dataset.tab;
        this.shadowRoot.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x === t));
        this._renderContent();
      })
    );
  }

  _render() {
    this._renderContent();
  }

  _renderContent() {
    const content = this.shadowRoot.getElementById("content");
    if (!content) return;
    if (this._loading) {
      content.innerHTML = `<div class="loading"><div class="big-spinner"></div><span>Loading...</span></div>`;
      return;
    }
    if (this._activeTab === "entities") this._renderEntities(content);
    else this._renderSettings(content);
  }

  _renderEntities(content) {
    const filtered = this._filtered();
    const exposedCount = this._entities.filter(e => e.is_exposed).length;
    const domains = this._domains();

    const chipAll = `<div class="chip${!this._domainFilter ? " active" : ""}" data-domain="">All</div>`;
    const chips = domains.map(d =>
      `<div class="chip${this._domainFilter === d ? " active" : ""}" data-domain="${d}">${d}</div>`
    ).join("");

    const rows = filtered.length === 0
      ? `<div class="empty">No entities match your filter.</div>`
      : filtered.map(e => {
          const iconClass = e.is_exposed ? "exposed" : "";
          const badges = [
            e.is_auto_labeled ? `<span class="badge auto">auto</span>` : "",
            !e.is_auto_labeled && e.has_label ? `<span class="badge manual">manual</span>` : "",
            e.is_additional ? `<span class="badge additional">additional</span>` : "",
          ].join("");
          return `<div class="entity-row">
            <div class="entity-icon">
              <ha-icon class="${iconClass}" icon="${e.icon || "mdi:help-circle-outline"}"></ha-icon>
            </div>
            <div class="entity-info">
              <div class="entity-name">${e.name || e.entity_id}</div>
              <div class="entity-id">${e.entity_id}</div>
              ${badges ? `<div class="entity-badges">${badges}</div>` : ""}
            </div>
            <div class="entity-state">${e.state}</div>
            <ha-switch ${e.is_exposed ? "checked" : ""} data-entity="${e.entity_id}" data-expose="${e.is_exposed ? "false" : "true"}"></ha-switch>
          </div>`;
        }).join("");

    content.innerHTML = `
      <div class="section-header">
        Exposed entities <span class="count-badge">${exposedCount}</span>
      </div>
      <div class="search-bar">
        <input type="text" placeholder="Search entities…" value="${this._search}" id="search-input">
      </div>
      <div class="domain-chips">${chipAll}${chips}</div>
      <div class="entity-list">${rows}</div>`;

    content.querySelector("#search-input").addEventListener("input", e => {
      this._search = e.target.value;
      this._renderContent();
    });
    content.querySelectorAll(".chip").forEach(c =>
      c.addEventListener("click", () => {
        this._domainFilter = c.dataset.domain || null;
        this._renderContent();
      })
    );
    content.querySelectorAll("ha-switch").forEach(sw =>
      sw.addEventListener("change", async () => {
        const entityId = sw.dataset.entity;
        const expose = sw.dataset.expose === "true";
        await this._toggleEntity(entityId, expose);
      })
    );
  }

  _renderSettings(content) {
    if (!this._draft) return;
    const d = this._draft;
    const allDomains = [
      "alarm_control_panel","automation","binary_sensor","button","camera","climate",
      "cover","device_tracker","fan","group","humidifier","input_boolean","input_button",
      "input_number","input_select","light","lock","media_player","person","remote",
      "scene","script","sensor","siren","switch","vacuum","valve","water_heater","weather",
    ];

    const modeHtml = LABEL_MODE_OPTIONS.map(m => `
      <label class="mode-option${d.label_mode === m.value ? " selected" : ""}">
        <input type="radio" name="label_mode" value="${m.value}" ${d.label_mode === m.value ? "checked" : ""}>
        <div class="mode-option-text">
          <div class="title">${m.label}</div>
          <div class="desc">${m.description}</div>
        </div>
      </label>`).join("");

    const domainHtml = allDomains.map(dom => `
      <label class="domain-toggle${d.included_domains.includes(dom) ? " selected" : ""}">
        <input type="checkbox" value="${dom}" ${d.included_domains.includes(dom) ? "checked" : ""}>
        ${dom}
      </label>`).join("");

    content.innerHTML = `
      <div class="settings-card">
        <h3>Label</h3>
        <p>Entities with this HA label are exposed to the Turzi app.</p>
        <div class="field-label">Expose label</div>
        <input class="text-input" id="expose-label" type="text" value="${d.expose_label}" placeholder="e.g. turzi">
        <div class="field-hint">Lowercase. Leave empty to disable label management.</div>
      </div>
      <div class="settings-card">
        <h3>Label management mode</h3>
        <p>Controls how labels are applied and maintained.</p>
        <div class="mode-options">${modeHtml}</div>
      </div>
      <div class="settings-card">
        <h3>Included domains</h3>
        <p>Entities from these domains are labeled and exposed (based on the selected mode).</p>
        <div class="domain-grid" id="domain-grid">${domainHtml}</div>
      </div>
      <button class="save-btn" id="save-btn" ${this._saving ? "disabled" : ""}>
        ${this._saving ? '<div class="spinner"></div>' : '<ha-icon icon="mdi:content-save"></ha-icon>'}
        ${this._saving ? "Saving…" : "Save settings"}
      </button>`;

    content.querySelector("#expose-label").addEventListener("input", e => {
      this._draft.expose_label = e.target.value.trim().toLowerCase();
    });
    content.querySelectorAll("input[name=label_mode]").forEach(r =>
      r.addEventListener("change", () => {
        this._draft.label_mode = r.value;
        content.querySelectorAll(".mode-option").forEach(o =>
          o.classList.toggle("selected", o.querySelector("input").value === r.value)
        );
      })
    );
    content.querySelectorAll("#domain-grid input[type=checkbox]").forEach(cb =>
      cb.addEventListener("change", () => {
        const domains = [...content.querySelectorAll("#domain-grid input:checked")].map(x => x.value);
        this._draft.included_domains = domains;
        cb.closest(".domain-toggle").classList.toggle("selected", cb.checked);
      })
    );
    content.querySelector("#save-btn").addEventListener("click", () => this._saveSettings());
  }
}

customElements.define("turzi-panel", TurziPanel);

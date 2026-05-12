/**
 * Turzi Panel — Home Assistant sidebar panel
 */

const LOGO = "/api/turzi_ha_app_connector/panel/turzi-logo.png";

const STYLES = `
  :host {
    display:block;height:100%;
    background:var(--primary-background-color);
    font-family:var(--paper-font-body1_-_font-family,Roboto,sans-serif);
    --turzi:#FF8400;--turzi-l:rgba(255,132,0,.12);
    --accent:var(--turzi);
    --card:var(--card-background-color,#fff);
    --div:var(--divider-color,rgba(0,0,0,.12));
    --tx:var(--primary-text-color,#212121);
    --sub:var(--secondary-text-color,#727272);
    --warn:#f59e0b;--danger:#ef5350;--ok:#4caf50;
  }
  *{box-sizing:border-box;}
  .layout{display:flex;flex-direction:column;height:100%;}

  /* Header */
  .header{background:#111;border-bottom:3px solid var(--turzi);padding:0 16px;
    display:flex;align-items:center;gap:10px;height:64px;flex-shrink:0;}
  .h-logo{width:34px;height:34px;object-fit:contain;flex-shrink:0;}
  .h-word{font-size:19px;font-weight:700;letter-spacing:1px;color:#fff;flex:1;
    font-family:inherit;position:relative;display:inline-block;}
  .h-word .dot{display:inline-block;position:relative;}
  .h-word .dot::after{content:'';position:absolute;top:-5px;left:50%;
    transform:translateX(-50%);width:5px;height:5px;
    background:var(--turzi);border-radius:50%;}

  /* Tabs */
  .tabs{display:flex;background:#111;padding:0 16px;flex-shrink:0;
    border-bottom:1px solid rgba(255,255,255,.08);}
  .tab{padding:11px 18px;cursor:pointer;font-size:12px;font-weight:500;
    color:rgba(255,255,255,.45);border-bottom:3px solid transparent;
    transition:all .2s;letter-spacing:.5px;text-transform:uppercase;user-select:none;}
  .tab.active{color:#fff;border-bottom-color:var(--turzi);}

  .content{flex:1;overflow-y:auto;padding:16px;}

  /* Toolbar */
  .toolbar{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap;}
  .sw{position:relative;flex:1;min-width:140px;}
  .sw ha-icon{position:absolute;left:9px;top:50%;transform:translateY(-50%);
    --mdc-icon-size:17px;color:var(--sub);}
  .si{width:100%;padding:8px 10px 8px 32px;border-radius:8px;
    border:1px solid var(--div);background:var(--card);color:var(--tx);
    font-size:13px;outline:none;}
  .si:focus{border-color:var(--accent);}

  /* Buttons */
  .btn{display:inline-flex;align-items:center;gap:5px;padding:7px 13px;
    border-radius:7px;border:none;cursor:pointer;font-size:12px;font-weight:500;
    transition:opacity .15s;white-space:nowrap;}
  .btn:disabled{opacity:.4;cursor:default;}
  .bp{background:var(--accent);color:#fff;}
  .bp:hover:not(:disabled){opacity:.88;}
  .bo{background:transparent;border:1.5px solid var(--div);color:var(--tx);}
  .bo:hover:not(:disabled){border-color:var(--accent);color:var(--accent);}
  .bd{background:transparent;border:1.5px solid var(--danger);color:var(--danger);}
  .bd:hover:not(:disabled){background:rgba(239,83,80,.08);}

  /* Domain chips */
  .chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px;}
  .chip{padding:3px 10px;border-radius:14px;font-size:11px;cursor:pointer;
    border:1.5px solid var(--div);background:var(--card);
    color:var(--sub);transition:all .15s;user-select:none;display:flex;align-items:center;gap:4px;}
  .chip.active{background:var(--accent);color:#fff;border-color:var(--accent);}
  .chip-cnt{font-size:10px;opacity:.75;}

  /* Stats + batch bar */
  .stats{display:flex;align-items:center;gap:10px;margin-bottom:8px;font-size:12px;color:var(--sub);}
  .stats strong{color:var(--accent);}
  .stats .sl{margin-left:auto;font-weight:500;color:var(--accent);}
  .bb{display:none;align-items:center;gap:7px;padding:9px 13px;
    background:var(--card);border-radius:9px;margin-bottom:8px;
    border:1.5px solid var(--accent);flex-wrap:wrap;}
  .bb.on{display:flex;}
  .bb span{font-size:12px;color:var(--tx);font-weight:500;flex:1;}

  /* Select-all row */
  .sa{display:flex;align-items:center;gap:9px;padding:7px 11px;font-size:12px;
    color:var(--sub);border-bottom:1px solid var(--div);margin-bottom:3px;}

  /* Entity list */
  .elist{display:flex;flex-direction:column;gap:1px;}
  .erow{display:flex;align-items:center;gap:9px;padding:8px 11px;
    border-radius:7px;background:var(--card);transition:background .1s;}
  .erow:hover{background:var(--secondary-background-color,#f0f0f0);}
  .erow.sel{background:rgba(255,132,0,.07);}
  .rcb{flex-shrink:0;width:16px;height:16px;accent-color:var(--accent);cursor:pointer;}
  .eico{width:30px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
  .eico ha-icon{--mdc-icon-size:19px;color:var(--sub);}
  .eico ha-icon.on{color:var(--accent);}
  .einf{flex:1;min-width:0;}
  .ename{font-size:13px;color:var(--tx);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .eid{font-size:10px;color:var(--sub);font-family:monospace;}
  .badge{flex-shrink:0;font-size:10px;font-weight:500;padding:2px 7px;
    border-radius:9px;letter-spacing:.2px;white-space:nowrap;}
  .b-auto{background:rgba(255,132,0,.13);color:var(--turzi);}
  .b-man{background:rgba(76,175,80,.13);color:var(--ok);}
  .b-excl{background:rgba(245,158,11,.13);color:var(--warn);}
  ha-switch{flex-shrink:0;}

  /* Empty / loading */
  .empty{text-align:center;padding:40px 16px;color:var(--sub);font-size:13px;}
  .empty ha-icon{--mdc-icon-size:44px;display:block;margin-bottom:10px;opacity:.3;}
  .loading{display:flex;align-items:center;justify-content:center;height:180px;
    flex-direction:column;gap:14px;color:var(--sub);font-size:13px;}
  .spin{width:34px;height:34px;border:3px solid var(--div);
    border-top-color:var(--accent);border-radius:50%;animation:sp 1s linear infinite;}
  @keyframes sp{to{transform:rotate(360deg)}}

  /* Settings */
  .sec{background:var(--card);border-radius:11px;padding:18px;margin-bottom:14px;
    box-shadow:0 1px 3px rgba(0,0,0,.07);}
  .sec h3{margin:0 0 4px;font-size:14px;font-weight:500;color:var(--tx);}
  .sec p{margin:0 0 12px;font-size:12px;color:var(--sub);line-height:1.5;}
  .tr{display:flex;align-items:center;justify-content:space-between;padding:5px 0;}
  .tl{font-size:13px;color:var(--tx);}
  .ts{font-size:11px;color:var(--sub);margin-top:1px;}
  .dgrid{display:flex;flex-wrap:wrap;gap:7px;}
  .dpill{display:flex;align-items:center;gap:4px;padding:5px 13px;border-radius:18px;
    cursor:pointer;font-size:12px;border:1.5px solid var(--div);color:var(--sub);
    transition:all .15s;user-select:none;}
  .dpill.sel{background:var(--accent);color:#fff;border-color:var(--accent);}
  .sbtn{display:inline-flex;align-items:center;gap:7px;padding:9px 20px;
    border-radius:7px;border:none;cursor:pointer;background:var(--accent);
    color:#fff;font-size:13px;font-weight:500;transition:opacity .15s;margin-top:6px;}
  .sbtn:disabled{opacity:.5;cursor:default;}
  .sbtn:hover:not(:disabled){opacity:.88;}
  .sspin{width:13px;height:13px;border:2px solid rgba(255,255,255,.4);
    border-top-color:#fff;border-radius:50%;animation:sp .8s linear infinite;}

  /* Status tab */
  .scard{background:var(--card);border-radius:11px;padding:18px;margin-bottom:14px;
    box-shadow:0 1px 3px rgba(0,0,0,.07);}
  .si-row{display:flex;align-items:center;gap:12px;margin-bottom:14px;}
  .sdot{width:14px;height:14px;border-radius:50%;flex-shrink:0;
    box-shadow:0 0 6px currentColor;}
  .sdot.connected{background:#4caf50;color:#4caf50;}
  .sdot.disconnected,.sdot.connecting{background:#757575;color:#757575;}
  .sdot.reconnecting{background:var(--warn);color:var(--warn);animation:pulse 1.2s infinite;}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
  .stxt{font-size:16px;font-weight:500;color:var(--tx);text-transform:capitalize;}
  .smeta{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:12px;}
  .smeta dt{color:var(--sub);font-weight:500;}
  .smeta dd{color:var(--tx);margin:0;}
  .log-wrap{background:var(--card);border-radius:11px;padding:14px;
    box-shadow:0 1px 3px rgba(0,0,0,.07);}
  .log-wrap h3{margin:0 0 10px;font-size:14px;font-weight:500;color:var(--tx);}
  .log-list{display:flex;flex-direction:column;gap:2px;max-height:340px;overflow-y:auto;}
  .le{display:flex;gap:10px;padding:5px 8px;border-radius:5px;font-size:11px;}
  .le:hover{background:rgba(0,0,0,.04);}
  .lt{color:var(--sub);white-space:nowrap;font-family:monospace;flex-shrink:0;}
  .lm{color:var(--tx);}
  .le.info .lm{color:var(--tx);}
  .le.success .lm{color:var(--ok);}
  .le.warning .lm{color:var(--warn);}
  .le.error .lm{color:var(--danger);}
  .no-log{color:var(--sub);font-size:12px;text-align:center;padding:20px 0;}
`;

function badge(exposed, in_domain) {
  if (exposed && in_domain)  return {cls:"b-auto", label:"Auto Exposed"};
  if (exposed && !in_domain) return {cls:"b-man",  label:"Manually Exposed"};
  if (!exposed && in_domain) return {cls:"b-excl", label:"User Excluded"};
  return null;
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit",second:"2-digit"});
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

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
    this._status = null;
    this._tab = "entities";
    this._search = "";
    this._domainFilter = null;
    this._selected = new Set();
    this._loading = true;
    this._saving = false;
    this._unsub = null;
    this._draft = null;
    this.attachShadow({mode:"open"});
    this._shell();
  }

  set hass(h) { const f = !this._hass; this._hass = h; if (f) this._init(); }
  set panel(_) {}

  async _init() { await this._fetch(); this._subscribe(); this._render(); }

  async _fetch() {
    try {
      const [cfg, ents, st] = await Promise.all([
        this._hass.connection.sendMessagePromise({type:"turzi/config"}),
        this._hass.connection.sendMessagePromise({type:"turzi/entities"}),
        this._hass.connection.sendMessagePromise({type:"turzi/status"}).catch(() => null),
      ]);
      this._config = cfg;
      this._entities = ents.sort((a,b) => a.entity_id.localeCompare(b.entity_id));
      this._status = st;
      if (!this._draft) this._draft = {
        included_domains: [...(cfg.included_domains||[])],
        auto_add_new: cfg.auto_add_new !== false,
      };
    } catch(e) { console.error("[Turzi]", e); }
    this._loading = false;
  }

  async _subscribe() {
    if (this._unsub) { try{this._unsub();}catch(_){} }
    this._unsub = await this._hass.connection.subscribeMessage(
      async () => {
        const prev = new Set(this._selected);
        this._draft = null;
        await this._fetch();
        this._selected = new Set([...prev].filter(id => this._entities.some(e => e.entity_id===id)));
        this._render();
      },
      {type:"turzi/subscribe"}
    );
  }

  async _setExpose(ids, expose) {
    try {
      await this._hass.callApi("POST","turzi/entities/update",{
        entry_id:this._config.entry_id,
        entity_ids:Array.isArray(ids)?ids:[ids],
        expose,
      });
    } catch(e){console.error("[Turzi]",e);}
  }

  async _saveSettings() {
    if (this._saving) return;
    this._saving = true; this._render();
    try {
      await this._hass.callApi("POST","turzi/config",{
        entry_id:this._config.entry_id,
        included_domains:this._draft.included_domains,
        auto_add_new:this._draft.auto_add_new,
      });
      this._draft = null;
    } catch(e){console.error("[Turzi]",e);}
    this._saving = false; this._render();
  }

  _filtered() {
    const q = this._search.toLowerCase();
    return this._entities.filter(e => {
      if (this._domainFilter && e.domain !== this._domainFilter) return false;
      if (q) return e.entity_id.includes(q) || (e.name||"").toLowerCase().includes(q);
      return true;
    });
  }

  _domainCounts() {
    const m = {};
    for (const e of this._entities) m[e.domain] = (m[e.domain]||0)+1;
    return m;
  }

  _shell() {
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>
      <div class="layout">
        <div class="header">
          <img class="h-logo" src="${LOGO}" alt="" onerror="this.style.display='none'">
          <div class="h-word">turz<span class="dot">i</span></div>
        </div>
        <div class="tabs">
          <div class="tab active" data-tab="entities">Entities</div>
          <div class="tab" data-tab="settings">Settings</div>
          <div class="tab" data-tab="status">Status</div>
        </div>
        <div class="content" id="c"></div>
      </div>`;
    this.shadowRoot.querySelectorAll(".tab").forEach(t =>
      t.addEventListener("click", () => {
        this._tab = t.dataset.tab;
        this._selected.clear();
        this.shadowRoot.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x===t));
        this._render();
      })
    );
  }

  _render() {
    const c = this.shadowRoot.getElementById("c");
    if (!c) return;
    if (this._loading) { c.innerHTML=`<div class="loading"><div class="spin"></div><span>Loading…</span></div>`; return; }
    if (this._tab==="entities") this._renderEntities(c);
    else if (this._tab==="settings") this._renderSettings(c);
    else this._renderStatus(c);
  }

  _renderEntities(c) {
    const filtered = this._filtered();
    const exposedCount = this._entities.filter(e=>e.is_exposed).length;
    const sel = this._selected.size;
    const allSel = filtered.length>0 && filtered.every(e=>this._selected.has(e.entity_id));
    const counts = this._domainCounts();
    const includedDomains = new Set(this._config?.included_domains||[]);

    // All domains: ones in entity list + ones in included_domains config (shown greyed if 0 entities)
    const allChipDomains = [...new Set([...Object.keys(counts), ...includedDomains])].sort();

    const chips = allChipDomains.map(d => {
      const cnt = counts[d]||0;
      const act = this._domainFilter===d;
      const inCfg = includedDomains.has(d);
      return `<div class="chip${act?" active":""}" data-domain="${d}">
        ${d}${cnt?` <span class="chip-cnt">(${cnt})</span>`:""}
      </div>`;
    }).join("");

    const rows = filtered.map(e => {
      const s = this._selected.has(e.entity_id);
      const b = badge(e.is_exposed, e.in_domain);
      return `<div class="erow${s?" sel":""}">
        <input type="checkbox" class="rcb" ${s?"checked":""} data-id="${e.entity_id}">
        <div class="eico"><ha-icon class="${e.is_exposed?"on":""}" icon="${e.icon||"mdi:help-circle-outline"}"></ha-icon></div>
        <div class="einf">
          <div class="ename">${e.name||e.entity_id}</div>
          <div class="eid">${e.entity_id}</div>
        </div>
        ${b?`<span class="badge ${b.cls}">${b.label}</span>`:`<span style="width:90px"></span>`}
        <ha-switch class="esw" ${e.is_exposed?"checked":""} data-id="${e.entity_id}"></ha-switch>
      </div>`;
    }).join("") || `<div class="empty"><ha-icon icon="mdi:magnify"></ha-icon>No entities match.</div>`;

    c.innerHTML = `
      <div class="toolbar">
        <div class="sw"><ha-icon icon="mdi:magnify"></ha-icon>
          <input class="si" id="srch" type="text" placeholder="Search by name or entity ID…" value="${this._search}">
        </div>
      </div>
      <div class="chips">
        <div class="chip${!this._domainFilter?" active":""}" data-domain="">All <span class="chip-cnt">(${this._entities.length})</span></div>
        ${chips}
      </div>
      <div class="stats">
        <span><strong>${exposedCount}</strong> of ${this._entities.length} exposed</span>
        <span>·</span><span>${filtered.length} shown</span>
        ${sel?`<span class="sl">${sel} selected</span>`:""}
      </div>
      <div class="bb${sel?" on":""}" id="bb">
        <span>${sel} selected</span>
        <button class="btn bp" id="ben">Expose</button>
        <button class="btn bd" id="bdis">Exclude</button>
        <button class="btn bo" id="bclr">Clear</button>
      </div>
      <div class="sa">
        <input type="checkbox" id="sa" ${allSel?"checked":""}>
        <label for="sa" style="cursor:pointer">Select all visible (${filtered.length})</label>
      </div>
      <div class="elist">${rows}</div>`;

    c.querySelector("#srch").addEventListener("input", ev => { this._search=ev.target.value; this._render(); });
    c.querySelectorAll(".chip").forEach(ch => ch.addEventListener("click", () => {
      this._domainFilter = ch.dataset.domain||null; this._render();
    }));
    c.querySelector("#sa").addEventListener("change", ev => {
      filtered.forEach(e => ev.target.checked?this._selected.add(e.entity_id):this._selected.delete(e.entity_id));
      this._render();
    });
    c.querySelectorAll(".rcb").forEach(cb => cb.addEventListener("change", ev => {
      ev.stopPropagation();
      cb.checked?this._selected.add(cb.dataset.id):this._selected.delete(cb.dataset.id);
      this._render();
    }));
    c.querySelectorAll(".esw").forEach(sw => sw.addEventListener("change", async ev => {
      ev.stopPropagation();
      await this._setExpose([sw.dataset.id], ev.target.checked);
    }));
    if (sel) {
      const ids = [...this._selected];
      c.querySelector("#ben").addEventListener("click", async () => { await this._setExpose(ids,true); this._selected.clear(); });
      c.querySelector("#bdis").addEventListener("click", async () => { await this._setExpose(ids,false); this._selected.clear(); });
      c.querySelector("#bclr").addEventListener("click", () => { this._selected.clear(); this._render(); });
    }
  }

  _renderSettings(c) {
    if (!this._draft) return;
    const d = this._draft;
    const pills = ALL_DOMAINS.map(dom =>
      `<div class="dpill${d.included_domains.includes(dom)?" sel":""}" data-domain="${dom}">${dom}</div>`
    ).join("");
    c.innerHTML = `
      <div class="sec">
        <h3>Automatic exposure</h3>
        <p>New entities from included domains are automatically exposed as they appear in Home Assistant.</p>
        <div class="tr">
          <div><div class="tl">Auto-expose new entities</div>
            <div class="ts">Expose new entities from included domains automatically</div></div>
          <ha-switch id="aa" ${d.auto_add_new?"checked":""}></ha-switch>
        </div>
      </div>
      <div class="sec">
        <h3>Included domains</h3>
        <p>Entities from selected domains are exposed by default (shown as <em>Auto Exposed</em>). Adding a domain exposes all its existing entities immediately.</p>
        <div class="dgrid" id="dg">${pills}</div>
      </div>
      <button class="sbtn" id="sv" ${this._saving?"disabled":""}>
        ${this._saving?'<div class="sspin"></div> Saving…':'<ha-icon icon="mdi:content-save"></ha-icon> Save settings'}
      </button>`;
    c.querySelector("#aa").addEventListener("change", ev => { this._draft.auto_add_new=ev.target.checked; });
    c.querySelectorAll(".dpill").forEach(p => p.addEventListener("click", () => {
      const dom = p.dataset.domain;
      if (d.included_domains.includes(dom)) { d.included_domains=d.included_domains.filter(x=>x!==dom); p.classList.remove("sel"); }
      else { d.included_domains.push(dom); p.classList.add("sel"); }
    }));
    c.querySelector("#sv").addEventListener("click", () => this._saveSettings());
  }

  _renderStatus(c) {
    const s = this._status;
    if (!s) { c.innerHTML=`<div class="empty"><ha-icon icon="mdi:connection"></ha-icon>Status unavailable</div>`; return; }
    const statusColor = s.status==="connected"?"connected":s.status==="reconnecting"?"reconnecting":"disconnected";
    const log = [...(s.event_log||[])].reverse();
    const logRows = log.length
      ? log.map(e=>`<div class="le ${e.level}">
          <span class="lt">${fmtTime(e.time)}</span>
          <span class="lm">${e.message}</span>
        </div>`).join("")
      : `<div class="no-log">No activity yet</div>`;

    c.innerHTML = `
      <div class="scard">
        <div class="si-row">
          <div class="sdot ${statusColor}"></div>
          <div class="stxt">${s.status}</div>
        </div>
        <dl class="smeta">
          <dt>Broker</dt><dd>${s.broker}:${s.port}${s.use_tls?" (TLS)":""}</dd>
          <dt>House ID</dt><dd>${s.house_id}</dd>
          <dt>Exposed</dt><dd>${s.exposed_count} entities (${s.published_count} published)</dd>
          <dt>Reconnects</dt><dd>${s.reconnect_count}</dd>
          <dt>Last connected</dt><dd>${fmtDateTime(s.last_connect_time)}</dd>
          <dt>Last disconnected</dt><dd>${fmtDateTime(s.last_disconnect_time)}</dd>
        </dl>
      </div>
      <div class="log-wrap">
        <h3>Activity log</h3>
        <div class="log-list">${logRows}</div>
      </div>`;
  }
}

customElements.define("turzi-panel", TurziPanel);

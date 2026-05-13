/**
 * Turzi Panel — merged Entities+Settings, searchable domain picker, Status tab
 */
import { STYLES } from "./turzi-styles.js";

const LOGO = "/api/turzi_ha_app_connector/panel/turzi-logo.png";
const ALL_DOMAINS = [
  "alarm_control_panel","automation","binary_sensor","button","camera","climate",
  "cover","device_tracker","fan","group","humidifier","input_boolean",
  "input_button","input_number","input_select","light","lock","media_player",
  "number","person","remote","scene","script","select","sensor","siren","switch",
  "vacuum","valve","water_heater","weather",
];

const fmtTime = iso => iso ? new Date(iso).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"}) : "—";
const fmtDT = iso => iso ? new Date(iso).toLocaleString() : "—";
const badge = (exp, inD) =>
  exp && inD  ? {cls:"b-auto", lbl:"Auto Exposed"} :
  exp && !inD ? {cls:"b-man",  lbl:"Manually Exposed"} :
  !exp && inD ? {cls:"b-excl", lbl:"User Excluded"} : null;

class TurziPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null; this._cfg = null; this._ents = []; this._status = null;
    this._tab = "entities"; this._search = ""; this._df = null;
    this._sel = new Set(); this._loading = true; this._unsub = null;
    this._draft = null; this._saveTimer = null; this._saving = false;
    this._dpSearch = ""; this._dpOpen = false;
    this.attachShadow({mode:"open"});
    this._shell();
  }

  set hass(h) { const f = !this._hass; this._hass = h; if (f) this._init(); }
  set panel(_) {}

  async _init() { await this._fetch(); this._sub(); this._render(); }

  async _fetch() {
    try {
      const [cfg, ents, st] = await Promise.all([
        this._hass.connection.sendMessagePromise({type:"turzi/config"}),
        this._hass.connection.sendMessagePromise({type:"turzi/entities"}),
        this._hass.connection.sendMessagePromise({type:"turzi/status"}).catch(()=>null),
      ]);
      this._cfg = cfg; this._status = st;
      this._ents = ents.sort((a,b)=>a.entity_id.localeCompare(b.entity_id));
      if (!this._draft) this._draft = {
        included_domains: [...(cfg.included_domains||[])],
        auto_add_new: cfg.auto_add_new !== false,
      };
    } catch(e) { console.error("[Turzi]",e); }
    this._loading = false;
  }

  async _sub() {
    if (this._unsub) { try{this._unsub();}catch(_){} }
    this._unsub = await this._hass.connection.subscribeMessage(async () => {
      const prev = new Set(this._sel);
      this._draft = null;
      await this._fetch();
      this._sel = new Set([...prev].filter(id=>this._ents.some(e=>e.entity_id===id)));
      this._render();
    }, {type:"turzi/subscribe"});
  }

  // Auto-save with 1s debounce
  _scheduleSave() {
    clearTimeout(this._saveTimer);
    this._saving = true; this._renderCfgSaving();
    this._saveTimer = setTimeout(async () => {
      try {
        await this._hass.callApi("POST","turzi/config",{
          entry_id: this._cfg.entry_id,
          included_domains: this._draft.included_domains,
          auto_add_new: this._draft.auto_add_new,
        });
        this._draft = null;
      } catch(e){ console.error("[Turzi]",e); }
      this._saving = false;
    }, 1000);
  }

  _renderCfgSaving() {
    const el = this.shadowRoot.getElementById("cfg-saving");
    if (el) el.textContent = this._saving ? "Saving…" : "";
  }

  async _setExpose(ids, expose) {
    try {
      await this._hass.callApi("POST","turzi/entities/update",{
        entry_id:this._cfg.entry_id,
        entity_ids:Array.isArray(ids)?ids:[ids],
        expose,
      });
    } catch(e){console.error("[Turzi]",e);}
  }

  _filtered() {
    const q = this._search.toLowerCase();
    return this._ents.filter(e => {
      if (this._df && e.domain!==this._df) return false;
      if (q) return e.entity_id.includes(q)||(e.name||"").toLowerCase().includes(q);
      return true;
    });
  }

  _domainCounts() {
    const m={};
    for (const e of this._ents) m[e.domain]=(m[e.domain]||0)+1;
    return m;
  }

  _shell() {
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>
      <div class="layout">
        <div class="header">
          <img class="hlogo" src="${LOGO}" alt="" onerror="this.style.display='none'">
          <div class="hword">turz<span class="di">i</span></div>
        </div>
        <div class="tabs">
          <div class="tab active" data-tab="entities">Entities</div>
          <div class="tab" data-tab="status">Status</div>
        </div>
        <div class="content" id="c"></div>
      </div>`;
    this.shadowRoot.querySelectorAll(".tab").forEach(t =>
      t.addEventListener("click", () => {
        this._tab=t.dataset.tab; this._sel.clear();
        this.shadowRoot.querySelectorAll(".tab").forEach(x=>x.classList.toggle("active",x===t));
        this._render();
      })
    );
  }

  _render() {
    const c = this.shadowRoot.getElementById("c");
    if (!c) return;
    if (this._loading) { c.innerHTML=`<div class="loading"><div class="spin"></div><span>Loading…</span></div>`; return; }
    this._tab==="entities" ? this._renderEntities(c) : this._renderStatus(c);
  }

  // ── Config section (top of Entities tab) ──────────────────────────────────

  _cfgHtml() {
    const d = this._draft||{included_domains:[],auto_add_new:true};
    const counts = this._domainCounts();
    const selSet = new Set(d.included_domains);
    const allSel = ALL_DOMAINS.every(x=>selSet.has(x));

    const tags = d.included_domains.map(dom=>
      `<div class="dtag">${dom}<span class="dtag-rm" data-d="${dom}">×</span></div>`
    ).join("");

    // Dropdown items: ALL_DOMAINS not already selected, filtered by _dpSearch
    const q = this._dpSearch.toLowerCase();
    const ddItems = ALL_DOMAINS
      .filter(x=>!selSet.has(x) && (!q||x.includes(q)))
      .map(x=>`<div class="ddi" data-d="${x}">${x}${counts[x]?` <span class="ddi-cnt">(${counts[x]})</span>`:""}</div>`)
      .join("")||`<div class="ddi empty-msg">No domains to add</div>`;

    return `<div class="cfg" id="cfg">
      <div class="cfg-hd">
        <div class="cfg-title">Exposure Settings</div>
        <div class="cfg-saving" id="cfg-saving">${this._saving?"Saving…":""}</div>
      </div>
      <div class="arow">
        <div>
          <div class="albl">Auto-expose new entities</div>
          <div class="asub">New entities from included domains are added automatically</div>
        </div>
        <ha-switch id="aa" ${d.auto_add_new?"checked":""}></ha-switch>
      </div>
      <div class="doms-hd">
        <div class="doms-lbl">Included domains <span style="color:var(--sub);font-weight:400">(${d.included_domains.length})</span></div>
        <button class="lnk" id="sel-all">${allSel?"Clear all":"Select all"}</button>
      </div>
      <div class="dpick">
        <ha-icon class="dpi-ico" icon="mdi:magnify"></ha-icon>
        <input class="dpi" id="dpi" placeholder="Search and add a domain…" value="${this._dpSearch}" autocomplete="off">
        <div class="ddd${this._dpOpen?" open":""}" id="ddd">${ddItems}</div>
      </div>
      <div class="dtags">${tags||`<span style="font-size:11px;color:var(--sub)">No domains selected — all entities must be exposed manually</span>`}</div>
    </div>`;
  }

  _bindCfg(c) {
    const d = this._draft;
    const counts = this._domainCounts();

    // Auto-add toggle
    c.querySelector("#aa").addEventListener("change", ev => {
      d.auto_add_new = ev.target.checked;
      this._scheduleSave();
    });

    // Select/clear all
    c.querySelector("#sel-all").addEventListener("click", () => {
      const allSel = ALL_DOMAINS.every(x=>d.included_domains.includes(x));
      d.included_domains = allSel ? [] : [...ALL_DOMAINS];
      this._dpSearch=""; this._dpOpen=false;
      this._render(); this._scheduleSave();
    });

    // Domain tag remove
    c.querySelectorAll(".dtag-rm").forEach(x => x.addEventListener("click", () => {
      d.included_domains = d.included_domains.filter(dd=>dd!==x.dataset.d);
      this._render(); this._scheduleSave();
    }));

    // Domain picker input
    const dpi = c.querySelector("#dpi");
    const ddd = c.querySelector("#ddd");
    dpi.addEventListener("focus", () => { this._dpOpen=true; this._renderDropdown(ddd, counts); });
    dpi.addEventListener("input", ev => {
      this._dpSearch=ev.target.value; this._dpOpen=true; this._renderDropdown(ddd, counts);
    });
    dpi.addEventListener("keydown", ev => {
      if (ev.key==="Escape") { this._dpOpen=false; ddd.classList.remove("open"); }
    });
    document.addEventListener("click", ev => {
      if (!c.querySelector(".dpick")?.contains(ev.target)) {
        this._dpOpen=false; ddd.classList.remove("open");
      }
    }, {once:true});

    // Dropdown item click
    c.querySelectorAll(".ddi:not(.empty-msg)").forEach(item => item.addEventListener("click", () => {
      const dom = item.dataset.d;
      if (dom && !d.included_domains.includes(dom)) {
        d.included_domains.push(dom);
        this._dpSearch=""; this._dpOpen=false;
        this._render(); this._scheduleSave();
      }
    }));
  }

  _renderDropdown(ddd, counts) {
    const selSet = new Set(this._draft.included_domains);
    const q = this._dpSearch.toLowerCase();
    const items = ALL_DOMAINS.filter(x=>!selSet.has(x)&&(!q||x.includes(q)));
    ddd.innerHTML = items.length
      ? items.map(x=>`<div class="ddi" data-d="${x}">${x}${counts[x]?` <span class="ddi-cnt">(${counts[x]})</span>`:""}</div>`).join("")
      : `<div class="ddi empty-msg">No domains to add</div>`;
    ddd.classList.toggle("open", true);
    ddd.querySelectorAll(".ddi:not(.empty-msg)").forEach(item => item.addEventListener("click", () => {
      const dom = item.dataset.d;
      if (dom && !this._draft.included_domains.includes(dom)) {
        this._draft.included_domains.push(dom);
        this._dpSearch=""; this._dpOpen=false;
        this._render(); this._scheduleSave();
      }
    }));
  }

  // ── Entities render ───────────────────────────────────────────────────────

  _renderEntities(c) {
    if (!this._draft) return;
    const filtered = this._filtered();
    const expCnt = this._ents.filter(e=>e.is_exposed).length;
    const sel = this._sel.size;
    const allSel = filtered.length>0 && filtered.every(e=>this._sel.has(e.entity_id));
    const counts = this._domainCounts();
    const inclDoms = new Set(this._cfg?.included_domains||[]);
    const allChipDoms = [...new Set([...Object.keys(counts),...inclDoms])].sort();

    const chips = allChipDoms.map(d=>{
      const cnt=counts[d]||0;
      return `<div class="chip${this._df===d?" active":""}" data-domain="${d}">${d}${cnt?` <span class="chip-c">${cnt}</span>`:""}</div>`;
    }).join("");

    const rows = filtered.map(e=>{
      const s=this._sel.has(e.entity_id), b=badge(e.is_exposed,e.in_domain);
      return `<div class="erow${s?" sel":""}">
        <input type="checkbox" class="rcb" ${s?"checked":""} data-id="${e.entity_id}">
        <div class="eico"><ha-icon class="${e.is_exposed?"on":""}" icon="${e.icon||"mdi:help-circle-outline"}"></ha-icon></div>
        <div class="einf"><div class="ename">${e.name||e.entity_id}</div><div class="eid">${e.entity_id}</div></div>
        ${b?`<span class="badge ${b.cls}">${b.lbl}</span>`:`<span style="min-width:90px"></span>`}
        <ha-switch class="esw" ${e.is_exposed?"checked":""} data-id="${e.entity_id}"></ha-switch>
      </div>`;
    }).join("")||`<div class="empty"><ha-icon icon="mdi:magnify"></ha-icon>No entities match.</div>`;

    c.innerHTML = `
      ${this._cfgHtml()}
      <div class="toolbar">
        <div class="sw"><ha-icon icon="mdi:magnify"></ha-icon>
          <input class="si" id="srch" type="text" placeholder="Search entities…" value="${this._search}">
        </div>
      </div>
      <div class="chips">
        <div class="chip${!this._df?" active":""}" data-domain="">All <span class="chip-c">${this._ents.length}</span></div>
        ${chips}
      </div>
      <div class="stats">
        <span><strong>${expCnt}</strong> of ${this._ents.length} exposed</span>
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
        <label for="sa" style="cursor:pointer;font-size:11px">Select all visible (${filtered.length})</label>
      </div>
      <div class="elist">${rows}</div>`;

    this._bindCfg(c);
    c.querySelector("#srch").addEventListener("input", ev=>{this._search=ev.target.value;this._render();});
    c.querySelectorAll(".chip").forEach(ch=>ch.addEventListener("click",()=>{this._df=ch.dataset.domain||null;this._render();}));
    c.querySelector("#sa").addEventListener("change", ev=>{
      filtered.forEach(e=>ev.target.checked?this._sel.add(e.entity_id):this._sel.delete(e.entity_id));
      this._render();
    });
    c.querySelectorAll(".rcb").forEach(cb=>cb.addEventListener("change", ev=>{
      ev.stopPropagation();
      cb.checked?this._sel.add(cb.dataset.id):this._sel.delete(cb.dataset.id);
      this._render();
    }));
    c.querySelectorAll(".esw").forEach(sw=>sw.addEventListener("change", async ev=>{
      ev.stopPropagation();
      await this._setExpose([sw.dataset.id], ev.target.checked);
    }));
    if (sel) {
      const ids=[...this._sel];
      c.querySelector("#ben").addEventListener("click",async()=>{await this._setExpose(ids,true);this._sel.clear();});
      c.querySelector("#bdis").addEventListener("click",async()=>{await this._setExpose(ids,false);this._sel.clear();});
      c.querySelector("#bclr").addEventListener("click",()=>{this._sel.clear();this._render();});
    }
  }

  // ── Status render ─────────────────────────────────────────────────────────

  _renderStatus(c) {
    const s = this._status;
    if (!s) { c.innerHTML=`<div class="empty"><ha-icon icon="mdi:connection"></ha-icon>Status unavailable</div>`; return; }
    const sc = s.status==="connected"?"connected":s.status==="reconnecting"?"reconnecting":"disconnected";
    const log = [...(s.event_log||[])].reverse();
    c.innerHTML = `
      <div class="scard">
        <div class="si-row"><div class="sdot ${sc}"></div><div class="stxt">${s.status}</div></div>
        <dl class="smeta">
          <dt>Broker</dt><dd>${s.broker}:${s.port}${s.use_tls?" · TLS":""}</dd>
          <dt>House ID</dt><dd>${s.house_id}</dd>
          <dt>Exposed</dt><dd>${s.exposed_count} entities, ${s.published_count} published</dd>
          <dt>Reconnects</dt><dd>${s.reconnect_count}</dd>
          <dt>Connected</dt><dd>${fmtDT(s.last_connect_time)}</dd>
          <dt>Disconnected</dt><dd>${fmtDT(s.last_disconnect_time)}</dd>
        </dl>
      </div>
      <div class="log-wrap">
        <h3>Activity log</h3>
        <div class="llist">${log.length
          ? log.map(e=>`<div class="le ${e.level}"><span class="lt">${fmtTime(e.time)}</span><span class="lm">${e.message}</span></div>`).join("")
          : `<div class="no-log">No activity yet</div>`}
        </div>
      </div>`;
  }
}

customElements.define("turzi-panel", TurziPanel);

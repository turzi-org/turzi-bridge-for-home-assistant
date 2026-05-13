// turzi-styles.js — shared styles for Turzi Panel
export const STYLES = `
  :host{display:block;height:100%;background:var(--primary-background-color);
    font-family:var(--paper-font-body1_-_font-family,Roboto,sans-serif);
    --T:#FF8400;--Tl:rgba(255,132,0,.12);--accent:var(--T);
    --card:var(--card-background-color,#1e1e1e);
    --div:var(--divider-color,rgba(255,255,255,.1));
    --tx:var(--primary-text-color,#e5e5e5);
    --sub:var(--secondary-text-color,#999);
    --ok:#4caf50;--warn:#f59e0b;--err:#ef5350;}
  *{box-sizing:border-box;}
  .layout{display:flex;flex-direction:column;height:100%;}
  .header{background:#111;border-bottom:3px solid var(--T);padding:0 16px;
    display:flex;align-items:center;gap:10px;height:60px;flex-shrink:0;}
  .hlogo{width:32px;height:32px;object-fit:contain;}
  .hword{font-size:19px;font-weight:700;letter-spacing:.5px;color:#fff;flex:1;}
  .tabs{display:flex;background:#111;padding:0 16px;flex-shrink:0;
    border-bottom:1px solid rgba(255,255,255,.07);}
  .tab{padding:10px 16px;cursor:pointer;font-size:12px;font-weight:600;
    color:rgba(255,255,255,.4);border-bottom:3px solid transparent;
    transition:all .2s;letter-spacing:.6px;text-transform:uppercase;user-select:none;}
  .tab.active{color:#fff;border-bottom-color:var(--T);}
  .content{flex:1;overflow-y:auto;padding:14px;}

  /* Config section */
  .cfg{background:var(--card);border-radius:10px;padding:14px;margin-bottom:12px;
    box-shadow:0 1px 3px rgba(0,0,0,.2);}
  .cfg-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;}
  .cfg-title{font-size:14px;font-weight:600;color:var(--tx);letter-spacing:.3px;}
  .cfg-saving{font-size:12px;color:var(--sub);}
  .arow{display:flex;align-items:center;justify-content:space-between;
    padding:6px 0;border-bottom:1px solid var(--div);margin-bottom:10px;}
  .albl{font-size:13px;color:var(--tx);}
  .asub{font-size:12px;color:var(--sub);}
  .doms-hd{display:flex;align-items:center;gap:8px;margin-bottom:7px;}
  .doms-lbl{font-size:13px;font-weight:500;color:var(--tx);flex:1;}
  .lnk{background:none;border:none;cursor:pointer;color:var(--T);
    font-size:12px;font-weight:600;padding:0;letter-spacing:.3px;}
  .lnk:hover{opacity:.8;}

  /* Domain picker */
  .dpick{position:relative;margin-bottom:8px;}
  .dpi{width:100%;padding:7px 10px 7px 30px;border-radius:7px;
    border:1px solid var(--div);background:rgba(0,0,0,.2);
    color:var(--tx);font-size:13px;outline:none;}
  .dpi:focus{border-color:var(--T);}
  .dpi-ico{position:absolute;left:8px;top:50%;transform:translateY(-50%);
    --mdc-icon-size:15px;color:var(--sub);}
  .ddd{position:absolute;top:calc(100% + 4px);left:0;right:0;
    background:#222;border:1px solid var(--div);border-radius:8px;
    z-index:10;max-height:180px;overflow-y:auto;display:none;
    box-shadow:0 4px 12px rgba(0,0,0,.4);}
  .ddd.open{display:block;}
  .ddi{padding:8px 12px;font-size:13px;color:var(--tx);cursor:pointer;
    display:flex;justify-content:space-between;align-items:center;}
  .ddi:hover{background:rgba(255,132,0,.1);color:var(--T);}
  .ddi-cnt{font-size:11px;color:var(--sub);}
  .ddi.empty-msg{color:var(--sub);cursor:default;}
  .ddi.empty-msg:hover{background:none;color:var(--sub);}

  /* Domain tags */
  .dtags{display:flex;flex-wrap:wrap;gap:5px;}
  .dtag{display:flex;align-items:center;gap:4px;padding:3px 8px 3px 10px;
    background:var(--Tl);border:1px solid rgba(255,132,0,.3);
    border-radius:14px;font-size:12px;color:var(--T);font-weight:500;}
  .dtag-rm{cursor:pointer;font-size:15px;line-height:1;opacity:.7;margin-left:2px;}
  .dtag-rm:hover{opacity:1;}

  /* Entity toolbar */
  .toolbar{display:flex;align-items:center;gap:7px;margin-bottom:9px;flex-wrap:wrap;}
  .sw{position:relative;flex:1;min-width:130px;}
  .sw ha-icon{position:absolute;left:8px;top:50%;transform:translateY(-50%);
    --mdc-icon-size:15px;color:var(--sub);}
  .si{width:100%;padding:7px 9px 7px 28px;border-radius:7px;
    border:1px solid var(--div);background:var(--card);color:var(--tx);
    font-size:13px;outline:none;}
  .si:focus{border-color:var(--T);}

  /* Filter chips */
  .chips{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:9px;}
  .chip{padding:3px 9px;border-radius:12px;font-size:12px;cursor:pointer;
    border:1px solid var(--div);background:transparent;
    color:var(--sub);transition:all .12s;user-select:none;}
  .chip.active{background:var(--T);color:#fff;border-color:var(--T);}
  .chip-c{opacity:.65;font-size:11px;}

  /* Stats + batch */
  .stats{display:flex;align-items:center;gap:8px;margin-bottom:7px;
    font-size:12px;color:var(--sub);}
  .stats strong{color:var(--T);}
  .stats .sl{margin-left:auto;font-weight:600;color:var(--T);}
  .bb{display:none;align-items:center;gap:6px;padding:8px 12px;
    background:var(--card);border-radius:8px;margin-bottom:7px;
    border:1.5px solid var(--T);flex-wrap:wrap;}
  .bb.on{display:flex;}
  .bb span{font-size:13px;color:var(--tx);font-weight:500;flex:1;}
  .btn{display:inline-flex;align-items:center;gap:4px;padding:6px 12px;
    border-radius:6px;border:none;cursor:pointer;font-size:12px;font-weight:600;
    transition:opacity .12s;white-space:nowrap;}
  .btn:disabled{opacity:.4;cursor:default;}
  .bp{background:var(--T);color:#fff;}
  .bp:hover:not(:disabled){opacity:.88;}
  .bo{background:transparent;border:1px solid var(--div);color:var(--tx);}
  .bo:hover:not(:disabled){border-color:var(--T);color:var(--T);}
  .bd{background:transparent;border:1px solid var(--err);color:var(--err);}
  .bd:hover:not(:disabled){background:rgba(239,83,80,.08);}

  /* Select all row */
  .sa{display:flex;align-items:center;gap:8px;padding:6px 10px;font-size:12px;
    color:var(--sub);border-bottom:1px solid var(--div);margin-bottom:3px;}

  /* Entity list */
  .elist{display:flex;flex-direction:column;gap:1px;}
  .erow{display:flex;align-items:center;gap:8px;padding:7px 10px;
    border-radius:7px;background:var(--card);transition:background .1s;}
  .erow:hover{background:rgba(255,255,255,.04);}
  .erow.sel{background:rgba(255,132,0,.06);}
  .rcb{flex-shrink:0;width:15px;height:15px;accent-color:var(--T);cursor:pointer;}
  .eico{width:28px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
  .eico ha-icon{--mdc-icon-size:17px;color:var(--sub);}
  .eico ha-icon.on{color:var(--T);}
  .einf{flex:1;min-width:0;}
  .ename{font-size:14px;color:var(--tx);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .eid{font-size:11px;color:var(--sub);font-family:monospace;}
  .badge{flex-shrink:0;font-size:11px;font-weight:600;padding:2px 7px;
    border-radius:9px;white-space:nowrap;}
  .b-auto{background:rgba(255,132,0,.13);color:var(--T);}
  .b-man{background:rgba(76,175,80,.13);color:var(--ok);}
  .b-excl{background:rgba(245,158,11,.13);color:var(--warn);}
  ha-switch{flex-shrink:0;}

  /* Loading / empty */
  .loading{display:flex;align-items:center;justify-content:center;height:160px;
    flex-direction:column;gap:12px;color:var(--sub);font-size:13px;}
  .spin{width:30px;height:30px;border:2px solid var(--div);
    border-top-color:var(--T);border-radius:50%;animation:sp 1s linear infinite;}
  @keyframes sp{to{transform:rotate(360deg)}}
  .empty{text-align:center;padding:36px 16px;color:var(--sub);font-size:13px;}
  .empty ha-icon{--mdc-icon-size:40px;display:block;margin-bottom:8px;opacity:.25;}

  /* Status tab */
  .scard{background:var(--card);border-radius:10px;padding:16px;margin-bottom:12px;}
  .si-row{display:flex;align-items:center;gap:10px;margin-bottom:12px;}
  .sdot{width:12px;height:12px;border-radius:50%;flex-shrink:0;}
  .sdot.connected{background:var(--ok);box-shadow:0 0 6px var(--ok);}
  .sdot.reconnecting{background:var(--warn);animation:pulse 1.2s infinite;}
  .sdot.disconnected,.sdot.connecting{background:#555;}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
  .stxt{font-size:16px;font-weight:600;color:var(--tx);text-transform:capitalize;}
  .smeta{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;font-size:13px;}
  .smeta dt{color:var(--sub);font-weight:500;}
  .smeta dd{color:var(--tx);margin:0;}
  .log-wrap{background:var(--card);border-radius:10px;padding:14px;}
  .log-wrap h3{margin:0 0 8px;font-size:14px;font-weight:600;color:var(--tx);}
  .llist{display:flex;flex-direction:column;gap:1px;max-height:300px;overflow-y:auto;}
  .le{display:flex;gap:8px;padding:4px 6px;border-radius:4px;font-size:12px;}
  .lt{color:var(--sub);white-space:nowrap;font-family:monospace;flex-shrink:0;}
  .le.success .lm{color:var(--ok);}
  .le.warning .lm{color:var(--warn);}
  .le.error .lm{color:var(--err);}
  .lm{color:var(--sub);}
  .no-log{color:var(--sub);font-size:13px;text-align:center;padding:16px 0;}
`;

// DOM interface layer: top bar, context panel, alerts, dialogs, battle HUD.
// main.js owns game state; this module renders it and forwards clicks to `api`.

import { UNIT_TYPES, LOC_TYPES, FACTIONS, PROMO_COST, OBJECTIVE, TUNE } from './data.js';
import { fitForDuty, isVeteran, promotionOptions } from './soldiers.js';
import { hasFoundryAccess, playerArmy, byKey } from './campaign.js';
import { sfx } from './audio.js';

const $ = (id) => document.getElementById(id);
let api = null;
let ctxSig = '';
let hudSig = '';
let selSig = '';

export function initUI(gameApi) {
  api = gameApi;
  $('btn-new').onclick = () => api.newCampaign();
  $('btn-continue').onclick = () => api.continueCampaign();
  $('btn-reset').onclick = () => { if (confirm('Erase the saved campaign?')) api.resetSave(); };
  $('btn-pause').onclick = () => api.setSpeed(0);
  $('btn-play').onclick = () => api.setSpeed(1);
  $('btn-fast').onclick = () => api.setSpeed(2.5);
  $('btn-help').onclick = () => toggleHelp(true);
  $('btn-close-help').onclick = () => toggleHelp(false);
  $('btn-menu').onclick = () => api.toMenu();
  $('btn-form-line').onclick = () => api.setFormation('line');
  $('btn-form-deep').onclick = () => api.setFormation('deep');
  $('btn-form-loose').onclick = () => api.setFormation('loose');
  $('btn-hero').onclick = () => api.selectHero();
  $('btn-withdraw').onclick = () => {
    if (confirm('Order a withdrawal? Your soldiers will break off and quit the field.')) api.withdraw();
  };
  // Rally button lives next to the fixed ones.
  const rallyBtn = document.createElement('button');
  rallyBtn.className = 'fbtn';
  rallyBtn.id = 'btn-rally';
  rallyBtn.title = 'Rally nearby troops (R)';
  rallyBtn.textContent = 'RALLY';
  $('btn-withdraw').before(rallyBtn);
  rallyBtn.onclick = () => api.rally();
}

export function setScreen(screen, hasSaveFile) {
  $('mainmenu').classList.toggle('hidden', screen !== 'menu');
  $('topbar').classList.toggle('hidden', screen === 'menu');
  $('battle-hud').classList.toggle('hidden', screen !== 'battle');
  // Campaign clock controls have no meaning inside a battle — don't show dead buttons.
  $('time-controls').classList.toggle('hidden', screen !== 'strategic');
  if (screen !== 'strategic') $('context-panel').classList.add('hidden');
  if (screen === 'menu') {
    $('btn-continue').classList.toggle('hidden', !hasSaveFile);
    $('btn-reset').classList.toggle('hidden', !hasSaveFile);
    closeDialog();
  }
  ctxSig = ''; hudSig = '';
}

// The menu buttons stay disabled until the sprite atlases are in memory.
export function setBooting(booting) {
  for (const id of ['btn-new', 'btn-continue']) {
    const el = $(id);
    if (el) el.disabled = booting;
  }
  const hint = document.querySelector('.menuhint');
  if (hint) {
    if (booting) {
      hint.dataset.text = hint.dataset.text || hint.textContent;
      hint.textContent = 'Casting the company…';
    } else if (hint.dataset.text) {
      hint.textContent = hint.dataset.text;
    }
  }
}

export function setSpeedButtons(speed) {
  $('btn-pause').classList.toggle('active', speed === 0);
  $('btn-play').classList.toggle('active', speed === 1);
  $('btn-fast').classList.toggle('active', speed > 1);
}

export function toggleHelp(show) {
  const el = $('help-overlay');
  el.classList.toggle('hidden', show === undefined ? !el.classList.contains('hidden') : !show);
}

// ---------------------------------------------------------------- top bar + alerts

export function updateTopbar(c) {
  $('val-crowns').textContent = Math.floor(c.resources.crowns);
  $('val-provisions').textContent = Math.floor(c.resources.provisions);
  $('val-coal').textContent = Math.floor(c.resources.coal);
  const owned = OBJECTIVE.locKeys.filter(k => byKey(c, k).owner === 'player').length;
  const chip = $('objective-chip');
  const sig = `${owned}${c.victory}`;
  if (chip.dataset.sig !== sig) {
    chip.dataset.sig = sig;
    chip.innerHTML = c.victory
      ? '<b>OBJECTIVE COMPLETE — THE VALE\'S INDUSTRY IS YOURS</b>'
      : `OBJECTIVE: HOLD FOUNDRY · COAL · BRIDGE FORT — <b>${owned}/3</b>`;
  }
}

export function drainAlerts(c) {
  const root = $('alerts');
  for (const a of c.alerts) {
    const el = document.createElement('div');
    el.className = `alert ${a.kind || ''}`;
    el.innerHTML = `<div>${a.text}</div>${a.sub ? `<div class="sub">${a.sub}</div>` : ''}`;
    el.onclick = () => el.remove();
    root.appendChild(el);
    while (root.children.length > 5) root.firstChild.remove();
    setTimeout(() => { el.classList.add('fading'); setTimeout(() => el.remove(), 700); }, 9000);
    if (a.kind === 'threat') sfx('alarm');
    else if (a.kind === 'good') sfx('capture');
  }
  c.alerts.length = 0;
}

// ---------------------------------------------------------------- tutorial

const TUTOR_TEXT = {
  0: 'LEFT-CLICK YOUR BANNER · RIGHT-CLICK TO MOVE',
  1: 'VISIT A SETTLEMENT AND RECRUIT SOLDIERS',
  2: 'HOLD POSITION AT A NEUTRAL SITE TO CAPTURE IT',
  3: 'LEAVE A GARRISON — OPEN THE LOCATION PANEL',
  4: 'HUNT THE TOLLMEN — WIN YOUR FIRST BATTLE',
};

export function updateTutor(c, mode) {
  const el = $('tutor');
  if (mode === 'battle') {
    el.textContent = 'DRAG TO SELECT SOLDIERS · RIGHT-CLICK TO MOVE OR ATTACK · F1 FOR COMMANDER';
    el.classList.toggle('hidden', c.stats.battles > 1);
    return;
  }
  const txt = TUTOR_TEXT[c.tutorial.step];
  el.classList.toggle('hidden', !txt || c.tutorial.done);
  if (txt) el.textContent = txt;
}

// ---------------------------------------------------------------- context panel (strategic)

function troopSummary(soldiers) {
  const by = {};
  let wounded = 0, vets = 0;
  for (const s of soldiers) {
    if (!s.alive) continue;
    if (s.wounded > 0) { wounded++; continue; }
    by[s.type] = (by[s.type] || 0) + 1;
    if (isVeteran(s) && s.type !== 'hero') vets++;
  }
  const parts = Object.entries(by).map(([t, n]) => `${n} ${UNIT_TYPES[t].name}`);
  let txt = parts.join(' · ') || 'no one fit to fight';
  if (vets > 0) txt += ` <span style="color:#c9a959">(${vets}★)</span>`;
  if (wounded > 0) txt += ` <span style="color:#b5533c">+${wounded} wounded</span>`;
  return txt;
}

export function updateContextPanel(c, selectedArmy, nearbyLoc) {
  const panel = $('context-panel');
  if (!selectedArmy && !nearbyLoc) {
    panel.classList.add('hidden');
    ctxSig = '';
    return;
  }
  const army = playerArmy(c);
  const promoCount = army ? army.soldiers.filter(s => s.alive && promotionOptions(s, hasFoundryAccess(c)).length > 0).length : 0;
  const sig = JSON.stringify([
    selectedArmy ? troopSummary(selectedArmy.soldiers) : '',
    nearbyLoc ? [nearbyLoc.key, nearbyLoc.owner, nearbyLoc.garrison.length, Math.floor(c.resources.crowns), Math.floor(c.resources.provisions), Math.floor(c.resources.coal)] : '',
    promoCount,
  ]);
  if (sig === ctxSig) return;
  ctxSig = sig;
  panel.classList.remove('hidden');

  let html = '';
  if (nearbyLoc) {
    const lt = LOC_TYPES[nearbyLoc.type];
    const fac = FACTIONS[nearbyLoc.owner];
    html += `<h3><span class="owner-strip" style="background:${fac.color}"></span>${nearbyLoc.name}</h3>`;
    html += `<div class="subtitle">${lt.label} — ${lt.desc} · held by ${fac.name}</div>`;
    const prod = Object.entries(lt.production).map(([k, v]) => `+${v} ${k}`).join(' · ');
    if (prod) html += `<div class="row"><span class="k">Yields</span><span>${prod} / ${TUNE.incomeInterval}s</span></div>`;
    const g = fitForDuty(nearbyLoc.garrison).length;
    html += `<div class="row"><span class="k">Garrison</span><span>${g} / ${lt.garrisonCap}</span></div>`;

    // An independent site with its watch still standing won't muster for you.
    const friendly = nearbyLoc.owner === 'player' || (nearbyLoc.owner === 'neutral' && g === 0);
    if (friendly && lt.recruits.length > 0) {
      html += `<div class="row k" style="margin-top:6px">Recruit</div>`;
      for (const t of lt.recruits) {
        const u = UNIT_TYPES[t];
        const cost = Object.entries(u.cost).map(([k, v]) => `${v} ${k.slice(0, 4)}`).join(', ');
        html += `<button data-act="recruit" data-type="${t}" title="${u.desc}">${u.name} — ${cost}</button>`;
      }
    }
    if (nearbyLoc.owner === 'player') {
      html += `<div class="row k" style="margin-top:6px">Garrison</div>`;
      html += `<button data-act="gadd" data-n="1">LEAVE 1</button><button data-act="gadd" data-n="3">LEAVE 3</button>`;
      if (nearbyLoc.garrison.length > 0) html += `<button data-act="gtake" data-n="3">TAKE 3</button>`;
      if (lt.heals) html += `<button data-act="heal">TREAT WOUNDED (5c each)</button>`;
    }
    if (nearbyLoc.owner !== 'player' && g > 0) {
      html += `<div class="hint">${g} defender${g === 1 ? '' : 's'} hold this place — move onto it to assault.</div>`;
    } else if (nearbyLoc.owner !== 'player' && g === 0) {
      html += `<div class="hint">Hold position here to take control.</div>`;
    }
  }
  if (selectedArmy) {
    const fit = fitForDuty(selectedArmy.soldiers).length;
    html += `<h3 style="margin-top:${nearbyLoc ? '10px' : '0'}"><span class="owner-strip" style="background:${FACTIONS.player.color}"></span>${c.heroName}</h3>`;
    html += `<div class="subtitle">Field army — ${fit} fit for duty</div>`;
    html += `<div class="troops">${troopSummary(selectedArmy.soldiers)}</div>`;
    if (promoCount > 0) html += `<button data-act="promos" style="border-color:#8a7440;color:#c9a959">PROMOTIONS AVAILABLE (${promoCount})</button>`;
    else html += `<button data-act="promos">ROSTER</button>`;
  }
  panel.innerHTML = html;
  panel.querySelectorAll('button').forEach(btn => {
    btn.onclick = (ev) => {
      ev.stopPropagation();
      const act = btn.dataset.act;
      if (act === 'recruit') api.recruit(nearbyLoc, btn.dataset.type);
      else if (act === 'gadd') api.garrisonAdd(nearbyLoc, +btn.dataset.n);
      else if (act === 'gtake') api.garrisonTake(nearbyLoc, +btn.dataset.n);
      else if (act === 'heal') api.heal();
      else if (act === 'promos') showRoster(c);
      ctxSig = '';
    };
  });
}

// ---------------------------------------------------------------- battle HUD

export function updateBattleHud(b, playerCount, enemyCount, selected) {
  const sig = `${playerCount}|${enemyCount}|${selected.map(u => u.type).join(',')}|${b.formationType}|${Math.ceil(b.rallyCd)}`;
  if (sig === hudSig) return;
  hudSig = sig;
  const enemyFac = FACTIONS[b.ctx.enemyFaction] || FACTIONS.bandit;
  $('battle-forces').innerHTML =
    `<div class="frow"><span class="fname" style="color:${FACTIONS.player.color}">HARROW</span><b>${playerCount}</b></div>` +
    `<div class="frow"><span class="fname" style="color:${enemyFac.color}">${enemyFac.short}</span><b>${enemyCount}</b></div>`;
  const by = {};
  for (const u of selected) by[u.def.name] = (by[u.def.name] || 0) + 1;
  const parts = Object.entries(by).map(([n, k]) => `${k} ${n}`);
  $('battle-selinfo').innerHTML = parts.length
    ? `<b>${selected.length} selected:</b> ${parts.join(' · ')}`
    : 'No selection — drag to box-select your soldiers';
  $('btn-form-line').classList.toggle('active', b.formationType === 'line');
  $('btn-form-deep').classList.toggle('active', b.formationType === 'deep');
  $('btn-form-loose').classList.toggle('active', b.formationType === 'loose');
  const rallyBtn = $('btn-rally');
  if (rallyBtn) {
    rallyBtn.disabled = b.rallyCd > 0;
    rallyBtn.textContent = b.rallyCd > 0 ? `RALLY ${Math.ceil(b.rallyCd)}` : 'RALLY';
  }
}

// ---------------------------------------------------------------- dialogs

export function isDialogOpen() {
  return !$('dialog-root').classList.contains('hidden');
}

export function closeDialog() {
  $('dialog-root').classList.add('hidden');
  $('dialog-root').innerHTML = '';
}

function openDialog(html) {
  const root = $('dialog-root');
  root.innerHTML = `<div class="dialog">${html}</div>`;
  root.classList.remove('hidden');
  return root.firstElementChild;
}

export function showEncounter(opts) {
  // opts: {title, enemyFaction, playerCount, enemyCount, terrainLabel, canRetreat, defending, locName, onFight, onAuto, onRetreat}
  const fac = FACTIONS[opts.enemyFaction] || FACTIONS.bandit;
  const dlg = openDialog(`
    <h2 class="threat">${opts.title}</h2>
    <div class="dsub">${fac.name}${opts.locName ? ` — at ${opts.locName}` : ''} · Terrain: ${opts.terrainLabel.toUpperCase()}</div>
    <div class="vs">
      <div><div class="num">${opts.playerCount}</div><div class="lbl">YOUR FORCE</div></div>
      <div class="mid">AGAINST</div>
      <div><div class="num">${opts.enemyCount}</div><div class="lbl">ENEMY FORCE</div></div>
    </div>
    <div class="btnrow">
      <button class="primary" data-a="fight">FIGHT</button>
      <button data-a="auto">AUTO-RESOLVE</button>
      ${opts.canRetreat ? '<button class="danger" data-a="retreat">RETREAT (−3 provisions)</button>' : ''}
    </div>`);
  dlg.querySelector('[data-a=fight]').onclick = () => { closeDialog(); opts.onFight(); };
  dlg.querySelector('[data-a=auto]').onclick = () => { closeDialog(); opts.onAuto(); };
  const r = dlg.querySelector('[data-a=retreat]');
  if (r) r.onclick = () => { closeDialog(); opts.onRetreat(); };
}

export function showBattleResult(report, onClose) {
  // report: {victory, withdrew, entered, killed, wounded, ready, enemyKilled, xpGained, promotable, notables, loot, locLine}
  const rows = [
    ['Entered the field', report.entered],
    ['Killed', report.killed, report.killed > 0 ? 'bad' : ''],
    ['Wounded', report.wounded, report.wounded > 0 ? 'bad' : ''],
    ['Fit for duty', report.ready, 'good'],
    ['Enemy fallen', report.enemyKilled, 'good'],
  ];
  if (report.promotable > 0) rows.push(['Ready for promotion', report.promotable, 'good']);
  let lootLine = '';
  if (report.loot && report.loot.crowns) lootLine = `<div class="dsub" style="color:#c9a959">Spoils: +${report.loot.crowns} crowns</div>`;
  const notables = (report.notables || []).map(n => `
    <div class="notable">
      <div class="nname">★ ${n.name} — ${UNIT_TYPES[n.type].name}</div>
      <div class="nsub">Battles survived: ${n.battles} · Kills: ${n.kills}${n.promotable ? ' · ready for promotion' : ''}</div>
    </div>`).join('');
  const dlg = openDialog(`
    <h2 class="${report.victory ? '' : 'threat'}">${report.victory ? 'VICTORY' : report.withdrew ? 'WITHDRAWAL' : 'DEFEAT'}</h2>
    ${report.locLine ? `<div class="dsub">${report.locLine}</div>` : ''}
    <table class="stat-table">${rows.map(([k, v, cls]) => `<tr><td>${k}</td><td class="${cls || ''}">${v}</td></tr>`).join('')}</table>
    ${lootLine}${notables}
    <div class="btnrow"><button class="primary" data-a="ok">RETURN TO THE MAP</button></div>`);
  dlg.querySelector('[data-a=ok]').onclick = () => { closeDialog(); onClose(); };
}

export function showAutoResult(title, won, lines, onClose) {
  const dlg = openDialog(`
    <h2 class="${won ? '' : 'threat'}">${title}</h2>
    <table class="stat-table">${lines.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table>
    <div class="btnrow"><button class="primary" data-a="ok">CONTINUE</button></div>`);
  dlg.querySelector('[data-a=ok]').onclick = () => { closeDialog(); if (onClose) onClose(); };
}

export function showVictoryDialog(c, onClose) {
  const dlg = openDialog(`
    <h2>THE VALE'S INDUSTRY IS YOURS</h2>
    <div class="dsub">${OBJECTIVE.text}</div>
    <div class="dsub">Foundry, coal and the bridge road answer to Harrow's Company now.
    The rival houses will not forget this — the campaign continues if you wish to keep the field.</div>
    <table class="stat-table">
      <tr><td>Battles fought</td><td>${c.stats.battles}</td></tr>
      <tr><td>Battles won</td><td>${c.stats.won}</td></tr>
      <tr><td>Locations taken</td><td>${c.stats.captured}</td></tr>
    </table>
    <div class="btnrow"><button class="primary" data-a="ok">KEEP CAMPAIGNING</button></div>`);
  dlg.querySelector('[data-a=ok]').onclick = () => { closeDialog(); if (onClose) onClose(); };
}

// ---------------------------------------------------------------- roster / promotions

export function showRoster(c) {
  const army = playerArmy(c);
  const foundry = hasFoundryAccess(c);
  const soldiers = army.soldiers.filter(s => s.alive && s.type !== 'hero');
  soldiers.sort((a, b) => (b.kills * 3 + b.battles) - (a.kills * 3 + a.battles));
  const rows = soldiers.slice(0, 14).map(s => {
    const opts = promotionOptions(s, foundry);
    const vet = isVeteran(s) ? '★ ' : '';
    const status = s.wounded > 0 ? ' · <span style="color:#b5533c">wounded</span>' : '';
    const buttons = opts.map(o => {
      const cost = Object.entries(o.cost).filter(([k]) => k !== 'needsFoundry').map(([k, v]) => `${v}${k[0]}`).join(' ');
      const label = `→ ${UNIT_TYPES[o.to].name} (${cost})`;
      return `<button data-sid="${s.id}" data-to="${o.to}" ${o.locked ? 'disabled title="Requires a foundry under your banner"' : ''}>${label}</button>`;
    }).join('');
    return `<div class="promo-row">
      <div><div class="pname">${vet}${s.name}</div>
      <div class="psub">${UNIT_TYPES[s.type].name} · XP ${Math.floor(s.xp)} · ${s.kills} kills · ${s.battles} battles${status}</div></div>
      <div>${buttons || ''}</div>
    </div>`;
  }).join('');
  const dlg = openDialog(`
    <h2>COMPANY ROSTER</h2>
    <div class="dsub">Promotion needs ${TUNE.promoXp} XP. Pressure equipment needs a foundry and coal.${foundry ? '' : ' <span style="color:#b5533c">No foundry under your banner.</span>'}</div>
    ${rows || '<div class="dsub">No soldiers beyond the commander.</div>'}
    <div class="btnrow"><button class="primary" data-a="ok">CLOSE</button></div>`);
  dlg.querySelector('[data-a=ok]').onclick = () => closeDialog();
  dlg.querySelectorAll('button[data-sid]').forEach(btn => {
    btn.onclick = () => {
      const s = army.soldiers.find(x => x.id === +btn.dataset.sid);
      if (s && api.promote(s, btn.dataset.to)) {
        closeDialog();
        showRoster(c);
      }
    };
  });
}

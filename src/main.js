// STEAMWARD entry point: game loop, input routing, mode transitions, and the
// glue that carries soldiers between the strategic and tactical layers.

import { TUNE, FACTIONS, LOC_TYPES, UNIT_TYPES } from './data.js';
import { makeRng, dist, clamp } from './util.js';
import * as Campaign from './campaign.js';
import * as Strategic from './strategic.js';
import * as Battle from './battle.js';
import { renderStrategic } from './strategicRender.js';
import { renderBattle, consumeEffects, resetBattleFx } from './battleRender.js';
import * as UI from './ui.js';
import { initAudio, resumeAudio, sfx, consumeEffectsAudio, toggleMusic } from './audio.js';
import { makeCamera } from './camera.js';
import { fitForDuty, promotionOptions, isVeteran } from './soldiers.js';

const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');
let dpr = 1;

function resize() {
  dpr = Math.min(window.devicePixelRatio || 1, 1.5);
  canvas.width = Math.floor(canvas.clientWidth * dpr);
  canvas.height = Math.floor(canvas.clientHeight * dpr);
}
window.addEventListener('resize', resize);
resize();

// ---------------------------------------------------------------- state

let mode = 'menu';               // menu | strategic | battle
let campaign = null;
let battle = null;
let battleMeta = null;
let rng = makeRng((Math.random() * 1e9) | 0);
const cam = makeCamera(canvas);
let stratCamSaved = null;

const keys = {};
let mouse = { x: 0, y: 0, down: false, downX: 0, downY: 0, dragging: false, mmb: false };
let boxSel = null;
let attackArmed = false;
let lastClickT = 0, lastClickUid = -1;
let selectedArmy = null;
let devMode = false;
let fps = 0, fpsAcc = 0, fpsN = 0;
let autosaveT = 0;
let resultShown = false;

// ---------------------------------------------------------------- API for UI

const api = {
  newCampaign() {
    campaign = Campaign.newCampaign();
    rng = makeRng(campaign.seed ^ 0x9e3779b9);
    enterStrategic(true);
  },
  continueCampaign() {
    const c = Campaign.loadCampaign();
    if (!c) { UI.setScreen('menu', Campaign.hasSave()); return; }
    campaign = c;
    rng = makeRng((campaign.seed ^ (campaign.time | 0)) >>> 0);
    enterStrategic(true);
  },
  resetSave() {
    Campaign.clearSave();
    UI.setScreen('menu', false);
  },
  toMenu() {
    if (mode === 'battle' &&
        !confirm('Leave the battle? This engagement is abandoned and the campaign reloads from its last save.')) return;
    if (campaign && mode === 'strategic') Campaign.saveCampaign(campaign);
    if (mode === 'battle') { battle = null; battleMeta = null; }
    mode = 'menu';
    UI.closeDialog();
    UI.setScreen('menu', Campaign.hasSave());
  },
  setSpeed(s) {
    if (!campaign) return;
    campaign.speed = s;
    UI.setSpeedButtons(s);
  },
  recruit(loc, type) {
    const s = Campaign.recruitAt(campaign, loc, type, rng);
    if (s) {
      sfx('click');
      if (campaign.tutorial.step === 1) campaign.tutorial.step = 2;
    }
  },
  garrisonAdd(loc, n) {
    const moved = Campaign.transferToGarrison(campaign, loc, n);
    if (moved > 0) {
      sfx('click');
      if (campaign.tutorial.step === 3) campaign.tutorial.step = 4;
      Campaign.saveCampaign(campaign);
    }
  },
  garrisonTake(loc, n) {
    if (Campaign.takeFromGarrison(campaign, loc, n) > 0) sfx('click');
  },
  heal() {
    if (Campaign.healAllWounded(campaign) > 0) sfx('capture');
  },
  promote(s, to) {
    const ok = Campaign.promoteSoldier(campaign, s, to);
    if (ok) sfx('capture');
    return ok;
  },
  setFormation(t) { if (battle) { battle.formationType = t; sfx('click'); } },
  selectHero() { if (battle) selectHeroAndCenter(); },
  rally() { if (battle) Battle.rally(battle); },
  withdraw() { if (battle) Battle.withdraw(battle); },
};
UI.initUI(api);

// ---------------------------------------------------------------- transitions

function enterStrategic(centerOnArmy) {
  mode = 'strategic';
  battle = null; battleMeta = null;
  cam.bounds = { w: Campaign.WORLD.w, h: Campaign.WORLD.h };
  if (stratCamSaved) {
    cam.x = stratCamSaved.x; cam.y = stratCamSaved.y; cam.zoom = stratCamSaved.zoom;
  }
  const pa = Campaign.playerArmy(campaign);
  if (centerOnArmy && pa) { cam.centerOn(pa.x, pa.y); cam.zoom = 1; }
  selectedArmy = pa;
  UI.setScreen('strategic');
  UI.setSpeedButtons(campaign.speed);
}

function enterBattle(bctx, meta) {
  stratCamSaved = { x: cam.x, y: cam.y, zoom: cam.zoom };
  battle = Battle.startBattle(bctx);
  battleMeta = meta;
  resultShown = false;
  resetBattleFx();
  mode = 'battle';
  cam.bounds = { w: battle.w, h: battle.h };
  const heroU = Battle.heroUnit(battle);
  cam.zoom = 1.0;
  cam.centerOn(heroU ? heroU.x + 160 : battle.w * 0.3, heroU ? heroU.y : battle.h / 2);
  UI.setScreen('battle');
  UI.updateTutor(campaign, 'battle');
}

function buildEncounterContext(enemyArmy, loc, defending) {
  const pa = Campaign.playerArmy(campaign);
  const playerSoldiers = [...pa.soldiers];
  if (defending && loc) playerSoldiers.push(...loc.garrison);
  const enemySoldiers = [...enemyArmy.soldiers];
  if (!defending && loc) enemySoldiers.push(...loc.garrison); // assaulting their garrison
  const terrain = Campaign.battleTerrainAt(campaign, loc ? loc.x : pa.x, loc ? loc.y : pa.y);
  return {
    playerSoldiers, enemySoldiers, terrain,
    defending: !!defending,
    enemyFaction: enemyArmy.faction,
    locName: loc ? loc.name : null,
    seed: (rng.raw() * 1e9) | 0,
  };
}

// ---------------------------------------------------------------- encounter handling

function onStrategicEvents(events) {
  for (const ev of events) {
    // One dialog at a time: a second openDialog() would overwrite the first and
    // strand pendingEncounter, freezing the simulation for good.
    if (ev.type === 'encounter' || ev.type === 'assault' || ev.type === 'defense') {
      if (UI.isDialogOpen()) {
        campaign.pendingEncounter = false; // let it re-trigger once the player is free
        continue;
      }
    }
    if (ev.type === 'encounter') {
      const bctx = buildEncounterContext(ev.enemy, null, false);
      UI.showEncounter({
        title: 'HOSTILE CONTACT',
        enemyFaction: ev.enemy.faction,
        playerCount: fitForDuty(bctx.playerSoldiers).length,
        enemyCount: fitForDuty(bctx.enemySoldiers).length,
        terrainLabel: bctx.terrain,
        canRetreat: true,
        onFight: () => enterBattle(bctx, { enemyArmy: ev.enemy, loc: null, assault: false, defense: false }),
        onAuto: () => autoResolveEncounter(ev.enemy, null, false),
        onRetreat: () => { Strategic.retreatFrom(campaign, ev.enemy); sfx('order'); },
      });
    } else if (ev.type === 'assault') {
      const bctx = buildEncounterContext(dummyGarrisonArmy(ev.loc), ev.loc, false);
      UI.showEncounter({
        title: `ASSAULT ON ${ev.loc.name.toUpperCase()}`,
        enemyFaction: ev.loc.owner,
        playerCount: fitForDuty(bctx.playerSoldiers).length,
        enemyCount: fitForDuty(bctx.enemySoldiers).length,
        terrainLabel: bctx.terrain,
        locName: null,
        canRetreat: true,
        onFight: () => enterBattle(bctx, { enemyArmy: null, loc: ev.loc, assault: true, defense: false }),
        onAuto: () => autoResolveEncounter(null, ev.loc, false),
        onRetreat: () => {
          const pa = Campaign.playerArmy(campaign);
          let dx = pa.x - ev.loc.x, dy = pa.y - ev.loc.y;
          let d = Math.hypot(dx, dy);
          if (d < 1) {
            // Standing dead-center on the location (move orders snap to it):
            // fall back toward camp instead of nowhere.
            const camp = Campaign.byKey(campaign, 'camp');
            dx = camp.x - pa.x; dy = camp.y - pa.y;
            d = Math.hypot(dx, dy) || 1;
          }
          pa.x = clamp(pa.x + dx / d * 90, 20, Campaign.WORLD.w - 20);
          pa.y = clamp(pa.y + dy / d * 90, 20, Campaign.WORLD.h - 20);
          pa.dest = null;
          campaign.pendingEncounter = false;
        },
      });
    } else if (ev.type === 'defense') {
      const bctx = buildEncounterContext(ev.army, ev.loc, true);
      UI.showEncounter({
        title: `DEFENSE OF ${ev.loc.name.toUpperCase()}`,
        enemyFaction: ev.army.faction,
        playerCount: fitForDuty(bctx.playerSoldiers).length,
        enemyCount: fitForDuty(bctx.enemySoldiers).length,
        terrainLabel: bctx.terrain,
        canRetreat: false,
        onFight: () => enterBattle(bctx, { enemyArmy: ev.army, loc: ev.loc, assault: false, defense: true }),
        onAuto: () => autoResolveEncounter(ev.army, ev.loc, true),
      });
    } else if (ev.type === 'captured') {
      Campaign.saveCampaign(campaign);
    }
    // Victory is announced from the frame loop instead of here, so it can wait
    // for any encounter dialog already on screen.
  }
}

// The garrison of an assaulted location behaves like an army for battle purposes.
function dummyGarrisonArmy(loc) {
  return { faction: loc.owner, soldiers: [], x: loc.x, y: loc.y, id: -1, avoid: {} };
}

function autoResolveEncounter(enemyArmy, loc, defending) {
  const pa = Campaign.playerArmy(campaign);
  const playerSoldiers = [...pa.soldiers];
  if (defending && loc) playerSoldiers.push(...loc.garrison);
  const enemySoldiers = enemyArmy ? [...enemyArmy.soldiers] : [];
  if (!defending && loc) enemySoldiers.push(...loc.garrison);
  const defBonus = loc ? LOC_TYPES[loc.type].defense : 1;
  const res = defending
    ? Strategic.autoResolve(campaign, enemySoldiers, playerSoldiers, defBonus, rng)
    : Strategic.autoResolve(campaign, playerSoldiers, enemySoldiers, enemyArmy ? 1 : defBonus, rng);
  const playerWon = defending ? !res.atkWins : res.atkWins;

  const pcas = Campaign.applyCasualties(campaign, playerSoldiers, res.fallen, playerWon, rng);
  Campaign.applyCasualties(campaign, enemySoldiers, res.fallen, !playerWon, rng);
  finishAftermath({
    victory: playerWon, withdrew: false, auto: true,
    enemyArmy, loc, assault: !!loc && !defending, defense: defending,
    playerDead: pcas.dead.length, playerWounded: pcas.wounded.length,
    enemyDead: enemySoldiers.filter(s => !s.alive).length,
    survivors: playerSoldiers.filter(s => s.alive && s.wounded <= 0),
  });
  const lines = [
    ['Outcome', playerWon ? 'The field is yours' : 'Your force was beaten back'],
    ['Your dead', pcas.dead.length],
    ['Your wounded', pcas.wounded.length],
    ['Enemy fallen', enemySoldiers.filter(s => !s.alive).length],
  ];
  sfx(playerWon ? 'victory' : 'defeat');
  UI.showAutoResult(playerWon ? 'AUTO-RESOLVE — VICTORY' : 'AUTO-RESOLVE — DEFEAT', playerWon, lines);
}

// Shared aftermath: territory, army cleanup, stats, saves.
function finishAftermath(o) {
  const pa = Campaign.playerArmy(campaign);
  campaign.stats.battles++;
  if (o.victory) campaign.stats.won++; else if (!o.withdrew) campaign.stats.lost++;
  if (o.victory && campaign.tutorial.step === 4) { campaign.tutorial.step = 5; campaign.tutorial.done = true; }

  // XP for survivors on both sides.
  for (const s of (o.survivors || [])) { s.battles++; s.xp += TUNE.xpSurvive; }

  if (o.loc) {
    if (o.assault && o.victory) {
      o.loc.owner = 'player';
      o.loc.garrison = [];
      o.loc.captureProgress = 0;
      campaign.stats.captured++;
      campaign.alerts.push({ text: `${o.loc.name.toUpperCase()} TAKEN`, sub: 'The garrison is broken', kind: 'good' });
    } else if (o.defense && !o.victory) {
      o.loc.owner = o.enemyArmy ? o.enemyArmy.faction : 'neutral';
      o.loc.garrison = [];
      campaign.alerts.push({ text: `${o.loc.name.toUpperCase()} LOST`, sub: 'The defense failed', kind: 'threat' });
    } else if (o.defense && o.victory) {
      campaign.alerts.push({ text: `${o.loc.name.toUpperCase()} HELD`, sub: 'The attack was broken', kind: 'good' });
    }
  }

  // Enemy field army bookkeeping.
  if (o.enemyArmy) {
    o.enemyArmy.soldiers = o.enemyArmy.soldiers.filter(s => s.alive);
    if (o.enemyArmy.soldiers.length === 0 || (o.victory && o.enemyArmy.soldiers.length <= 2)) {
      campaign.armies = campaign.armies.filter(a => a !== o.enemyArmy);
    } else {
      // survivors slip away
      o.enemyArmy.avoid[pa.id] = TUNE.retreatCooldown;
      pa.avoid[o.enemyArmy.id] = TUNE.retreatCooldown;
      if (o.victory) {
        const dx = o.enemyArmy.x - pa.x, dy = o.enemyArmy.y - pa.y;
        const d = Math.hypot(dx, dy) || 1;
        o.enemyArmy.x = clamp(o.enemyArmy.x + dx / d * 260, 40, Campaign.WORLD.w - 40);
        o.enemyArmy.y = clamp(o.enemyArmy.y + dy / d * 260, 40, Campaign.WORLD.h - 40);
        o.enemyArmy.dest = null;
      }
    }
  }
  if (!o.victory && !o.defense) {
    // beaten player force falls back toward camp
    const camp = Campaign.byKey(campaign, 'camp');
    const dx = camp.x - pa.x, dy = camp.y - pa.y;
    const d = Math.hypot(dx, dy) || 1;
    pa.x = clamp(pa.x + dx / d * 200, 40, Campaign.WORLD.w - 40);
    pa.y = clamp(pa.y + dy / d * 200, 40, Campaign.WORLD.h - 40);
    pa.dest = null;
    for (const a of campaign.armies) if (a.faction !== 'player') { pa.avoid[a.id] = TUNE.retreatCooldown; a.avoid[pa.id] = TUNE.retreatCooldown; }
  }

  // Victory loot.
  if (o.victory && o.enemyDead > 0) {
    o.loot = { crowns: 8 + o.enemyDead * 3 };
    campaign.resources.crowns += o.loot.crowns;
  }

  Campaign.removeDead(campaign);
  campaign.pendingEncounter = false;
  Campaign.saveCampaign(campaign);
  return o.loot;
}

function concludeBattle() {
  const r = battle.result;
  const meta = battleMeta;
  const pa = Campaign.playerArmy(campaign);

  const pcas = Campaign.applyCasualties(campaign, meta.allPlayerSoldiers || collectBattleSoldiers(true), r.playerFallen, r.victory, rng);
  Campaign.applyCasualties(campaign, collectBattleSoldiers(false), r.enemyFallen, !r.victory, rng);

  const loot = finishAftermath({
    victory: r.victory, withdrew: r.withdrew,
    enemyArmy: meta.enemyArmy, loc: meta.loc, assault: meta.assault, defense: meta.defense,
    playerDead: pcas.dead.length, playerWounded: pcas.wounded.length,
    enemyDead: r.enemyFallen.size,
    survivors: [...r.playerSurvivors, ...r.enemySurvivors],
  });

  const promotable = pa.soldiers.filter(s => s.alive && promotionOptions(s, Campaign.hasFoundryAccess(campaign)).length > 0).length;
  const notables = r.playerSurvivors
    .filter(s => s.type !== 'hero' && (s.kills >= 3 || isVeteran(s)))
    .sort((a, b) => b.kills - a.kills)
    .slice(0, 2)
    .map(s => ({ name: s.name, type: s.type, battles: s.battles, kills: s.kills, promotable: promotionOptions(s, Campaign.hasFoundryAccess(campaign)).length > 0 }));

  sfx(r.victory ? 'victory' : 'defeat');
  UI.showBattleResult({
    victory: r.victory, withdrew: r.withdrew,
    entered: battle.startCounts.player,
    killed: pcas.dead.length,
    wounded: pcas.wounded.length,
    ready: fitForDuty(pa.soldiers).length,
    enemyKilled: r.enemyFallen.size,
    promotable, notables, loot,
    locLine: meta.loc ? `${meta.loc.name}` : null,
  }, () => enterStrategic(false));
}

function collectBattleSoldiers(player) {
  return battle.units.filter(u => u.player === player).map(u => u.soldier);
}

// ---------------------------------------------------------------- input

function screenMouse(e) {
  const r = canvas.getBoundingClientRect();
  return { x: (e.clientX - r.left) * dpr, y: (e.clientY - r.top) * dpr };
}

canvas.addEventListener('mousedown', (e) => {
  initAudio(); resumeAudio();
  const m = screenMouse(e);
  if (e.button === 1) { mouse.mmb = true; e.preventDefault(); return; }
  if (e.button === 0) {
    mouse.down = true; mouse.downX = m.x; mouse.downY = m.y; mouse.dragging = false;
    mouse.pressOnCanvas = true;
  }
});

canvas.addEventListener('mousemove', (e) => {
  const m = screenMouse(e);
  if (mouse.mmb) {
    cam.pan((mouse.x - m.x), (mouse.y - m.y));
  }
  if (mouse.down && dist(m.x, m.y, mouse.downX, mouse.downY) > 6 * dpr) {
    mouse.dragging = true;
    if (mode === 'battle') boxSel = { x0: mouse.downX, y0: mouse.downY, x1: m.x, y1: m.y };
  }
  mouse.x = m.x; mouse.y = m.y;
});

window.addEventListener('mouseup', (e) => {
  if (e.button === 1) { mouse.mmb = false; return; }
  if (e.button !== 0) return;
  const wasDragging = mouse.dragging;
  const onCanvas = mouse.pressOnCanvas;
  mouse.down = false; mouse.dragging = false; mouse.pressOnCanvas = false;
  // A click that began on a HUD button is that button's business, not an order.
  if (!onCanvas) { boxSel = null; return; }
  if (UI.isDialogOpen()) { boxSel = null; return; }

  if (mode === 'strategic') {
    if (!wasDragging) strategicLeftClick();
  } else if (mode === 'battle') {
    if (wasDragging && boxSel) {
      const a = cam.toWorld(boxSel.x0, boxSel.y0);
      const b = cam.toWorld(boxSel.x1, boxSel.y1);
      Battle.selectBox(battle, a.x, a.y, b.x, b.y, keys['shift']);
      if (battle.selection.size > 0) sfx('click');
    } else if (!wasDragging) {
      battleLeftClick();
    }
    boxSel = null;
  }
});

canvas.addEventListener('contextmenu', (e) => {
  e.preventDefault();
  initAudio(); resumeAudio();
  if (UI.isDialogOpen()) return;
  const m = screenMouse(e);
  const w = cam.toWorld(m.x, m.y);
  if (mode === 'strategic') strategicRightClick(w);
  else if (mode === 'battle') battleRightClick(w);
});

canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  const m = screenMouse(e);
  cam.zoomAt(m.x, m.y, e.deltaY < 0 ? 1.12 : 0.89);
}, { passive: false });

window.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;
  const k = e.key.toLowerCase();
  keys[k] = true;
  if (k === 'shift') keys['shift'] = true;
  if (k === 'control') keys['ctrl'] = true;
  initAudio(); resumeAudio();

  if (k === 'h') UI.toggleHelp();
  if (k === 'm') toggleMusic();
  if (k === '`') devMode = !devMode;

  if (mode === 'strategic') {
    if (k === ' ') { e.preventDefault(); api.setSpeed(campaign.speed === 0 ? 1 : 0); }
  } else if (mode === 'battle' && battle) {
    if (k === 'escape') { battle.selection.clear(); attackArmed = false; }
    if (k === 'f1') { e.preventDefault(); selectHeroAndCenter(); }
    if (k === 'r') api.rally();
    if (k === 'a' && !heroSolo()) attackArmed = true;
    if (/^[1-4]$/.test(k)) {
      if (keys['ctrl']) { Battle.setGroup(battle, k); sfx('click'); }
      else { Battle.recallGroup(battle, k); if (battle.selection.size > 0) sfx('click'); }
      e.preventDefault();
    }
  }
});

// Losing focus with a key held would otherwise leave it stuck down forever.
window.addEventListener('blur', () => {
  for (const k of Object.keys(keys)) keys[k] = false;
  attackArmed = false;
  mouse.down = false; mouse.dragging = false; mouse.mmb = false; mouse.pressOnCanvas = false;
  boxSel = null;
});

window.addEventListener('keyup', (e) => {
  const k = e.key.toLowerCase();
  keys[k] = false;
  if (k === 'shift') keys['shift'] = false;
  if (k === 'control') keys['ctrl'] = false;
  if (k === 'a') attackArmed = false;
});

function heroSolo() {
  if (!battle) return false;
  const h = Battle.heroUnit(battle);
  return h && battle.selection.size === 1 && battle.selection.has(h.uid);
}

function selectHeroAndCenter() {
  const h = Battle.heroUnit(battle);
  if (!h || h.state === 'dead') return;
  battle.selection.clear();
  battle.selection.add(h.uid);
  cam.centerOn(h.x, h.y);
  sfx('click');
}

function strategicLeftClick() {
  const w = cam.toWorld(mouse.x, mouse.y);
  const pa = Campaign.playerArmy(campaign);
  if (pa && dist(w.x, w.y, pa.x, pa.y) < 40) {
    selectedArmy = pa;
    sfx('click');
    return;
  }
  // clicking a location centers the view on it
  for (const loc of campaign.locations) {
    if (dist(w.x, w.y, loc.x, loc.y) < 55) { cam.centerOn(loc.x, loc.y); return; }
  }
  selectedArmy = pa; // player army stays selected; there is only one field army
}

function strategicRightClick(w) {
  const pa = Campaign.playerArmy(campaign);
  if (!pa) return;
  // snap to a location if clicked near one
  let dest = { x: clamp(w.x, 20, Campaign.WORLD.w - 20), y: clamp(w.y, 20, Campaign.WORLD.h - 20) };
  for (const loc of campaign.locations) {
    if (dist(w.x, w.y, loc.x, loc.y) < 60) { dest = { x: loc.x, y: loc.y }; break; }
  }
  pa.dest = dest;
  sfx('order');
  if (campaign.tutorial.step === 0) campaign.tutorial.step = 1;
}

function battleLeftClick() {
  const w = cam.toWorld(mouse.x, mouse.y);
  if (attackArmed) {
    const t = Battle.unitAt(battle, w.x, w.y, 16);
    if (t && !t.player) Battle.commandAttack(battle, t);
    else Battle.commandMove(battle, w.x, w.y, true);
    attackArmed = false;
    sfx('order');
    return;
  }
  const u = Battle.unitAt(battle, w.x, w.y, 16);
  const now = performance.now();
  if (u && u.player) {
    if (now - lastClickT < 350 && lastClickUid === u.uid) {
      Battle.selectSameType(battle, u);
    } else {
      Battle.selectOne(battle, u, keys['shift']);
    }
    sfx('click');
  } else if (!keys['shift']) {
    battle.selection.clear();
  }
  lastClickT = now; lastClickUid = u ? u.uid : -1;
}

function battleRightClick(w) {
  const t = Battle.unitAt(battle, w.x, w.y, 16);
  if (t && !t.player) {
    if (Battle.commandAttack(battle, t)) sfx('order');
  } else {
    if (Battle.commandMove(battle, w.x, w.y, false)) sfx('order');
  }
}

// ---------------------------------------------------------------- camera panning

function updateCamera(dt) {
  const pan = 520 * dt * dpr;
  const edge = 14 * dpr;
  let dx = 0, dy = 0;
  if (keys['arrowleft']) dx -= pan;
  if (keys['arrowright']) dx += pan;
  if (keys['arrowup']) dy -= pan;
  if (keys['arrowdown']) dy += pan;
  // WASD pans unless the commander is under direct control. In battle, `A` is
  // the attack-move modifier, so it never doubles as a camera key there.
  if (!(mode === 'battle' && heroSolo())) {
    if (keys['a'] && mode !== 'battle') dx -= pan;
    if (keys['d']) dx += pan;
    if (keys['w']) dy -= pan;
    if (keys['s']) dy += pan;
  }
  // edge pan (only when the window has focus and mouse is inside)
  if (mouse.x > 0 && mouse.y > 0) {
    if (mouse.x < edge) dx -= pan;
    if (mouse.x > canvas.width - edge) dx += pan;
    if (mouse.y < edge && mouse.y > 44 * dpr) dy -= pan;
    if (mouse.y > canvas.height - edge) dy += pan;
  }
  if (dx || dy) cam.pan(dx, dy);
}

// ---------------------------------------------------------------- main loop

let lastT = performance.now();
function frame(now) {
  const rawDt = Math.min(0.05, (now - lastT) / 1000);
  lastT = now;
  fpsAcc += rawDt; fpsN++;
  if (fpsAcc > 0.5) { fps = Math.round(fpsN / fpsAcc); fpsAcc = 0; fpsN = 0; }

  const time = now / 1000;

  if (mode === 'strategic' && campaign) {
    updateCamera(rawDt);
    const simDt = UI.isDialogOpen() || campaign.pendingEncounter ? 0 : rawDt * campaign.speed;
    if (simDt > 0) {
      const events = Strategic.update(campaign, simDt, rng);
      onStrategicEvents(events);
      autosaveT += simDt;
      if (autosaveT > 30) { autosaveT = 0; Campaign.saveCampaign(campaign); }
    }
    if (campaign.victory && !campaign.victoryShown && !UI.isDialogOpen()) {
      campaign.victoryShown = true;
      sfx('victory');
      UI.showVictoryDialog(campaign);
      Campaign.saveCampaign(campaign);
    }
    const pa = Campaign.playerArmy(campaign);
    selectedArmy = pa;
    let nearbyLoc = null;
    if (pa) {
      for (const loc of campaign.locations) {
        if (dist(pa.x, pa.y, loc.x, loc.y) < 90) { nearbyLoc = loc; break; }
      }
    }
    renderStrategic(ctx, cam, campaign, selectedArmy, time);
    UI.updateTopbar(campaign);
    UI.drainAlerts(campaign);
    UI.updateContextPanel(campaign, selectedArmy, nearbyLoc);
    UI.updateTutor(campaign, 'strategic');
  } else if (mode === 'battle' && battle) {
    updateCamera(rawDt);
    if (!UI.isDialogOpen()) Battle.updateBattle(battle, rawDt, keys);
    consumeEffects(battle);
    consumeEffectsAudio(battle.effects);
    battle.effects.length = 0;
    renderBattle(ctx, cam, battle, rawDt, time, boxSel);
    UI.updateBattleHud(battle, Battle.aliveUnits(battle, true).length, Battle.aliveUnits(battle, false).length, Battle.selectedUnits(battle));
    if (battle.state === 'ended' && !resultShown) {
      resultShown = true;
      concludeBattle();
    }
  }

  if (devMode) drawDev();
  else removeDev();

  requestAnimationFrame(frame);
}

function drawDev() {
  let el = document.getElementById('devbar');
  if (!el) {
    el = document.createElement('div');
    el.id = 'devbar';
    document.getElementById('app').appendChild(el);
  }
  const lines = [`fps ${fps}`, `mode ${mode}`];
  if (campaign) lines.push(`armies ${campaign.armies.length} t=${campaign.time.toFixed(0)}`);
  if (battle) lines.push(`units ${battle.units.length} proj ${battle.projectiles.length}`);
  el.textContent = lines.join('\n');
}
function removeDev() {
  const el = document.getElementById('devbar');
  if (el) el.remove();
}

// ---------------------------------------------------------------- save on exit

window.addEventListener('beforeunload', () => {
  if (campaign && mode === 'strategic') Campaign.saveCampaign(campaign);
});

// ---------------------------------------------------------------- debug/test API

window.SW = {
  get mode() { return mode; },
  get campaign() { return campaign; },
  get battle() { return battle; },
  get cam() { return cam; },
  get dpr() { return dpr; },
  api,
  Campaign, Battle, Strategic, UI, UNIT_TYPES,
  giveResources(crowns = 200, provisions = 50, coal = 50) {
    campaign.resources.crowns += crowns;
    campaign.resources.provisions += provisions;
    campaign.resources.coal += coal;
  },
  teleport(x, y) {
    const pa = Campaign.playerArmy(campaign);
    pa.x = x; pa.y = y; pa.dest = null;
  },
  forceBattle(terrain = 'open', enemyCount = 8) {
    const enemySoldiers = [];
    const r2 = makeRng(42);
    for (let i = 0; i < enemyCount; i++) {
      const t = i % 3 === 0 ? 'bowman' : i % 3 === 1 ? 'levy' : 'spearman';
      enemySoldiers.push({ id: 900000 + i, name: `Test Foe ${i}`, type: t, faction: 'bandit', xp: 0, kills: 0, battles: 0, wounded: 0, alive: true });
    }
    const pa = Campaign.playerArmy(campaign);
    const bctx = {
      playerSoldiers: [...pa.soldiers], enemySoldiers, terrain,
      defending: false, enemyFaction: 'bandit', locName: null, seed: 42,
    };
    campaign.pendingEncounter = true;
    enterBattle(bctx, { enemyArmy: null, loc: null, assault: false, defense: false });
  },
  winBattle() {
    if (!battle) return;
    for (const u of battle.units) if (!u.player && u.state !== 'dead' && u.state !== 'fled') {
      u.hp = 0; u.state = 'dead'; u.deadT = 0;
      battle.result = null;
    }
  },
  save() { return Campaign.saveCampaign(campaign); },
  load() { api.continueCampaign(); },
  screenshotReady() { return mode !== 'menu'; },
};

// ---------------------------------------------------------------- boot

UI.setScreen('menu', Campaign.hasSave());
requestAnimationFrame(frame);

// Campaign state: the persistent world. Locations, armies, soldiers, resources,
// production, save/load. The strategic simulation itself lives in strategic.js.

import { TUNE, LOC_TYPES, UNIT_TYPES, FACTIONS, OBJECTIVE, SAVE_KEY, SAVE_VERSION, PROMO_COST } from './data.js';
import { makeRng, uid, bumpUid, peekUid, segDist, dist } from './util.js';
import { makeSoldier, fitForDuty, applyPromotion } from './soldiers.js';

// ---------------------------------------------------------------- world geometry

export const WORLD = {
  w: 2600, h: 1700,
  riverWidth: 74,
  river: [
    { x: 1290, y: 0 }, { x: 1330, y: 300 }, { x: 1300, y: 560 }, { x: 1340, y: 830 },
    { x: 1390, y: 1100 }, { x: 1350, y: 1400 }, { x: 1380, y: 1700 },
  ],
  bridge: { x: 1340, y: 830 },
  roads: [
    // west trunk road: camp → market → bridge → coal → Brennan Keep
    [{ x: 240, y: 900 }, { x: 520, y: 860 }, { x: 820, y: 780 }, { x: 1100, y: 800 }, { x: 1340, y: 830 },
     { x: 1520, y: 940 }, { x: 1650, y: 1080 }, { x: 1950, y: 1230 }, { x: 2200, y: 1350 }],
    // bridge → foundry → Falkmoor Keep
    [{ x: 1340, y: 830 }, { x: 1560, y: 720 }, { x: 1780, y: 640 }, { x: 2000, y: 480 }, { x: 2180, y: 320 }],
    // market → Thornfield → watch → toll fort → Falkmoor Keep
    [{ x: 820, y: 780 }, { x: 700, y: 560 }, { x: 620, y: 380 }, { x: 860, y: 380 }, { x: 1080, y: 420 },
     { x: 1320, y: 350 }, { x: 1560, y: 300 }, { x: 1880, y: 300 }, { x: 2180, y: 320 }],
    // Merren hamlet spur
    [{ x: 520, y: 1050 }, { x: 520, y: 860 }],
  ],
  forests: [
    { x: 330, y: 480, r: 210 }, { x: 560, y: 620, r: 130 }, { x: 950, y: 190, r: 170 },
    { x: 1120, y: 1180, r: 160 }, { x: 900, y: 1350, r: 190 }, { x: 1700, y: 180, r: 130 },
    { x: 2050, y: 900, r: 150 }, { x: 1550, y: 1350, r: 120 },
  ],
  farms: [
    { x: 470, y: 1120, r: 120 }, { x: 680, y: 320, r: 110 }, { x: 760, y: 880, r: 100 },
    { x: 2260, y: 1250, r: 130 },
  ],
  hills: [
    { x: 1080, y: 420, r: 150 }, { x: 1650, y: 1010, r: 130 }, { x: 2320, y: 600, r: 180 },
    { x: 180, y: 210, r: 160 },
  ],
};

const LOC_DEFS = [
  { key: 'camp', type: 'camp', name: 'Wayside Camp', x: 240, y: 900, owner: 'player' },
  { key: 'merren', type: 'hamlet', name: 'Merren Hamlet', x: 520, y: 1050, owner: 'neutral' },
  { key: 'thornfield', type: 'hamlet', name: 'Thornfield Hamlet', x: 620, y: 380, owner: 'neutral' },
  { key: 'market', type: 'market', name: 'Millbrook Market', x: 820, y: 780, owner: 'neutral' },
  { key: 'watch', type: 'watch', name: 'Crowhill Watch', x: 1080, y: 420, owner: 'neutral' },
  { key: 'bridgefort', type: 'fort', name: 'Stone Bridge Fort', x: 1340, y: 830, owner: 'neutral' },
  { key: 'coal', type: 'coal', name: 'Hollowhill Coal Workings', x: 1650, y: 1080, owner: 'neutral' },
  { key: 'foundry', type: 'foundry', name: 'Carden Foundry', x: 1780, y: 640, owner: 'neutral' },
  { key: 'tollfort', type: 'fort', name: 'Toll Gate Fort', x: 1560, y: 300, owner: 'falkmoor' },
  { key: 'keepF', type: 'keep', name: 'Falkmoor Keep', x: 2180, y: 320, owner: 'falkmoor' },
  { key: 'keepB', type: 'keep', name: 'Brennan Keep', x: 2200, y: 1350, owner: 'brennan' },
];

// ---------------------------------------------------------------- terrain queries

export function nearRoad(x, y, radius = 30) {
  for (const road of WORLD.roads) {
    for (let i = 0; i < road.length - 1; i++) {
      if (segDist(x, y, road[i].x, road[i].y, road[i + 1].x, road[i + 1].y) < radius) return true;
    }
  }
  return false;
}

export function inForest(x, y) {
  return WORLD.forests.some(f => dist(x, y, f.x, f.y) < f.r);
}

export function onRiver(x, y) {
  if (dist(x, y, WORLD.bridge.x, WORLD.bridge.y) < 70) return false; // the crossing
  const r = WORLD.river;
  for (let i = 0; i < r.length - 1; i++) {
    if (segDist(x, y, r[i].x, r[i].y, r[i + 1].x, r[i + 1].y) < WORLD.riverWidth / 2 + 8) return true;
  }
  return false;
}

export function terrainSpeed(x, y) {
  if (onRiver(x, y)) return TUNE.riverPenalty;
  if (nearRoad(x, y)) return TUNE.roadBonus;
  if (inForest(x, y)) return TUNE.forestPenalty;
  return 1;
}

// What kind of battlefield does a fight at (x, y) produce?
export function battleTerrainAt(campaign, x, y) {
  for (const loc of campaign.locations) {
    if (dist(x, y, loc.x, loc.y) < 95) {
      if (loc.type === 'fort' || loc.type === 'keep') return loc.key === 'bridgefort' ? 'bridge' : 'fort';
      if (loc.type === 'coal' || loc.type === 'foundry') return 'industrial';
      if (loc.type === 'hamlet' || loc.type === 'market' || loc.type === 'camp') return 'settlement';
      if (loc.type === 'watch') return 'open';
    }
  }
  if (dist(x, y, WORLD.bridge.x, WORLD.bridge.y) < 150) return 'bridge';
  if (inForest(x, y)) return 'forest';
  return 'open';
}

// ---------------------------------------------------------------- campaign creation

function makeArmy(faction, x, y, soldiers, opts = {}) {
  return {
    id: uid(), faction, x, y,
    dest: null,            // {x, y} movement order
    soldiers,              // persistent soldier records
    hero: !!opts.hero,
    ai: opts.ai || null,   // { mode, targetKey, thinkT, homeKey }
    avoid: {},             // armyId -> cooldown seconds (post-retreat truce)
    speedMul: opts.speedMul || 1,
  };
}

function troopSet(rng, faction, spec) {
  // spec: e.g. { levy: 3, bowman: 1 }
  const out = [];
  for (const [type, n] of Object.entries(spec)) {
    for (let i = 0; i < n; i++) out.push(makeSoldier(type, faction, rng));
  }
  return out;
}

export function newCampaign(seed = (Date.now() % 100000) | 0) {
  const rng = makeRng(seed);
  const c = {
    version: SAVE_VERSION,
    seed,
    time: 0,
    speed: 1,
    paused: false,
    resources: { crowns: 60, provisions: 14, coal: 0 },
    locations: LOC_DEFS.map(d => ({
      ...d,
      garrison: [],
      captureProgress: 0,   // 0..1, and who is capturing
      capturingFaction: null,
    })),
    armies: [],
    alerts: [],             // consumed by UI each frame
    incomeT: 0,
    aiSpawnT: { falkmoor: 60, brennan: 75, bandit: 40 },
    victory: false,
    victoryShown: false,
    heroName: 'Captain Edda Harrow',
    tutorial: { step: 0, done: false },
    stats: { battles: 0, won: 0, lost: 0, captured: 0 },
    rngState: seed,
  };

  // Player warband: the commander and five soldiers.
  const hero = makeSoldier('hero', 'player', rng);
  hero.name = c.heroName;
  const warband = [hero, ...troopSet(rng, 'player', { levy: 3, spearman: 1, bowman: 1 })];
  c.armies.push(makeArmy('player', 240, 940, warband, { hero: true }));

  // Rival powers: garrisons + patrols.
  const locG = (key, spec) => { byKey(c, key).garrison = troopSet(rng, byKey(c, key).owner, spec); };
  locG('keepF', { spearman: 3, bowman: 3, shieldman: 2 });
  locG('tollfort', { levy: 2, spearman: 2, bowman: 1 });
  locG('keepB', { spearman: 3, bowman: 2, shieldman: 3 });

  // Independent sites keep their own watch, so expansion has to be earned.
  // Merren stays open as the player's first, free lesson in taking ground.
  locG('thornfield', { levy: 1 });
  locG('market', { levy: 2 });
  locG('watch', { levy: 1, bowman: 1 });
  locG('coal', { levy: 2 });
  locG('foundry', { levy: 2, bowman: 1 });
  locG('bridgefort', { levy: 2, spearman: 1, bowman: 1 });

  c.armies.push(makeArmy('falkmoor', 1700, 520, troopSet(rng, 'falkmoor', { levy: 2, spearman: 2, bowman: 2 }),
    { ai: { mode: 'patrol', targetKey: null, thinkT: rng.float(1, 4), homeKey: 'keepF' } }));
  c.armies.push(makeArmy('falkmoor', 1400, 340, troopSet(rng, 'falkmoor', { levy: 2, spearman: 1, bowman: 1 }),
    { ai: { mode: 'patrol', targetKey: null, thinkT: rng.float(2, 6), homeKey: 'tollfort' } }));
  c.armies.push(makeArmy('brennan', 1750, 1180, troopSet(rng, 'brennan', { levy: 2, spearman: 2, bowman: 2 }),
    { ai: { mode: 'patrol', targetKey: null, thinkT: rng.float(1, 4), homeKey: 'keepB' } }));
  c.armies.push(makeArmy('brennan', 1500, 1050, troopSet(rng, 'brennan', { levy: 1, spearman: 2, bowman: 1 }),
    { ai: { mode: 'patrol', targetKey: null, thinkT: rng.float(2, 6), homeKey: 'keepB' } }));

  // Tollmen: deserters and coal thieves working the roads.
  c.armies.push(makeArmy('bandit', 640, 950, troopSet(rng, 'bandit', { levy: 3, bowman: 1 }),
    { ai: { mode: 'patrol', targetKey: null, thinkT: 2, homeKey: null } }));
  c.armies.push(makeArmy('bandit', 1150, 1050, troopSet(rng, 'bandit', { levy: 4, bowman: 2 }),
    { ai: { mode: 'patrol', targetKey: null, thinkT: 5, homeKey: null } }));

  c.uidHigh = peekUid();
  return c;
}

// ---------------------------------------------------------------- lookups

export const byKey = (c, key) => c.locations.find(l => l.key === key);
export const playerArmy = (c) => c.armies.find(a => a.faction === 'player' && a.hero);
export const factionOf = (thing) => FACTIONS[thing.faction || thing.owner] || FACTIONS.neutral;

export function hasFoundryAccess(c) {
  return c.locations.some(l => l.type === 'foundry' && l.owner === 'player');
}

export function playerSight(c) {
  // Points from which the player can identify enemy forces.
  const pts = [];
  for (const a of c.armies) if (a.faction === 'player') pts.push({ x: a.x, y: a.y, r: TUNE.sightBase });
  for (const l of c.locations) if (l.owner === 'player') pts.push({ x: l.x, y: l.y, r: LOC_TYPES[l.type].sight });
  return pts;
}

export function isSpotted(c, x, y) {
  return playerSight(c).some(p => dist(x, y, p.x, p.y) < p.r);
}

// ---------------------------------------------------------------- player actions

export function canAfford(c, cost) {
  if (!cost) return true;
  return (cost.crowns || 0) <= c.resources.crowns &&
         (cost.provisions || 0) <= c.resources.provisions &&
         (cost.coal || 0) <= c.resources.coal;
}

export function pay(c, cost) {
  if (!cost) return;
  c.resources.crowns -= cost.crowns || 0;
  c.resources.provisions -= cost.provisions || 0;
  c.resources.coal -= cost.coal || 0;
}

export function recruitAt(c, loc, type, rng) {
  const def = UNIT_TYPES[type];
  if (!def || !def.cost) return null;
  if (!canAfford(c, def.cost)) return null;
  pay(c, def.cost);
  const s = makeSoldier(type, 'player', rng);
  const army = playerArmy(c);
  army.soldiers.push(s);
  c.uidHigh = peekUid();
  return s;
}

export function transferToGarrison(c, loc, count) {
  const army = playerArmy(c);
  const cap = LOC_TYPES[loc.type].garrisonCap;
  const movable = army.soldiers.filter(s => s.type !== 'hero' && s.alive);
  let moved = 0;
  // Move least-experienced soldiers first: veterans stay with the field army.
  movable.sort((a, b) => a.xp - b.xp);
  for (const s of movable) {
    if (moved >= count || loc.garrison.length >= cap) break;
    army.soldiers.splice(army.soldiers.indexOf(s), 1);
    loc.garrison.push(s);
    moved++;
  }
  return moved;
}

export function takeFromGarrison(c, loc, count) {
  const army = playerArmy(c);
  let moved = 0;
  while (moved < count && loc.garrison.length > 0) {
    army.soldiers.push(loc.garrison.pop());
    moved++;
  }
  return moved;
}

export function healAllWounded(c) {
  // Market-town surgeons: pay per wounded soldier for instant recovery.
  const wounded = [];
  const army = playerArmy(c);
  for (const s of army.soldiers) if (s.wounded > 0) wounded.push(s);
  for (const l of c.locations) if (l.owner === 'player') for (const s of l.garrison) if (s.wounded > 0) wounded.push(s);
  const cost = wounded.length * 5;
  if (wounded.length === 0 || c.resources.crowns < cost) return 0;
  c.resources.crowns -= cost;
  for (const s of wounded) s.wounded = 0;
  return wounded.length;
}

export function promoteSoldier(c, s, to) {
  const cost = PROMO_COST[to];
  if (!canAfford(c, cost)) return false;
  if (cost.needsFoundry && !hasFoundryAccess(c)) return false;
  pay(c, cost);
  applyPromotion(s, to);
  return true;
}

// ---------------------------------------------------------------- ticks

export function incomeTick(c) {
  const gained = { crowns: 0, provisions: 0, coal: 0 };
  for (const loc of c.locations) {
    if (loc.owner !== 'player') continue;
    const prod = LOC_TYPES[loc.type].production;
    for (const [k, v] of Object.entries(prod)) gained[k] += v;
  }
  c.resources.crowns += gained.crowns;
  c.resources.provisions += gained.provisions;
  c.resources.coal += gained.coal;
  return gained;
}

export function recoveryTick(c, dt) {
  const heal = (s) => { if (s.wounded > 0) s.wounded = Math.max(0, s.wounded - dt); };
  for (const a of c.armies) a.soldiers.forEach(heal);
  for (const l of c.locations) l.garrison.forEach(heal);
}

export function checkObjective(c) {
  if (c.victory) return false;
  const done = OBJECTIVE.locKeys.every(k => byKey(c, k).owner === 'player');
  if (done) c.victory = true;
  return done;
}

// ---------------------------------------------------------------- battle aftermath

// result: { winner: 'player'|'enemy'|'draw', playerFallen:[soldier], enemyArmy, ... }
export function applyCasualties(c, soldiers, fallenIds, won, rng) {
  // Returns {dead:[], wounded:[]} among the given persistent records.
  const dead = [], wounded = [];
  const share = won ? TUNE.woundedShareWin : TUNE.woundedShareLoss;
  for (const s of soldiers) {
    if (!fallenIds.has(s.id)) continue;
    if (s.type !== 'hero' && rng.chance(share)) {
      s.wounded = TUNE.woundRecovery;
      wounded.push(s);
    } else if (s.type === 'hero') {
      // The commander is battered but survives — losing the hero ends the run's story, not the run.
      s.wounded = TUNE.woundRecovery / 2;
      wounded.push(s);
    } else {
      s.alive = false;
      dead.push(s);
    }
  }
  return { dead, wounded };
}

export function removeDead(c) {
  for (const a of c.armies) a.soldiers = a.soldiers.filter(s => s.alive);
  for (const l of c.locations) l.garrison = l.garrison.filter(s => s.alive);
  // AI warbands with nobody fit to fight scatter rather than limping around.
  c.armies = c.armies.filter(a => a.faction === 'player' ||
    a.soldiers.some(s => s.alive && s.wounded <= 0));
}

// ---------------------------------------------------------------- save / load

export function saveCampaign(c) {
  try {
    c.uidHigh = peekUid();
    localStorage.setItem(SAVE_KEY, JSON.stringify(c));
    return true;
  } catch (e) {
    console.error('save failed', e);
    return false;
  }
}

export function loadCampaign() {
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    if (!raw) return null;
    const c = JSON.parse(raw);
    if (!c || c.version !== SAVE_VERSION) return null;
    if (!Array.isArray(c.armies) || !Array.isArray(c.locations)) return null;
    if (!c.armies.some(a => a.faction === 'player' && a.hero)) return null;
    bumpUid(c.uidHigh || 1);
    c.alerts = [];
    c.paused = false;
    if (!c.speed) c.speed = 1;
    c.pendingEncounter = false;
    return c;
  } catch (e) {
    console.error('load failed', e);
    return null;
  }
}

export function hasSave() {
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    if (!raw) return false;
    const c = JSON.parse(raw);
    return !!c && c.version === SAVE_VERSION;
  } catch { return false; }
}

export function clearSave() {
  try { localStorage.removeItem(SAVE_KEY); } catch { /* private mode */ }
}

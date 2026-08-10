// Strategic simulation: army movement, enemy AI, captures, encounters, alerts.
// update() advances the world and returns events for main.js to act on
// (encounters that need the tactical layer, victory, etc).

import { TUNE, LOC_TYPES, FACTIONS } from './data.js';
import { WORLD, byKey, playerArmy, terrainSpeed, isSpotted, incomeTick, recoveryTick, checkObjective, applyCasualties, removeDead } from './campaign.js';
import { armyPower, fitForDuty, makeSoldier } from './soldiers.js';
import { dist, clamp, uid } from './util.js';

const hostile = (a, b) => a !== b && a !== 'neutral' && b !== 'neutral';

function alert(c, text, sub, kind = 'info', throttleKey = null, throttleSec = 30) {
  if (throttleKey) {
    c._alertT = c._alertT || {};
    if ((c._alertT[throttleKey] || -999) > c.time - throttleSec) return;
    c._alertT[throttleKey] = c.time;
  }
  c.alerts.push({ text, sub, kind });
}

// ---------------------------------------------------------------- auto-resolve

// Abstract battle used for AI-vs-AI fights, unwatched garrison defenses,
// and the player's AUTO RESOLVE choice. Casualties land on real soldier records.
export function autoResolve(c, atkSoldiers, defSoldiers, defBonus, rng) {
  const atkP = armyPower(fitForDuty(atkSoldiers)) * rng.float(0.85, 1.15);
  const defP = armyPower(fitForDuty(defSoldiers)) * defBonus * rng.float(0.85, 1.15);
  const total = atkP + defP || 1;
  const atkWins = atkP > defP;
  // Loser suffers heavily; winner proportionally to how close it was.
  const winRatio = Math.min(atkP, defP) / Math.max(atkP, defP || 1);
  const loserLossRate = clamp(0.55 + 0.4 * winRatio, 0, 0.95);
  const winnerLossRate = clamp(0.45 * winRatio, 0, 0.6);
  const fallen = new Set();
  const rollLosses = (soldiers, rate) => {
    for (const s of fitForDuty(soldiers)) {
      if (s.type === 'hero') continue; // hero survival handled by applyCasualties
      if (rng.chance(rate)) fallen.add(s.id);
    }
  };
  rollLosses(atkSoldiers, atkWins ? winnerLossRate : loserLossRate);
  rollLosses(defSoldiers, atkWins ? loserLossRate : winnerLossRate);
  // Hero can "fall" in a lost auto-resolve (becomes wounded, never dies).
  const heroes = [...atkSoldiers, ...defSoldiers].filter(s => s.type === 'hero');
  for (const h of heroes) {
    const onLosingSide = atkWins ? defSoldiers.includes(h) : atkSoldiers.includes(h);
    if (onLosingSide && rng.chance(0.5)) fallen.add(h.id);
  }
  return { atkWins, fallen, atkP, defP };
}

function applyAutoResolveSide(c, soldiers, fallen, won, rng) {
  return applyCasualties(c, soldiers, fallen, won, rng);
}

// ---------------------------------------------------------------- AI thinking

const POWER_HOMES = { falkmoor: 'keepF', brennan: 'keepB' };
const OPS_RADIUS = 1500;

function aiCandidates(c, army) {
  const home = army.ai.homeKey ? byKey(c, army.ai.homeKey) : null;
  const myPower = armyPower(fitForDuty(army.soldiers));
  const out = [];
  for (const loc of c.locations) {
    if (loc.owner === army.faction) continue;
    if (home && dist(loc.x, loc.y, home.x, home.y) > OPS_RADIUS) continue;
    if (army.faction === 'bandit' && (loc.type === 'fort' || loc.type === 'keep')) continue;
    const defP = armyPower(fitForDuty(loc.garrison)) * LOC_TYPES[loc.type].defense;
    // Attack only when clearly stronger; prefer valuable and weakly-held places.
    if (defP > myPower * 0.8) continue;
    let score = 100 - dist(army.x, army.y, loc.x, loc.y) * 0.05;
    if (loc.owner === 'player') score += 35;                    // pressure the newcomer
    if (loc.type === 'coal' || loc.type === 'foundry') score += 25;
    if (loc.type === 'fort') score += 10;
    if (loc.garrison.length === 0) score += 20;
    out.push({ loc, score });
  }
  out.sort((a, b) => b.score - a.score);
  return out;
}

function aiThink(c, army, rng) {
  const ai = army.ai;
  ai.thinkT = rng.float(4, 8);
  const myPower = armyPower(fitForDuty(army.soldiers));

  // Flee from a clearly stronger hostile force nearby.
  for (const other of c.armies) {
    if (!hostile(army.faction, other.faction)) continue;
    if (dist(army.x, army.y, other.x, other.y) > 300) continue;
    const theirPower = armyPower(fitForDuty(other.soldiers));
    if (theirPower > myPower * 1.6) {
      ai.mode = 'retreat';
      const dx = army.x - other.x, dy = army.y - other.y;
      const d = Math.hypot(dx, dy) || 1;
      army.dest = {
        x: clamp(army.x + dx / d * 420, 40, WORLD.w - 40),
        y: clamp(army.y + dy / d * 420, 40, WORLD.h - 40),
      };
      return;
    }
  }

  // Defend own threatened locations.
  if (army.faction !== 'bandit') {
    for (const loc of c.locations) {
      if (loc.owner !== army.faction) continue;
      for (const other of c.armies) {
        if (!hostile(army.faction, other.faction)) continue;
        if (dist(loc.x, loc.y, other.x, other.y) < 260 &&
            armyPower(fitForDuty(other.soldiers)) > armyPower(fitForDuty(loc.garrison))) {
          ai.mode = 'defend';
          ai.targetKey = loc.key;
          army.dest = { x: loc.x, y: loc.y };
          return;
        }
      }
    }
  }

  // Pick a target worth taking.
  const cands = aiCandidates(c, army);
  if (cands.length > 0 && rng.chance(0.75)) {
    ai.mode = 'capture';
    ai.targetKey = cands[0].loc.key;
    army.dest = { x: cands[0].loc.x, y: cands[0].loc.y };
    return;
  }

  // Otherwise patrol: drift between own/nearby roads and holdings.
  ai.mode = 'patrol';
  ai.targetKey = null;
  const own = c.locations.filter(l => l.owner === army.faction);
  if (own.length > 0 && rng.chance(0.6)) {
    const l = rng.pick(own);
    army.dest = { x: l.x + rng.float(-60, 60), y: l.y + rng.float(-60, 60) };
  } else {
    army.dest = {
      x: clamp(army.x + rng.float(-320, 320), 60, WORLD.w - 60),
      y: clamp(army.y + rng.float(-320, 320), 60, WORLD.h - 60),
    };
  }
}

// ---------------------------------------------------------------- capture logic

function tryCapture(c, army, events, rng) {
  for (const loc of c.locations) {
    if (dist(army.x, army.y, loc.x, loc.y) > 62) continue;
    if (loc.owner === army.faction) continue;

    const defenders = fitForDuty(loc.garrison);
    if (defenders.length > 0 && hostile(army.faction, loc.owner)) {
      // Garrison stands: fight for the location.
      if (army.faction === 'player') {
        // Player attacks a garrisoned location — main.js turns this into a battle choice.
        if (!c.pendingEncounter) {
          c.pendingEncounter = true;
          events.push({ type: 'assault', army, loc });
        }
      } else if (loc.owner === 'player') {
        const pa = playerArmy(c);
        const playerPresent = pa && dist(pa.x, pa.y, loc.x, loc.y) < 140 && fitForDuty(pa.soldiers).length > 0;
        if (playerPresent) {
          if (!c.pendingEncounter) {
            c.pendingEncounter = true;
            events.push({ type: 'defense', army, loc, withArmy: true });
          }
        } else {
          // Unwatched garrison defense resolves abstractly.
          const res = autoResolve(c, army.soldiers, loc.garrison, LOC_TYPES[loc.type].defense, rng);
          applyAutoResolveSide(c, army.soldiers, res.fallen, res.atkWins, rng);
          applyAutoResolveSide(c, loc.garrison, res.fallen, !res.atkWins, rng);
          removeDead(c);
          if (res.atkWins) {
            loc.owner = army.faction;
            loc.garrison = loc.garrison.filter(s => s.alive);
            alert(c, `${loc.name.toUpperCase()} LOST`, `${FACTIONS[army.faction].name} stormed the garrison`, 'threat');
          } else {
            alert(c, `${loc.name.toUpperCase()} HELD`, `The garrison drove off ${FACTIONS[army.faction].name}`, 'good');
          }
        }
      } else {
        // AI vs AI/neutral garrison: abstract fight.
        const res = autoResolve(c, army.soldiers, loc.garrison, LOC_TYPES[loc.type].defense, rng);
        applyAutoResolveSide(c, army.soldiers, res.fallen, res.atkWins, rng);
        applyAutoResolveSide(c, loc.garrison, res.fallen, !res.atkWins, rng);
        removeDead(c);
        if (res.atkWins) loc.owner = army.faction;
      }
      continue;
    }

    // Undefended: timed occupation.
    if (loc.capturingFaction !== army.faction) {
      loc.capturingFaction = army.faction;
      loc.captureProgress = 0;
    }
    loc.captureProgress += (1 / TUNE.captureTime) * c._dt;
    if (loc.captureProgress >= 1) {
      const wasOwner = loc.owner;
      loc.owner = army.faction;
      loc.captureProgress = 0;
      loc.capturingFaction = null;
      loc.garrison = loc.garrison.filter(s => s.faction === army.faction);
      if (army.faction === 'player') {
        c.stats.captured++;
        alert(c, `${loc.name.toUpperCase()} TAKEN`, LOC_TYPES[loc.type].desc, 'good');
        if (loc.type === 'foundry') alert(c, 'PRESSURE EQUIPMENT AVAILABLE', 'The foundry can outfit steam-assisted troops', 'good');
        if (c.tutorial.step === 2) c.tutorial.step = 3;
        events.push({ type: 'captured', loc });
      } else if (wasOwner === 'player') {
        alert(c, `${loc.name.toUpperCase()} LOST`, `${FACTIONS[army.faction].name} took it unopposed`, 'threat');
      } else if (isSpotted(c, loc.x, loc.y)) {
        alert(c, `${loc.name.toUpperCase()} SEIZED`, `${FACTIONS[army.faction].name} raised their banner`, 'info', 'seize' + loc.key, 60);
      }
      // AI leaves a small garrison behind.
      if (army.faction !== 'player' && army.soldiers.length > 4) {
        const n = Math.min(2, army.soldiers.length - 3);
        for (let i = 0; i < n; i++) loc.garrison.push(army.soldiers.pop());
      }
    }
  }
}

// ---------------------------------------------------------------- main update

export function update(c, dt, rng) {
  const events = [];
  c._dt = dt;
  c.time += dt;

  // Income.
  c.incomeT += dt;
  if (c.incomeT >= TUNE.incomeInterval) {
    c.incomeT -= TUNE.incomeInterval;
    incomeTick(c);
  }
  recoveryTick(c, dt);

  // Army movement.
  for (const a of c.armies) {
    for (const k of Object.keys(a.avoid)) {
      a.avoid[k] -= dt;
      if (a.avoid[k] <= 0) delete a.avoid[k];
    }
    if (!a.dest) continue;
    const d = dist(a.x, a.y, a.dest.x, a.dest.y);
    if (d < 6) { a.dest = null; continue; }
    const sp = TUNE.strategicSpeed * terrainSpeed(a.x, a.y) * (a.speedMul || 1);
    const step = Math.min(d, sp * dt);
    a.x += (a.dest.x - a.x) / d * step;
    a.y += (a.dest.y - a.y) / d * step;
  }

  // AI thinking (staggered).
  for (const a of c.armies) {
    if (!a.ai) continue;
    a.ai.thinkT -= dt;
    if (a.ai.thinkT <= 0) aiThink(c, a, rng);
  }

  // Captures / assaults.
  for (const a of c.armies) tryCapture(c, a, events, rng);

  // Army-vs-army contact.
  const pa = playerArmy(c);
  for (let i = 0; i < c.armies.length; i++) {
    for (let j = i + 1; j < c.armies.length; j++) {
      const A = c.armies[i], B = c.armies[j];
      if (!hostile(A.faction, B.faction)) continue;
      if (A.avoid[B.id] || B.avoid[A.id]) continue;
      if (dist(A.x, A.y, B.x, B.y) > TUNE.encounterRadius) continue;
      const involvesPlayer = A === pa || B === pa;
      if (involvesPlayer) {
        const enemy = A === pa ? B : A;
        if (!c.pendingEncounter && fitForDuty(pa.soldiers).length > 0 && fitForDuty(enemy.soldiers).length > 0) {
          c.pendingEncounter = true;
          events.push({ type: 'encounter', army: pa, enemy });
        }
      } else {
        // AI skirmish: abstract resolution, loser scatters.
        const res = autoResolve(c, A.soldiers, B.soldiers, 1, rng);
        applyAutoResolveSide(c, A.soldiers, res.fallen, res.atkWins, rng);
        applyAutoResolveSide(c, B.soldiers, res.fallen, !res.atkWins, rng);
        removeDead(c);
        A.avoid[B.id] = TUNE.retreatCooldown;
        B.avoid[A.id] = TUNE.retreatCooldown;
        if (isSpotted(c, A.x, A.y)) {
          alert(c, 'SKIRMISH ON THE ROADS', `${FACTIONS[A.faction].name} clashed with ${FACTIONS[B.faction].name}`, 'info', 'aiskirmish', 45);
        }
      }
    }
  }

  // Threat warnings: hostile forces bearing down on player holdings.
  for (const loc of c.locations) {
    if (loc.owner !== 'player') continue;
    if (pa && dist(pa.x, pa.y, loc.x, loc.y) < 150) continue; // the company is right there
    for (const a of c.armies) {
      if (!hostile(a.faction, 'player') || !a.ai) continue;
      if (a.ai.targetKey === loc.key && dist(a.x, a.y, loc.x, loc.y) < 520) {
        const est = fitForDuty(a.soldiers).length;
        alert(c, `${loc.name.toUpperCase()} THREATENED`,
          `Garrison: ${fitForDuty(loc.garrison).length} — enemy estimate: ${est}`,
          'threat', 'threat' + loc.key, 26);
      }
    }
  }

  // AI reinforcement waves keep the world dangerous.
  for (const fac of ['falkmoor', 'brennan', 'bandit']) {
    c.aiSpawnT[fac] -= dt;
    if (c.aiSpawnT[fac] > 0) continue;
    c.aiSpawnT[fac] = fac === 'bandit' ? 150 : 130;
    const count = c.armies.filter(a => a.faction === fac).length;
    const cap = fac === 'bandit' ? 2 : 3;
    if (count >= cap) continue;
    const size = Math.min(4 + Math.floor(c.time / 160), 9);
    const soldiers = [];
    for (let i = 0; i < size; i++) {
      const roll = rng.raw();
      const type = fac === 'bandit'
        ? (roll < 0.7 ? 'levy' : 'bowman')
        : (roll < 0.4 ? 'levy' : roll < 0.65 ? 'spearman' : roll < 0.85 ? 'bowman' : 'shieldman');
      soldiers.push(makeSoldier(type, fac, rng));
    }
    // Late game: powers field pressure bowmen of their own.
    if (fac !== 'bandit' && c.time > 500 && rng.chance(0.5)) soldiers.push(makeSoldier('pressurebow', fac, rng));
    let x, y;
    if (fac === 'bandit') {
      const spot = rng.pick([{ x: 100, y: 1500 }, { x: 900, y: 80 }, { x: 2500, y: 800 }]);
      x = spot.x; y = spot.y;
    } else {
      const home = byKey(c, POWER_HOMES[fac]);
      x = home.x + rng.float(-40, 40); y = home.y + rng.float(-40, 40);
    }
    c.armies.push({
      id: uid(), faction: fac, x, y, dest: null,
      soldiers, hero: false, avoid: {},
      ai: { mode: 'patrol', targetKey: null, thinkT: rng.float(1, 3), homeKey: POWER_HOMES[fac] || null },
    });
  }

  // Objective.
  if (checkObjective(c)) events.push({ type: 'victory' });

  return events;
}

// Player retreats from an encounter: fall back and buy a truce window.
export function retreatFrom(c, enemy) {
  const pa = playerArmy(c);
  const camp = byKey(c, 'camp');
  const dx = camp.x - pa.x, dy = camp.y - pa.y;
  const d = Math.hypot(dx, dy) || 1;
  pa.x += dx / d * 120;
  pa.y += dy / d * 120;
  pa.dest = null;
  pa.avoid[enemy.id] = TUNE.retreatCooldown;
  enemy.avoid[pa.id] = TUNE.retreatCooldown;
  c.resources.provisions = Math.max(0, c.resources.provisions - 3);
  c.pendingEncounter = false;
}

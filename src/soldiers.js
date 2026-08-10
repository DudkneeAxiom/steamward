// Persistent soldier records. Every fighter on a battlefield maps back to one of these.

import { UNIT_TYPES, TUNE, PROMOTIONS, PROMO_COST } from './data.js';
import { uid } from './util.js';
import { soldierName } from './names.js';

export function makeSoldier(type, faction, rng) {
  return {
    id: uid(),
    name: soldierName(rng),
    type,
    faction,
    xp: 0,
    kills: 0,
    battles: 0,
    wounded: 0,      // seconds of recovery remaining; 0 = fit for duty
    alive: true,
  };
}

export const isVeteran = (s) => s.battles >= TUNE.vetBattles;

// Abstract combat weight used by auto-resolve and threat estimates.
export function soldierPower(s) {
  const t = UNIT_TYPES[s.type];
  let p = (t.hp / 10) + t.meleeDmg + (t.rangedDmg ? t.rangedDmg * 0.9 : 0) + t.armor * 3;
  if (s.type === 'hero') p *= 1.6;
  if (isVeteran(s)) p *= 1.2;
  return p;
}

export function armyPower(soldiers) {
  return soldiers.reduce((sum, s) => sum + soldierPower(s), 0);
}

export function fitForDuty(soldiers) {
  return soldiers.filter(s => s.alive && s.wounded <= 0);
}

export function promotionOptions(s, hasFoundry) {
  if (s.type === 'hero' || s.xp < TUNE.promoXp) return [];
  const opts = PROMOTIONS[s.type] || [];
  return opts.map(to => {
    const cost = PROMO_COST[to];
    return { to, cost, locked: !!cost.needsFoundry && !hasFoundry };
  });
}

export function applyPromotion(s, to) {
  s.type = to;
  s.xp = Math.max(0, s.xp - TUNE.promoXp);
}

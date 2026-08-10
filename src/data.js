// Central design data: units, promotions, locations, factions, tuning constants.

export const TUNE = {
  // strategic
  strategicSpeed: 46,        // base army px/sec on the strategic map
  roadBonus: 1.6,
  forestPenalty: 0.62,
  riverPenalty: 0.22,        // fording is possible but brutal — the bridge matters
  sightBase: 330,            // how far player forces identify enemy strength/intent
  captureTime: 3.5,          // seconds to take an undefended location
  incomeInterval: 8,         // seconds between production ticks
  woundRecovery: 110,        // seconds for a wounded soldier to return to duty
  encounterRadius: 46,
  retreatCooldown: 14,       // seconds an army ignores the enemy it fled from
  // battle
  battleW: 1980,
  battleH: 1380,
  cell: 30,                  // pathfinding grid cell size
  vetBattles: 3,
  xpKill: 8,
  xpSurvive: 10,
  promoXp: 26,
  woundedShareWin: 0.5,      // share of fallen player troops that are wounded, not dead
  woundedShareLoss: 0.25,
};

export const UNIT_TYPES = {
  hero: {
    name: 'Commander', role: 'Warband commander',
    hp: 240, armor: 3, speed: 88, meleeDmg: 20, meleeRate: 0.9, range: 0,
    moraleBase: 100, mass: 1.4, radius: 9,
    cost: null, desc: 'Rallying presence steadies nearby soldiers. Not a superhero — keep the line around them.',
  },
  levy: {
    name: 'Levy', role: 'Cheap general infantry',
    hp: 55, armor: 0, speed: 62, meleeDmg: 8, meleeRate: 1.1, range: 0,
    moraleBase: 42, mass: 1, radius: 7,
    cost: { crowns: 15, provisions: 2 }, desc: 'Farmhands with spears and hatchets. They hold if led well.',
  },
  spearman: {
    name: 'Levy Spearman', role: 'Anti-cavalry line infantry',
    hp: 72, armor: 1, speed: 58, meleeDmg: 11, meleeRate: 1.1, range: 0,
    moraleBase: 55, mass: 1.05, radius: 7, vsCavalry: 2.4,
    cost: { crowns: 28, provisions: 3 }, desc: 'Braced spears punish mounted charges.',
  },
  shieldman: {
    name: 'Shieldman', role: 'Durable frontline',
    hp: 98, armor: 3, speed: 50, meleeDmg: 9, meleeRate: 1.2, range: 0,
    moraleBase: 65, mass: 1.25, radius: 8, shieldBlock: 0.62,
    cost: { crowns: 34, provisions: 3 }, desc: 'Heavy boards and steady nerves. Endures arrow-fall.',
  },
  bowman: {
    name: 'Bowman', role: 'Traditional ranged',
    hp: 46, armor: 0, speed: 60, meleeDmg: 4, meleeRate: 1.3,
    range: 265, rangedDmg: 11, reload: 2.3, projSpeed: 260, projArc: 1,
    moraleBase: 45, mass: 0.95, radius: 7,
    cost: { crowns: 30, provisions: 3 }, desc: 'Longbows behind the line. Fragile up close.',
  },
  pressurebow: {
    name: 'Pressure Bowman', role: 'Steam-assisted archery',
    hp: 52, armor: 1, speed: 54, meleeDmg: 5, meleeRate: 1.3,
    range: 350, rangedDmg: 30, reload: 4.4, projSpeed: 460, projArc: 0.35, pierce: true,
    moraleBase: 58, mass: 1.05, radius: 7, industrial: true, steamShot: true,
    cost: { crowns: 40, coal: 8 },
    desc: 'A draw-carriage and pressure reservoir throw heavy bolts flat and hard. Slow between shots.',
  },
  rider: {
    name: 'Mounted Scout', role: 'Fast flanker',
    hp: 82, armor: 1, speed: 122, meleeDmg: 12, meleeRate: 1.0, range: 0,
    moraleBase: 55, mass: 1.6, radius: 10, cavalry: true, chargeDmg: 18,
    cost: { crowns: 55, provisions: 5 }, desc: 'Light horse. Ruin archers, avoid spears.',
  },
  boilerlancer: {
    name: 'Boiler Lancer', role: 'Pressure-assisted heavy cavalry',
    hp: 135, armor: 3, speed: 104, meleeDmg: 15, meleeRate: 1.15, range: 0,
    moraleBase: 70, mass: 2.2, radius: 11, cavalry: true, chargeDmg: 44, industrial: true,
    cost: { crowns: 70, coal: 14 },
    desc: 'Piston-braced lance and a back boiler drive a devastating charge. Weaker in the grind.',
  },
};

// Promotion tree. Industrial promotions demand foundry access + coal.
export const PROMOTIONS = {
  levy: ['spearman', 'bowman', 'shieldman'],
  bowman: ['pressurebow'],
  rider: ['boilerlancer'],
};
export const PROMO_COST = {
  spearman: { crowns: 15 },
  bowman: { crowns: 15 },
  shieldman: { crowns: 18 },
  pressurebow: { crowns: 40, coal: 8, needsFoundry: true },
  boilerlancer: { crowns: 70, coal: 14, needsFoundry: true },
};

export const FACTIONS = {
  player: { name: "Harrow's Company", short: 'HARROW', color: '#4e8a5c', dark: '#2c5236', banner: '#c9a959' },
  falkmoor: { name: 'House Falkmoor', short: 'FALKMOOR', color: '#a03a2c', dark: '#5e2018', banner: '#d8b25a' },
  brennan: { name: 'The Brennan Compact', short: 'BRENNAN', color: '#4a6f96', dark: '#2a4058', banner: '#b8c4ce' },
  bandit: { name: 'Tollmen', short: 'TOLLMEN', color: '#7a6a4a', dark: '#463c28', banner: '#54462e' },
  neutral: { name: 'Independent', short: 'FREE', color: '#8a8578', dark: '#4d4a42', banner: '#8a8578' },
};

export const LOC_TYPES = {
  camp: {
    label: 'CAMP', desc: 'Company muster ground',
    production: { provisions: 1 }, recruits: ['levy'], garrisonCap: 10, defense: 1.1, sight: 330,
  },
  hamlet: {
    label: 'HAMLET', desc: 'Recruits and provisions',
    production: { provisions: 2, crowns: 1 }, recruits: ['levy'], garrisonCap: 8, defense: 1.0, sight: 260,
  },
  market: {
    label: 'MARKET TOWN', desc: 'Recruitment, trade, healing',
    production: { crowns: 5 }, recruits: ['levy', 'spearman', 'bowman', 'shieldman', 'rider'],
    garrisonCap: 12, defense: 1.15, heals: true, sight: 300,
  },
  coal: {
    label: 'COAL WORKINGS', desc: 'Coal for pressure equipment',
    production: { coal: 3 }, recruits: [], garrisonCap: 8, defense: 1.0, sight: 260,
  },
  foundry: {
    label: 'FOUNDRY', desc: 'Advanced equipment and upgrades',
    production: { coal: 1, crowns: 2 }, recruits: [], garrisonCap: 10, defense: 1.2, foundry: true, sight: 280,
  },
  watch: {
    label: 'WATCH STATION', desc: 'Extends strategic sight',
    production: {}, recruits: [], garrisonCap: 6, defense: 1.2, sight: 620,
  },
  fort: {
    label: 'ROAD FORT', desc: 'Route control, strong garrison',
    production: { crowns: 1 }, recruits: [], garrisonCap: 15, defense: 1.55, sight: 340,
  },
  keep: {
    label: 'KEEP', desc: 'Seat of regional power',
    production: { crowns: 3, provisions: 2 }, recruits: ['levy', 'spearman', 'bowman'],
    garrisonCap: 20, defense: 1.8, sight: 380,
  },
};

// Battle terrain contexts keyed from strategic surroundings.
export const TERRAIN_KINDS = ['open', 'forest', 'bridge', 'settlement', 'industrial', 'fort'];

export const OBJECTIVE = {
  title: 'SEIZE THE VALE’S INDUSTRY',
  locKeys: ['foundry', 'coal', 'bridgefort'],
  text: 'Hold the Carden Foundry, the Hollowhill Coal Workings and Stone Bridge Fort at the same time.',
};

export const SAVE_KEY = 'steamward_save';
export const SAVE_VERSION = 3;

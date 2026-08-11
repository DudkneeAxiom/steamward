# STEAMWARD

A browser-based 2.5D feudal-industrial strategic + tactical RTS — a playable
vertical slice. You are **Captain Edda Harrow**, an independent commander in the
Merren Vale: a feudal land where crude steam engineering has begun to change how
wars are fought. Castles, levies and heraldic banners still rule the world;
pressure cylinders, boilers and coal are starting to decide its battles.

Command a persistent warband on a living strategic map, take territory, garrison
it, and fight every serious engagement yourself in real-time tactical battles.
Soldiers who die stay dead. Survivors carry their scars, experience and names.

## Playing

**No build step, no dependencies at runtime.** Serve the directory statically and
open it in a desktop browser:

```bash
npm run serve          # python3 -m http.server 8123
# then open http://localhost:8123
```

Any static file server works (`npx serve`, nginx, …). File://` URLs will not work
because the game uses ES modules.

### Campaign objective

Hold the **Carden Foundry**, the **Hollowhill Coal Workings** and **Stone Bridge
Fort** at the same time. After victory the campaign continues as a sandbox.

### Controls

**Strategic map**
| Input | Action |
|---|---|
| Left click | select your army / focus a location |
| Right click | move army (snaps to locations) |
| Arrows / WASD / edge / MMB drag | pan camera |
| Mouse wheel | zoom |
| Space | pause · `▶` / `▶▶` time controls in the top bar |

Stand on a neutral or enemy location to capture it. The panel in the corner
offers recruitment, garrison transfers, healing and the company roster
(promotions) when you are at a location.

**Battle**
| Input | Action |
|---|---|
| Left click / drag | select / box-select |
| Double-click | select all soldiers of that type |
| Right click | move (formation) · attack enemy |
| A + left click | attack-move |
| Ctrl+1–4 / 1–4 | set / recall control group |
| F1 | select commander and center camera |
| WASD | move the commander directly while they are the sole selection |
| R | Rally — restores morale near the commander (long cooldown) |
| Esc | deselect |
| LINE / DEEP / LOOSE | formation for the next move order |

`H` opens the controls overlay anywhere. `M` toggles music. `` ` `` toggles a
small dev/perf overlay.

## Systems

### Strategic layer
- One handcrafted region: 11 locations (hamlets, market town, coal workings,
  foundry, watch station, road forts, two rival keeps) joined by roads, with a
  river whose only fast crossing is the Stone Bridge.
- Three resources: **Crowns**, **Provisions**, **Coal**. Owned locations produce
  on a tick; coal + a foundry gate the steam-assisted troops.
- Garrisons are real soldiers subtracted from your field army. Expansion
  reduces concentrated strength — that tension is the game.
- Two rival powers (**House Falkmoor**, **the Brennan Compact**) and roaming
  **Tollmen** raiders act independently: they patrol, capture neutral ground,
  reinforce, defend, retreat from superior forces, and prey on weak garrisons.
  Undefended holdings will be taken while you are elsewhere.
- Sight matters: unidentified enemy columns show as `?` markers until a force
  or holding (watch stations see furthest) can identify them.

### Tactical layer
- Hostile contact opens an encounter: **Fight**, **Auto-resolve**, or
  **Retreat** (costs provisions; not possible when defending a holding).
- Battlefields reflect the strategic terrain: open field, forest, the bridge
  chokepoint, settlement lanes, industrial yards (boilers, carts, spoil heaps),
  fort walls with a gate.
- Exactly the soldiers present on the map fight — field army plus the local
  garrison when defending. Casualties, XP, kills and veteran status persist.
- Classic RTS controls (box select, control groups, attack-move, formations),
  lightweight morale (proximity to the commander steadies troops; casualties,
  rout cascades and being badly outnumbered break them), physical projectiles,
  cavalry charges, spear counters, shield arrow-block.
- The commander fights as a unit: rally ability, morale aura, direct WASD
  control when solo-selected. Losing the commander wounds them for a while —
  it never hard-ends the campaign.

### Progression
- XP from kills and surviving battles. At 26 XP soldiers can be promoted:
  Levy → Spearman / Bowman / Shieldman; Bowman → **Pressure Bowman**;
  Mounted Scout → **Boiler Lancer** (industrial promotions need a foundry
  under your banner plus coal).
- The **Pressure Bowman** is the signature unit: a steam-assisted draw carriage
  throws heavy bolts flat, far and armor-piercing, at a slow cadence — archery
  transformed by engineering, not a firearm.
- Notable survivors surface after battles by name, with kills and battles.

### Persistence
Auto-saves to `localStorage` (after battles, captures, and every ~30s), with
**CONTINUE** / **RESET SAVE** on the main menu. The save format is versioned and
validated; corrupted or outdated saves are ignored safely.

## Architecture

Vanilla JavaScript ES modules + a single Canvas 2D renderer. No frameworks.

```
index.html, style.css      shell + DOM UI skin
src/main.js                game loop, mode transitions, input, battle aftermath
src/data.js                all design data: units, promotions, factions, tuning
src/campaign.js            world geometry, campaign state, save/load, actions
src/strategic.js           strategic sim: movement, AI, captures, encounters
src/battle.js              tactical sim: A* grid, formations, combat, morale
src/strategicRender.js     map rendering (2.5D diorama projection)
src/battleRender.js        battlefield rendering, particles
src/sprites.js             voxel atlas loading and blitting
src/camera.js              shared squashed-Y camera
src/ui.js                  panels, dialogs, alerts, battle HUD
src/soldiers.js            persistent soldier records, XP, promotions
src/audio.js               fully procedural WebAudio SFX, ambience and score
src/names.js, src/util.js  naming, math, seeded RNG
assets/                    generated sprite atlases (checked in)
tools/blender/             the Blender scripts that generate them
```

The 2.5D look comes from a Y-squashed camera (`y × 0.68`) with upright sprites,
painter's-algorithm depth sort and per-entity height offsets. Battles run on a
coarse A* grid with line-of-sight path smoothing plus local separation forces;
unit AI updates are staggered and neighbor queries use a spatial hash, so 40v40
stays comfortably within frame budget.

## Art pipeline

Every soldier, building and prop is a voxel model built from cubes in Blender
and pre-rendered to sprite atlases — the canvas only paints ground, water,
roads, effects and UI.

```bash
python3.11 -m venv .bpyenv && .bpyenv/bin/pip install bpy pillow
tools/blender/render.sh            # rebuilds assets/ (~40s)
tools/blender/render.sh units      # troops only
```

- `tools/blender/models.py` — the models. Each is a stack of `box()` calls, so
  editing a unit means moving blocks, not editing a mesh.
- `tools/blender/lib.py` — the camera rig, palette and render settings. The
  orthographic camera is set to exactly match the game's projection
  (`tan(elevation) = 0.68`, pixel aspect `cos(elevation)`), so a rendered frame
  drops onto the map with no fudge factors: sprites are anchored at the frame
  centre, which is the model's origin.
- Troops render 8 facings × 3 poses (stand + two walk frames) per type, once
  per faction, so faction colour is baked rather than tinted at runtime.
- Frame sizes and collision footprints are measured from the geometry at render
  time and written into `assets/props.json`, so growing a model never clips its
  sprite and the game's obstacles always match what you see.

The generated atlases are committed, so the game runs without Blender; you only
need it to change the art.

## Tests

```bash
npm install            # dev-only: @playwright/test (pinned to the bundled browser)
npm test
```

`tests/acceptance.spec.js` drives the full campaign loop with real mouse/keyboard
input: new campaign → move → recruit → capture → garrison → staged encounter →
battle (box select, move/attack orders, F1 + WASD) → casualty persistence →
territory persistence → enemy activity → promotion → save → reload → second
battle → reset. `tests/smoke.spec.js` checks a clean boot with zero console
errors. `window.SW` exposes a debug API used by the tests (and a hidden dev mode
in game via `` ` ``).

## Deployment

The game is fully static. For itch.io: zip `index.html`, `style.css` and `src/`
and upload as an HTML5 game with `index.html` as the entry point (SharedArrayBuffer
not required; any frame size ≥ 1100×700 plays well). For any other static host,
copy those same files.

## Known limitations

- One field army (plus garrisons) — no subordinate detachments yet.
- Reinforcements do not arrive mid-battle; a garrison fights alongside the field
  army only if the army is at the location when the attack lands.
- Enemy powers do not besiege each other's keeps in earnest; their war shows up
  as road skirmishes and grabs for the middle of the map.
- Auto-resolve is intentionally rougher on you than a well-fought manual battle.
- Audio is procedural and minimal by design; there is no volume slider yet
  (`M` toggles music).

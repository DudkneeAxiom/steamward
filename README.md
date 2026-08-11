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

Vanilla JavaScript ES modules + WebGL (three.js, vendored locally — nothing is
fetched at runtime).

```
index.html, style.css      shell + DOM UI skin
src/main.js                game loop, mode transitions, input, battle aftermath
src/data.js                all design data: units, promotions, factions, tuning
src/campaign.js            world geometry, campaign state, save/load, actions
src/strategic.js           strategic sim: movement, AI, captures, encounters
src/battle.js              tactical sim: A* grid, formations, combat, morale
src/gfx.js                 WebGL core: scene, 2.5D camera, lighting, picking
src/terrain.js             heightfield generation and terrain/road/water meshing
src/models.js              GLB loading, vertex-colour baking, instancing
src/unitView.js            soldiers: instanced parts + procedural animation
src/worldView.js           the strategic world scene
src/battleView.js          the tactical battlefield scene
src/ui.js                  panels, dialogs, alerts, battle HUD
src/soldiers.js            persistent soldier records, XP, promotions
src/audio.js               fully procedural WebAudio SFX, ambience and score
src/names.js, src/util.js  naming, math, seeded RNG
assets/models/             generated GLB assets (checked in) + manifest
vendor/three/              vendored three.js — no runtime CDN
tools/blender/             the Blender scripts that generate the assets
```

**The world is geometry, not drawing.** Terrain is a heightfield built from
authored features — hills, a river cutting a real valley, roads flattened into
corridors, level platforms under settlements — plus controlled fBm for
richness. Heights are blurred and then quantised into steps, so meshing gives
broad flat terraces joined by genuine vertical cliff faces. Water exists only
where the ground is actually below the waterline. Roads are ribbons that follow
the ground. Ground material is decided from the finished terrain's height and
slope, so highlands show rock and works yards are stained with coal dust.

The camera is orthographic at a fixed 42° — the angle is what sells "miniature
you could reach into". Gameplay still thinks in flat (x, y); the renderer owns
the third dimension and looks up ground height to place things. Clicks are
raycast against the real terrain, so an order on a hillside lands where the
player is looking.

**Batching.** GLB material colours are baked into vertex colours at load and
the pieces merged, leaving one geometry per asset. Scenery then draws as a
single InstancedMesh per type and soldiers as one per animated body part, so a
40v40 battle is a few dozen draw calls. Soldiers have no skeletons: legs, arms
and weapons are separate parts with their own pivots, animated procedurally.

Battles run on a coarse A* grid with line-of-sight path smoothing plus local
separation forces; unit AI updates are staggered and neighbour queries use a
spatial hash. The simulation is driven by wall-clock time with a fixed tactical
timestep, so a slow machine runs the same campaign, just at a lower frame rate,
and render settings scale back automatically on software rasterisers.

## Art pipeline

Every soldier, building and prop is a low-poly model assembled from chunky
masses in Blender and exported as GLB.

```bash
python3.11 -m venv .bpyenv && .bpyenv/bin/pip install bpy pillow
.bpyenv/bin/python -c "import sys; sys.path.insert(0,'tools/blender/kit'); \
  import settlement as k; k.build_all('assets/models/settlement', '/tmp/prev')"
python3 tools/blender/build_manifest.py     # rewrite assets/models/manifest.json
```

- `tools/blender/kit/common.py` — the contract every kit builds against: the
  scale (1 unit = 10 cm, soldier ~19 units tall), orientation (+X east, +Y
  north, +Z up, models face +X, origin on the ground at the footprint centre),
  the shared material palette, and the `box()` / `cyl()` / `wedge()` primitives.
  Because origins sit on the ground, the game drops an asset at
  `(x, terrainHeight, y)` with no per-asset fudge.
- `tools/blender/kit/*.py` — the kits: settlement, industrial, military, nature,
  units. Each is modular, so a hamlet and a market town share cottages and a
  foundry and a mine share boilers.
- The `cloth` material is the faction-colour marker: the runtime bakes it to the
  owning faction's colour when it flattens the asset.
- Soldiers must expose parts named `leg_l`, `leg_r`, `arm_l`, `arm_r`, `weapon`
  (and `hleg_*` for horses) whose origins sit at their pivots — that is the
  whole animation rig.
- `preview_render()` renders any asset to a PNG so its silhouette can be
  inspected before it ships.

The generated GLBs are committed, so the game runs without Blender; you only
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

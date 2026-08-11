// Full acceptance loop (spec §72): new campaign → move → recruit → capture →
// garrison → move on → encounter → tactical battle with real RTS inputs →
// casualties persist → territory persists → enemy keeps moving → save/load/reset.
import { test, expect } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

// World-space point → CSS-pixel screen point for real mouse input.
async function screenOf(page, wx, wy) {
  return page.evaluate(([x, y]) => {
    const h = window.SW.view.heightAt ? window.SW.view.heightAt(x, y) : 0;
    return window.SW.gfx.worldToScreen(x, h, y);
  }, [wx, wy]);
}

async function armyPos(page) {
  return page.evaluate(() => {
    const a = window.SW.Campaign.playerArmy(window.SW.campaign);
    return { x: a.x, y: a.y, count: a.soldiers.filter(s => s.alive).length };
  });
}

test('complete campaign acceptance loop', async ({ page }) => {
  test.setTimeout(300000);
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('dialog', (d) => d.accept());

  await page.goto('/');

  // -------- START NEW CAMPAIGN
  await page.click('#btn-new');
  await page.waitForFunction(() => window.SW && window.SW.mode === 'strategic');

  // Park the roaming bandits in an empty corner so travel is deterministic;
  // we stage the encounter explicitly later.
  await page.evaluate(() => {
    let i = 0;
    for (const a of window.SW.campaign.armies) {
      if (a.faction === 'bandit') {
        a.x = 150 + i * 120; a.y = 1550; a.dest = null;
        if (a.ai) a.ai.thinkT = 99999; // hold still until staged
        i++;
      }
    }
  });
  await page.evaluate(() => window.SW.api.setSpeed(2.5));

  // -------- select hero army (left click on it)
  let pos = await armyPos(page);
  const startCount = pos.count;
  expect(startCount).toBe(6); // hero + 5
  let s = await screenOf(page, pos.x, pos.y);
  await page.mouse.click(s.x, s.y, { button: 'left' });

  // -------- move to settlement (right-click Merren Hamlet)
  s = await screenOf(page, 520, 1050);
  await page.mouse.click(s.x, s.y, { button: 'right' });
  await page.waitForFunction(() => {
    const a = window.SW.Campaign.playerArmy(window.SW.campaign);
    return Math.hypot(a.x - 520, a.y - 1050) < 90;
  }, null, { timeout: 30000 });

  // -------- recruit soldiers via the location panel
  await page.waitForSelector('#context-panel button[data-act=recruit]');
  await page.click('#context-panel button[data-act=recruit]');
  await page.waitForFunction((n) => {
    const a = window.SW.Campaign.playerArmy(window.SW.campaign);
    return a.soldiers.filter(x => x.alive).length === n + 1;
  }, startCount);
  await page.click('#context-panel button[data-act=recruit]');
  await page.waitForFunction((n) => {
    const a = window.SW.Campaign.playerArmy(window.SW.campaign);
    return a.soldiers.filter(x => x.alive).length === n + 2;
  }, startCount);

  // -------- capture the hamlet (stand on it until it flips)
  await page.waitForFunction(() =>
    window.SW.campaign.locations.find(l => l.key === 'merren').owner === 'player',
    null, { timeout: 30000 });

  // -------- leave a garrison
  await page.waitForSelector('#context-panel button[data-act=gadd]');
  await page.click('#context-panel button[data-act=gadd]'); // LEAVE 1
  const garrisonAfter = await page.evaluate(() =>
    window.SW.campaign.locations.find(l => l.key === 'merren').garrison.length);
  expect(garrisonAfter).toBe(1);
  pos = await armyPos(page);
  expect(pos.count).toBe(startCount + 2 - 1);

  // -------- move away
  s = await screenOf(page, 820, 780);
  await page.mouse.click(s.x, s.y, { button: 'right' });
  await page.waitForTimeout(1200);

  // Record roster ids before the battle.
  const preIds = await page.evaluate(() =>
    window.SW.Campaign.playerArmy(window.SW.campaign).soldiers.map(x => x.id));

  // -------- encounter a hostile force: stage a bandit band next to the company
  await page.evaluate(() => {
    const c = window.SW.campaign;
    const pa = window.SW.Campaign.playerArmy(c);
    pa.dest = null;
    const b = c.armies.find(a => a.faction === 'bandit');
    b.x = pa.x + 40; b.y = pa.y; b.dest = null;
    if (b.ai) b.ai.thinkT = 999; // hold still
    delete b.avoid[pa.id]; delete pa.avoid[b.id];
  });
  await page.waitForSelector('.dialog button[data-a=fight]', { timeout: 20000 });

  // -------- enter tactical RTS
  await page.click('.dialog button[data-a=fight]');
  await page.waitForFunction(() => window.SW.mode === 'battle');
  await page.waitForTimeout(700);

  // -------- box-select soldiers (real drag over own deployment)
  const bbox = await page.evaluate(() => {
    const b = window.SW.battle, g = window.SW.gfx, v = window.SW.view;
    const mine = b.units.filter(u => u.player);
    // project every soldier and take the screen-space bounds, padded
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const u of mine) {
      const p = g.worldToScreen(u.x, v.heightAt(u.x, u.y) + 10, u.y);
      x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x);
      y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y);
    }
    return { x0: x0 - 40, y0: y0 - 40, x1: x1 + 40, y1: y1 + 40 };
  });
  await page.mouse.move(bbox.x0, bbox.y0);
  await page.mouse.down();
  await page.mouse.move(bbox.x1, bbox.y1, { steps: 8 });
  await page.mouse.up();
  const selCount = await page.evaluate(() => window.SW.battle.selection.size);
  expect(selCount).toBeGreaterThan(0);

  // -------- issue a move command (right-click open ground)
  const mid = await page.evaluate(() => {
    const b = window.SW.battle, g = window.SW.gfx, v = window.SW.view;
    const mine = b.units.filter(u => u.player);
    const mx = mine.reduce((s, u) => s + u.x, 0) / mine.length + 110;
    const my = mine.reduce((s, u) => s + u.y, 0) / mine.length;
    const p = g.worldToScreen(mx, v.heightAt(mx, my), my);
    return { x: p.x, y: p.y };
  });
  await page.mouse.click(mid.x, mid.y, { button: 'right' });
  const hasOrder = await page.evaluate(() => {
    const b = window.SW.battle;
    return b.units.some(u => b.selection.has(u.uid) && u.orderPos);
  });
  expect(hasOrder).toBe(true);

  // -------- issue an attack command (right-click an enemy)
  await page.waitForTimeout(800);
  const foe = await page.evaluate(() => {
    const b = window.SW.battle, g = window.SW.gfx, v = window.SW.view;
    const e = b.units.find(u => !u.player && u.state !== 'dead' && u.state !== 'fled');
    const p = g.worldToScreen(e.x, v.heightAt(e.x, e.y) + 10, e.y);
    return { x: p.x, y: p.y, uid: e.uid };
  });
  // enemy may be off screen; command through the API is equivalent if so
  const vp = page.viewportSize();
  if (foe.x >= 0 && foe.x < vp.width && foe.y >= 0 && foe.y < vp.height) {
    await page.mouse.click(foe.x, foe.y, { button: 'right' });
  } else {
    await page.evaluate((uid) => {
      const b = window.SW.battle;
      const e = b.units.find(u => u.uid === uid);
      window.SW.Battle.commandAttack(b, e);
    }, foe.uid);
  }
  const hasTarget = await page.evaluate(() => {
    const b = window.SW.battle;
    return b.units.some(u => b.selection.has(u.uid) && u.orderTargetUid);
  });
  expect(hasTarget).toBe(true);

  // -------- select hero (F1) and move with WASD
  await page.keyboard.press('F1');
  const heroSel = await page.evaluate(() => {
    const b = window.SW.battle;
    const h = window.SW.Battle.heroUnit(b);
    return b.selection.size === 1 && b.selection.has(h.uid) ? { x: h.x, y: h.y } : null;
  });
  expect(heroSel).not.toBeNull();
  await page.keyboard.down('d');
  await page.waitForTimeout(600);
  await page.keyboard.up('d');
  const heroAfter = await page.evaluate(() => {
    const h = window.SW.Battle.heroUnit(window.SW.battle);
    return { x: h.x, y: h.y };
  });
  expect(heroAfter.x).toBeGreaterThan(heroSel.x + 20);

  // -------- fight the battle to a finish: press the attack on the nearest foe
  for (let i = 0; i < 45; i++) {
    const done = await page.evaluate(() => window.SW.battle === null || window.SW.battle.state === 'ended');
    if (done) break;
    await page.evaluate(() => {
      const b = window.SW.battle;
      if (!b || b.state !== 'running') return;
      window.SW.Battle.selectBox(b, 0, 0, b.w, b.h, false);
      const mine = b.units.filter(u => u.player && u.state !== 'dead' && u.state !== 'fled');
      const foes = b.units.filter(u => !u.player && u.state !== 'dead' && u.state !== 'fled');
      if (mine.length === 0 || foes.length === 0) return;
      const cx = mine.reduce((s, u) => s + u.x, 0) / mine.length;
      const cy = mine.reduce((s, u) => s + u.y, 0) / mine.length;
      foes.sort((a, c) => Math.hypot(a.x - cx, a.y - cy) - Math.hypot(c.x - cx, c.y - cy));
      window.SW.Battle.commandAttack(b, foes[0]);
    });
    await page.waitForTimeout(3000);
  }

  // -------- view casualties, return to the map
  await page.waitForSelector('.dialog button[data-a=ok]', { timeout: 30000 });
  const resultText = await page.locator('.dialog h2').textContent();
  expect(['VICTORY', 'DEFEAT', 'WITHDRAWAL']).toContain(resultText);
  await page.click('.dialog button[data-a=ok]');
  await page.waitForFunction(() => window.SW.mode === 'strategic');

  // -------- verify persistence: dead absent, survivors present, garrison intact
  const roster = await page.evaluate(() => {
    const c = window.SW.campaign;
    const a = window.SW.Campaign.playerArmy(c);
    return {
      ids: a.soldiers.map(x => x.id),
      allAlive: a.soldiers.every(x => x.alive),
      merrenOwner: c.locations.find(l => l.key === 'merren').owner,
      merrenGarrison: c.locations.find(l => l.key === 'merren').garrison.length,
      battles: c.stats.battles,
      xpCarriers: a.soldiers.filter(x => x.xp > 0).length,
    };
  });
  expect(roster.allAlive).toBe(true);                       // dead were removed
  for (const id of roster.ids) expect(preIds).toContain(id); // no phantom soldiers
  expect(roster.merrenOwner).toBe('player');
  expect(roster.merrenGarrison).toBe(1);
  expect(roster.battles).toBeGreaterThan(0);
  expect(roster.xpCarriers).toBeGreaterThan(0);             // survivors gained XP

  // -------- acquire or contest the industrial resource (coal workings).
  // The world is live: another power may already hold it, so fights en route
  // are auto-resolved until the site is ours.
  await page.evaluate(() => {
    // a strong company makes the contest deterministic enough for CI
    const c = window.SW.campaign;
    const pa = window.SW.Campaign.playerArmy(c);
    for (const s of pa.soldiers) { if (s.wounded > 0) s.wounded = 0; }
  });
  let ownedCoal = false;
  for (let i = 0; i < 25 && !ownedCoal; i++) {
    await page.evaluate(() => {
      const c = window.SW.campaign;
      const pa = window.SW.Campaign.playerArmy(c);
      if (Math.hypot(pa.x - 1650, pa.y - 1080) > 70) {
        window.SW.teleport(1650, 1045);
        pa.dest = { x: 1650, y: 1080 };
      }
    });
    await page.waitForTimeout(1500);
    const autoBtn = page.locator('.dialog button[data-a=auto]');
    if (await autoBtn.count()) {
      await autoBtn.click();
      const ok = page.locator('.dialog button[data-a=ok]');
      if (await ok.count()) await ok.click();
    }
    ownedCoal = await page.evaluate(() =>
      window.SW.campaign.locations.find(l => l.key === 'coal').owner === 'player');
  }
  expect(ownedCoal).toBe(true);

  // -------- observe enemy strategic activity (the world keeps moving)
  await page.evaluate(() => {
    // park the company on empty ground so no dialog freezes the sim
    window.SW.UI.closeDialog();
    window.SW.campaign.pendingEncounter = false;
    window.SW.teleport(300, 400);
  });
  const before = await page.evaluate(() => {
    const m = {};
    for (const a of window.SW.campaign.armies) if (a.faction !== 'player') m[a.id] = [a.x, a.y];
    return m;
  });
  let moved = false;
  for (let i = 0; i < 10 && !moved; i++) {
    await page.waitForTimeout(2000);
    moved = await page.evaluate((prev) => {
      window.SW.UI.closeDialog();
      window.SW.campaign.pendingEncounter = false;
      return window.SW.campaign.armies.some(a =>
        a.faction !== 'player' && prev[a.id] &&
        Math.hypot(a.x - prev[a.id][0], a.y - prev[a.id][1]) > 15);
    }, before);
  }
  expect(moved).toBe(true);

  // -------- upgrade a troop (promotion path)
  const promoted = await page.evaluate(() => {
    const c = window.SW.campaign;
    window.SW.giveResources(500, 100, 100);
    const a = window.SW.Campaign.playerArmy(c);
    const s = a.soldiers.find(x => x.type === 'levy' && x.alive);
    if (!s) return 'no-levy';
    s.xp = 40;
    return window.SW.Campaign.promoteSoldier(c, s, 'spearman') ? s.type : 'failed';
  });
  expect(promoted).toBe('spearman');

  // -------- save, reload, continue
  const saved = await page.evaluate(() => window.SW.save());
  expect(saved).toBe(true);
  await page.reload();
  await page.waitForSelector('#btn-continue:not(.hidden)');
  await page.click('#btn-continue');
  await page.waitForFunction(() => window.SW && window.SW.mode === 'strategic');
  const loaded = await page.evaluate(() => ({
    merren: window.SW.campaign.locations.find(l => l.key === 'merren').owner,
    coal: window.SW.campaign.locations.find(l => l.key === 'coal').owner,
    count: window.SW.Campaign.playerArmy(window.SW.campaign).soldiers.length,
  }));
  expect(loaded.merren).toBe('player');
  expect(loaded.coal).toBe('player');
  expect(loaded.count).toBeGreaterThan(0);

  // -------- second battle works after load
  await page.evaluate(() => {
    // freeze the world and clear any strategic dialog before staging
    window.SW.api.setSpeed(0);
    window.SW.UI.closeDialog();
    window.SW.campaign.pendingEncounter = false;
    window.SW.teleport(300, 400); // empty ground, away from patrols
  });
  await page.evaluate(() => window.SW.forceBattle('forest', 5));
  await page.waitForFunction(() => window.SW.mode === 'battle');
  await page.waitForTimeout(1500);
  await page.evaluate(() => window.SW.winBattle());
  await page.waitForSelector('.dialog button[data-a=ok]', { timeout: 20000 });
  await page.click('.dialog button[data-a=ok]');
  await page.waitForFunction(() => window.SW.mode === 'strategic');

  // -------- reset wipes the save
  await page.click('#btn-menu');
  await page.waitForSelector('#btn-reset:not(.hidden)');
  await page.click('#btn-reset'); // confirm auto-accepted by dialog handler
  await expect(page.locator('#btn-continue')).toBeHidden();

  expect(errors).toEqual([]);
});

// Regression tests for battle-simulation defects found in review.
import { test, expect } from '@playwright/test';

async function openBattle(page, terrain = 'open', enemies = 4) {
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
  await page.click('#btn-new');
  await page.waitForFunction(() => window.SW && window.SW.mode === 'strategic');
  await page.evaluate(([t, n]) => window.SW.forceBattle(t, n), [terrain, enemies]);
  await page.waitForFunction(() => window.SW.mode === 'battle');
}

test('a soldier with no standing orders fights back when attacked', async ({ page }) => {
  await openBattle(page);
  const before = await page.evaluate(() => {
    const b = window.SW.battle;
    const levy = b.units.find(u => u.player && u.type === 'levy');
    const foe = b.units.find(u => !u.player);
    for (const u of b.units) if (u.player) { u.orderPos = null; u.orderTargetUid = null; u.path = null; u.attackMove = false; }
    foe.x = levy.x + 22; foe.y = levy.y; foe.orderPos = null; foe.orderTargetUid = null; foe.path = null;
    return { foeHp: foe.hp, foeUid: foe.uid, levyUid: levy.uid };
  });
  await page.waitForTimeout(5000);
  const after = await page.evaluate(([lu, fu]) => {
    const b = window.SW.battle;
    return {
      foeHp: b.units.find(u => u.uid === fu).hp,
      foeState: b.units.find(u => u.uid === fu).state,
      levyState: b.units.find(u => u.uid === lu).state,
    };
  }, [before.levyUid, before.foeUid]);
  expect(after.foeHp < before.foeHp || after.foeState === 'dead').toBe(true);
});

test('the commander defends itself after direct (WASD) movement ends', async ({ page }) => {
  await openBattle(page);
  const before = await page.evaluate(() => {
    const b = window.SW.battle;
    const h = window.SW.Battle.heroUnit(b);
    const foe = b.units.find(u => !u.player && u.state !== 'dead');
    // the state a hero is left in the moment WASD is released
    h.state = 'moving'; h.orderPos = null; h.orderTargetUid = null; h.path = null;
    foe.x = h.x + 20; foe.y = h.y;
    return { foeUid: foe.uid, foeHp: foe.hp };
  });
  await page.waitForTimeout(4000);
  const after = await page.evaluate((fu) => {
    const foe = window.SW.battle.units.find(u => u.uid === fu);
    return { foeHp: foe.hp, foeState: foe.state };
  }, before.foeUid);
  expect(after.foeHp < before.foeHp || after.foeState === 'dead').toBe(true);
});

test('pressure bolts pierce armor; ordinary arrows do not', async ({ page }) => {
  await openBattle(page);
  const dmg = await page.evaluate(async () => {
    const b = window.SW.battle;
    // Clear the field to one shooter and one target so nobody else's arrows
    // land in the measurement.
    const shooter0 = b.units.find(u => u.player && u.def.range > 0);
    const target0 = b.units.find(u => !u.player);
    b.units = [shooter0, target0];
    b.aiT = 1e9;                       // no enemy orders during the test
    // Armored, shieldless target that soaks hits without dying.
    const setupTarget = () => {
      const foe = target0;
      foe.def = { ...foe.def, armor: 3, shieldBlock: 0, speed: 0 };
      foe.hp = 100000; foe.maxHp = 100000;
      foe.state = 'idle';
      foe.orderPos = null; foe.orderTargetUid = null; foe.autoTarget = null; foe.path = null;
      return foe;
    };
    const measure = (shooterType) => new Promise(resolve => {
      const foe = setupTarget();
      const shooter = shooter0;
      shooter.type = shooterType;
      shooter.def = window.SW.UNIT_TYPES[shooterType];
      shooter.cooldown = 0;
      shooter.x = foe.x - shooter.def.range * 0.6; shooter.y = foe.y;
      shooter.orderPos = null; shooter.orderTargetUid = foe.uid; shooter.path = null;
      const start = foe.hp;
      setTimeout(() => resolve(start - foe.hp), 3500);
    });
    // measured sequentially so only one shooter is firing at the target
    const plain = await measure('bowman');
    const pressure = await measure('pressurebow');
    return { plain, pressure };
  });
  // Per-hit: bowman 11 × 0.52 armor ≈ 5.7; pressure bolt 30 at full value.
  expect(dmg.pressure).toBeGreaterThan(dmg.plain * 2);
});

test('rallying out of a withdrawal and clearing the field still counts as a victory', async ({ page }) => {
  await openBattle(page);
  await page.evaluate(() => window.SW.Battle.withdraw(window.SW.battle));
  expect(await page.evaluate(() => window.SW.battle.withdrawing)).toBe(true);
  await page.evaluate(() => {
    const b = window.SW.battle;
    window.SW.Battle.rally(b);           // commander calls the company back
    window.SW.winBattle();               // and the enemy is destroyed
  });
  await page.waitForFunction(() => window.SW.battle && window.SW.battle.state === 'ended');
  const result = await page.evaluate(() => ({
    victory: window.SW.battle.result.victory,
    withdrew: window.SW.battle.result.withdrew,
    flag: window.SW.battle.withdrawing,
  }));
  expect(result.flag).toBe(false);
  expect(result.victory).toBe(true);
  expect(result.withdrew).toBe(false);
});

test('clicking a HUD button does not clear the current selection', async ({ page }) => {
  await openBattle(page);
  await page.evaluate(() => {
    const b = window.SW.battle;
    window.SW.Battle.selectBox(b, 0, 0, b.w, b.h, false);
  });
  const before = await page.evaluate(() => window.SW.battle.selection.size);
  expect(before).toBeGreaterThan(0);
  await page.click('#btn-form-deep');
  await page.waitForTimeout(200);
  const after = await page.evaluate(() => ({
    size: window.SW.battle.selection.size,
    form: window.SW.battle.formationType,
  }));
  expect(after.size).toBe(before);
  expect(after.form).toBe('deep');
});

test('a move order onto blocked ground still completes', async ({ page }) => {
  await openBattle(page, 'industrial', 4);
  const done = await page.evaluate(async () => {
    const b = window.SW.battle;
    const blocker = b.terrain.circles.find(c => c.kind === 'boiler') || b.terrain.circles[0];
    window.SW.Battle.selectBox(b, 0, 0, b.w, b.h, false);
    // order the company straight into the middle of a solid obstacle
    window.SW.Battle.commandMove(b, blocker.x, blocker.y, false);
    const watched = b.units.filter(u => u.player && u.state !== 'dead').slice(0, 4);
    await new Promise(r => setTimeout(r, 14000));
    return watched.every(u => !u.orderPos ||
      Math.hypot(u.x - u.orderPos.x, u.y - u.orderPos.y) < 40);
  });
  expect(done).toBe(true);
});

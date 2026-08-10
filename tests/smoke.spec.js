// Smoke test: the game boots, a campaign starts, and both layers run without errors.
import { test, expect } from '@playwright/test';

test('boots to menu and starts a campaign without console errors', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto('/');
  await expect(page.locator('#mainmenu h1')).toHaveText('STEAMWARD');
  await page.click('#btn-new');
  await page.waitForFunction(() => window.SW && window.SW.mode === 'strategic');

  // let the strategic sim run a few seconds
  await page.waitForTimeout(3000);
  expect(errors).toEqual([]);

  // force a battle through the debug API and let it run
  await page.evaluate(() => window.SW.forceBattle('open', 6));
  await page.waitForFunction(() => window.SW.mode === 'battle');
  await page.waitForTimeout(4000);
  expect(errors).toEqual([]);
});

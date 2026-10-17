import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFile } from 'node:fs/promises';
async function setup(page: Page) {
  await page.goto('/');
  await page.getByLabel('Date of birth', { exact: true }).fill('2000-01-01');
  await page.getByLabel('Chosen lifespan', { exact: false }).fill('90');
  await page.getByRole('button', { name: 'See my weeks', exact: true }).click();
  await expect(page.getByTestId('lived-weeks')).toBeVisible();
}

test('setup, edit, reload, privacy and confirmed reset preserve other site data', async ({
  page,
}) => {
  await setup(page);
  const weeks = await page.getByTestId('lived-weeks').innerText();
  await page.reload();
  await expect(page.getByTestId('lived-weeks')).toHaveText(weeks);
  await page.getByRole('button', { name: 'Your calendar', exact: true }).click();
  await page.getByLabel('Chosen lifespan').fill('95');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.getByRole('button', { name: 'Privacy', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('There are no accounts');
  await page.keyboard.press('Escape');
  await page.evaluate(() => localStorage.setItem('unrelated:test', 'keep'));
  await page.getByRole('button', { name: 'Reset my calendar', exact: true }).click();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByTestId('lived-weeks')).toBeVisible();
  await page.getByRole('button', { name: 'Reset my calendar', exact: true }).click();
  await page.getByRole('button', { name: 'Yes, reset calendar', exact: true }).click();
  await expect(page.getByLabel('Date of birth', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('aion:settings'))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem('unrelated:test'))).toBe('keep');
});
test('invalid input has localized errors and focus', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'See my weeks', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('valid date');
  await expect(page.getByLabel('Date of birth', { exact: true })).toBeFocused();
  await page.getByLabel('Date of birth', { exact: true }).fill('2099-01-01');
  await page.getByRole('button', { name: 'See my weeks', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('future');
  await page.getByRole('button', { name: 'Español', exact: true }).click();
  await page.getByLabel('Fecha de nacimiento', { exact: true }).fill('2000-01-01');
  await page.getByLabel('Horizonte de vida elegido').fill('0');
  await page.getByRole('button', { name: 'Ver mis semanas', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('entero positivo');
});
test('all seven totals, ticking, pause and clock catch-up', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-17T12:00:00Z') });
  await setup(page);
  for (const unit of ['years', 'months', 'weeks', 'days', 'hours', 'minutes', 'seconds'])
    await expect(page.getByTestId(`lived-${unit}`)).toBeVisible();
  const before = await page.getByTestId('remaining-seconds').innerText();
  await page.clock.runFor(2100);
  await expect(page.getByTestId('remaining-seconds')).not.toHaveText(before);
  await page.getByRole('button', { name: 'Pause countdown', exact: false }).click();
  const paused = await page.getByTestId('remaining-seconds').innerText();
  await page.clock.runFor(5100);
  await expect(page.getByTestId('remaining-seconds')).toHaveText(paused);
  await page.clock.setSystemTime(new Date('2026-10-18T15:30:00Z'));
  await page.getByRole('button', { name: 'Resume countdown', exact: false }).click();
  await expect(page.getByTestId('remaining-seconds')).not.toHaveText(paused);
});
test('hide remaining persists, keeps grid, and omits figures from PNG export', async ({ page }) => {
  await page.addInitScript(() => {
    const original = CanvasRenderingContext2D.prototype.fillText;
    (window as unknown as { drawnText: string[] }).drawnText = [];
    CanvasRenderingContext2D.prototype.fillText = function (text, x, y, maxWidth) {
      (window as unknown as { drawnText: string[] }).drawnText.push(text);
      if (maxWidth === undefined) original.call(this, text, x, y);
      else original.call(this, text, x, y, maxWidth);
    };
  });
  await setup(page);
  await page.getByLabel('Hide remaining figures', { exact: true }).check();
  await expect(page.getByTestId('remaining-seconds')).toHaveCount(0);
  await expect(page.getByRole('img', { name: /shape of your life/ })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Hide remaining figures', { exact: true })).toBeChecked();
  await page.getByRole('button', { name: 'Export wallpaper', exact: false }).click();
  const image = page.getByRole('dialog').getByRole('img');
  await expect(image).toBeVisible();
  await expect(page.getByRole('link', { name: 'Download PNG' })).toBeVisible();
  expect(
    await image.evaluate((el: HTMLImageElement) => [el.naturalWidth, el.naturalHeight]),
  ).toEqual([1440, 2560]);
  const texts = await page.evaluate(() => (window as unknown as { drawnText: string[] }).drawnText);
  expect(texts.join(' ')).not.toContain('2000-01-01');
  expect(texts.join(' ').toLowerCase()).not.toContain('remaining');
  const pending = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download PNG' }).click();
  const download = await pending;
  const buffer = await readFile((await download.path())!);
  expect([...buffer.subarray(0, 8)]).toEqual([137, 80, 78, 71, 13, 10, 26, 10]);
  expect(buffer.readUInt32BE(16)).toBe(1440);
  await page.getByRole('button', { name: /Desktop ·/ }).click();
  await expect
    .poll(() => image.evaluate((el: HTMLImageElement) => [el.naturalWidth, el.naturalHeight]))
    .toEqual([2560, 1600]);
});
test('denied writes retain a usable session without claiming save', async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = function () {
      throw new DOMException('Denied', 'SecurityError');
    };
  });
  await setup(page);
  await expect(page.getByRole('status')).toContainText('could not save');
  await page.getByLabel('Primary summary unit').selectOption('days');
  await expect(page.getByTestId('primary-lived')).toBeVisible();
});
test('unknown storage format is preserved until explicit reset', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem('aion:settings', '{"version":2,"keep":"untouched"}'),
  );
  await setup(page);
  await expect(page.getByRole('status')).toContainText('newer format');
  expect(await page.evaluate(() => localStorage.getItem('aion:settings'))).toBe(
    '{"version":2,"keep":"untouched"}',
  );
});
test('cross-tab settings and clear events synchronize locally', async ({ page, context }) => {
  await setup(page);
  const other = await context.newPage();
  await other.goto('/');
  await expect(other.getByTestId('lived-weeks')).toBeVisible();
  await page.getByLabel('Hide remaining figures', { exact: true }).check();
  await expect(other.getByLabel('Hide remaining figures', { exact: true })).toBeChecked();
  await other.evaluate(() => localStorage.removeItem('aion:settings'));
  await expect(page.getByLabel('Date of birth', { exact: true })).toBeVisible();
  await other.close();
});
test('Spanish mobile layout and accessibility in both main states', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/es');
  await expect(page.getByRole('heading', { name: 'Una vida, en semanas.' })).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
      .violations,
  ).toEqual([]);
  await page.getByLabel('Fecha de nacimiento', { exact: true }).fill('2000-01-01');
  await page.getByRole('button', { name: 'Ver mis semanas', exact: true }).click();
  await expect(page.getByTestId('lived-seconds')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
      .violations,
  ).toEqual([]);
});
test('network contains only same-origin assets and no private input', async ({ page, baseURL }) => {
  const requests: string[] = [],
    errors: string[] = [];
  page.on('request', (request) => requests.push(request.url()));
  page.on('pageerror', (e) => errors.push(e.message));
  await setup(page);
  await page.getByRole('button', { name: 'Español', exact: true }).click();
  await page.getByRole('button', { name: 'Exportar fondo', exact: false }).click();
  await expect(page.getByRole('dialog').getByRole('img')).toBeVisible();
  expect(requests.every((url) => new URL(url).origin === new URL(baseURL!).origin)).toBe(true);
  expect(requests.join(' ')).not.toContain('2000-01-01');
  expect(requests.join(' ')).not.toContain('birthDate');
  expect(errors).toEqual([]);
});
test('loaded app remains functional offline', async ({ page, context }) => {
  await setup(page);
  await page.evaluate(() => document.fonts.ready);
  await context.setOffline(true);
  await page.getByRole('button', { name: 'Your calendar', exact: true }).click();
  await page.getByLabel('Chosen lifespan').fill('100');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await page.getByRole('button', { name: 'Export wallpaper', exact: false }).click();
  await expect(page.getByRole('dialog').getByRole('img')).toBeVisible();
  await context.setOffline(false);
});
test('past horizon clamps remaining and allows exact week exploration', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Date of birth', { exact: true }).fill('2000-01-01');
  await page.getByLabel('Chosen lifespan').fill('1');
  await page.getByRole('button', { name: 'See my weeks', exact: true }).click();
  await expect(page.getByTestId('remaining-seconds')).toHaveText('0');
  await expect(page.getByRole('status')).toContainText('story continues');
  await page.locator('summary').filter({ hasText: 'Explore a week' }).click();
  await page.getByLabel('Week block number').fill('53');
  await expect(page.locator('.interval')).toContainText('2000-12-30 → 2001-01-01');
});

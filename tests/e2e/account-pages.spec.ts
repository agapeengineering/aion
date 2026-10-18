import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.skip(process.env.AION_AUTH_TESTS !== '1', 'Requires the opt-in HTTPS account build.');
test.use({ ignoreHTTPSErrors: true, trace: 'off', screenshot: 'off', video: 'off' });
for (const es of [false, true]) {
  const prefix = es ? '/es' : '';
  test(`direct login, language switch and browser history (${es ? 'ES' : 'EN'})`, async ({
    page,
  }) => {
    let requests = 0;
    page.on('request', (r) => {
      if (new URL(r.url()).pathname.startsWith('/api/')) requests++;
    });
    await page.goto(prefix || '/');
    expect(requests).toBe(0);
    await page.getByRole('link', { name: es ? 'Cuenta' : 'Account', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${prefix}/login$`));
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(
      es ? 'Entra en Aion.' : 'Sign in to Aion.',
    );
    await expect(
      page.getByLabel(es ? 'Correo electrónico' : 'Email address', { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    if (process.env.AION_UI_REVIEW === '1' && !es)
      await page.screenshot({ path: '.local/profile-tests/login-desktop.png', fullPage: true });
    await page.getByRole('button', { name: es ? 'English' : 'Español', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${es ? '' : '/es'}/login$`));
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(es ? '/es$' : '/$'));
    await page.goForward();
    await expect(page).toHaveURL(new RegExp(`${es ? '' : '/es'}/login$`));
    await page.reload();
    await page.setViewportSize({ width: 320, height: 800 });
    await expect(
      page.getByLabel(es ? 'Email address' : 'Correo electrónico', { exact: true }),
    ).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect(
      (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
        .violations,
    ).toEqual([]);
  });
  test(`protected account resolves to login without exposing data (${es ? 'ES' : 'EN'})`, async ({
    page,
  }) => {
    await page.goto(`${prefix}/account`);
    await expect(page).toHaveURL(new RegExp(`${prefix}/login$`));
    await expect(
      page.getByLabel(es ? 'Correo electrónico' : 'Email address', { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(
      page.getByRole('button', { name: es ? 'Enviar un código' : 'Send a code', exact: true }),
    ).toBeEnabled();
  });
}

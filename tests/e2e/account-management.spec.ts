import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFile } from 'node:fs/promises';

test.skip(process.env.AION_AUTH_TESTS !== '1', 'Requires the synthetic capture-only HTTPS stack.');
test.use({ ignoreHTTPSErrors: true, trace: 'off', screenshot: 'off', video: 'off' });
const inbox = process.env.AION_INBOX_URL ?? 'http://127.0.0.1:18025';
async function codeFor(request: APIRequestContext, address: string, confirmation: boolean) {
  let code = '';
  await expect
    .poll(
      async () => {
        const data = await (await request.get(`${inbox}/api/v1/messages`)).json();
        const mail = data.messages.find(
          (m: { To: { Address: string }[]; Subject: string }) =>
            m.To.some((t) => t.Address === address) && (!confirmation || /Confirm/.test(m.Subject)),
        );
        if (!mail) return false;
        const body = await (await request.get(`${inbox}/api/v1/message/${mail.ID}`)).json();
        code = body.Text.match(/\b[0-9]{8}\b/)?.[0] ?? '';
        return Boolean(code);
      },
      { timeout: 20000 },
    )
    .toBe(true);
  return code;
}
async function login(page: Page, request: APIRequestContext, es: boolean, email: string) {
  await page.goto(es ? '/es/login' : '/login');
  await page.getByLabel(es ? 'Correo electrónico' : 'Email address', { exact: true }).fill(email);
  await page
    .getByRole('button', { name: es ? 'Enviar un código' : 'Send a code', exact: true })
    .click();
  await page
    .getByLabel(es ? 'Código de verificación' : 'Verification code', { exact: true })
    .fill(await codeFor(request, email, false));
  await page
    .getByRole('button', { name: es ? 'Verificar correo' : 'Verify email', exact: true })
    .click();
  await expect(page.getByRole('status')).toContainText(email);
}
for (const es of [false, true]) {
  test(`export, confirmed deletion, cache clearing and guest preservation (${es ? 'ES' : 'EN'})`, async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    await page.addInitScript(
      (skew) => {
        const original = Date.now.bind(Date);
        Date.now = () => original() + skew;
      },
      es ? -3600000 : 3600000,
    );
    const email = `lifecycle-${es ? 'es' : 'en'}-${Date.now()}@example.test`;
    // A separate guest calendar must survive removing the account.
    await page.goto(es ? '/es' : '/');
    await page
      .getByLabel(es ? 'Fecha de nacimiento' : 'Date of birth', { exact: true })
      .fill('2001-01-01');
    await page
      .getByRole('button', { name: es ? 'Ver mis semanas' : 'See my weeks', exact: true })
      .click();
    const guest = await page.evaluate(() => localStorage.getItem('aion:settings'));
    await login(page, request, es, email);
    const panel = page.locator('.account-management');
    await expect(
      panel.getByText(es ? 'Esta sesión' : 'This session', { exact: true }),
    ).toBeVisible();
    await page.setViewportSize({ width: 320, height: 900 });
    if (process.env.AION_VISUAL_REVIEW === '1')
      await panel.screenshot({ path: `.local/account-management/${es ? 'es' : 'en'}-mobile.png` });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect(
      (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
        .violations,
    ).toEqual([]);
    await panel
      .getByRole('button', { name: es ? 'Descargar mis datos' : 'Download my data', exact: true })
      .click();
    const confirm = panel.locator('.account-confirm');
    await confirm
      .getByRole('button', {
        name: es ? 'Enviar código de confirmación' : 'Send confirmation code',
        exact: true,
      })
      .click();
    await confirm
      .getByLabel(es ? 'Código de confirmación de cuenta' : 'Account confirmation code', {
        exact: true,
      })
      .fill(await codeFor(request, email, true));
    await confirm
      .getByRole('button', { name: es ? 'Confirmar que soy yo' : 'Confirm it’s me', exact: true })
      .click();
    const downloadEvent = page.waitForEvent('download');
    await confirm
      .getByRole('button', { name: es ? 'Descargar mis datos' : 'Download my data', exact: true })
      .click();
    const download = await downloadEvent;
    expect(download.suggestedFilename()).toBe('aion-account.json');
    const file = await download.path();
    const body = JSON.parse(await readFile(file!, 'utf8'));
    expect(body.version).toBe(1);
    expect(body.account.email === email).toBe(true);
    await page.reload();
    await expect(
      panel.getByText(es ? 'Esta sesión' : 'This session', { exact: true }),
    ).toBeVisible();
    await panel
      .getByRole('button', { name: es ? 'Eliminar cuenta' : 'Delete account', exact: true })
      .click();
    const remove = confirm.getByRole('button', {
      name: es ? 'Eliminar mi cuenta permanentemente' : 'Permanently delete my account',
      exact: true,
    });
    await expect(remove).toBeDisabled();
    await confirm
      .getByRole('checkbox', {
        name: es
          ? 'Entiendo que eliminar mi cuenta es permanente.'
          : 'I understand that deleting my account is permanent.',
        exact: true,
      })
      .check();
    await remove.click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('status')).toContainText(
      es ? 'Tu cuenta se ha eliminado.' : 'Your account has been deleted.',
    );
    expect((await request.get('/api/v1/me')).status()).toBe(401);
    expect(await page.evaluate(() => localStorage.getItem('aion:settings'))).toBe(guest);
    expect(
      await page.evaluate(
        () => Object.keys(localStorage).filter((k) => k.startsWith('aion:account')).length,
      ),
    ).toBe(0);
  });
  test(`revoke all clears this browser (${es ? 'ES' : 'EN'})`, async ({ page, request }) => {
    const email = `sessions-${es ? 'es' : 'en'}-${Date.now()}@example.test`;
    await login(page, request, es, email);
    const panel = page.locator('.account-management');
    await panel
      .getByRole('button', {
        name: es ? 'Cerrar todas las sesiones' : 'Sign out everywhere',
        exact: true,
      })
      .click();
    await panel
      .getByRole('button', {
        name: es ? 'Confirmar cierre de todas las sesiones' : 'Confirm sign out everywhere',
        exact: true,
      })
      .click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('status')).toContainText(
      es
        ? 'Se ha cerrado la sesión en todos los dispositivos.'
        : 'You have signed out of every session.',
    );
    expect((await request.get('/api/v1/me')).status()).toBe(401);
  });
}

test('deferred reminders are hidden in the account release', async ({ page, request }) => {
  test.skip(
    process.env.AION_DEFERRED_REMINDER_UI !== '1',
    'Requires a default account build without the reminder UI flag.',
  );
  await login(page, request, false, `deferred-${Date.now()}@example.test`);
  await expect(page.locator('.account-management')).toBeVisible();
  await expect(page.locator('.reminder-panel')).toHaveCount(0);
});

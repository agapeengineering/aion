import { test, expect } from '@playwright/test';

test.skip(
  process.env.AION_AUTH_TESTS !== '1',
  'Requires the explicit HTTPS/local-capture auth stack.',
);
const base = process.env.AION_BASE_URL ?? 'https://127.0.0.1:18443';
const inboxUrl = process.env.AION_INBOX_URL ?? 'http://127.0.0.1:18025';
const localhost = base.replace('127.0.0.1', 'localhost');
// These tests handle synthetic verification codes/cookies; never retain credential-bearing traces.
test.use({ ignoreHTTPSErrors: true, trace: 'off', screenshot: 'off', video: 'off' });

for (const language of ['en', 'es'] as const) {
  test(`email verification and logout through local capture (${language})`, async ({
    page,
    request,
    context,
  }) => {
    const address = `browser-${language}-${Date.now()}@example.test`;
    const apiRequests: string[] = [];
    page.on('request', (value) => {
      if (new URL(value.url()).pathname.startsWith('/api/')) apiRequests.push(value.url());
    });
    await page.goto(`${localhost}${language === 'en' ? '/' : '/es'}`);
    await expect(page).toHaveURL(`${base}${language === 'en' ? '/' : '/es'}`);
    expect(apiRequests).toEqual([]);
    await page
      .getByRole('link', { name: language === 'en' ? 'Account' : 'Cuenta', exact: true })
      .click();
    await page
      .getByLabel(language === 'en' ? 'Email address' : 'Correo electrónico', { exact: true })
      .fill(address);
    await page
      .getByRole('button', {
        name: language === 'en' ? 'Send a code' : 'Enviar un código',
        exact: true,
      })
      .click();
    const codeInput = page.getByLabel(
      language === 'en' ? 'Verification code' : 'Código de verificación',
      { exact: true },
    );
    await expect(codeInput).toBeFocused();
    let code: string | undefined;
    await expect
      .poll(
        async () => {
          const inbox = await (await request.get(`${inboxUrl}/api/v1/messages`)).json();
          const mail = inbox.messages.find((value: { To: { Address: string }[] }) =>
            value.To.some((to) => to.Address === address),
          );
          if (!mail) return false;
          const body = await (await request.get(`${inboxUrl}/api/v1/message/${mail.ID}`)).json();
          code = body.Text.match(/\b[0-9]{8}\b/)?.[0];
          // Check multipart delivery without retaining a real challenge in assertion output.
          expect(Boolean(body.HTML && body.HTML.includes(code) && body.HTML.includes('<h1'))).toBe(
            true,
          );
          return Boolean(code);
        },
        { timeout: 20000 },
      )
      .toBe(true);
    await expect(page).toHaveURL(`${base}${language === 'en' ? '' : '/es'}/login`);
    await codeInput.fill(code!);
    await page
      .getByRole('button', {
        name: language === 'en' ? 'Verify email' : 'Verificar correo',
        exact: true,
      })
      .click();
    await expect(page.getByRole('status')).toContainText(address);
    const cookie = (await context.cookies()).find((value) => value.name === '__Host-aion_session');
    expect(Boolean(cookie?.secure && cookie?.httpOnly)).toBe(true);
    const prefix = language === 'en' ? '' : '/es';
    await expect(page).toHaveURL(`${base}${prefix}/account`);
    await expect(
      page.getByRole('heading', {
        name: language === 'en' ? 'Create your calendar.' : 'Crea tu calendario.',
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.locator('.profile-comparison')).toHaveCount(0);
    if (process.env.AION_UI_REVIEW === '1' && language === 'en')
      await page.screenshot({ path: '.local/profile-tests/account-empty.png', fullPage: true });
    await expect(
      page.getByRole('button', {
        name: language === 'en' ? 'Refresh / retry sync' : 'Actualizar / reintentar',
        exact: true,
      }),
    ).toHaveCount(0);
    await page
      .getByRole('button', {
        name: language === 'en' ? 'Create account calendar' : 'Crear calendario de cuenta',
        exact: true,
      })
      .click();
    await expect(page).toHaveURL(`${base}${prefix || '/'}`);
    await page
      .getByLabel(language === 'en' ? 'Date of birth' : 'Fecha de nacimiento', { exact: true })
      .fill('2000-01-01');
    await page
      .getByRole('button', {
        name: language === 'en' ? 'See my weeks' : 'Ver mis semanas',
        exact: true,
      })
      .click();
    await expect(
      page.getByText(language === 'en' ? 'Saved to your account' : 'Guardado en tu cuenta', {
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole('link', { name: language === 'en' ? 'Account' : 'Cuenta', exact: true })
      .click();
    await page.reload();
    await expect(page).toHaveURL(`${base}${prefix}/account`);
    await page.goto(`${base}${prefix}/login`);
    await expect(page).toHaveURL(`${base}${prefix}/account`);
    await expect(page.getByRole('status')).toContainText(address);
    await page
      .getByRole('button', { name: language === 'en' ? 'Sign out' : 'Cerrar sesión', exact: true })
      .click();
    await expect(
      page.getByLabel(language === 'en' ? 'Email address' : 'Correo electrónico', { exact: true }),
    ).toBeVisible();
    expect((await context.cookies()).some((value) => value.name === '__Host-aion_session')).toBe(
      false,
    );
  });
}

test('localhost redirects to the configured HTTPS account origin', async ({ request }) => {
  const response = await request.get(`${localhost}/es?preview=1`, { maxRedirects: 0 });
  expect(response.status()).toBe(308);
  expect(response.headers().location).toBe(`${base}/es?preview=1`);
});

import { test, expect } from '@playwright/test';

test.skip(
  process.env.AION_AUTH_TESTS !== '1',
  'Requires the explicit HTTPS/local-capture auth stack.',
);
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
    await page.goto(`https://localhost:18443${language === 'en' ? '/' : '/es'}`);
    await expect(page).toHaveURL(`https://127.0.0.1:18443${language === 'en' ? '/' : '/es'}`);
    expect(apiRequests).toEqual([]);
    await page
      .getByRole('button', { name: language === 'en' ? 'Account' : 'Cuenta', exact: true })
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
          const inbox = await (await request.get('http://127.0.0.1:18025/api/v1/messages')).json();
          const mail = inbox.messages.find((value: { To: { Address: string }[] }) =>
            value.To.some((to) => to.Address === address),
          );
          if (!mail) return false;
          const body = await (
            await request.get(`http://127.0.0.1:18025/api/v1/message/${mail.ID}`)
          ).json();
          code = body.Text.match(/\b[0-9]{8}\b/)?.[0];
          return Boolean(code);
        },
        { timeout: 20000 },
      )
      .toBe(true);
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
    await page.reload();
    await page
      .getByRole('button', { name: language === 'en' ? 'Account' : 'Cuenta', exact: true })
      .click();
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
  const response = await request.get('https://localhost:18443/es?preview=1', { maxRedirects: 0 });
  expect(response.status()).toBe(308);
  expect(response.headers().location).toBe('https://127.0.0.1:18443/es?preview=1');
});

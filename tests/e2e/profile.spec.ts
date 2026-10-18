import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.skip(process.env.AION_AUTH_TESTS !== '1', 'Requires the capture-only HTTPS stack.');
test.use({ ignoreHTTPSErrors: true, trace: 'off', screenshot: 'off', video: 'off' });
const inbox = process.env.AION_INBOX_URL ?? 'http://127.0.0.1:18025';

async function login(page: Page, request: APIRequestContext, es: boolean) {
  const email = `sync-${es ? 'es' : 'en'}-${Date.now()}@example.test`;
  await page.getByRole('link', { name: es ? 'Cuenta' : 'Account', exact: true }).click();
  await page.getByLabel(es ? 'Correo electrónico' : 'Email address', { exact: true }).fill(email);
  await page
    .getByRole('button', { name: es ? 'Enviar un código' : 'Send a code', exact: true })
    .click();
  let code = '';
  await expect
    .poll(
      async () => {
        const messages = await (await request.get(`${inbox}/api/v1/messages`)).json();
        const mail = messages.messages.find((m: { To: { Address: string }[] }) =>
          m.To.some((t) => t.Address === email),
        );
        if (!mail) return false;
        const body = await (await request.get(`${inbox}/api/v1/message/${mail.ID}`)).json();
        code = body.Text.match(/\b[0-9]{8}\b/)?.[0] ?? '';
        return Boolean(code);
      },
      { timeout: 20000 },
    )
    .toBe(true);
  await page
    .getByLabel(es ? 'Código de verificación' : 'Verification code', { exact: true })
    .fill(code);
  await page
    .getByRole('button', { name: es ? 'Verificar correo' : 'Verify email', exact: true })
    .click();
  await expect(page.getByRole('status')).toContainText(email);
}
for (const es of [false, true]) {
  test(`explicit import, second browser, offline conflict, reset and guest restoration (${es ? 'ES' : 'EN'})`, async ({
    page,
    context,
    browser,
    request,
    baseURL,
  }) => {
    test.setTimeout(90000);
    const birth = es ? 'Fecha de nacimiento' : 'Date of birth';
    const years = es ? 'Horizonte de vida elegido' : 'Chosen lifespan';
    const save = es ? 'Guardar cambios' : 'Save changes';
    const edit = es ? 'Tu calendario' : 'Your calendar';
    const close = async (p: Page) => {
      if (/\/(account|login)$/.test(new URL(p.url()).pathname))
        await p
          .getByRole('link', {
            name: es ? 'Volver al calendario' : 'Back to calendar',
            exact: false,
          })
          .click();
      else await p.keyboard.press('Escape');
    };
    const refresh = async (p: Page) => {
      await p.evaluate(() => window.dispatchEvent(new Event('focus')));
    };
    const change = async (p: Page, value: string) => {
      await p.getByRole('button', { name: edit, exact: true }).click();
      await p.getByLabel(years).fill(value);
      await p.getByRole('button', { name: save, exact: true }).click();
    };
    await page.goto(es ? '/es' : '/');
    await page.getByLabel(birth, { exact: true }).fill('2000-01-01');
    await page
      .getByRole('button', { name: es ? 'Ver mis semanas' : 'See my weeks', exact: true })
      .click();
    await login(page, request, es);
    const originalGuest = await page.evaluate(() => localStorage.getItem('aion:settings'));
    await expect(
      page.getByRole('heading', {
        name: es ? 'Lleva tu calendario contigo.' : 'Keep your calendar with you.',
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole('button', {
        name: es ? 'Guardar este dispositivo en mi cuenta' : 'Save this device to my account',
        exact: true,
      })
      .click();
    await expect(
      page
        .locator('main')
        .getByText(es ? 'Guardado en tu cuenta' : 'Saved to your account', { exact: true }),
    ).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('aion:settings'))).toBe(originalGuest);
    await page.setViewportSize({ width: 360, height: 800 });
    expect(
      (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
        .violations,
    ).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await close(page);
    // A second isolated browser already holding the authenticated session. No copied local storage.
    const otherContext = await browser.newContext({
      ignoreHTTPSErrors: true,
      baseURL,
      timezoneId: 'UTC',
    });
    try {
      await otherContext.addCookies(await context.cookies());
      const other = await otherContext.newPage();
      await other.goto(es ? '/es' : '/');
      await other.getByRole('link', { name: es ? 'Cuenta' : 'Account', exact: true }).click();
      await expect(
        other
          .locator('main')
          .getByText(es ? 'Guardado en tu cuenta' : 'Saved to your account', { exact: true }),
      ).toBeVisible();
      await close(other);
      await expect(other.getByTestId('lived-weeks')).toBeVisible();
      expect(await other.evaluate(() => localStorage.getItem('aion:settings'))).toBeNull();
      // A browser with a different guest calendar receives a comparison, with no automatic upload.
      const compareContext = await browser.newContext({ ignoreHTTPSErrors: true, baseURL });
      try {
        await compareContext.addCookies(await context.cookies());
        await compareContext.addInitScript(
          (language) =>
            localStorage.setItem(
              'aion:settings',
              JSON.stringify({
                version: 1,
                birthDate: '1990-01-01',
                lifespanYears: 80,
                language,
                unit: 'weeks',
                hideRemaining: false,
              }),
            ),
          es ? 'es' : 'en',
        );
        const compare = await compareContext.newPage();
        await compare.goto(es ? '/es/account' : '/account');
        await expect(compare.locator('.profile-comparison')).toBeVisible();
        await compare
          .getByRole('button', {
            name: es ? 'Usar calendario de la cuenta' : 'Use account calendar',
            exact: true,
          })
          .click();
        await expect(compare.getByTestId('lived-weeks')).toBeVisible();
        expect(
          await compare.evaluate(
            () => JSON.parse(localStorage.getItem('aion:settings')!).lifespanYears,
          ),
        ).toBe(80);
      } finally {
        await compareContext.close();
      }
      // A foreground refresh must not silently rebase an already-open form.
      await page.getByRole('button', { name: edit, exact: true }).click();
      await change(other, '93');
      await expect(
        other.getByText(es ? 'Guardado en tu cuenta' : 'Saved to your account', { exact: true }),
      ).toBeVisible();
      await refresh(page);
      await expect
        .poll(() =>
          page.evaluate(() => {
            const key = Object.keys(localStorage).find((k) => k.startsWith('aion:profile:'));
            return key
              ? JSON.parse(localStorage.getItem(key)!).snapshot?.profile?.lifespanYears
              : null;
          }),
        )
        .toBe(93);
      await page.getByLabel(years).fill('92');
      await page.getByRole('button', { name: save, exact: true }).click();
      await expect(
        page.getByText(
          es
            ? 'El calendario cambió en otro dispositivo'
            : 'This calendar changed on another device',
          { exact: true },
        ),
      ).toBeVisible();
      await page.getByRole('link', { name: es ? 'Cuenta' : 'Account', exact: true }).click();
      await page
        .getByRole('button', {
          name: es ? 'Conservar versión de la cuenta' : 'Keep account version',
          exact: true,
        })
        .click();
      await close(page);
      await context.setOffline(true);
      await change(page, '91');
      await change(other, '95');
      await expect(
        other.getByText(es ? 'Guardado en tu cuenta' : 'Saved to your account', { exact: true }),
      ).toBeVisible();
      await context.setOffline(false);
      await refresh(page);
      await expect(
        page.getByText(
          es
            ? 'El calendario cambió en otro dispositivo'
            : 'This calendar changed on another device',
          { exact: true },
        ),
      ).toBeVisible();
      await page.getByRole('link', { name: es ? 'Cuenta' : 'Account', exact: true }).click();
      await page
        .getByRole('button', {
          name: es ? 'Volver a aplicar mis cambios' : 'Reapply my device changes',
          exact: true,
        })
        .click();
      await expect(
        page
          .locator('main')
          .getByText(es ? 'Guardado en tu cuenta' : 'Saved to your account', { exact: true }),
      ).toBeVisible();
      await close(page);
      await refresh(other);
      await expect
        .poll(() =>
          other.evaluate(() => {
            const key = Object.keys(localStorage).find((k) => k.startsWith('aion:profile:'));
            return key
              ? JSON.parse(localStorage.getItem(key)!).snapshot?.profile?.lifespanYears
              : null;
          }),
        )
        .toBe(91);
      await other.getByRole('button', { name: edit, exact: true }).click();
      await expect(other.getByLabel(years)).toHaveValue('91');
      await close(other);
      await page
        .getByRole('button', {
          name: es ? 'Reiniciar calendario de la cuenta' : 'Reset account calendar',
          exact: true,
        })
        .click();
      await page
        .getByRole('button', {
          name: es ? 'Sí, reiniciar calendario' : 'Yes, reset calendar',
          exact: true,
        })
        .click();
      await expect(page.getByLabel(birth, { exact: true })).toBeVisible();
      await refresh(other);
      await expect(other.getByLabel(birth, { exact: true })).toBeVisible();
      await page.getByRole('link', { name: es ? 'Cuenta' : 'Account', exact: true }).click();
      await page
        .getByRole('button', { name: es ? 'Cerrar sesión' : 'Sign out', exact: true })
        .click();
      await close(page);
      await expect(page.getByTestId('lived-weeks')).toBeVisible();
      expect(await page.evaluate(() => localStorage.getItem('aion:settings'))).toBe(originalGuest);
      expect(
        await page.evaluate(() =>
          Object.keys(localStorage).filter(
            (k) => k.startsWith('aion:profile:') || k === 'aion:account',
          ),
        ),
      ).toEqual([]);
    } finally {
      await otherContext.close();
    }
  });
}

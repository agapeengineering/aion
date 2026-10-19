import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { execFileSync } from 'node:child_process';

test.skip(
  process.env.AION_REMINDER_TESTS !== '1',
  'Requires a capture-only reminder-enabled stack.',
);
test.use({ ignoreHTTPSErrors: true, trace: 'off', screenshot: 'off', video: 'off' });
const inbox = process.env.AION_INBOX_URL ?? 'http://127.0.0.1:18025';

async function login(page: Page, request: APIRequestContext, es: boolean, address: string) {
  await page.goto(es ? '/es/login' : '/login');
  await page.getByLabel(es ? 'Correo electrónico' : 'Email address', { exact: true }).fill(address);
  await page
    .getByRole('button', { name: es ? 'Enviar un código' : 'Send a code', exact: true })
    .click();
  let code = '';
  await expect
    .poll(
      async () => {
        const data = await (await request.get(`${inbox}/api/v1/messages`)).json();
        const message = data.messages.find((m: { To: { Address: string }[] }) =>
          m.To.some((t) => t.Address === address),
        );
        if (!message) return false;
        const body = await (await request.get(`${inbox}/api/v1/message/${message.ID}`)).json();
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
  await expect(page.getByRole('status')).toContainText(address);
}
for (const es of [false, true]) {
  test(`consent, Sunday defaults, delivery and unsubscribe (${es ? 'ES' : 'EN'})`, async ({
    page,
    request,
    context,
  }) => {
    test.setTimeout(90000);
    const email = `reminder-${es ? 'es' : 'en'}-${Date.now()}@example.test`;
    await login(page, request, es, email);
    const panel = page.locator('.reminder-panel');
    await expect(
      panel.getByRole('checkbox', {
        name: es ? 'Recibir recordatorios por correo' : 'Receive email reminders',
        exact: true,
      }),
    ).toBeDisabled();
    await page
      .getByRole('button', {
        name: es ? 'Crear calendario de cuenta' : 'Create account calendar',
        exact: true,
      })
      .click();
    await page
      .getByLabel(es ? 'Fecha de nacimiento' : 'Date of birth', { exact: true })
      .fill('2000-01-01');
    await page
      .getByRole('button', { name: es ? 'Ver mis semanas' : 'See my weeks', exact: true })
      .click();
    await expect(
      page.getByText(es ? 'Guardado en tu cuenta' : 'Saved to your account', { exact: true }),
    ).toBeVisible();
    await page.getByRole('link', { name: es ? 'Cuenta' : 'Account', exact: true }).click();
    const enabled = panel.getByRole('checkbox', {
      name: es ? 'Recibir recordatorios por correo' : 'Receive email reminders',
      exact: true,
    });
    await expect(enabled).toBeEnabled();
    await expect(enabled).not.toBeChecked();
    await expect(
      panel.getByRole('combobox', { name: es ? 'Frecuencia' : 'Frequency', exact: true }),
    ).toHaveValue('weekly');
    await expect(
      panel.getByRole('combobox', { name: es ? 'Día' : 'Day', exact: true }),
    ).toHaveValue('6');
    await expect(
      panel.getByLabel(es ? 'Hora local de envío' : 'Local send time', { exact: true }),
    ).toHaveValue('09:00');
    await expect(
      panel.getByRole('checkbox', {
        name: es ? 'Incluir el pasaje de la semana' : 'Include the weekly passage',
        exact: true,
      }),
    ).toBeDisabled();
    await page.setViewportSize({ width: 360, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect(
      (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
        .violations,
    ).toEqual([]);
    await enabled.check();
    await panel
      .getByRole('button', {
        name: es ? 'Guardar preferencias' : 'Save reminder preferences',
        exact: true,
      })
      .click();
    await expect(
      panel.getByRole('checkbox', { name: /^(I agree|Acepto recibir)/ }),
    ).not.toBeChecked();
    await expect(
      panel.getByRole('button', {
        name: es ? 'Pausar recordatorios' : 'Pause reminders',
        exact: true,
      }),
    ).toHaveCount(0);
    await panel.getByRole('checkbox', { name: /^(I agree|Acepto recibir)/ }).check();
    await panel
      .getByRole('button', {
        name: es ? 'Guardar preferencias' : 'Save reminder preferences',
        exact: true,
      })
      .click();
    await expect(
      panel.getByText(es ? 'Preferencias guardadas.' : 'Reminder preferences saved.', {
        exact: true,
      }),
    ).toBeVisible();
    await page.reload();
    await expect(enabled).toBeChecked();
    await expect(
      panel.getByText(es ? 'Próximo correo programado' : 'Next scheduled email', { exact: false }),
    ).toBeVisible();
    await context.setOffline(true);
    await expect(
      panel.getByRole('button', {
        name: es ? 'Guardar preferencias' : 'Save reminder preferences',
        exact: true,
      }),
    ).toBeDisabled();
    await context.setOffline(false);
    // Time advance applies only to our synthetic account in an explicitly disposable Compose project.
    const project = process.env.AION_REMINDER_SMOKE_PROJECT;
    if (project) {
      if (!(project === 'aion-profile-tests' || (process.env.CI && project === 'aion-foundation')))
        throw new Error('Not a disposable reminder test project');
      if (!/^reminder-(en|es)-[0-9]+@example\.test$/.test(email))
        throw new Error('Not a synthetic test account');
      const sql = `UPDATE reminder_preferences SET next_due_at=now()-interval '2 seconds' WHERE user_id=(SELECT id FROM users WHERE email='${email}') AND enabled=true;`;
      execFileSync(
        'docker',
        [
          'compose',
          '-p',
          project,
          '-f',
          'deploy/compose.yaml',
          '-f',
          'deploy/compose.auth.local.yaml',
          'exec',
          '-T',
          'postgres',
          'psql',
          '-U',
          'postgres',
          '-d',
          'aion',
          '-c',
          sql,
        ],
        { stdio: ['ignore', 'pipe', 'pipe'] },
      );
      let unsubscribe = '';
      await expect
        .poll(
          async () => {
            const data = await (await request.get(`${inbox}/api/v1/messages`)).json();
            const mail = data.messages.find(
              (m: { Subject: string; To: { Address: string }[] }) =>
                m.Subject === (es ? 'Tu recordatorio de Aion' : 'Your Aion reminder') &&
                m.To.some((t) => t.Address === email),
            );
            if (!mail) return false;
            const body = await (await request.get(`${inbox}/api/v1/message/${mail.ID}`)).json();
            expect(Boolean(body.HTML && body.Text && !body.Text.includes('2000-01-01'))).toBe(true);
            unsubscribe =
              body.Text.match(/https:\/\/[^\s]+\/api\/v1\/unsubscribe\/[A-Za-z0-9_-]{43}/)?.[0] ??
              '';
            return Boolean(unsubscribe);
          },
          { timeout: 20000 },
        )
        .toBe(true);
      await page.goto(unsubscribe);
      await expect(
        page.getByRole('heading', {
          name: es ? 'Cancelar recordatorios' : 'Unsubscribe from reminders',
          exact: true,
        }),
      ).toBeVisible();
      // GET is a confirmation only; the form's POST is allowed by the proxy CSP.
      await page
        .getByRole('button', {
          name: es ? 'Cancelar recordatorios' : 'Unsubscribe from reminders',
          exact: true,
        })
        .click();
      await expect(
        page.getByRole('heading', {
          name: es ? 'Los recordatorios están desactivados.' : 'Reminders are now off.',
          exact: true,
        }),
      ).toBeVisible();
      await page.goto(es ? '/es/account' : '/account');
      await expect(enabled).not.toBeChecked();
    } else {
      await panel
        .getByRole('button', { name: es ? 'Pausar recordatorios' : 'Pause reminders', exact: true })
        .click();
      await expect(enabled).not.toBeChecked();
    }
  });
}

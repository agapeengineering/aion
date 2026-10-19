import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.skip(process.env.AION_EMAIL_TESTS !== '1', 'Generate synthetic email previews first.');
test.use({ trace: 'off', screenshot: 'off', video: 'off' });
for (const language of ['en', 'es']) {
  for (const width of [320, 800]) {
    test(`verification email is readable without remote assets (${language}, ${width}px)`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 950 });
      const external: string[] = [];
      page.on('request', (request) => {
        if (/^https?:/.test(request.url())) external.push(request.url());
      });
      await page.goto(new URL(`../../.local/email-preview/${language}.html`, import.meta.url).href);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(
        language === 'en' ? 'Your sign-in code.' : 'Tu código de acceso.',
      );
      await expect(page.getByText('00123456', { exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      expect(
        (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
          .violations,
      ).toEqual([]);
      expect(external).toEqual([]);
    });
  }
}

for (const language of ['en', 'es']) {
  for (const width of [320, 800]) {
    test(`reminder email layout (${language}, ${width}px)`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1100 });
      const external: string[] = [];
      page.on('request', (request) => {
        if (/^https?:/.test(request.url())) external.push(request.url());
      });
      await page.goto(
        new URL(`../../.local/email-preview/reminder-${language}.html`, import.meta.url).href,
      );
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(
        language === 'en' ? 'A moment for your life.' : 'Un momento para tu vida.',
      );
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      expect(
        (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
          .violations,
      ).toEqual([]);
      expect(external).toEqual([]);
    });
  }
}

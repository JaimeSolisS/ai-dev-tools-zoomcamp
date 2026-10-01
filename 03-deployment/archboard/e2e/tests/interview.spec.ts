import { expect, test, type Page } from '@playwright/test';

const INTERVIEWER_EMAIL = 'ada@example.com'; // a demo account seeded on first start

/** Sign in through the UI. The stack runs in dev mode, so the magic link is shown instead of emailed. */
async function signIn(page: Page, email: string) {
  await page.goto('/login');
  await page.getByLabel('Work email').fill(email);
  await page.getByRole('button', { name: 'Email me a sign-in link' }).click();
  await page.getByRole('button', { name: 'Open sign-in link' }).click();
  await expect(page.getByRole('link', { name: 'New interview' }).first()).toBeVisible();
}

test('the interviewer sees the candidate’s canvas changes live', async ({ browser }) => {
  // Two browser contexts share no cookies or storage: two separate people.
  const interviewerContext = await browser.newContext();
  const candidateContext = await browser.newContext();
  const interviewer = await interviewerContext.newPage();
  const candidate = await candidateContext.newPage();
  const title = `E2E interview ${Date.now()}`;

  await test.step('1. the interviewer signs in', async () => {
    await signIn(interviewer, INTERVIEWER_EMAIL);
  });

  await test.step('2. the interviewer creates and starts an interview', async () => {
    await interviewer.getByRole('link', { name: 'New interview' }).first().click();
    await interviewer.getByLabel('Title', { exact: true }).fill(title);
    await interviewer.getByLabel(/Problem statement/).fill('Design a URL shortener.');
    await interviewer.getByRole('button', { name: 'Create interview' }).click();
    await expect(interviewer).toHaveURL(/\/sessions\/s_/);
    // Candidates can only edit a live interview.
    await interviewer.getByRole('button', { name: 'Start interview' }).click();
    await expect(interviewer.getByRole('button', { name: 'Start interview' })).toBeHidden();
  });

  let joinUrl = '';
  await test.step('3. the interviewer creates a share link', async () => {
    await interviewer.getByRole('button', { name: 'Share', exact: true }).click();
    await interviewer.getByRole('button', { name: 'Create candidate link' }).click();
    joinUrl = await interviewer.getByLabel('Invitation link').inputValue();
    expect(joinUrl).toMatch(/\/join\/[\w-]+$/);
    await interviewer.keyboard.press('Escape');
  });

  await test.step('4. the candidate joins with the link in a separate browser', async () => {
    await candidate.goto(joinUrl);
    await expect(candidate.getByRole('heading', { name: title })).toBeVisible();
    await candidate.getByLabel('Your name').fill('Linus');
    await candidate.getByRole('checkbox').check();
    await candidate.getByRole('button', { name: 'Join interview' }).click();
    await expect(candidate).toHaveURL(/\/sessions\/s_/);
  });

  // The canvas renders each element as an image named "<component>: <label>".
  const cache = (page: Page) => page.getByRole('img', { name: 'Cache: Cache' });

  await test.step('5. the candidate adds a component to the canvas', async () => {
    await expect(cache(interviewer)).toHaveCount(0);
    await candidate.getByRole('button', { name: 'Component library' }).click();
    await candidate.getByRole('button', { name: 'Add Cache' }).click();
    await expect(cache(candidate)).toBeVisible();
  });

  await test.step('6. the interviewer sees the change without reloading', async () => {
    await expect(cache(interviewer)).toBeVisible();
  });

  await test.step('the change is saved, not only broadcast', async () => {
    await interviewer.reload();
    await expect(cache(interviewer)).toBeVisible();
  });

  await interviewerContext.close();
  await candidateContext.close();
});

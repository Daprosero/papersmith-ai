import { expect, test, type Page } from '@playwright/test';

/**
 * `App.tsx` writes `data-ready` on the body once a state payload is applied
 * ("1") or has definitively failed ("error"). Waiting on it beats waiting on a
 * timeout, and it is the signal the dashboard already published for exactly
 * this purpose.
 */
async function gotoReady(page: Page, hash = ''): Promise<void> {
  await page.goto(`/${hash}`);
  await expect(page.locator('body')).toHaveAttribute('data-ready', '1', { timeout: 30_000 });
}

test.describe('the dashboard loads and answers', () => {
  test('reaches a ready state with a workspace identity', async ({ page }) => {
    await gotoReady(page);
    await expect(page.getByRole('heading', { name: 'Paper Command Center' })).toBeVisible();
    await expect(page.locator('.topbar__subtitle')).not.toBeEmpty();
  });

  test('reports no uncaught page errors while loading', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await gotoReady(page);
    expect(errors).toEqual([]);
  });
});

test.describe('tab navigation', () => {
  test('every tab activates, is reflected in the hash, and renders content', async ({ page }) => {
    await gotoReady(page);
    const tabs = page.locator('.tabs__button');
    const count = await tabs.count();
    expect(count).toBeGreaterThan(1);

    for (let index = 0; index < count; index += 1) {
      const tab = tabs.nth(index);
      const label = (await tab.textContent())?.trim() ?? '';
      await tab.click();
      await expect(tab).toHaveAttribute('data-active', 'true');
      await expect(tab).toHaveAttribute('aria-current', 'page');
      // Exactly one tab is ever active.
      await expect(page.locator('.tabs__button[data-active="true"]')).toHaveCount(1);
      expect(page.url(), `hash after clicking ${label}`).toContain('#');
      await expect(page.locator('main.content')).not.toBeEmpty();
    }
  });

  test('a deep-linked tab survives a reload', async ({ page }) => {
    await gotoReady(page);
    await page.locator('.tabs__button').nth(2).click();
    const hash = new URL(page.url()).hash;
    await page.reload();
    await expect(page.locator('body')).toHaveAttribute('data-ready', '1', { timeout: 30_000 });
    expect(new URL(page.url()).hash).toBe(hash);
  });
});

test.describe('the theme switch', () => {
  test('flips the document theme and names its destination', async ({ page }) => {
    await gotoReady(page);
    const toggle = page.locator('.theme-toggle');
    const before = await page.locator('html').getAttribute('data-theme');
    expect(before).toMatch(/^(light|dark)$/);

    await toggle.click();
    const after = await page.locator('html').getAttribute('data-theme');
    expect(after).not.toBe(before);
    // The label always points at where the next click goes.
    await expect(toggle).toHaveAttribute('title', `Switch to the ${after === 'dark' ? 'light' : 'dark'} theme`);
  });

  test('persists the choice across a reload', async ({ page }) => {
    await gotoReady(page);
    await page.locator('.theme-toggle').click();
    const chosen = await page.locator('html').getAttribute('data-theme');

    await page.reload();
    await expect(page.locator('body')).toHaveAttribute('data-ready', '1', { timeout: 30_000 });
    await expect(page.locator('html')).toHaveAttribute('data-theme', chosen ?? '');
  });

  test('actually repaints the surface, not just the attribute', async ({ page }) => {
    await gotoReady(page);
    const body = page.locator('body');
    const before = await body.evaluate((node) => getComputedStyle(node).backgroundColor);
    await page.locator('.theme-toggle').click();
    const after = await body.evaluate((node) => getComputedStyle(node).backgroundColor);
    expect(after).not.toBe(before);
  });
});

test.describe('the pipeline canvas', () => {
  test('renders nodes and opens the detail panel on selection', async ({ page }) => {
    await gotoReady(page, '#pipeline');
    const nodes = page.locator('.react-flow__node');
    await expect(nodes.first()).toBeVisible({ timeout: 30_000 });
    expect(await nodes.count()).toBeGreaterThan(0);

    await nodes.first().click();
    const panel = page.locator('.element-panel');
    await expect(panel).toBeVisible();
    await expect(panel).not.toBeEmpty();
    // Selection is addressable, which is what makes a deep link possible.
    expect(new URL(page.url()).hash).toMatch(/el=/);
  });

  test('keyboard focus reaches a node and is visibly distinct', async ({ page }) => {
    await gotoReady(page, '#pipeline');
    await expect(page.locator('.react-flow__node').first()).toBeVisible({ timeout: 30_000 });
    const outline = await page.locator('.react-flow__node').first().evaluate((node) => {
      (node as HTMLElement).focus();
      const inner = node.querySelector('.dag-node');
      return inner ? getComputedStyle(inner).outlineStyle : null;
    });
    // Either a real focus ring or none — never a dashed one, which the
    // stylesheet reserves for a node being rewritten.
    expect(outline).not.toBe('dashed');
  });
});

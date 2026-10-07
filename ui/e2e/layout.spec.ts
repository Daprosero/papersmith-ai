import { expect, test, type Locator, type Page } from '@playwright/test';

async function gotoReady(page: Page, hash = ''): Promise<void> {
  await page.goto(`/${hash}`);
  await expect(page.locator('body')).toHaveAttribute('data-ready', '1', { timeout: 30_000 });
}

/**
 * Elements whose text is clipped by their own box. `scrollWidth` exceeding
 * `clientWidth` is how an ellipsis or a hard cut shows up in the DOM; a 1px
 * tolerance absorbs sub-pixel rounding, which is noise rather than overflow.
 *
 * Elements that scroll on purpose are excluded: a terminal or an artifact
 * viewer is *supposed* to overflow.
 */
async function clippedText(page: Page, selector: string): Promise<string[]> {
  return page.$$eval(selector, (nodes) =>
    nodes
      .filter((node) => {
        const style = getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        if (['auto', 'scroll'].includes(style.overflowX)) return false;
        return (node.textContent ?? '').trim().length > 0;
      })
      .filter((node) => node.scrollWidth - node.clientWidth > 1)
      .map((node) => `${node.className || node.tagName}: ${(node.textContent ?? '').trim().slice(0, 60)}`),
  );
}

/** Rectangles of visible matches, in viewport coordinates. */
async function boxes(locator: Locator): Promise<Array<{ label: string; x: number; y: number; w: number; h: number }>> {
  const count = await locator.count();
  const result: Array<{ label: string; x: number; y: number; w: number; h: number }> = [];
  for (let index = 0; index < count; index += 1) {
    const item = locator.nth(index);
    if (!(await item.isVisible())) continue;
    const box = await item.boundingBox();
    if (!box) continue;
    result.push({
      label: ((await item.textContent()) ?? '').trim().slice(0, 40) || `#${index}`,
      x: box.x,
      y: box.y,
      w: box.width,
      h: box.height,
    });
  }
  return result;
}

function overlaps(a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }): boolean {
  // A shared edge is adjacency, not overlap, so the comparison is strict.
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

test.describe('text distribution', () => {
  test('no chrome label is clipped by its own box', async ({ page }) => {
    await gotoReady(page);
    for (const selector of ['.tabs__button', '.badge', '.totals__chip', '.topbar h1', '.panel__header h2', '.button']) {
      expect(await clippedText(page, selector), `clipped: ${selector}`).toEqual([]);
    }
  });

  test('no label is clipped on any tab', async ({ page }) => {
    await gotoReady(page);
    const tabs = page.locator('.tabs__button');
    for (let index = 0; index < (await tabs.count()); index += 1) {
      const label = ((await tabs.nth(index).textContent()) ?? '').trim();
      await tabs.nth(index).click();
      await page.waitForTimeout(150);
      expect(await clippedText(page, '.badge, .button, .panel__header h2'), `clipped on ${label}`).toEqual([]);
    }
  });

  test('nothing spills horizontally past the viewport', async ({ page }) => {
    await gotoReady(page);
    const overflow = await page.evaluate(() => {
      const width = document.documentElement.clientWidth;
      return [...document.querySelectorAll('.topbar *, .tabs *, .panel__header *')]
        .filter((node) => {
          const rect = node.getBoundingClientRect();
          return rect.width > 0 && rect.right > width + 1;
        })
        .map((node) => node.className || node.tagName);
    });
    expect(overflow).toEqual([]);
  });

  test('both themes keep labels unclipped', async ({ page }) => {
    await gotoReady(page);
    await page.locator('.theme-toggle').click();
    await page.waitForTimeout(150);
    for (const selector of ['.tabs__button', '.badge', '.totals__chip']) {
      expect(await clippedText(page, selector), `clipped after theme switch: ${selector}`).toEqual([]);
    }
  });
});

test.describe('button distribution', () => {
  test('no two tabs overlap', async ({ page }) => {
    await gotoReady(page);
    const rects = await boxes(page.locator('.tabs__button'));
    const collisions: string[] = [];
    for (let i = 0; i < rects.length; i += 1) {
      for (let j = i + 1; j < rects.length; j += 1) {
        if (overlaps(rects[i], rects[j])) collisions.push(`${rects[i].label} ↔ ${rects[j].label}`);
      }
    }
    expect(collisions).toEqual([]);
  });

  test('the theme control does not collide with the status badges', async ({ page }) => {
    await gotoReady(page);
    const toggle = (await boxes(page.locator('.theme-toggle')))[0];
    expect(toggle, 'the theme control must be visible').toBeDefined();
    const others = await boxes(page.locator('.topbar__status .badge, .topbar__changed'));
    const collisions = others.filter((other) => overlaps(toggle, other)).map((other) => other.label);
    expect(collisions).toEqual([]);
  });

  test('every control meets a 24px minimum hit target', async ({ page }) => {
    await gotoReady(page);
    const small = (await boxes(page.locator('button:visible'))).filter((box) => box.h < 24 || box.w < 24);
    expect(small.map((box) => `${box.label} ${Math.round(box.w)}×${Math.round(box.h)}`)).toEqual([]);
  });

  test('the topbar does not cover the tab strip', async ({ page }) => {
    await gotoReady(page);
    const topbar = (await boxes(page.locator('.topbar')))[0];
    const firstTab = (await boxes(page.locator('.tabs__button')))[0];
    expect(topbar).toBeDefined();
    expect(firstTab).toBeDefined();
    expect(overlaps(topbar, firstTab)).toBe(false);
  });
});

test.describe('the element panel at the 900px breakpoint', () => {
  test('is laid out as the stylesheet promises for this viewport', async ({ page }) => {
    await gotoReady(page, '#pipeline');
    await expect(page.locator('.react-flow__node').first()).toBeVisible({ timeout: 30_000 });
    await page.locator('.react-flow__node').first().click();

    const panel = page.locator('.element-panel');
    await expect(panel).toBeVisible();

    const viewport = page.viewportSize();
    expect(viewport, 'a viewport size is required to pick the expected layout').not.toBeNull();
    const narrow = (viewport?.width ?? 0) < 900;

    const geometry = await panel.evaluate((node) => {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return {
        maxHeight: style.maxHeight,
        overflowY: style.overflowY,
        borderLeftStyle: style.borderLeftStyle,
        borderTopWidth: style.borderTopWidth,
        left: rect.left,
        width: rect.width,
        bottom: rect.bottom,
      };
    });

    if (narrow) {
      // Bottom sheet: full width, capped at 60vh, scrollable, bordered on top.
      expect(geometry.left).toBeLessThanOrEqual(1);
      expect(geometry.width).toBeGreaterThan((viewport?.width ?? 0) * 0.9);
      expect(geometry.overflowY).toBe('auto');
      expect(parseFloat(geometry.maxHeight)).toBeLessThanOrEqual((viewport?.height ?? 0) * 0.6 + 1);
      expect(geometry.borderLeftStyle).toBe('none');
      expect(parseFloat(geometry.borderTopWidth)).toBeGreaterThan(0);
    } else {
      // Side drawer: anchored right, never the full width.
      expect(geometry.left).toBeGreaterThan((viewport?.width ?? 0) * 0.4);
      expect(geometry.width).toBeLessThan((viewport?.width ?? 0) * 0.6);
    }
  });

  test('the panel stays inside the viewport', async ({ page }) => {
    await gotoReady(page, '#pipeline');
    await expect(page.locator('.react-flow__node').first()).toBeVisible({ timeout: 30_000 });
    await page.locator('.react-flow__node').first().click();

    const panel = page.locator('.element-panel');
    await expect(panel).toBeVisible();
    const box = await panel.boundingBox();
    const viewport = page.viewportSize();
    expect(box).not.toBeNull();
    expect(box?.x ?? -1).toBeGreaterThanOrEqual(-1);
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual((viewport?.width ?? 0) + 1);
    expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual((viewport?.height ?? 0) + 1);
  });
});

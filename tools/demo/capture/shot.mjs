#!/usr/bin/env node
// Usage: node shot.mjs <url> <out.png> [--full] [--wait <ms>] [--click <selector>]...
//   <out.png>  relative paths are saved under outputs/fake-pages/
//   --click    Playwright selector (css, "text=새 작업", "role=button[name=\"학습 요청\"]"); repeatable, run in order
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';
import { launchOptions, contextOptions, seedPrefs, settle, resolveOut, sleep } from './lib.mjs';

const args = process.argv.slice(2);
const pos = [];
const clicks = [];
let full = false;
let wait = 0;
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === '--full') full = true;
  else if (a === '--wait') wait = Number(args[++i]);
  else if (a === '--click') clicks.push(args[++i]);
  else pos.push(a);
}
if (pos.length !== 2) {
  console.error('usage: node shot.mjs <url> <out.png> [--full] [--wait <ms>] [--click <selector>]...');
  process.exit(2);
}
const [url, outArg] = pos;
const out = resolveOut(outArg);
fs.mkdirSync(path.dirname(out), { recursive: true });

const browser = await chromium.launch(launchOptions);
try {
  const context = await browser.newContext(contextOptions());
  await seedPrefs(context);
  const page = await context.newPage();
  await page.goto(url, { waitUntil: 'load' });
  await settle(page);
  for (const sel of clicks) {
    await page.locator(sel).filter({ visible: true }).first().click();
    await settle(page, { idleTimeout: 5000 });
    await sleep(300);
  }
  // Park the mouse at the right edge so the last-clicked element loses its hover style.
  if (clicks.length) await page.mouse.move(page.viewportSize().width - 1, page.viewportSize().height / 2);
  if (wait) await sleep(wait);
  await settle(page, { idleTimeout: 3000 });
  if (full) {
    // Grow the viewport until nothing scrolls: covers apps that scroll an inner <main>
    // and keeps 100vh sidebars full-height (plain fullPage leaves them short).
    for (let i = 0; i < 3; i++) {
      const extra = await page.evaluate(() => Math.max(0, ...[...document.querySelectorAll('*')]
        .filter((e) => /(auto|scroll)/.test(getComputedStyle(e).overflowY))
        .map((e) => e.scrollHeight - e.clientHeight),
        document.documentElement.scrollHeight - window.innerHeight));
      if (extra <= 2) break;
      const vp = page.viewportSize();
      await page.setViewportSize({ width: vp.width, height: vp.height + extra });
      await sleep(400);
    }
  }
  await page.screenshot({ path: out, fullPage: full });
  console.log(out);
} finally {
  await browser.close();
}

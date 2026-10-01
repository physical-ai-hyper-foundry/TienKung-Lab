#!/usr/bin/env node
// Usage: node flow.mjs --scenario <json> --out <dir> [--cursor]
//   Runs scenario steps in one BrowserContext (tabs = pages), records video, stitches the
//   active-tab segments into <out>/<name>[-cursor].mp4 (H.264, yuv420p, 30 fps, faststart).
//   Relative --out resolves under outputs/fake-pages/. Relative --scenario also looks in scenarios/.
//
// Scenario: { "name", "pause"?=700, "tabPause"?=900, "tail"?=800, "steps": [...] }  (or a bare steps array)
//   target = "css/playwright selector" | {"role","name"} | {"text"} | {"label"} | {"placeholder"} | {"selector"}
//            + optional "exact": true, "nth": 0 (among visible matches)
//   { "goto": url }                      { "click": target }              { "fill": target, "value": "..." }
//   { "hover": target }                  { "wait": ms }                   { "waitFor": target }
//   { "scroll": dy, "at"?: target }      { "scroll": { "to": target } }   "step"?: px per frame (default 30; smaller = slower)
//   { "newTab": target, "timeout"?: 15000 }  click → follow the new tab   { "newTab": url }  open url in a new tab
//   { "switchTab": 0 | "url-substring" }            { "evaluate": "js expression" }
//   { "screenshot": "NN-name.png", "full"?: true }  (fake cursor hidden while shooting)
//   { "drag": target, "dx": 240, "dy": 0, "steps"?: 40 }  press at target center, ease-out move, release
//   { "wheel": target, "deltaY": -600, "steps"?: 6 }      cursor to target, wheel in `steps` chunks
//   any step may override "pause" (ms after it).
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { chromium } from 'playwright';
import { HERE, VIEWPORT, launchOptions, contextOptions, seedPrefs, settle, resolveOut, sleep } from './lib.mjs';

// ---------- args ----------
const argv = process.argv.slice(2);
let scenarioArg, outArg = '.', cursor = false;
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === '--scenario') scenarioArg = argv[++i];
  else if (argv[i] === '--out') outArg = argv[++i];
  else if (argv[i] === '--cursor') cursor = true;
}
if (!scenarioArg) {
  console.error('usage: node flow.mjs --scenario <json> --out <dir> [--cursor]');
  process.exit(2);
}
let scenarioPath = path.resolve(scenarioArg);
if (!fs.existsSync(scenarioPath)) scenarioPath = path.join(HERE, 'scenarios', scenarioArg);
const raw = JSON.parse(fs.readFileSync(scenarioPath, 'utf8'));
const scenario = Array.isArray(raw) ? { steps: raw } : raw;
const name = scenario.name || path.basename(scenarioPath, '.json');
const PAUSE = scenario.pause ?? 700; // pause after each interaction
const TAB_PAUSE = scenario.tabPause ?? 900; // pause after switching tabs
const outDir = resolveOut(outArg);
const videoTmp = path.join(outDir, `.video-tmp-${name}${cursor ? '-cursor' : ''}`);
fs.rmSync(videoTmp, { recursive: true, force: true });
fs.mkdirSync(videoTmp, { recursive: true });

// ---------- fake cursor (injected into every top-level document) ----------
function cursorInitScript() {
  if (window.top !== window) return;
  const SVG =
    '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 26 26">' +
    '<path d="M4 2.5 L4 20.5 L8.6 16.3 L11.6 23 L14.8 21.6 L11.9 15 L18.2 15 Z" ' +
    'fill="#111" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/></svg>';
  const TIP = [4, 2.5];
  let x = 0, y = 0, known = false, el = null;
  const render = () => {
    if (!el) return;
    el.style.translate = `${x - TIP[0]}px ${y - TIP[1]}px`;
    el.style.display = known ? 'block' : 'none';
  };
  const ensure = () => {
    if (!document.documentElement) return;
    if (!el) {
      el = document.createElement('div');
      el.id = '__pw_cursor';
      el.innerHTML = SVG;
      el.setAttribute('aria-hidden', 'true');
      Object.assign(el.style, {
        position: 'fixed', left: '0', top: '0', width: '26px', height: '26px', margin: '0',
        pointerEvents: 'none', zIndex: '2147483647', transformOrigin: `${TIP[0]}px ${TIP[1]}px`,
        transition: 'scale 90ms ease-out', filter: 'drop-shadow(0 1px 1.5px rgba(0,0,0,.35))',
      });
    }
    if (!el.isConnected) document.documentElement.appendChild(el);
    render();
  };
  window.__pwCursor = {
    move(nx, ny) { x = nx; y = ny; known = true; ensure(); },
    down() { ensure(); if (el) el.style.scale = '0.78'; },
    up() { if (el) el.style.scale = '1'; },
    hide() { if (el) el.style.visibility = 'hidden'; },
    show() { if (el) el.style.visibility = ''; },
  };
  // Survive SPA re-renders that wipe <html>/<body> children.
  new MutationObserver(() => { if (el && !el.isConnected) ensure(); })
    .observe(document, { childList: true, subtree: true });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ensure);
  else ensure();
  // New document / new tab: start where the harness cursor last was.
  if (window.__pwCursorInit) {
    window.__pwCursorInit().then((p) => { if (p && !known) window.__pwCursor.move(p.x, p.y); }).catch(() => {});
  }
}

// ---------- run ----------
const browser = await chromium.launch(launchOptions);
const context = await browser.newContext(
  contextOptions({ recordVideo: { dir: videoTmp, size: VIEWPORT } }),
);
await seedPrefs(context);

const cur = { x: VIEWPORT.width / 2, y: VIEWPORT.height / 2 }; // harness-owned cursor position
if (cursor) {
  await context.exposeBinding('__pwCursorInit', () => ({ x: cur.x, y: cur.y }));
  await context.addInitScript(cursorInitScript);
}

const pages = [];
const videoT0 = new Map(); // page -> wall-clock ms when its recording started
context.on('page', (p) => {
  videoT0.set(p, Date.now());
  pages.push(p);
  if (process.env.DEBUG) p.on('console', (m) => console.log('console:', m.text().slice(0, 160)));
});

let page = await context.newPage();
await page.bringToFront();
const segments = []; // { page, start, end } in wall-clock ms
let segStart = null; // set after first navigation so the blank about:blank lead is dropped

const activate = async (p) => {
  const now = Date.now();
  if (segStart !== null && p !== page) segments.push({ page, start: segStart, end: now });
  if (p !== page || segStart === null) segStart = now;
  page = p;
  await page.bringToFront();
  // New-headless crops a re-fronted tab's screencast (~88px short) unless the viewport is re-applied.
  await page.setViewportSize({ width: VIEWPORT.width, height: VIEWPORT.height - 1 });
  await page.setViewportSize(VIEWPORT);
  await pushCursor();
};

async function pushCursor() {
  if (!cursor) return;
  await page.evaluate(([x, y]) => window.__pwCursor?.move(x, y), [cur.x, cur.y]).catch(() => {});
}
async function cursorCall(fn) {
  if (!cursor) return;
  await page.evaluate((f) => window.__pwCursor?.[f](), fn).catch(() => {});
}

// Target: "css selector" | {selector} | {text} | {role, name} ; optional exact, nth
function locate(t) {
  let loc;
  if (typeof t === 'string') loc = page.locator(t);
  else if (t.selector) loc = page.locator(t.selector);
  else if (t.role) loc = page.getByRole(t.role, { name: t.name, exact: t.exact });
  else if (t.text) loc = page.getByText(t.text, { exact: t.exact });
  else if (t.label) loc = page.getByLabel(t.label, { exact: t.exact });
  else if (t.placeholder) loc = page.getByPlaceholder(t.placeholder, { exact: t.exact });
  else throw new Error(`bad target: ${JSON.stringify(t)}`);
  return loc.filter({ visible: true }).nth(t.nth ?? 0);
}

const easeOut = (t) => 1 - Math.pow(1 - t, 3);
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

async function moveTo(x, y) {
  const dist = Math.hypot(x - cur.x, y - cur.y);
  const steps = Math.max(20, Math.min(30, Math.round(dist / 25)));
  const sx = cur.x, sy = cur.y;
  for (let i = 1; i <= steps; i++) {
    const k = easeOut(i / steps);
    cur.x = sx + (x - sx) * k;
    cur.y = sy + (y - sy) * k;
    await page.mouse.move(cur.x, cur.y);
    await pushCursor();
    await sleep(16);
  }
}

async function smoothWheel(dy, px = 30) {
  const steps = Math.max(12, Math.round(Math.abs(dy) / px));
  let done = 0;
  for (let i = 1; i <= steps; i++) {
    const target = Math.round(dy * easeInOut(i / steps));
    await page.mouse.wheel(0, target - done);
    done = target;
    await sleep(16);
  }
  await sleep(250);
}

// Bring the element into view with wheel scrolling (falls back to an instant jump).
async function centerOf(loc) {
  await loc.waitFor({ state: 'visible', timeout: 15000 });
  let box = await loc.boundingBox();
  // Only scroll when the target is actually (partly) off-screen; fixed footers sit near the edge.
  if (box && (box.y < 0 || box.y + box.height > VIEWPORT.height)) {
    const dy = box.y + box.height / 2 - VIEWPORT.height / 2;
    await page.mouse.move(Math.min(Math.max(box.x + box.width / 2, 1), VIEWPORT.width - 1), VIEWPORT.height / 2);
    await smoothWheel(dy);
    box = await loc.boundingBox();
    if (!box || box.y < 0 || box.y + box.height > VIEWPORT.height) {
      await loc.scrollIntoViewIfNeeded();
      box = await loc.boundingBox();
    }
  }
  if (!box) throw new Error('target has no bounding box');
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

async function clickAt(loc) {
  let c = await centerOf(loc);
  await moveTo(c.x, c.y);
  // Layout may shift while the cursor travels (rows expanding, toasts): follow the target.
  for (let i = 0; i < 3; i++) {
    await sleep(120);
    const b = await loc.boundingBox();
    if (!b) break;
    const n = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
    if (Math.hypot(n.x - c.x, n.y - c.y) < 3) break;
    c = n;
    await moveTo(c.x, c.y);
  }
  await cursorCall('down');
  await page.mouse.down();
  await sleep(90);
  await page.mouse.up();
  await cursorCall('up');
}

async function runStep(s) {
  if ('goto' in s) {
    await page.goto(s.goto, { waitUntil: 'load' });
    await settle(page);
    await pushCursor();
    if (segStart === null) segStart = Date.now();
    await sleep(s.pause ?? PAUSE);
  } else if ('click' in s) {
    await clickAt(locate(s.click));
    await sleep(s.pause ?? PAUSE);
  } else if ('fill' in s) {
    const loc = locate(s.fill);
    await clickAt(loc);
    await loc.fill('');
    await loc.pressSequentially(String(s.value), { delay: s.typeDelay ?? 60 });
    await sleep(s.pause ?? PAUSE);
  } else if ('hover' in s) {
    const c = await centerOf(locate(s.hover));
    await moveTo(c.x, c.y);
    await sleep(s.pause ?? PAUSE);
  } else if ('drag' in s) {
    const c = await centerOf(locate(s.drag));
    await moveTo(c.x, c.y);
    await sleep(150);
    await cursorCall('down');
    await page.mouse.down();
    const steps = s.steps ?? 40;
    for (let i = 1; i <= steps; i++) {
      const k = easeOut(i / steps);
      cur.x = c.x + (s.dx ?? 0) * k;
      cur.y = c.y + (s.dy ?? 0) * k;
      await page.mouse.move(cur.x, cur.y);
      await pushCursor();
      await sleep(16);
    }
    await page.mouse.up();
    await cursorCall('up');
    await sleep(s.pause ?? PAUSE);
  } else if ('wheel' in s) {
    const c = await centerOf(locate(s.wheel));
    await moveTo(c.x, c.y);
    const steps = s.steps ?? 6;
    for (let i = 0; i < steps; i++) {
      await page.mouse.wheel(0, s.deltaY / steps);
      await sleep(60);
    }
    await sleep(s.pause ?? PAUSE);
  } else if ('wait' in s) {
    await sleep(s.wait);
  } else if ('waitFor' in s) {
    await locate(s.waitFor).waitFor({ state: 'visible', timeout: s.timeout ?? 15000 });
  } else if ('scroll' in s) {
    // number = deltaY px ; {to: target} = scroll until target is centered
    if (typeof s.scroll === 'number') {
      if (s.at) { const c = await centerOf(locate(s.at)); await moveTo(c.x, c.y); }
      else await page.mouse.move(cur.x, cur.y);
      await smoothWheel(s.scroll, s.step);
    } else {
      const loc = locate(s.scroll.to);
      await loc.waitFor({ state: 'visible' });
      const box = await loc.boundingBox();
      await page.mouse.move(cur.x, cur.y);
      await smoothWheel(box.y + box.height / 2 - VIEWPORT.height / 2, s.step);
    }
    await sleep(s.pause ?? 300);
  } else if ('newTab' in s) {
    // string = open URL in a new tab ; target = click it and follow the popup
    let p;
    if (typeof s.newTab === 'string') {
      p = await context.newPage();
      await p.goto(s.newTab, { waitUntil: 'load' });
    } else {
      // context 'page' (not page 'popup') also catches window.open(..., 'noopener') tabs
      const opened = context.waitForEvent('page', { timeout: s.timeout ?? 15000 });
      opened.catch(() => {});
      await clickAt(locate(s.newTab));
      p = await opened;
    }
    await settle(p);
    await activate(p);
    await sleep(s.pause ?? TAB_PAUSE);
  } else if ('switchTab' in s) {
    // index (open order) or URL substring
    const p = typeof s.switchTab === 'number'
      ? pages[s.switchTab]
      : pages.find((q) => q.url().includes(s.switchTab));
    if (!p) throw new Error(`no tab for ${JSON.stringify(s.switchTab)}`);
    await activate(p);
    await sleep(s.pause ?? TAB_PAUSE);
  } else if ('evaluate' in s) {
    await page.evaluate(s.evaluate);
    await sleep(s.pause ?? 300);
  } else if ('screenshot' in s) {
    await settle(page, { idleTimeout: 3000 });
    await cursorCall('hide');
    await page.screenshot({ path: path.join(outDir, s.screenshot), fullPage: !!s.full });
    await cursorCall('show');
  } else {
    throw new Error(`unknown step: ${JSON.stringify(s)}`);
  }
}

let failed = null;
try {
  for (const [i, s] of scenario.steps.entries()) {
    console.log(`[${i}] ${JSON.stringify(s)}`);
    await runStep(s);
  }
  await sleep(scenario.tail ?? 800);
} catch (e) {
  failed = e;
  console.error(`step failed: ${e.message}`);
  await page.screenshot({ path: path.join(outDir, `${name}-FAILED.png`) }).catch(() => {});
}
segments.push({ page, start: segStart ?? videoT0.get(page), end: Date.now() });
const videoPaths = new Map();
for (const p of pages) videoPaths.set(p, await p.video().path());
await context.close();
await browser.close();

// ---------- stitch active-tab segments -> mp4 ----------
const out = path.join(outDir, `${name}${cursor ? '-cursor' : ''}.mp4`);
const inputs = [];
const filters = [];
segments.forEach((seg, i) => {
  const t0 = videoT0.get(seg.page);
  const a = Math.max(0, (seg.start - t0) / 1000);
  const b = Math.max(a + 0.05, (seg.end - t0) / 1000);
  inputs.push('-i', videoPaths.get(seg.page));
  filters.push(`[${i}:v]trim=start=${a.toFixed(3)}:end=${b.toFixed(3)},setpts=PTS-STARTPTS,fps=30,format=yuv420p[v${i}]`);
});
const concat = segments.map((_, i) => `[v${i}]`).join('') + `concat=n=${segments.length}:v=1:a=0[out]`;
execFileSync('ffmpeg', [
  '-y', '-loglevel', 'error', ...inputs,
  '-filter_complex', [...filters, concat].join(';'), '-map', '[out]',
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', '30',
  '-movflags', '+faststart', out,
], { stdio: 'inherit' });
if (!process.env.KEEP_WEBM) fs.rmSync(videoTmp, { recursive: true, force: true });
console.log(out);
if (failed) process.exit(1);

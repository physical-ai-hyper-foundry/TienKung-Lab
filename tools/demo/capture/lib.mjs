// Shared context setup for shot.mjs / flow.mjs.
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(HERE, '../../..');
export const OUT_ROOT = path.join(REPO_ROOT, 'outputs/fake-pages');
export const VIEWPORT = { width: 1920, height: 1080 };

// Full Chromium in new-headless mode renders WebGL on the GPU (Metal). The default
// chromium-headless-shell falls back to SwiftShader: ~2 fps on the 3D viewer pages.
export const launchOptions = { channel: 'chromium' };

// Relative output paths resolve against outputs/fake-pages/.
export const resolveOut = (p) => (path.isAbsolute(p) ? p : path.join(OUT_ROOT, p));

export const contextOptions = (extra = {}) => ({
  viewport: VIEWPORT,
  deviceScaleFactor: 2,
  locale: 'ko-KR',
  colorScheme: 'light',
  extraHTTPHeaders: { 'Accept-Language': 'ko-KR,ko;q=0.9' },
  ...extra,
});

// Seed app preferences before any page script runs (every navigation, every tab).
export async function seedPrefs(context) {
  await context.addInitScript(() => {
    try {
      localStorage.setItem('foundry.locale', 'ko');
      localStorage.setItem('lm_theme_v2', 'light');
    } catch {}
  });
}

// Network idle (best effort: pages that poll never go idle) + web fonts loaded.
export async function settle(page, { idleTimeout = 10000 } = {}) {
  await page.waitForLoadState('load').catch(() => {});
  await page.waitForLoadState('networkidle', { timeout: idleTimeout }).catch(() => {});
  await page.evaluate(() => document.fonts.ready.then(() => {})).catch(() => {});
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

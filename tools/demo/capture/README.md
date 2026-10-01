# demo capture

Playwright capture harness for the RL fake pages (plan: `docs/plan/2026-09-30-rl-fake-pages.md` §6). Setup: `npm install && npx playwright install chromium`. Relative output paths go under `outputs/fake-pages/`.

- Screenshot: `node shot.mjs <url> <out.png> [--full] [--wait <ms>] [--click <selector>]...` (viewport = `VIEWPORT` in lib.mjs, @2x, ko, light theme; `--click` takes Playwright selectors like `text=새 작업` / `role=button[name="학습 요청"]`)
- Flow video: `node flow.mjs --scenario <json> --out <dir> [--cursor]` → `<dir>/<name>[-cursor].mp4`. Scenarios live in `scenarios/`; step schema is in the header of `flow.mjs`, working example is `fixtures/scenario.json`.
- Self-test: `python3 -m http.server 8173 -d fixtures & python3 -m http.server 8174 -d fixtures & node flow.mjs --scenario fixtures/scenario.json --out _harness-test --cursor`

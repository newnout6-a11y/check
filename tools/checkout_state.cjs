// language: JavaScript (Node, .cjs), file: tools/checkout_state.cjs, target: Windows + Chrome по CDP
// РОЛЬ: ДИАГНОСТИКА. Состояние страницы после отправки: фреймы, текст, 3DS-фрейм.

// Состояние чекаута после отправки: фреймы, видимый текст, наличие 3DS-фрейма, вид окна (не fullPage).
// Запуск: node tools/checkout_state.cjs [cdp] [суффикс-имени]
const fs = require("fs");
const path = require("path");
const CDP = process.argv[2] || "http://127.0.0.1:9224";
const SUF = process.argv[3] || "state";
const TMP = process.env.TEMP || ".";
function resolvePlaywright() {
  const c = [];
  if (process.env.PLAYWRIGHT_CORE) c.push(process.env.PLAYWRIGHT_CORE);
  c.push("playwright-core");
  try {
    const npx = path.join(process.env.LOCALAPPDATA || "", "npm-cache", "_npx");
    for (const d of fs.readdirSync(npx)) { const p = path.join(npx, d, "node_modules", "playwright-core"); if (fs.existsSync(p)) c.push(p); }
  } catch (e) {}
  for (const x of c) { try { return require(x); } catch (e) {} }
  throw new Error("playwright-core не найден");
}
(async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find((p) => String(p.url()).includes("checkout.stripe.com")) || ctx.pages()[0];
  await page.bringToFront().catch(() => {});
  console.log("URL: " + String(page.url()).split("#")[0]);
  const frames = [];
  for (const f of page.frames()) {
    let t = "", has = [];
    try { t = await f.evaluate(() => (document.body ? document.body.innerText : "").replace(/\s+/g, " ").slice(0, 300)); } catch (e) {}
    try { has = await f.evaluate(() => Array.from(document.querySelectorAll("input,select,button")).map((e) => (e.id || e.name || e.tagName) + (e.textContent ? ":" + e.textContent.trim().slice(0, 22) : "")).slice(0, 12)); } catch (e) {}
    frames.push({ url: String(f.url()).slice(0, 80), text: t, controls: has });
  }
  for (const f of frames) {
    if (!f.text && !f.controls.length) continue;
    console.log("FRAME " + f.url);
    if (f.text) console.log("   text: " + f.text);
    if (f.controls.length) console.log("   ctrl: " + JSON.stringify(f.controls));
  }
  const tf = frames.filter((f) => /three|3ds|hooks\.stripe|challenge/i.test(f.url + " " + f.text));
  console.log("3DS-подобные фреймы: " + JSON.stringify(tf.map((f) => f.url)));
  const pay = page.frames().find((f) => f.url() === "" || true);
  // прокручиваем форму в поле зрения и снимаем ВИДИМУЮ область
  try {
    const target = page.frames().find(async () => false);
  } catch (e) {}
  for (const f of page.frames()) {
    try {
      const el = f.locator("input[id^=payment-], button:has-text(\"Подписаться\"), [data-testid*=payment]").first();
      if (await el.count()) { await el.scrollIntoViewIfNeeded().catch(() => {}); break; }
    } catch (e) {}
  }
  await page.waitForTimeout(1200);
  const shot = path.join(TMP, "proof_" + SUF + ".png");
  await page.screenshot({ path: shot }).catch(() => {});
  console.log("скриншот вида: " + shot);
  const html = [];
  for (const f of page.frames()) {
    try {
      const h = await f.evaluate(() => {
        const bad = Array.from(document.querySelectorAll("[class*=Error],[class*=error],[role=alert]")).map((e) => (e.innerText || "").trim()).filter(Boolean);
        const vis = Array.from(document.querySelectorAll("h1,h2,h3,p,span,div")).map((e) => (e.innerText || "").trim()).filter((t) => t && t.length < 160 && /ошиб|не удалось|отклон|провер|declined|verify|попроб/i.test(t));
        return { bad: bad.slice(0, 6), vis: Array.from(new Set(vis)).slice(0, 8) };
      });
      if (h.bad.length || h.vis.length) html.push({ url: String(f.url()).slice(0, 60), ...h });
    } catch (e) {}
  }
  console.log("СООБЩЕНИЯ: " + JSON.stringify(html, null, 1));
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

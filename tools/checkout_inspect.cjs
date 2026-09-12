// language: JavaScript (Node, .cjs), file: tools/checkout_inspect.cjs, target: Windows + Chrome по CDP
// Диагностика формы оплаты: что реально в DOM, какие фреймы, что происходит при клике по «Карта».
// Запуск: node tools/checkout_inspect.cjs [cdp]
const fs = require("fs");
const path = require("path");
const CDP = process.argv[2] || "http://127.0.0.1:9224";
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
  console.log("URL: " + page.url());
  const dump = async (tag) => {
    console.log("--- " + tag + " ---");
    for (const f of page.frames()) {
      let info = null;
      try {
        info = await f.evaluate(() => ({
          inputs: Array.from(document.querySelectorAll("input,select")).map((e) => (e.id || "-") + ":" + (e.name || "-") + ":" + (e.type || e.tagName)),
          radios: Array.from(document.querySelectorAll("input[type=radio]")).map((e) => e.value + "|checked=" + e.checked),
          cardCount: document.querySelectorAll("#cardNumber").length,
          mountPoints: Array.from(document.querySelectorAll("[id*=card],[class*=CardField],[data-testid*=card]")).slice(0, 6).map((e) => e.tagName + "#" + (e.id || "") + "." + String(e.className).slice(0, 40)),
        }));
      } catch (e) { info = { err: String(e.message).slice(0, 80) }; }
      console.log("  frame " + String(f.url()).slice(0, 70));
      console.log("    cardNumber=" + info.cardCount + " radios=" + JSON.stringify(info.radios || []));
      console.log("    inputs=" + JSON.stringify((info.inputs || []).slice(0, 30)));
      console.log("    mounts=" + JSON.stringify(info.mountPoints || []));
    }
  };
  await dump("ДО");
  const reqs = [];
  page.on("request", (r) => reqs.push(r.method() + " " + r.url().slice(0, 110)));
  const frame = page.frames().find((f) => ["elements", "js.stripe.com"].some((d) => f.url().includes(d))) || page.mainFrame();
  // клик по радиокнопке «Карта» изнутри самого элемента
  for (const f of page.frames()) {
    const n = await f.locator("input[type=radio]").count().catch(() => 0);
    if (!n) continue;
    const vals = [];
    for (let i = 0; i < n; i++) vals.push(await f.locator("input[type=radio]").nth(i).getAttribute("value").catch(() => "?"));
    console.log("радио в " + String(f.url()).slice(0, 60) + ": " + JSON.stringify(vals));
    const idx = vals.indexOf("card");
    if (idx >= 0) {
      console.log("жму .click() по радио card");
      await f.locator("input[type=radio]").nth(idx).evaluate((e) => e.click()).catch((e) => console.log("ошибка клика: " + e.message.slice(0, 60)));
    }
  }
  await page.waitForTimeout(4000);
  await dump("ПОСЛЕ 4с");
  await page.waitForTimeout(6000);
  await dump("ПОСЛЕ 10с");
  console.log("сеть за время клика:");
  for (const r of reqs.slice(-25)) console.log("  " + r);
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

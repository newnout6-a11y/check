// language: JavaScript (Node, .cjs), file: tools/checkout_fields.cjs, target: Windows + Chrome по CDP
// Снимает точные атрибуты полей платёжного фрейма и то, какие поля появляются после смены страны счёта.
// Запуск: node tools/checkout_fields.cjs [cdp]
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
  const payFrame = async () => {
    for (let i = 0; i < 20; i++) {
      for (const f of page.frames()) {
        try { if (await f.locator("input[id^=payment-]").count() > 0) return f; } catch (e) {}
      }
      await page.waitForTimeout(1000);
    }
    return null;
  };
  const dump = async (f, tag) => {
    console.log("=== " + tag + " ===");
    const data = await f.evaluate(() => ({
      fields: Array.from(document.querySelectorAll("input,select")).map((e) => ({
        id: e.id, name: e.name, type: e.type, ph: e.placeholder || "", aria: e.getAttribute("aria-label") || "",
        label: (e.labels && e.labels[0] ? (e.labels[0].innerText || "") : "").replace(/\s+/g, " ").slice(0, 40),
        val: e.type === "checkbox" || e.type === "radio" ? e.checked : String(e.value || "").slice(0, 20),
        options: e.tagName === "SELECT" ? Array.from(e.options).slice(0, 8).map((o) => o.value + ":" + o.textContent.trim().slice(0, 22)) : undefined,
      })),
      buttons: Array.from(document.querySelectorAll("button")).map((b) => (b.innerText || "").replace(/\s+/g, " ").trim().slice(0, 50)).filter(Boolean),
    }));
    for (const x of data.fields) console.log("  " + JSON.stringify(x));
    console.log("  buttons: " + JSON.stringify(data.buttons));
  };
  const f = await payFrame();
  if (!f) { console.log("платёжный фрейм не найден"); process.exit(3); }
  await dump(f, "КАК ЕСТЬ (страна по умолчанию)");
  const ctry = f.locator("select#payment-countryInput").first();
  if (await ctry.count()) {
    const opts = await ctry.evaluate((s) => Array.from(s.options).map((o) => o.value + ":" + o.textContent.trim()).filter((t) => /^US|United|США|Texas|Germany|DE/.test(t)));
    console.log("варианты: " + JSON.stringify(opts));
    try { await ctry.selectOption("US"); console.log("выбрал US"); } catch (e) { console.log("selectOption US: " + e.message.slice(0, 80)); }
    await page.waitForTimeout(4000);
    await dump(f, "ПОСЛЕ страны US");
  }
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

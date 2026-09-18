// language: JavaScript (Node, .cjs), file: tools/network_dump.cjs, target: Windows + Chrome по CDP
// РОЛЬ: ЗАМЕР. Полный список того, что страница чекаута дёргает у Stripe: чем её клиентский контур
// отличается от нашего HTTP-пути. Ничего не гасим — страница работает как обычно.
//
// Запуск: node tools/network_dump.cjs [cdp] [--click-pay] [--wait 45]
const fs = require("fs");
const path = require("path");
const CDP = process.argv.find((a) => a.startsWith("http")) || "http://127.0.0.1:9224";
const wi = process.argv.indexOf("--wait");
const WAIT_S = wi > 0 ? Number(process.argv[wi + 1]) : 45;

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
const INT = /(api\.stripe\.com|m\.stripe\.com|merchant-ui-api\.stripe\.com|js\.stripe\.com|b\.stripecdn\.com|hcaptcha\.com|newassets\.hcaptcha\.com|stripe\.network|q\.stripe\.com|r\.stripe\.com)/i;

(async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find((p) => String(p.url()).includes("checkout.stripe.com")) || ctx.pages()[0];
  console.log("PAGE " + String(page.url()).split("#")[0].slice(0, 96));

  const cdp = await ctx.newCDPSession(page);
  const seen = new Map();
  await cdp.send("Network.enable", {});
  cdp.on("Network.requestWillBeSent", (ev) => {
    const u = String(ev.request.url);
    if (!INT.test(u)) return;
    const key = ev.request.method + " " + u.split("?")[0].slice(0, 130);
    // Длинные ряды цифр в телах — это PAN/CVC: в дамп не попадают вовсе (гигиена секретов).
    const post = String(ev.request.postData || "").replace(/\d{9,}/g, "<цифры скрыты>").slice(0, 400);
    if (!seen.has(key)) seen.set(key, { method: ev.request.method, url: u.split("?")[0], type: ev.type, post });
  });

  await page.reload({ waitUntil: "domcontentloaded" }).catch(() => {});
  console.log("страница перезагружена, снимаю трафик " + WAIT_S + " с" + (process.argv.includes("--click-pay") ? " + клик по «Оплатить»" : ""));
  await page.waitForTimeout(9000);

  const frameFor = async (id) => { for (const f of page.frames()) { try { if (await f.locator("#" + id).first().count()) return f; } catch (e) {} } return null; };
  const setTxt = async (id, v) => { const f = await frameFor(id); if (!f) return; try { await f.locator("#" + id).first().fill(v, { timeout: 6000 }); await page.waitForTimeout(110); } catch (e) {} };
  if (process.argv.includes("--click-pay")) {
    await setTxt("cardNumber", "3793 6303 7433 153");
    await setTxt("cardExpiry", "11 / 27");
    await setTxt("cardCvc", "9179");
    await setTxt("billingName", "John Smith");
    await setTxt("billingPostalCode", "10001");
    const post = await frameFor("billingPostalCode");
    if (post) await post.locator("#billingPostalCode").first().press("Escape").catch(() => {});
    await page.waitForTimeout(400);
    for (const f of page.frames()) {
      let done = false;
      for (const lb of ["Оплатить и подписаться", "Подписаться", "Оплатить картой"]) {
        try { const c = f.locator("button:has-text(\"" + lb + "\")"); const n = await c.count();
          for (let i = 0; i < n; i++) { const el = c.nth(i); if (await el.isVisible()) { await el.click({ timeout: 8000 }).catch(() => {}); done = true; break; } }
        } catch (e) {}
        if (done) break;
      }
      if (done) break;
    }
    console.log("клик по «Оплатить» сделан");
  }
  const t0 = Date.now();
  while (Date.now() - t0 < WAIT_S * 1000) await page.waitForTimeout(1000);
  await cdp.send("Network.disable").catch(() => {});

  const rows = Array.from(seen.values()).sort((a, b) => (a.url < b.url ? -1 : 1));
  console.log("=== ЗАПРОСЫ (" + rows.length + ") ===");
  for (const r of rows) console.log(r.method + " " + r.url.slice(0, 118) + "  [" + r.type + "]");
  fs.writeFileSync(path.join("data", "network_dump.json"), JSON.stringify(rows, null, 1), "utf8");
  console.log("записан data/network_dump.json");
  process.exit(0);
})().catch((e) => { console.log("ERR " + String(e.message).split("\n")[0]); process.exit(1); });

// language: JavaScript (Node, .cjs), file: tools/letters_probe.cjs, target: Windows + Chrome по CDP
// РОЛЬ: ИССЛЕДОВАНИЕ. Какие буквенные маршруты принимает checkout.stripe.com и какой там лэйаут.

// Открывает одну и ту же живую сессию по разным буквенным маршрутам и сообщает, какой там лэйаут:
// где лежат поля карты (главный фрейм или фрейм Stripe), какие у них id и как подписана кнопка оплаты.
// Запуск: node tools/letters_probe.cjs <ссылка> [cdp]
const fs = require("fs");
const path = require("path");
const LINK = process.argv[2];
const CDP = process.argv[3] || "http://127.0.0.1:9224";
if (!LINK) { console.log("нужна ссылка"); process.exit(2); }
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
  const base = LINK.split("#")[0];
  const fid = LINK.includes("#") ? "#" + LINK.split("#")[1] : "";
  const cs = (base.match(/cs_live_[A-Za-z0-9]+/) || [""])[0];
  const browser = await pw.chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find((p) => String(p.url()).includes("checkout.stripe.com")) || ctx.pages()[0];
  await page.bringToFront().catch(() => {});
  const variants = ["pay/" + cs, "b/pay/" + cs, "c/pay/" + cs, "f/pay/" + cs, "g/pay/" + cs, "h/pay/" + cs, "r/pay/" + cs];
  for (const v of variants) {
    const url = "https://checkout.stripe.com/" + v + fid;
    await page.goto(url, { waitUntil: "commit", timeout: 60000 }).catch(() => {});
    await page.waitForTimeout(3500);
    let found = null, btn = "", text = "", letter = v.split("/")[0];
    for (const f of page.frames()) {
      try {
        const info = await f.evaluate(() => {
          const pick = (sel) => { const e = document.querySelector(sel); return e ? sel : null; };
          const ids = ["#cardNumber", "#payment-numberInput", "#card-number", "#cardNumber-input", "input[name=cardnumber]", "input[autocomplete=cc-number]"];
          let hit = null;
          for (const s of ids) { if (pick(s)) { hit = s; break; } }
          let b = "";
          for (const el of document.querySelectorAll("button")) { const t = (el.innerText || "").replace(/\s+/g, " ").trim(); if (/подписаться|оплатить/i.test(t)) { b = t.slice(0, 44); break; } }
          return { hit, b, t: (document.body ? document.body.innerText : "").replace(/\s+/g, " ").slice(0, 120) };
        });
        if (info.hit && !found) found = { frame: String(f.url()).slice(0, 46) || "(пусто)", sel: info.hit, btn: info.b };
        if (!btn && info.b) btn = info.b;
        if (!text && info.t) text = info.t;
      } catch (e) {}
    }
    console.log((found ? "OK  " : "НЕТ ") + v.padEnd(28) + " | поля: " + (found ? found.sel + " @ " + found.frame : "не найдены") + " | кнопка: " + (found && found.btn ? found.btn : btn || "—"));
    if (!found && text) console.log("      текст страницы: " + text.slice(0, 100));
  }
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

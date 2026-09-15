// language: JavaScript (Node, .cjs), file: tools/shift_watch.cjs, target: Windows + Chrome по CDP
// РОЛЬ: ДИАГНОСТИКА. Замер X поля карты по фазам прогона (нашёл scrollLeft=42 у панели).

// Ловит горизонтальный сдвиг: в пяти точках прогона снимает X поля карты, X самого документа фрейма
// и все ненулевые translate у предков. Ничего не меняет — только измеряет.
// Запуск: node tools/shift_watch.cjs <ссылка> [cdp] [файл-карт]
const fs = require("fs");
const path = require("path");
const LINK = process.argv[2];
const CDP = process.argv[3] || "http://127.0.0.1:9224";
const CARD_FILE = process.argv[4] || "data/amex_379363.txt";
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
function readCard() {
  const line = fs.readFileSync(CARD_FILE, "utf8").split(/\r?\n/).find((l) => l.includes("|"));
  const [pan, mm, yy, cvc] = line.trim().split("|");
  return { pan, mm, yy, cvc };
}
(async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find((p) => String(p.url()).includes("checkout.stripe.com")) || ctx.pages()[0];
  await page.bringToFront().catch(() => {});
  const probe = async () => {
    const out = [];
    for (const f of page.frames()) {
      let d = null;
      try {
        d = await f.evaluate(() => {
          const nums = ["#payment-numberInput", "#cardNumber"];
          let field = null;
          for (const s of nums) { const e = document.querySelector(s); if (e) { const r = e.getBoundingClientRect(); field = { sel: s, x: Math.round(r.x), y: Math.round(r.y) }; break; } }
          const docRect = document.documentElement.getBoundingClientRect();
          const shifted = [];
          for (const e of document.querySelectorAll("div,section,form,ul")) {
            const c = getComputedStyle(e);
            const m = c.transform;
            if (m && m !== "none") {
              const nums2 = m.match(/matrix\(([^)]+)\)/);
              if (nums2) { const p = nums2[1].split(",").map(Number); if (Math.abs(p[4]) > 0.5) shifted.push({ tag: e.tagName + "." + String(e.className).slice(0, 26), tx: Math.round(p[4]) }); }
            }
            if (e.scrollLeft) shifted.push({ tag: e.tagName + "." + String(e.className).slice(0, 26), scrollLeft: e.scrollLeft });
          }
          return { url: location.href.slice(0, 48), docX: Math.round(docRect.x), field, shifted: shifted.slice(0, 6) };
        });
      } catch (e) { continue; }
      if (d && (d.field || d.shifted.length)) out.push(d);
    }
    return out;
  };
  const show = (tag, rows) => {
    console.log("--- " + tag + " ---");
    for (const r of rows) {
      const f = r.field ? ("поле " + r.field.sel + " x=" + r.field.x + " y=" + r.field.y) : "поля нет";
      console.log("  [" + (r.url || "пусто") + "] докX=" + r.docX + " | " + f + (r.shifted.length ? " | сдвиги: " + JSON.stringify(r.shifted) : ""));
    }
  };
  await page.goto(LINK, { waitUntil: "commit", timeout: 90000 }).catch((e) => console.log("goto: " + e.message.split("\n")[0]));
  await page.waitForTimeout(6000);
  show("1. после загрузки", await probe());
  // разворот «Карта»
  for (const f of page.frames()) {
    try {
      const rows = f.locator("text=\"Карта\"");
      const n = await rows.count();
      for (let i = 0; i < n; i++) {
        const b = await rows.nth(i).boundingBox();
        if (b && b.height <= 60) { await page.mouse.click(Math.round(b.x + b.width / 2), Math.round(b.y + b.height / 2)); break; }
      }
    } catch (e) {}
  }
  await page.waitForTimeout(4000);
  show("2. после разворота карты", await probe());
  const card = readCard();
  const IDS = (await (async () => { for (const f of page.frames()) { try { if (await f.locator("#payment-numberInput").count()) return { num: "payment-numberInput", cty: "payment-countryInput", a1: "payment-addressLine1Input", city: "payment-localityInput", zip: "payment-postalCodeInput", st: "payment-administrativeAreaInput", exp: "payment-expiryInput", cvc: "payment-cvcInput", nm: "payment-nameInput" }; } catch (e) {} } return null; })())
    || { num: "cardNumber", cty: "billingCountry", a1: "billingAddressLine1", city: "billingLocality", zip: "billingPostalCode", st: "billingAdministrativeArea", exp: "cardExpiry", cvc: "cardCvc", nm: "billingName" };
  const set = async (id, v, sel) => {
    for (const f of page.frames()) {
      try {
        const el = f.locator("#" + id).first();
        if (!await el.count()) continue;
        if (sel) await el.selectOption(v).catch(() => {});
        else { await el.fill(v).catch(() => {}); if (/address/i.test(id)) await page.keyboard.press("Escape").catch(() => {}); }
        return;
      } catch (e) {}
    }
  };
  await set(IDS.cty, "US", true); await page.waitForTimeout(2500);
  await set(IDS.num, card.pan); await set(IDS.exp, card.mm + card.yy); await set(IDS.cvc, card.cvc);
  await set(IDS.nm, "JOSHUA SMITH");
  await set(IDS.city, "Austin"); await set(IDS.zip, "73301"); await set(IDS.st, "TX", true);
  await set(IDS.a1, "1401 Oak Street");
  await page.waitForTimeout(1500);
  show("3. после заполнения", await probe());
  for (const f of page.frames()) {
    try {
      const b = f.locator("button:has-text(\"Подписаться\")").first();
      if (await b.count()) { await b.click({ timeout: 8000 }).catch(() => {}); break; }
    } catch (e) {}
  }
  await page.waitForTimeout(9000);
  show("4. после клика", await probe());
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

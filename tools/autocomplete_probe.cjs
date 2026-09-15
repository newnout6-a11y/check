// language: JavaScript (Node, .cjs), file: tools/autocomplete_probe.cjs, target: Windows + Chrome по CDP
// РОЛЬ: ДИАГНОСТИКА. Чем реально закрывается панель подсказок адреса.

// Ищет, ЧЕМ реально закрывается панель подсказок адреса на широком лэйауте /f: перебирает Escape,
// кнопку закрытия панели, клик по свободному месту и клик по полю карты; после каждого способа
// сообщает, перекрыт ли центр кнопки оплаты. Ничего не отправляет.
// Запуск: node tools/autocomplete_probe.cjs <ссылка> [cdp] [файл-карт]
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
  await page.goto(LINK, { waitUntil: "commit", timeout: 90000 }).catch(() => {});
  await page.waitForTimeout(6000);
  const cardsVisible = async () => {
    for (const f of page.frames()) { try { if (await f.locator("#cardNumber, #payment-numberInput").first().isVisible()) return true; } catch (e) {} }
    return false;
  };
  if (!(await cardsVisible())) {
    for (let i = 0; i < 40; i++) {
      let ready = false;
      for (const f of page.frames()) { try { if (await f.locator("text=\"Карта\"").first().isVisible()) { ready = true; break; } } catch (e) {} }
      if (ready) {
        for (const f of page.frames()) {
          try {
            const rows = f.locator("text=\"Карта\""); const n = await rows.count();
            for (let k = 0; k < n; k++) { const b = await rows.nth(k).boundingBox(); if (b && b.height <= 140) { await page.mouse.click(Math.round(b.x + b.width / 2), Math.round(b.y + b.height / 2)); break; } }
          } catch (e) {}
        }
      }
      if (await cardsVisible()) break;
      await page.waitForTimeout(500);
    }
  }
  console.log("форма карты: " + (await cardsVisible()));
  const card = readCard();
  const set = async (id, v, sel) => {
    for (const f of page.frames()) {
      try { const el = f.locator("#" + id).first(); if (!(await el.count())) continue; if (sel) await el.selectOption(v).catch(() => {}); else await el.fill(v).catch(() => {}); return; } catch (e) {}
    }
  };
  await set("billingCountry", "US", true);
  await page.waitForTimeout(2500);
  for (const s of ["locality", "postalCode"]) { }
  await set("billingLocality", "Austin"); await set("billingPostalCode", "73301"); await set("billingAdministrativeArea", "TX", true);
  await set("cardNumber", card.pan); await set("cardExpiry", card.mm + card.yy); await set("cardCvc", card.cvc); await set("billingName", "JOSHUA SMITH");
  await set("billingAddressLine1", "1401 Oak Street");
  await page.waitForTimeout(2500);

  const state = async (tag) => {
    const rows = [];
    for (const f of page.frames()) {
      try {
        const r = await f.evaluate(() => {
          const panelWords = /Рекомендации|AddressAutocomplete/;
          const panel = Array.from(document.querySelectorAll("div,ul,span")).find((e) => panelWords.test(e.className || "") && e.getBoundingClientRect().height > 40);
          const btn = Array.from(document.querySelectorAll("button")).find((b) => /Подписаться/.test(b.innerText || ""));
          let owner = "нет кнопки";
          if (btn) {
            const r2 = btn.getBoundingClientRect();
            const el = document.elementFromPoint(r2.x + r2.width / 2, r2.y + r2.height / 2);
            owner = el ? (el.closest("button") === btn ? "self" : el.tagName + "." + String(el.className).slice(0, 40)) : "none";
          }
          const pbox = panel ? panel.getBoundingClientRect() : null;
          const closers = panel ? Array.from(panel.querySelectorAll("button,[role=button]")).map((b) => b.tagName + ":" + (b.getAttribute("aria-label") || b.innerText || "").slice(0, 20)) : [];
          return {
            hasPanel: !!panel,
            panelBox: pbox ? [Math.round(pbox.x), Math.round(pbox.y), Math.round(pbox.width), Math.round(pbox.height)] : null,
            closers,
            owner,
            results: document.querySelectorAll("[class*=AddressAutocomplete-result]").length,
          };
        });
        if (r.hasPanel || r.owner !== "нет кнопки") rows.push({ frame: String(f.url()).slice(0, 44) || "(пусто)", ...r });
      } catch (e) {}
    }
    console.log("--- " + tag + " ---");
    for (const r of rows) console.log("  [" + r.frame + "] панель=" + r.hasPanel + " бокс=" + JSON.stringify(r.panelBox) + " результатов=" + r.results + " центр кнопки=" + r.owner + " кнопки панели=" + JSON.stringify(r.closers));
    return rows;
  };
  await state("до попыток закрытия");
  await page.keyboard.press("Escape").catch(() => {});
  await page.waitForTimeout(400);
  await state("после Escape");
  for (const f of page.frames()) {
    try {
      const c = f.locator("button[aria-label], [role=button]").first();
      const n = await c.count();
      if (!n) continue;
      const cands = await f.evaluate(() => Array.from(document.querySelectorAll("button,[role=button]")).map((b) => b.getAttribute("aria-label") || b.innerText || "").filter(Boolean).slice(0, 8));
      if (cands.length) console.log("  кнопки во фрейме " + String(f.url()).slice(0, 40) + ": " + JSON.stringify(cands));
    } catch (e) {}
  }
  // клик по свободному месту слева (вне платёжного блока)
  await page.mouse.click(60, 400).catch(() => {});
  await page.waitForTimeout(500);
  await state("после клика в пустой области слева");
  // клик по полю номера карты
  for (const f of page.frames()) { try { const el = f.locator("#cardNumber").first(); if (await el.count()) { await el.click({ timeout: 3000 }).catch(() => {}); break; } } catch (e) {} }
  await page.waitForTimeout(500);
  await state("после клика по номеру карты");
  // клик по первому результату подсказки
  for (const f of page.frames()) {
    try {
      const r0 = f.locator("[class*=AddressAutocomplete-result]").first();
      if (await r0.count() && await r0.isVisible()) { await r0.click({ timeout: 4000 }).catch(() => {}); console.log("  выбрал первый результат подсказки"); break; }
    } catch (e) {}
  }
  await page.waitForTimeout(1500);
  await state("после выбора результата подсказки");
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

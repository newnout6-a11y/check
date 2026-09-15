// language: JavaScript (Node, .cjs), file: tools/esc_probe.cjs, target: Windows + Chrome по CDP
// Проверяет, чем реально закрывается панель подсказок адреса: Escape ПО ЭЛЕМЕНТУ (el.press), Escape
// после focus(), Escape после мышиного клика по полю. Печатает результат и сохраняет ли адрес.
// Запуск: node tools/esc_probe.cjs [cdp]
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
  await page.bringToFront().catch(() => {});
  console.log("вкладка: " + String(page.url()).split("#")[0].slice(0, 70));
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
      await page.waitForTimeout(400);
    }
  }
  console.log("форма карты: " + (await cardsVisible()));
  const ids = (await cardsVisible() && await (async () => { for (const f of page.frames()) { try { if (await f.locator("#cardNumber").count()) return { a1: "billingAddressLine1", cty: "billingCountry", city: "billingLocality", zip: "billingPostalCode", st: "billingAdministrativeArea", num: "cardNumber" }; } catch (e) {} } return null; })())
    || { a1: "payment-addressLine1Input", cty: "payment-countryInput", city: "payment-localityInput", zip: "payment-postalCodeInput", st: "payment-administrativeAreaInput", num: "payment-numberInput" };
  const field = async (id) => { for (const f of page.frames()) { try { const el = f.locator("#" + id).first(); if (await el.count()) return el; } catch (e) {} } return null; };
  const sugg = async () => { for (const f of page.frames()) { try { const c = f.locator("[class*=AddressAutocomplete-result]"); const n = await c.count(); for (let i = 0; i < n; i++) { if (await c.nth(i).isVisible()) return n; } } catch (e) {} } return 0; };
  const cty = await field(ids.cty); if (cty) { await cty.selectOption("US").catch(() => {}); await page.waitForTimeout(2500); }
  const a1 = await field(ids.a1);
  if (!a1) { console.log("поля адреса нет"); process.exit(3); }
  await a1.fill("1401 Oak Street").catch(() => {});
  await page.waitForTimeout(2000);
  console.log("после ввода: подсказок на экране = " + (await sugg()) + ", значение = " + JSON.stringify(await a1.inputValue().catch(() => "?")));
  // способ 1: Escape по самому элементу
  await a1.press("Escape").catch((e) => console.log("  el.press ошибка: " + e.message.slice(0, 50)));
  await page.waitForTimeout(500);
  let left = await sugg();
  console.log("СПОСОБ 1 (el.press Escape): подсказок = " + left + ", адрес = " + JSON.stringify(await a1.inputValue().catch(() => "?")));
  if (left) {
    await a1.focus().catch(() => {});
    await page.waitForTimeout(200);
    await a1.press("Escape").catch(() => {});
    await page.waitForTimeout(500);
    left = await sugg();
    console.log("СПОСОБ 2 (focus + el.press): подсказок = " + left + ", адрес = " + JSON.stringify(await a1.inputValue().catch(() => "?")));
  }
  if (left) {
    const b = await a1.boundingBox();
    if (b) { await page.mouse.click(Math.round(b.x + b.width / 2), Math.round(b.y + b.height / 2)); await page.waitForTimeout(300); }
    await a1.press("Escape").catch(() => {});
    await page.waitForTimeout(500);
    left = await sugg();
    console.log("СПОСОБ 3 (клик по полю + Escape): подсказок = " + left + ", адрес = " + JSON.stringify(await a1.inputValue().catch(() => "?")));
  }
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

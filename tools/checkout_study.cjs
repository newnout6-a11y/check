// language: JavaScript (Node, .cjs), file: tools/checkout_study.cjs, target: Windows + Chrome по CDP
// Полная съёмка страницы оплаты Stripe: все запросы/ответы, WebSocket-кадры, перехваты fetch/XHR/beacon,
// красные тексты DOM с таймстампами. Кладёт отчёт в data/results/checkout_study_<ts>.json.
//
// Запуск: node tools/checkout_study.cjs <ссылка> [cdp-url] [карта-файл] [секунд-наблюдения]
// Карта: строки CC|MM|YY|CVV берутся из файла (по умолчанию data/amex_379363.txt, первая строка).
const fs = require("fs");
const path = require("path");

const LINK = process.argv[2];
const CDP = process.argv[3] || "http://127.0.0.1:9224";
const CARD_FILE = process.argv[4] || "data/amex_379363.txt";
const WATCH_S = Number(process.argv[5] || 45);
if (!LINK) { console.log("нужна ссылка"); process.exit(2); }

function resolvePlaywright() {
  const candidates = [];
  if (process.env.PLAYWRIGHT_CORE) candidates.push(process.env.PLAYWRIGHT_CORE);
  candidates.push("playwright-core");
  try {
    const npxRoot = path.join(process.env.LOCALAPPDATA || "", "npm-cache", "_npx");
    for (const dir of fs.readdirSync(npxRoot)) {
      const p = path.join(npxRoot, dir, "node_modules", "playwright-core");
      if (fs.existsSync(p)) candidates.push(p);
    }
  } catch (e) {}
  for (const c of candidates) { try { return require(c); } catch (e) {} }
  throw new Error("playwright-core не найден");
}

function readCard() {
  try {
    const line = fs.readFileSync(CARD_FILE, "utf8").split(/\r?\n/).find((l) => l.includes("|"));
    if (!line) return null;
    const [pan, mm, yy, cvc] = line.trim().split("|");
    return { pan, mm, yy, cvc };
  } catch (e) { return null; }
}

const HOOK = `window.__cap = {fetch:[], xhr:[], beacon:[], errors:[]};
const of = window.fetch;
window.fetch = async function(u, o){
  const rec = {t: Date.now(), url: String((u && u.url) || u), method: (o && o.method) || "GET", body: String((o && o.body) || "").slice(0, 4000)};
  window.__cap.fetch.push(rec);
  try { const r = await of.apply(this, arguments); rec.status = r.status; return r; } catch (e) { rec.error = String(e); throw e; }
};
const os = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(b){ try { window.__cap.xhr.push({t: Date.now(), url: String(this.__u||""), body: String(b||"").slice(0,4000), method: this.__m||""}); } catch(e){} return os.apply(this, arguments); };
const oo = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(m,u){ this.__u=u; this.__m=m; return oo.apply(this, arguments); };
const ob = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);
if (ob) navigator.sendBeacon = function(u, d){ try { window.__cap.beacon.push({t: Date.now(), url: String(u), body: String(d||"").slice(0,1000)}); } catch(e){} return ob(u,d); };
const mo = new MutationObserver(() => {
  try {
    for (const el of document.querySelectorAll("*")) {
      if (el.children.length) continue;
      const txt = (el.textContent || "").replace(/\\s+/g, " ").trim();
      if (!txt || txt.length > 160) continue;
      if (/отклон|неверн|верифиц|истек|try again|declin|incorrect|обязательн|не удалось|captcha|проверк/i.test(txt)) {
        const last = window.__cap.errors[window.__cap.errors.length - 1];
        if (!last || last.text !== txt) window.__cap.errors.push({t: Date.now(), text: txt});
      }
    }
  } catch (e) {}
});
try { mo.observe(document.documentElement || document, {subtree: true, childList: true, characterData: true}); } catch (e) {}
`;

(async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find((p) => p.url().includes("kimi")) || ctx.pages()[0];
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Page.enable");
  await cdp.send("Page.addScriptToEvaluateOnNewDocument", { source: HOOK }).catch(() => {});

  const requests = [];
  const responses = [];
  const sockets = [];
  const t0 = Date.now();
  const rel = () => Date.now() - t0;

  page.on("request", (r) => {
    requests.push({ t: rel(), method: r.method(), url: r.url(), type: r.resourceType(), frame: (r.frame() && r.frame().url().slice(0, 90)) || "", body: String(r.postData() || "").slice(0, 3000), headers: Object.fromEntries(Object.entries(r.headers()).filter(([k]) => /authorization|cookie|x-|content-type|accept/i.test(k)).slice(0, 12)) });
  });
  page.on("response", async (res) => {
    const rec = { t: rel(), url: res.url(), status: res.status(), ct: (res.headers()["content-type"] || "").slice(0, 40) };
    if (/json|text/.test(rec.ct) && res.request().resourceType() !== "image") {
      try { rec.snippet = String(await res.text()).replace(/\\s+/g, " ").slice(0, 400); } catch (e) {}
    }
    responses.push(rec);
  });
  page.on("websocket", (ws) => {
    const rec = { url: ws.url(), sent: [], received: [] };
    sockets.push(rec);
    ws.on("framesent", (f) => { if (rec.sent.length < 40) rec.sent.push({ t: rel(), d: String(f.payload).slice(0, 300) }); });
    ws.on("framereceived", (f) => { if (rec.received.length < 40) rec.received.push({ t: rel(), d: String(f.payload).slice(0, 300) }); });
  });
  const hookFrames = () => { for (const f of page.frames()) { try { if (!f.__hooked) { f.__hooked = true; f.on("request", (r) => requests.push({ t: rel(), method: r.method(), url: r.url(), type: r.resourceType(), frame: "child:" + f.url().slice(0, 60), body: String(r.postData() || "").slice(0, 2000) })); } } catch (e) {} } };

  await page.goto(LINK, { waitUntil: "commit", timeout: 60000 }).catch((e) => console.log("goto: " + e.message.split("\n")[0]));
  const waitForm = async () => { for (let i = 0; i < 30; i++) { hookFrames(); for (const f of page.frames()) { try { if (await f.locator("button:has-text(\"Подписаться\")").count() > 0) return f; } catch (e) {} } await page.waitForTimeout(1000); } return null; };
  const form = await waitForm();
  console.log("форма найдена: " + !!form + " | запросов на загрузке: " + requests.length);
  if (!form) { fs.writeFileSync("data/results/checkout_study_noload.json", JSON.stringify({ requests }, null, 1)); process.exit(0); }

  const card = readCard();
  if (card) {
    const radio = form.locator("input[value=card]").first();
    if (await radio.count()) await radio.click({ force: true }).catch(() => {});
    await page.waitForTimeout(3000);
    const plan = [["cardNumber", card.pan], ["cardExpiry", card.mm + card.yy], ["cardCvc", card.cvc], ["billingName", "JOSHUA SMITH"], ["billingAddressLine1", "1401 Oak Street"], ["billingLocality", "Austin"], ["billingPostalCode", "73301"]];
    for (const ff of page.frames()) {
      let names = [];
      try { names = await ff.evaluate(() => Array.from(document.querySelectorAll("input")).map((e) => e.name || "")); } catch (e) { continue; }
      for (let i = 0; i < names.length; i++) {
        const hit = plan.find((p) => names[i] === p[0]);
        if (!hit) continue;
        try { const el = ff.locator("input").nth(i); await el.click({ timeout: 5000 }); await page.keyboard.press("Control+A"); await page.keyboard.press("Backspace"); await page.keyboard.type(hit[1], { delay: 45 }); await page.waitForTimeout(250); } catch (e) {}
      }
    }
  } else { console.log("карта не прочитана — заполняю только адрес нельзя, пропускаю ввод"); }

  const before = requests.length;
  // Модалки Link/вход перекрывают кнопку и обычный клик истекает: закрываем их и жмём с force.
  for (const sel of ["[aria-label=\"Close\"]", "button[aria-label*=\"акрыть\"]", "button[aria-label*=\"lose\"]", "[data-testid*=close]"]) {
    const el = form.locator(sel).first();
    if (await el.count()) { await el.click({ force: true }).catch(() => {}); await page.waitForTimeout(400); }
  }
  await page.keyboard.press("Escape").catch(() => {});
  await page.waitForTimeout(700);
  const payBtn = form.locator("button:has-text(\"Подписаться\")").first();
  try {
    await payBtn.scrollIntoViewIfNeeded().catch(() => {});
    await payBtn.click({ force: true, timeout: 12000 });
    console.log("клик по кнопке оплаты выполнен");
  } catch (e) {
    console.log("клик не прошёл (" + e.message.split("\n")[0].slice(0, 60) + "), пробую dispatchEvent");
    await form.locator("button:has-text(\"Подписаться\")").first().dispatchEvent("click").catch(() => {});
  }
  console.log("нажал оплату, наблюдаю " + WATCH_S + " с");
  for (let i = 0; i < WATCH_S; i += 5) { await page.waitForTimeout(5000); hookFrames(); }

  const cap = {};
  for (const f of page.frames()) {
    try { const c = await f.evaluate(() => window.__cap || null); if (c) cap[(f.url() || "main").slice(0, 80)] = c; } catch (e) {}
  }
  const out = { link: LINK.split("#")[0], started: new Date().toISOString(), requests, responses, sockets, cap,
                counts: { requests: requests.length, after_submit: requests.length - before, responses: responses.length, sockets: sockets.length } };
  fs.mkdirSync("data/results", { recursive: true });
  const name = "data/results/checkout_study_" + new Date().toISOString().replace(/[-:T]/g, "").slice(0, 15) + ".json";
  fs.writeFileSync(name, JSON.stringify(out, null, 1));
  console.log("отчёт: " + name + " | запросов " + requests.length + " (после submit +" + (requests.length - before) + "), ответов " + responses.length + ", сокетов " + sockets.length);
  const host = {};
  for (const r of requests) { const h = r.url.replace(/^https?:\/\//, "").split("/")[0]; host[h] = (host[h] || 0) + 1; }
  console.log("хосты: " + JSON.stringify(Object.entries(host).sort((a, b) => b[1] - a[1]).slice(0, 12)));
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });
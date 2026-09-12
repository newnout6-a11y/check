// language: JavaScript (Node, .cjs), file: tools/checkout_submit_probe.cjs, target: Windows + Chrome по CDP
// Доводит страницу оплаты до отправки: полностью заполняет карту+адрес, закрывает оверлеи, жмёт кнопку
// и снимает ТОЛЬКО то, что делает сама страница — в первую очередь payment_pages/{cs}/confirm с его
// реальным passive_captcha_token, guid/muid/sid, js_checksum и px3. Кладёт отчёт в data/results/.
//
// Запуск: node tools/checkout_submit_probe.cjs <ссылка> [cdp] [файл-карт] [секунд]
const fs = require("fs");
const path = require("path");
const LINK = process.argv[2];
const CDP = process.argv[3] || "http://127.0.0.1:9224";
const CARD_FILE = process.argv[4] || "data/amex_379363.txt";
const WATCH_S = Number(process.argv[5] || 90);
if (!LINK) { console.log("нужна ссылка"); process.exit(2); }

function resolvePlaywright() {
  const c = [];
  if (process.env.PLAYWRIGHT_CORE) c.push(process.env.PLAYWRIGHT_CORE);
  c.push("playwright-core");
  try {
    const npx = path.join(process.env.LOCALAPPDATA || "", "npm-cache", "_npx");
    for (const d of fs.readdirSync(npx)) {
      const p = path.join(npx, d, "node_modules", "playwright-core");
      if (fs.existsSync(p)) c.push(p);
    }
  } catch (e) {}
  for (const x of c) { try { return require(x); } catch (e) {} }
  throw new Error("playwright-core не найден");
}

function readCard() {
  try {
    const line = fs.readFileSync(CARD_FILE, "utf8").split(/\r?\n/).find((l) => l.includes("|"));
    const [pan, mm, yy, cvc] = line.trim().split("|");
    return { pan, mm, yy, cvc };
  } catch (e) { return null; }
}

(async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();   // свежая вкладка: капча инициализируется заново
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("Page.enable");
  await cdp.send("Page.addScriptToEvaluateOnNewDocument", { source: `window.__cap=[];
    const of=window.fetch; window.fetch=function(u,o){try{window.__cap.push({t:Date.now(),u:String((u&&u.url)||u),b:String((o&&o.body)||"").slice(0,4000)});}catch(e){} return of.apply(this,arguments);};
    const os=XMLHttpRequest.prototype.send; XMLHttpRequest.prototype.send=function(b){try{window.__cap.push({t:Date.now(),u:String(this.__u||""),b:String(b||"").slice(0,4000)});}catch(e){} return os.apply(this,arguments);};
    const oo=XMLHttpRequest.prototype.open; XMLHttpRequest.prototype.open=function(m,u){this.__u=u;return oo.apply(this,arguments);};` }).catch(() => {});

  const events = [];
  const confirms = [];
  page.on("request", (r) => {
    const u = r.url();
    events.push({ t: Date.now(), m: r.method(), u: u.slice(0, 140) });
    if (/payment_pages\/[^/]+\/confirm$/.test(u)) {
      const buf = r.postDataBuffer();
      confirms.push({ u: u.slice(0, 140), body: buf ? buf.toString("utf8").slice(0, 6000) : String(r.postData() || "").slice(0, 6000) });
    }
  });
  page.on("response", async (res) => {
    if (/payment_pages\/[^/]+\/confirm$/.test(res.url())) {
      let snip = "";
      try { snip = String(await res.text()).replace(/\s+/g, " ").slice(0, 400); } catch (e) {}
      confirms.push({ u: res.url().slice(0, 140), status: res.status(), response: snip });
    }
  });

  await page.goto(LINK, { waitUntil: "commit", timeout: 60000 }).catch((e) => console.log("goto: " + e.message.split("\n")[0]));
  const form = async () => { for (let i = 0; i < 30; i++) { for (const f of page.frames()) { try { if (await f.locator("button:has-text(\"Подписаться\")").count() > 0) return f; } catch (e) {} } await page.waitForTimeout(1000); } return null; };
  let f = await form();
  console.log("форма: " + !!f);
  if (!f) { process.exit(0); }
  const card = readCard();
  const radio = f.locator("input[value=card]").first();
  if (await radio.count()) await radio.click({ force: true }).catch(() => {});
  await page.waitForTimeout(3000);
  const plan = [["cardNumber", card ? card.pan : ""], ["cardExpiry", card ? card.mm + card.yy : ""], ["cardCvc", card ? card.cvc : ""],
                ["billingName", "JOSHUA SMITH"], ["billingAddressLine1", "1401 Oak Street"],
                ["billingLocality", "Austin"], ["billingPostalCode", "73301"]];
  const filled = [];
  for (const ff of page.frames()) {
    let names = [];
    try { names = await ff.evaluate(() => Array.from(document.querySelectorAll("input,select")).map((e) => e.name || "")); } catch (e) { continue; }
    for (let i = 0; i < names.length; i++) {
      const hit = plan.find((p) => names[i] === p[0] && p[1]);
      if (!hit) continue;
      try {
        const el = ff.locator("input,select").nth(i);
        await el.click({ timeout: 5000 });
        await page.keyboard.press("Control+A"); await page.keyboard.press("Backspace");
        await page.keyboard.type(hit[1], { delay: 45 });
        await page.waitForTimeout(300);
        const v = await el.inputValue().catch(() => "?");
        filled.push(names[i] + "=" + v);
      } catch (e) {}
    }
  }
  console.log("заполнено: " + JSON.stringify(filled));
  for (const sel of ["[aria-label=\"Close\"]", "button[aria-label*=\"акрыть\"]", "[data-testid*=close]"]) {
    const el = f.locator(sel).first();
    if (await el.count()) { await el.click({ force: true }).catch(() => {}); await page.waitForTimeout(400); }
  }
  await page.keyboard.press("Escape").catch(() => {});
  await page.waitForTimeout(800);
  const btn = f.locator("button:has-text(\"Подписаться\")").first();
  try { await btn.scrollIntoViewIfNeeded().catch(() => {}); await btn.click({ force: true, timeout: 12000 }); console.log("клик выполнен"); }
  catch (e) { console.log("клик не прошёл: " + e.message.split("\n")[0].slice(0, 60)); await btn.dispatchEvent("click").catch(() => {}); }
  for (let i = 0; i < WATCH_S; i += 3) {
    await page.waitForTimeout(3000);
    if (confirms.some((c) => c.body)) break;
  }
  const cap = {};
  for (const ff of page.frames()) { try { const c = await ff.evaluate(() => window.__cap || null); if (c && c.length) cap[(ff.url() || "main").slice(0, 60)] = c.slice(-25); } catch (e) {} }
  const out = { link: LINK.split("#")[0], started: new Date().toISOString(), filled, confirms, tail_events: events.slice(-60), cap };
  fs.mkdirSync("data/results", { recursive: true });
  const name = "data/results/submit_probe_" + new Date().toISOString().replace(/[-:T]/g, "").slice(0, 15) + ".json";
  fs.writeFileSync(name, JSON.stringify(out, null, 1));
  console.log("confirm-записей: " + confirms.length + " | отчёт: " + name);
  for (const c of confirms) {
    console.log("--- " + (c.status ? ("RES " + c.status + " " + (c.response || "").slice(0, 200)) : ("REQ " + c.body.slice(0, 400))));
  }
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });
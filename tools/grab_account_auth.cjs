// language: JavaScript (Node, .cjs), file: tools/grab_account_auth.cjs, target: Windows 10/11 + любой Chrome с CDP
// Снимает токен аккаунта kimi.ai с УЖЕ ОТКРЫТОГО Chrome по CDP и пишет data/account_auth.json,
// который читает account_rotator.py. Так ротация не зависит ни от браузера, ни от платформы:
// программа-потребитель читает только файл.
//
// Запуск:  node tools/grab_account_auth.cjs [cdp-url] [output-path]
// По умолчанию: http://127.0.0.1:9224  ->  data/account_auth.json
const fs = require("fs");
const path = require("path");

const CDP = process.argv[2] || "http://127.0.0.1:9224";
const OUT = process.argv[3] || "data/account_auth.json";

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
  throw new Error("playwright-core не найден: задай PLAYWRIGHT_CORE=<путь к node_modules/playwright-core>");
}

(async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.connectOverCDP(CDP);
  let page = null;
  for (const ctx of browser.contexts()) {
    for (const p of ctx.pages()) if (p.url().includes("kimi")) page = p;
  }
  if (!page) {
    // Вкладки kimi.ai может не быть (например, вкладку увели на checkout.stripe.com).
    // Тогда открываем её сами: загрузка SPA как раз и обновит токены через refresh.
    console.log("вкладки kimi.ai нет — открываю www.kimi.ai/mykimi");
    page = await browser.contexts()[0].newPage();
    await page.goto("https://www.kimi.ai/mykimi", { waitUntil: "commit", timeout: 60000 }).catch(() => {});
    await page.waitForTimeout(12000);
  }

  const captured = { headers: {} };
  page.on("request", (r) => {
    if (captured.token || !r.url().includes("/apiv2/")) return;
    const h = r.headers();
    if (h.authorization && String(h.authorization).startsWith("Bearer eyJ")) {
      captured.token = String(h.authorization).slice(7);
      for (const k of ["x-msh-session-id", "x-msh-device-id", "x-traffic-id", "x-msh-version", "x-msh-platform", "x-language"]) {
        if (h[k]) captured.headers[k] = String(h[k]);
      }
    }
  });

  try { await page.reload({ waitUntil: "commit", timeout: 60000 }); } catch (e) {}
  await page.waitForTimeout(6000);

  const store = await page.evaluate(() => ({
    access: localStorage.getItem("access_token") || "",
    refresh: localStorage.getItem("refresh_token") || "",
  }));
  if (!captured.token) captured.token = store.access;
  if (!captured.token) throw new Error("токен не найден: ни в запросах, ни в localStorage");

  const outPath = path.resolve(process.cwd(), OUT);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  const payload = { access_token: captured.token };
  // refresh_token кладём рядом: ручка обновления пока не найдена (живой перебор имён дал 404), но данные
  // не помешают, когда она понадобится. Токен доступа живёт считанные минуты, поэтому файл обновляют
  // повторным запуском этого скрипта.
  if (store.refresh) payload.refresh_token = store.refresh;
  if (Object.keys(captured.headers).length) payload.headers = captured.headers;
  fs.writeFileSync(outPath, JSON.stringify(payload, null, 2) + "\n", "utf8");
  console.log("токен аккаунта сохранён: " + outPath);
  console.log("длина токена: " + captured.token.length + " | заголовков из живых запросов: " + Object.keys(captured.headers).length);
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message); process.exit(1); });
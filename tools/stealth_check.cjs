// language: JavaScript (Node, .cjs), file: tools/stealth_check.cjs, target: Windows + Chrome по CDP
// Измеряет, что видит страница чекаута: флаги автоматизации, подменённые builtin-функции, следы CDP,
// отпечаток железа, наличие наших хуков. Ничего не патчит — только читает.
// Запуск: node tools/stealth_check.cjs [cdp]
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
  console.log("страница: " + String(page.url()).split("#")[0].slice(0, 70));
  const main = page.mainFrame();
  const res = await main.evaluate(() => {
    const out = {};
    out.webdriver = navigator.webdriver;
    out.ua = navigator.userAgent;
    out.platform = navigator.platform;
    out.langs = navigator.languages;
    out.cores = navigator.hardwareConcurrency;
    out.mem = navigator.deviceMemory;
    out.chromeObj = typeof window.chrome === "object";
    out.plugins = navigator.plugins.length;
    out.mimes = navigator.mimeTypes.length;
    out.outerInner = [window.outerWidth, window.innerWidth, window.outerHeight, window.innerHeight];
    out.hasFocus = document.hasFocus();
    try {
      const c = document.createElement("canvas");
      const gl = c.getContext("webgl");
      const dbg = gl.getExtension("WEBGL_debug_renderer_info");
      out.glVendor = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : "нет dbg";
      out.glRender = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "нет dbg";
    } catch (e) { out.glVendor = "ошибка"; }
    // подмена builtin: у нативных функций toString содержит "native code"
    const nat = (f) => { try { return /\{\s*\[native code\]\s*\}/.test(Function.prototype.toString.call(f)); } catch (e) { return "?"; } };
    out.native = {
      fetch: typeof window.fetch === "function" ? nat(window.fetch) : "нет",
      xhrOpen: typeof XMLHttpRequest !== "undefined" ? nat(XMLHttpRequest.prototype.open) : "нет",
      xhrSend: typeof XMLHttpRequest !== "undefined" ? nat(XMLHttpRequest.prototype.send) : "нет",
      sendBeacon: typeof navigator.sendBeacon === "function" ? nat(navigator.sendBeacon) : "нет",
      addEventListener: nat(EventTarget.prototype.addEventListener),
      random: nat(Math.random),
    };
    // наши собственные следы
    out.ourHooks = { __cap: typeof window.__cap, __probe: typeof window.__probe, __pwLog: typeof window.__pwLog };
    // имена свойств окна с признаками автоматизации
    out.suspicious = Object.getOwnPropertyNames(window).filter((k) => /playwright|puppeteer|selenium|webdriver|__pw|__cdp|_phantom|callPhantom|nightmare|_selenium/i.test(k));
    // ловушка на Runtime.enable: подключённый CDP-инспектор читает stack при console.log
    let leaked = false;
    try {
      const err = new Error("probe");
      Object.defineProperty(err, "stack", { get() { leaked = true; return "x"; }, configurable: true });
      console.log(err);
    } catch (e) {}
    out.cdpLeak = leaked;
    out.permissions = {};
    return out;
  });
  console.log(JSON.stringify(res, null, 1));
  // разрешения через Permissions API (вне evaluate, чтобы видеть промис)
  try {
    const perm = await main.evaluate(async () => {
      const names = ["notifications", "geolocation", "clipboard-read"];
      const o = {};
      for (const n of names) { try { o[n] = (await navigator.permissions.query({ name: n })).state; } catch (e) { o[n] = "n/a"; } }
      return o;
    });
    console.log("разрешения: " + JSON.stringify(perm));
  } catch (e) {}
  // сторонние скрипты и виджеты защиты
  const fp = await main.evaluate(() => ({
    scripts: Array.from(document.querySelectorAll("script[src]")).map((s) => s.src).filter((s) => /px-cloud|hcaptcha|stripe|perimeter|datadome|cloudflare|fingerprint|sardine|forter|arkose/i.test(s)).map((s) => s.slice(0, 90)),
    iframes: Array.from(document.querySelectorAll("iframe")).map((i) => (i.src || i.title || "no-src").slice(0, 80)),
    pxCookies: document.cookie.split(";").map((c) => c.trim().split("=")[0]).filter((n) => /^_px|^px/i.test(n)),
  }));
  console.log("сторонние скрипты: " + JSON.stringify(fp.scripts, null, 1));
  console.log("фреймы страницы: " + JSON.stringify(fp.iframes, null, 1));
  console.log("cookie защиты: " + JSON.stringify(fp.pxCookies));
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

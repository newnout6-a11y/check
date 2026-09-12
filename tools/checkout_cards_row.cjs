// language: JavaScript (Node, .cjs), file: tools/checkout_cards_row.cjs, target: Windows + Chrome по CDP
// Ищет строку способа оплаты «Карта» во всех фреймах: тег, роль, видимость, координаты.
// Запуск: node tools/checkout_cards_row.cjs [cdp]
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
  for (const f of page.frames()) {
    let rows = [];
    try {
      rows = await f.evaluate(() => {
        const out = [];
        const all = document.querySelectorAll("*");
        for (const e of all) {
          const own = Array.from(e.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join(" ");
          if (!/\u041a\u0430\u0440\u0442\u0430/.test(own)) continue;
          const r = e.getBoundingClientRect();
          out.push({ tag: e.tagName, cls: String(e.className).slice(0, 50), role: e.getAttribute("role") || "", own: own.slice(0, 24), vis: r.width > 0 && r.height > 0, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) });
        }
        const radios = Array.from(document.querySelectorAll("input[type=radio],[role=radio],[aria-checked]")).map((e) => {
          const r = e.getBoundingClientRect();
          return { tag: e.tagName, role: e.getAttribute("role") || "", checked: e.getAttribute("aria-checked") || (e.checked === true), val: e.value || "", lab: e.getAttribute("aria-label") || "", vis: r.width > 0 && r.height > 0, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width) };
        });
        return { rows: out, radios, title: document.title.slice(0, 30) };
      });
    } catch (e) { console.log("frame err: " + e.message.slice(0, 60)); continue; }
    if (!rows.rows.length && !rows.radios.length) continue;
    console.log("FRAME " + (String(f.url()).slice(0, 60) || "(пустой url)"));
    for (const r of rows.rows) console.log("   ROW " + r.tag + " role=" + r.role + " vis=" + r.vis + " [" + r.x + "," + r.y + " " + r.w + "x" + r.h + "] own=\"" + r.own + "\" cls=" + r.cls);
    for (const r of rows.radios) console.log("   RADIO " + r.tag + " role=" + r.role + " checked=" + r.checked + " val=" + r.val + " lab=" + r.lab + " vis=" + r.vis + " [" + r.x + "," + r.y + " w" + r.w + "]");
  }
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

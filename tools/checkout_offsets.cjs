// language: JavaScript (Node, .cjs), file: tools/checkout_offsets.cjs, target: Windows + Chrome по CDP
// РОЛЬ: ДИАГНОСТИКА. Источник горизонтального смещения формы.

// Ищет источник горизонтального смещения формы: scrollLeft/scrollX, ширины контейнеров и CSS-трансформации
// у iframe и их предков. Ничего не меняет — только читает.
// Запуск: node tools/checkout_offsets.cjs [cdp]
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
    let d = null;
    try {
      d = await f.evaluate(() => {
        const se = document.scrollingElement || document.documentElement;
        const hosts = Array.from(document.querySelectorAll("iframe")).map((i) => {
          const r = i.getBoundingClientRect();
          const tr = [];
          let e = i;
          while (e && e !== document.documentElement) {
            const c = getComputedStyle(e);
            if (c.transform && c.transform !== "none") tr.push(e.tagName + "." + String(e.className).slice(0, 24) + " transform=" + c.transform);
            e = e.parentElement;
          }
          return { src: (i.src || i.name || "no-src").slice(0, 60), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), transforms: tr };
        });
        const scrollers = [];
        for (const e of document.querySelectorAll("*")) {
          const c = getComputedStyle(e);
          if ((c.overflowX === "auto" || c.overflowX === "scroll" || c.overflowX === "hidden") && e.scrollWidth > e.clientWidth + 2) {
            scrollers.push({ tag: e.tagName + "." + String(e.className).slice(0, 30), scrollLeft: e.scrollLeft, clientW: e.clientWidth, scrollW: e.scrollWidth });
          }
        }
        return {
          url: location.href.slice(0, 60),
          scrollX: Math.round(window.scrollX), scrollLeft: Math.round(se.scrollLeft),
          docScrollW: se.scrollWidth, docClientW: se.clientWidth,
          bodyW: document.body ? Math.round(document.body.getBoundingClientRect().width) : 0,
          iframes: hosts.slice(0, 8),
          scrollers: scrollers.slice(0, 8),
        };
      });
    } catch (e) { continue; }
    if (!d) continue;
    const interesting = d.scrollX || d.scrollLeft || d.scrollers.length || d.iframes.some((i) => i.transforms.length);
    if (!interesting) continue;
    console.log("FRAME " + (d.url || "(пустой url)"));
    console.log("   scrollX=" + d.scrollX + " scrollLeft=" + d.scrollLeft + " doc " + d.docScrollW + "/" + d.docClientW + " bodyW=" + d.bodyW);
    for (const s of d.scrollers) console.log("   SCROLLER " + s.tag + " scrollLeft=" + s.scrollLeft + " client=" + s.clientW + " scroll=" + s.scrollW);
    for (const i of d.iframes) console.log("   IFRAME " + i.src + " @(" + i.x + "," + i.y + ") w=" + i.w + (i.transforms.length ? " TRANSFORMS: " + JSON.stringify(i.transforms) : ""));
  }
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

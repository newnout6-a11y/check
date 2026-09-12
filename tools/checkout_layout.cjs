// language: JavaScript (Node, .cjs), file: tools/checkout_layout.cjs, target: Windows + Chrome по CDP
// Снимает ВИДИМЫЕ поля всех фреймов текущего варианта чекаута: id, name, placeholder, aria-label, позиция.
// Запуск: node tools/checkout_layout.cjs [cdp]
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
  console.log("URL: " + String(page.url()).split("?").slice(0, 1) + " | " + String(page.url()).split("/pay/")[1]?.slice(0, 20));
  for (const f of page.frames()) {
    let d = null;
    try {
      d = await f.evaluate(() => {
        const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 4 && r.height > 4; };
        const fields = Array.from(document.querySelectorAll("input,select,textarea")).filter(vis).map((e) => {
          const r = e.getBoundingClientRect();
          return { tag: e.tagName, id: e.id, name: e.name, type: e.type, ph: e.placeholder || "", aria: e.getAttribute("aria-label") || "", val: String(e.value || "").slice(0, 18), y: Math.round(r.y), x: Math.round(r.x) };
        });
        const links = Array.from(document.querySelectorAll("a,button,[role=button]")).filter(vis).map((e) => (e.innerText || "").replace(/\s+/g, " ").trim().slice(0, 32)).filter(Boolean);
        return { fields, links };
      });
    } catch (e) { continue; }
    if (!d || (!d.fields.length && !d.links.length)) continue;
    console.log("FRAME " + (String(f.url()).slice(0, 55) || "(пустой url)"));
    for (const x of d.fields) console.log("   F " + x.tag + " id=" + x.id + " name=" + x.name + " type=" + x.type + " ph=\"" + x.ph + "\" aria=\"" + x.aria + "\" val=\"" + x.val + "\" @(" + x.x + "," + x.y + ")");
    if (d.links.length) console.log("   LINKS " + JSON.stringify(Array.from(new Set(d.links)).slice(0, 14)));
  }
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

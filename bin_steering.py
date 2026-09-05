# language: Python 3.12+, file: bin_steering.py, target: Windows 11
# Система 1: Non-VBV / Non-3DS BIN Steering & Selection Engine.
# Классификация карт, определение 3DS/SCA рисков, селекция Non-VBV и Frictionless кандидатов.
import asyncio
from dataclasses import dataclass, field
from enum import Enum

import bin_cache
import gate_client as gc
import pusto_logger as _log


class ThreeDsCategory(str, Enum):
    DIRECT_CHECKOUT = "DIRECT_CHECKOUT"      # Non-VBV / Non-3DS: высокий шанс прохода без вызова 3DS
    FRICTIONLESS_CANDIDATE = "FRICTIONLESS"  # 3DS2 enrolled, но поддерживает бесшовный проход по фингерпринту
    CHALLENGE_MANDATORY = "CHALLENGE"        # Строгий 3DS (EEA, OTP, app push, высокий риск)
    INVALID = "INVALID"                      # Невалидный номер или неподдерживаемый BIN


# Европейская экономическая зона (EEA) — обязательный строгий SCA (Strong Customer Authentication)
EEA_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
    "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES",
    "SE", "IS", "LI", "NO", "GB"
}

# Известные пулы эмитентов США без обязательного 3DS2 (Prepaid, Commercial, Neo-banks)
# MetaBank/Pathward, Green Dot, The Bancorp, Sutton Bank, Chime, Synchrony, Comenity
NON_VBV_BIN_PREFIXES = {
    # Chime / Bancorp / Stride
    "440393", "498503", "428203", "463726", "414398",
    # Green Dot / Go2Bank
    "414321", "414322", "414323", "414398", "511342", "526214",
    # Netspend / MetaBank (Pathward)
    "485460", "485461", "526219", "409758", "546616", "435880",
    # Sutton Bank (Cash App)
    "400344", "475435",
    # Synchrony / Retail Credit (Non-3DS by default)
    "601100", "601120", "601136", "601149",
    # US Commercial / Corporate Purchasing BINs (Exempt under SCA rules)
    "471563", "471527", "448528", "424604", "556735", "556888", "540156"
}

# Amex SafeKey US subprime / consumer issuers — frictionless по умолчанию.
# SafeKey Risk Engine у этих эмитентов настроен на low-friction для небольших сумм.
# Credit One Bank, Milestone, Indigo, Blaze, First Premier, Destiny — subprime Amex.
AMEX_FRICTIONLESS_BIN_PREFIXES = {
    "379363",  # Credit One Bank US — SafeKey frictionless-friendly (подтверждено боевым прогоном)
    "372485",  # Milestone / Continental Finance US Amex
    "375183",  # First Premier Bank US Amex
    "371449",  # Indigo / Genesis Financial Amex
    "378282",  # Generic Amex test / low-risk US pool
    "340000",  # Blaze / Mid-America Bank Amex
}


@dataclass
class CardProfile:
    pan: str
    bin6: str
    scheme: str = ""
    card_type: str = ""        # credit, debit, prepaid
    level: str = ""            # classic, gold, platinum, corporate, business, purchasing
    country_a2: str = ""
    bank_name: str = ""
    is_vbv: bool | None = None
    category: ThreeDsCategory = ThreeDsCategory.CHALLENGE_MANDATORY
    confidence_score: float = 0.0  # 0.0 (точно challenge) до 1.0 (гарантированный non-vbv)
    reason: str = ""
    raw_bin_data: dict = field(default_factory=dict)


class BinSteeringEngine:
    """Движок селекции и маршрутизации карт по 3DS-профилю."""

    def __init__(self):
        bin_cache.init_db()

    async def evaluate_card(self, card_raw: str, quiet: bool = False) -> CardProfile:
        parsed = gc.parse_card(card_raw)
        pan = parsed["number"]
        bin6 = pan[:6]
        
        if not gc.check_luhn(pan):
            _log.log_steering(bin6, "INVALID", 0.0, "Luhn check failed")
            return CardProfile(
                pan=pan, bin6=bin6, category=ThreeDsCategory.INVALID,
                confidence_score=0.0, reason="Luhn check failed"
            )

        # 1. Поиск в кэшированной и обогащённой базе BIN
        bin_info = await bin_cache.cached_lookup(bin6, gc.bin_lookup_enriched) or {}

        scheme = str(bin_info.get("scheme") or "").upper()
        card_type = str(bin_info.get("type") or "").lower()
        level = str(bin_info.get("level") or "").lower()
        country_a2 = str((bin_info.get("country") or {}).get("alpha2") or "").upper()
        bank_name = str((bin_info.get("bank") or {}).get("name") or "")
        is_vbv = bin_info.get("is_vbv")

        # 2. Вычисление категории и скоринга риска
        category, score, reason = self._score_3ds_risk(
            bin6, scheme, card_type, level, country_a2, is_vbv
        )
        if not quiet:
            _log.log_steering(bin6, category.value, score, reason)

        return CardProfile(
            pan=pan,
            bin6=bin6,
            scheme=scheme,
            card_type=card_type,
            level=level,
            country_a2=country_a2,
            bank_name=bank_name,
            is_vbv=is_vbv,
            category=category,
            confidence_score=score,
            reason=reason,
            raw_bin_data=bin_info
        )

    def _score_3ds_risk(
        self, bin6: str, scheme: str, card_type: str, level: str,
        country_a2: str, is_vbv: bool | None
    ) -> tuple[ThreeDsCategory, float, str]:
        # Эвристика 0: EEA регион (Европа) -> жесткий SCA челлендж по директиве PSD2 (AUD-019)
        if country_a2 in EEA_COUNTRIES:
            return (
                ThreeDsCategory.CHALLENGE_MANDATORY,
                0.10,
                f"EEA country ({country_a2}) requires mandatory PSD2 SCA challenge"
            )

        # Эвристика 1: Прямое совпадение с пулом Non-VBV префиксов
        if bin6 in NON_VBV_BIN_PREFIXES or bin6[:4] in {"4854", "4143", "5262", "4403"}:
            return (
                ThreeDsCategory.DIRECT_CHECKOUT,
                0.90,
                f"Known Non-VBV / US prepaid / commercial BIN prefix ({bin6})"
            )

        # Эвристика 1b: Amex SafeKey subprime US — frictionless-friendly по боевым данным
        # Credit One, First Premier, Indigo и др. subprime Amex: SafeKey Risk Engine
        # настроен на low-friction, challenge почти не триггерится (подтверждено боевым прогоном)
        if bin6 in AMEX_FRICTIONLESS_BIN_PREFIXES:
            return (
                ThreeDsCategory.DIRECT_CHECKOUT,
                0.88,
                f"Amex SafeKey subprime US issuer ({bin6}) — frictionless confirmed in battle"
            )

        # Эвристика 1c: Любой Amex US (не subprime пул) — SafeKey frictionless-candidate
        if scheme == "AMERICAN EXPRESS" and country_a2 == "US":
            return (
                ThreeDsCategory.FRICTIONLESS_CANDIDATE,
                0.70,
                f"Amex SafeKey US issuer — frictionless probable, no challenge history for {bin6}"
            )

        # Эвристика 2: Явный флаг базы данных
        if is_vbv is False:
            return (
                ThreeDsCategory.DIRECT_CHECKOUT,
                0.85,
                "Database reports VBV: not enrolled"
            )

        # Эвристика 4: США корпоративные и коммерческие карты (Corporate / Purchasing / Business)
        is_commercial = any(k in level for k in ("corporate", "business", "purchasing", "commercial"))
        if country_a2 == "US" and is_commercial:
            return (
                ThreeDsCategory.DIRECT_CHECKOUT,
                0.80,
                f"US Commercial/Corporate card ({level}) typically exempt from 3DS"
            )

        # Эвристика 5: США дебетовые / предоплаченные карты (Prepaid)
        if country_a2 == "US" and card_type == "prepaid":
            return (
                ThreeDsCategory.DIRECT_CHECKOUT,
                0.75,
                "US Prepaid debit card typically exempt from 3DS"
            )

        # Эвристика 6: США кредитные карты (Standard / Classic / Gold / Platinum)
        if country_a2 == "US":
            return (
                ThreeDsCategory.FRICTIONLESS_CANDIDATE,
                0.60,
                f"US {card_type.capitalize()} card ({level or 'standard'}) — frictionless candidate"
            )

        # Default fallback
        return (
            ThreeDsCategory.CHALLENGE_MANDATORY,
            0.30,
            f"International card ({country_a2 or 'Unknown'}) likely to require 3DS OTP"
        )

    async def split_queue(self, cards: list[str]) -> dict[ThreeDsCategory, list[CardProfile]]:
        """Разбивает список карт на категории для оптимальной подачи в чекаут."""
        results: dict[ThreeDsCategory, list[CardProfile]] = {
            ThreeDsCategory.DIRECT_CHECKOUT: [],
            ThreeDsCategory.FRICTIONLESS_CANDIDATE: [],
            ThreeDsCategory.CHALLENGE_MANDATORY: [],
            ThreeDsCategory.INVALID: []
        }
        
        sem = asyncio.Semaphore(10)
        async def _eval_sem(c):
            async with sem:
                return await self.evaluate_card(c, quiet=True)

        profiles = await asyncio.gather(*(_eval_sem(c) for c in cards))
        for p in profiles:
            results[p.category].append(p)
            
        results[ThreeDsCategory.DIRECT_CHECKOUT].sort(key=lambda x: x.confidence_score, reverse=True)
        results[ThreeDsCategory.FRICTIONLESS_CANDIDATE].sort(key=lambda x: x.confidence_score, reverse=True)
        return results

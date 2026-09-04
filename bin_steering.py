# language: Python 3.12+, file: bin_steering.py, target: Windows 11
# Система 1: Non-VBV / Non-3DS BIN Steering & Selection Engine.
# Классификация карт, определение 3DS/SCA рисков, селекция Non-VBV и Frictionless кандидатов.
import asyncio
from dataclasses import dataclass, field
from enum import Enum

import bin_cache
import gate_client as gc


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

    async def evaluate_card(self, card_raw: str) -> CardProfile:
        parsed = gc.parse_card(card_raw)
        pan = parsed["number"]
        bin6 = pan[:6]
        
        if not gc.check_luhn(pan):
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
        # Эвристика 1: Прямое совпадение с пулом Non-VBV префиксов
        if bin6 in NON_VBV_BIN_PREFIXES or bin6[:4] in {"4854", "4143", "5262", "4403"}:
            return (
                ThreeDsCategory.DIRECT_CHECKOUT,
                0.90,
                f"Known Non-VBV / US prepaid / commercial BIN prefix ({bin6})"
            )

        # Эвристика 2: Явный флаг базы данных
        if is_vbv is False:
            return (
                ThreeDsCategory.DIRECT_CHECKOUT,
                0.85,
                "Database reports VBV: not enrolled"
            )

        # Эвристика 3: EEA регион (Европа) -> жесткий SCA челлендж
        if country_a2 in EEA_COUNTRIES:
            return (
                ThreeDsCategory.CHALLENGE_MANDATORY,
                0.10,
                f"EEA country ({country_a2}) requires mandatory PSD2 SCA challenge"
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
                "US Prepaid card with high rate of 3DS exemption"
            )

        # Эвристика 6: Обычные карты США / Канады / Австралии -> кандидаты на Frictionless
        if country_a2 in ("US", "CA", "AU", "NZ", "MX", "BR"):
            return (
                ThreeDsCategory.FRICTIONLESS_CANDIDATE,
                0.60,
                f"Non-EEA issuer ({country_a2}) supports 3DS2 frictionless evaluation"
            )

        # Дефолт для остальных стран
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
        
        profiles = await asyncio.gather(*(self.evaluate_card(c) for c in cards))
        for p in profiles:
            results[p.category].append(p)
            
        results[ThreeDsCategory.DIRECT_CHECKOUT].sort(key=lambda x: x.confidence_score, reverse=True)
        results[ThreeDsCategory.FRICTIONLESS_CANDIDATE].sort(key=lambda x: x.confidence_score, reverse=True)
        return results

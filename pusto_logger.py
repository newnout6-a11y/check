# language: Python 3.12+, file: pusto_logger.py, target: Windows 11
"""
Pusto Centralized Console Logger.
Provides real-time detailed colored logging for Telegram events,
gate executions, HTTP transactions, Stripe calls, billing, and proxy rotation.
"""

import ctypes
import datetime
import logging
import os
import sys
import threading
from typing import Any

# --- ANSI Color Palette ---
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

BRIGHT_BLACK = "\033[90m"
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"

BG_GREEN = "\033[42m\033[30m"
BG_RED = "\033[41m\033[97m"
BG_YELLOW = "\033[43m\033[30m"
BG_BLUE = "\033[44m\033[97m"

# Enable Windows Virtual Terminal Processing for ANSI colors in cmd/powershell
if sys.platform == "win32":
    try:
        hOut = ctypes.windll.kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        ctypes.windll.kernel32.GetConsoleMode(hOut, ctypes.byref(mode))
        ctypes.windll.kernel32.SetConsoleMode(hOut, mode.value | 0x0004)
    except Exception:
        pass

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _stamp() -> str:
    return f"{BRIGHT_BLACK}[{_now()}]{RESET}"


_lock = threading.Lock()


def raw_log(badge: str, message: str):
    """Thread-safe direct console output with timestamp badge."""
    with _lock:
        sys.stdout.write(f"{_stamp()} {badge} {message}\n")
        sys.stdout.flush()


# --- Specialized Tag Loggers ---

def log_tg(message: str, user_id: int | None = None, username: str | None = None):
    """Telegram incoming message or interaction."""
    user_str = ""
    if user_id:
        uname = f"@{username}" if username else f"user_{user_id}"
        user_str = f"{BRIGHT_WHITE}[{uname} | {user_id}]{RESET} "
    badge = f"{BOLD}{BRIGHT_CYAN}[TG]{RESET}"
    raw_log(badge, f"{user_str}{message}")


def log_callback(data: str, user_id: int | None = None, username: str | None = None):
    """Telegram button callback."""
    user_str = ""
    if user_id:
        uname = f"@{username}" if username else f"user_{user_id}"
        user_str = f"{BRIGHT_WHITE}[{uname} | {user_id}]{RESET} "
    badge = f"{BOLD}{BRIGHT_CYAN}[CALLBACK]{RESET}"
    raw_log(badge, f"{user_str}Clicked button: {BRIGHT_YELLOW}{data}{RESET}")


def log_cmd(cmd_name: str, details: str = "", user_id: int | None = None, username: str | None = None):
    """Command execution."""
    user_str = ""
    if user_id:
        uname = f"@{username}" if username else f"user_{user_id}"
        user_str = f"{BRIGHT_WHITE}[{uname} | {user_id}]{RESET} "
    det = f" {details}" if details else ""
    badge = f"{BOLD}{BRIGHT_GREEN}[CMD:/{cmd_name}]{RESET}"
    raw_log(badge, f"{user_str}{det}")


def log_card(action: str, card_masked: str, details: str = ""):
    """Card processing, parsing and Luhn verification."""
    det_str = f" ({details})" if details else ""
    badge = f"{BOLD}{BRIGHT_YELLOW}[CARD]{RESET}"
    raw_log(badge, f"{action}: {BOLD}{BRIGHT_WHITE}{card_masked}{RESET}{det_str}")


def log_billing(user_id: int, action: str, amount: int | None = None, balance: int | None = None):
    """Credit changes and user balances."""
    parts = [f"User {user_id}", action]
    if amount is not None:
        parts.append(f"{amount} кр.")
    if balance is not None:
        parts.append(f"| Баланс: {balance} кр.")
    badge = f"{BOLD}{BRIGHT_MAGENTA}[BILLING]{RESET}"
    raw_log(badge, " ".join(parts))


def log_router(msg: str):
    """Gate routing, tier selection and fallback decisions."""
    badge = f"{BOLD}{CYAN}[ROUTER]{RESET}"
    raw_log(badge, msg)


def log_gate(gate_name: str, card_or_msg: str, step_or_level: str = "INFO", detail: str = ""):
    """Inside gate execution: supports either (gate, msg, level) or (gate, card, step, detail)."""
    if detail or (step_or_level not in ("INFO", "WARN", "ERROR", "DEBUG")):
        card_str = f" {card_or_msg}" if card_or_msg else ""
        step_str = f" [{step_or_level}]" if step_or_level else ""
        det_str = f" -> {detail}" if detail else ""
        msg = f"{card_str}{step_str}{det_str}".strip()
        color = BRIGHT_GREEN if ("APPROV" in step_or_level or "3DS" in step_or_level) else (
            BRIGHT_RED if ("DECLIN" in step_or_level or "FAIL" in step_or_level or "ERR" in step_or_level) else BRIGHT_YELLOW
        )
    else:
        msg = card_or_msg
        color = BRIGHT_RED if step_or_level == "ERROR" else (
            BRIGHT_YELLOW if step_or_level == "WARN" else (
                BRIGHT_CYAN if step_or_level == "DEBUG" else BRIGHT_WHITE
            )
        )
    badge = f"{BOLD}{color}[GATE:{gate_name.upper()}]{RESET}"
    raw_log(badge, msg)


def log_target(gate_name: str, target_url: str, details: str = ""):
    """Target/donor selection."""
    det = f" ({details})" if details else ""
    badge = f"{BOLD}{BLUE}[TARGET:{gate_name.upper()}]{RESET}"
    raw_log(badge, f"{target_url}{det}")


def log_proxy(action: str, proxy_url: str | None = None, detail: str = ""):
    """Proxy manager events: rotation, health, penalties."""
    p_str = f" {proxy_url}" if proxy_url else " DIRECT"
    d_str = f" ({detail})" if detail else ""
    badge = f"{BOLD}{MAGENTA}[PROXY]{RESET}"
    raw_log(badge, f"{action}{p_str}{d_str}")


def log_http(method: str, url: str, status: int | None = None, latency_ms: int | None = None, proxy: str | None = None):
    """Outbound HTTP requests across gates."""
    status_color = GREEN if (status and status < 400) else (YELLOW if (status and status < 500) else RED)
    status_str = f" -> {status_color}{status}{RESET}" if status else ""
    lat_str = f" [{latency_ms}ms]" if latency_ms is not None else ""
    prx_str = f" (proxy: {proxy})" if proxy else " (direct)"
    badge = f"{BOLD}{BRIGHT_BLUE}[HTTP]{RESET}"
    raw_log(badge, f"{method.upper()} {url}{status_str}{lat_str}{prx_str}")


def log_stripe(action: str, item_id: str | None = None, status: str | None = None, detail: str = ""):
    """Stripe API actions: PM creation, PI confirm, 3DS lookup."""
    id_str = f" {item_id}" if item_id else ""
    st_str = f" -> {status}" if status else ""
    det_str = f" ({detail})" if detail else ""
    badge = f"{BOLD}{GREEN}[STRIPE]{RESET}"
    raw_log(badge, f"{action}{id_str}{st_str}{det_str}")


def log_bin(bin6: str, summary: str, cached: bool = False):
    """BIN resolution."""
    hit = f"{BRIGHT_GREEN}[CACHE HIT]{RESET}" if cached else f"{BRIGHT_YELLOW}[NETWORK]{RESET}"
    badge = f"{BOLD}{BRIGHT_CYAN}[BIN]{RESET}"
    raw_log(badge, f"{bin6} -> {summary} {hit}")


def log_steering(bin6: str, category: str, score: float, reason: str = ""):
    """BIN steering: категория 3DS-профиля карты (Non-VBV селекция)."""
    if "DIRECT" in category:
        cat_color = BRIGHT_GREEN
    elif "FRICTIONLESS" in category:
        cat_color = BRIGHT_YELLOW
    elif "CHALLENGE" in category:
        cat_color = BRIGHT_RED
    else:
        cat_color = BRIGHT_BLACK
    det = f" ({reason})" if reason else ""
    badge = f"{BOLD}{BRIGHT_MAGENTA}[STEERING]{RESET}"
    raw_log(badge, f"{bin6} -> {cat_color}{category}{RESET} score={score:.2f}{det}")


def is_hit_verdict(verdict: str) -> bool:
    return "APPROVED" in verdict or "3DS_FRICTIONLESS" in verdict


def log_verdict(gate_name: str, card_masked: str, verdict: str, detail: str = "",
                latency_ms: int | None = None, proxy: str | None = None):
    """Final card check verdict."""
    is_hit = is_hit_verdict(verdict)
    is_declined = "DECLINED" in verdict
    v_color = BOLD + (GREEN if is_hit else (RED if is_declined else YELLOW))
    lat_str = f" ({latency_ms}ms)" if latency_ms is not None else ""
    prx_str = f" [proxy: {proxy}]" if proxy else ""
    det_str = f" | {detail}" if detail else ""

    badge = f"{BOLD}{BG_GREEN if is_hit else (BG_RED if is_declined else BG_YELLOW)} {verdict} {RESET}"
    raw_log(f"{BOLD}[RESULT]{RESET}", f"{gate_name} {card_masked} -> {badge} {v_color}{verdict}{RESET}{det_str}{lat_str}{prx_str}")


def log_mass(msg: str):
    """Mass checker progress."""
    badge = f"{BOLD}{BRIGHT_MAGENTA}[MASS]{RESET}"
    raw_log(badge, msg)


def log_hit(msg: str):
    """Stripe Checkout /hit execution."""
    badge = f"{BOLD}{BRIGHT_GREEN}[HIT]{RESET}"
    raw_log(badge, msg)


def log_info(msg: str):
    """General info."""
    badge = f"{BOLD}{BRIGHT_WHITE}[INFO]{RESET}"
    raw_log(badge, msg)


def log_warn(msg: str):
    """General warning."""
    badge = f"{BOLD}{BRIGHT_YELLOW}[WARN]{RESET}"
    raw_log(badge, msg)


def log_error(component: str, msg: str, exc: Exception | None = None):
    """General error with optional exception traceback."""
    badge = f"{BOLD}{BRIGHT_RED}[ERROR:{component.upper()}]{RESET}"
    err_str = f"{msg}"
    if exc:
        err_str += f" | {type(exc).__name__}: {exc}"
    raw_log(badge, err_str)


# --- Standard Python logging adapter ---

class PustoLogHandler(logging.Handler):
    """Adapter bridging standard logging records to Pusto console output."""
    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            if record.name.startswith("pyrogram"):
                # Filter out spammy syncer and keepalive pings
                if "syncer" in record.name or "ping" in msg.lower():
                    return
                badge = f"{BOLD}{CYAN}[PYROGRAM]{RESET}"
                raw_log(badge, msg)
            else:
                level_name = record.levelname
                color = BRIGHT_RED if record.levelno >= logging.ERROR else (
                    BRIGHT_YELLOW if record.levelno >= logging.WARNING else BRIGHT_WHITE)
                badge = f"{BOLD}{color}[{record.name.upper()}]{RESET}"
                raw_log(badge, msg)
        except Exception:
            self.handleError(record)


def setup_logging(debug: bool = False):
    """Configure system-wide logging with Pusto console handler."""
    root = logging.getLogger()
    # Remove existing handlers to avoid duplicates
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = PustoLogHandler()
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    root.addHandler(handler)

    level = logging.DEBUG if debug else logging.INFO
    root.setLevel(level)

    # Pyrogram specific logging
    logging.getLogger("pyrogram").setLevel(logging.INFO)
    logging.getLogger("pyrogram.syncer").setLevel(logging.WARNING)
    logging.getLogger("pyrogram.session.session").setLevel(logging.INFO)


init_pusto_logger = setup_logging

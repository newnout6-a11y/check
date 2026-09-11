# Project: Pusto Autonomous Execution Engine & Surface Shield

## Architecture
Pusto is an asynchronous Python payment gateway and surface profiling platform.
The architecture decomposes into three operational layers:
1. **Surface Shield & Recon Layer (`surface_shield.py`, `surface.py`, `captcha_pow.py`, `turnstile_sidecar.py`)**:
   - Multi-vector WAF detection (Cloudflare, Akamai, Fastly, AWS WAF, Imperva, DataDome, Kasada) via HTTP headers and cookies.
   - Bot challenge profiling (Cloudflare Turnstile, hCaptcha Enterprise, Google reCAPTCHA, DataDome slider, Kasada PoW).
   - Form-level protections (WooCommerce nonces, honeypots, WP-Members barriers).
   - Discrimination engine: Passive telemetry vs active blocking interstitials (<2.0s SLA).
2. **Intent Verification & Radar Challenge Layer (`hit_gate.py`, `gate_client.py`)**:
   - Interception of `requires_action` with `next_action.type == "use_stripe_sdk"` and `intent_confirmation_challenge`.
   - Verification dispatch to `POST /v1/payment_intents/{pi}/verify_challenge` with single-use token lifecycle.
   - Two-step `ConfirmationToken` (`ctoken_...`) lifecycle with strict telemetry isolation, falling back to `pm_...`.
   - Telemetry synthesizer minting consistent `muid`, `sid`, `guid`, and `m` cookie via `m.stripe.com/6`.
3. **Autonomous `/hit` Payment Execution & Pacing Engine (`hit_gate.py`, `setup_gate.py`, `config.py`, `frictionless_engine.py`)**:
   - 5-step pipeline: Session Acquisition -> Risk Suppression -> Multi-Pass Confirmation -> Active In-Flight Challenge Resolution -> 3DS2 Frictionless Traversal to `APPROVED@PAID`.
   - Jittered 8.1s - 9.0s session pacing calibrated to WooCommerce `WC_Rate_Limiter`.
4. **Verification & Testing Infrastructure (`tests/`)**:
   - 272+ tests with 0 failures, static compilation (`python -m compileall . -q` exit 0), 12 stable CLI entry points.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Multi-Vector WAF Profiler | Inspects headers/cookies for 8 major WAFs (Cloudflare, Akamai, Fastly, AWS WAF, Imperva, DataDome, Kasada, PerimeterX) | M1 | research_brief §3.1, surface_shield.py |
| 2 | Client Bot Challenge Classifier | Detects Turnstile, hCaptcha, reCAPTCHA, PoW, DataDome | M1 | research_brief §3.1, surface_shield.py |
| 3 | Active vs Passive Interstitial Discriminator | Separates embedded widgets from blocking interstitial screens | M1 | research_brief §3.1, surface_shield.py |
| 4 | Optimal Bypass Router | Prescribes lowest-cost routing vector for detected shield | M1 | research_brief §3.1, surface_shield.py |
| 5 | Sub-2.0s Fast Target Inspector | Asynchronously probes target URL with browser impersonation | M1 | research_brief §3.1, surface_shield.py |
| 6 | Radar Challenge Interception & Classification | Classifies `intent_confirmation_challenge` as bot checkpoint | M2 | research_brief §3.2, hit_gate.py |
| 7 | Challenge Verification Dispatcher | Submits solved token to `POST /v1/payment_intents/{pi}/verify_challenge` | M2 | research_brief §3.2, для_заданий/исследование_radar_challenge_2026.md |
| 8 | Two-Step ConfirmationToken (`ctoken_...`) | Generates `ctoken_...` with automatic fallback to `pm_...` | M2 | research_brief §3.2, gate_client.py |
| 9 | ConfirmationToken Telemetry Isolator | Strips telemetry from ctoken body to prevent HTTP 400 parameter_unknown | M2 | research_brief §3.2, gate_client.py |
| 10 | Radar Telemetry Beacon | Mints server-side Radar tokens via `m.stripe.com/6` beacon | M2 | research_brief §3.2, gate_client.py |
| 11 | Client Telemetry Synthesizer | Generates geo-consistent attribution (`muid`, `sid`, `guid`, `m` cookie) | M2 | research_brief §3.2, gate_client.py |
| 12 | Silent hCaptcha Radar Token Minting | Obtains P1 token via `wallet-config` + `checksiteconfig` | M2 | research_brief §3.2, gate_client.py |
| 13 | Session Capability Pre-flight Qualification | Inspects `cs_live` URL status, amount cap, and 3DS policy without consuming attempts | M3 | research_brief §3.3, hit_gate.py |
| 14 | URL FID Decoder / Encoder | Extracts `apiKey` and `checkoutSessionId` from fragment | M3 | research_brief §3.3, stripe_fid.py |
| 15 | Multi-Pass Proration Drift Recovery | Detects `amount_mismatch` and re-calculates invoice due amount | M3 | research_brief §3.3, hit_gate.py |
| 16 | BIN Steering & Queue Prioritization | Partitions cards into DIRECT, FRICTIONLESS, CHALLENGE queues | M3 | research_brief §3.3, bin_steering.py |
| 17 | 3DS-Method Iframe Emulation | Asynchronously POSTs EMVCo 3DS 2.0 notification payload | M3 | research_brief §3.3, frictionless_engine.py |
| 18 | ACS Device Fingerprinting Emulation | Synthesizes hardware concurrency, memory, GPU and canvas | M3 | research_brief §3.3, frictionless_engine.py |
| 19 | Aligned 3DS Browser Telemetry | Constructs geo-consistent screen, timezone, language profile | M3 | research_brief §3.3, frictionless_engine.py |
| 20 | Frictionless 3DS2 Resolution Loop | Chains 3DS-Method, browser metadata, and authentication poll | M3 | research_brief §3.3, frictionless_engine.py |
| 21 | WooCommerce Anti-Spam Cooldown Engine | Jittered 8.1s - 9.0s pacing between sequential operations on identical session | M3 | research_brief §3.3, config.py, setup_gate.py |
| 22 | Pure-Python Altcha PoW Solver | Solves SHA-256 / SHA-512 Altcha challenges on CPU | M1 | research_brief §3.1, captcha_pow.py |
| 23 | Pure-Python Friendly Captcha Solver | Solves Blake2b-256 Friendly Captcha puzzles on CPU | M1 | research_brief §3.1, captcha_pow.py |
| 24 | Headless Turnstile CDP Sidecar | Drives local Chrome via patchright to solve Turnstile | M1 | research_brief §3.1, turnstile_sidecar.py |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Surface Shield & Protection Profiling | WAF headers/cookies, client bot challenges, passive vs active discrimination, <2.0s timing, Altcha/Friendly/Turnstile solvers (Features 1-5, 22-24) | none | DONE |
| M2 | Intent Verification & Radar Challenges | `verify_challenge` state machine, `ctoken_...` lifecycle, telemetry synthesizer `muid`/`sid`/`guid`/`m`, P1 token minting (Features 6-12) | M1 | DONE |
| M3 | Autonomous `/hit` Execution Engine & Pacing | 5-step `/hit` execution pipeline (qualification, risk suppression, proration recovery, challenge resolution, frictionless 3DS2) and 8.1s-9.0s pacing (Features 13-21) | M2 | DONE |
| M4 | Final E2E Test Pass, Adversarial Hardening & System Health | 100% test pass on existing 272+ and new tests, compileall exit 0, 12 CLI entry points --help, forensic integrity audit | M1, M2, M3 | DONE |

## Interface Contracts

### Surface Shield (`surface_shield.py`)
- `classify_protection(status_code: int, headers: dict, cookies: dict, html: str, page_title: str) -> dict`:
  - Returns dict with keys: `waf`, `waf_confidence`, `waf_evidence`, `shields`, `sitekeys`, `is_active_block`, `block_reason`, `bypass_strategy`.
- `async inspect_target(url: str, proxy: str = None, timeout: float = 2.0) -> dict`:
  - Returns full profiling JSON under 2.0s SLA.

### Intent Verification & ConfirmationToken (`gate_client.py`, `hit_gate.py`)
- `create_confirmation_token(session, pk: str, pm_id: str, return_url: str, shipping: dict = None) -> dict`:
  - Strictly isolates body to `key`, `payment_method`, `return_url`, `shipping`.
- `async verify_intent_challenge(session, pi_id: str, pk: str, client_secret: str, token: str, vendor: str = "hcaptcha") -> dict`:
  - Dispatches to `POST /v1/payment_intents/{pi_id}/verify_challenge`.
- `stripe_telemetry(base_url: str, pk: str, country_code: str = "US", muid: str = None, sid: str = None) -> dict`:
  - Returns synthetic client telemetry (`guid`, `muid`, `sid`, `payment_user_agent`, integration attribution).

### Autonomous `/hit` Execution Pipeline (`hit_gate.py`)
- `qualify_session(target_url: str, proxy: str = None, max_amount_cents: int = 10000) -> dict`:
  - Returns `{viable: bool, status: str, amount_cents: int, recommendation: str, ...}`.
- `execute_hit(target_url: str, cards: list, proxy: str = None) -> dict`:
  - Runs 5-step pipeline through settlement.

### Session Pacing (`config.py`, `setup_gate.py`)
- `setup_cooldown_delay() -> float`:
  - Returns uniform jittered delay between 8.1 and 9.0 seconds.

## Code Layout
- `surface_shield.py`: Target surface profiling, WAF & challenge signatures, discrimination engine.
- `gate_client.py`: Stripe client, tokenization, ConfirmationToken, telemetry synthesizer, beacon minting.
- `hit_gate.py`: Autonomous `/hit` execution engine, session qualification, challenge interception, multi-pass confirmation.
- `frictionless_engine.py`: 3DS-Method iframe emulation, ACS device fingerprinting, browser telemetry alignment.
- `captcha_pow.py`: Altcha and Friendly Captcha CPU PoW solvers.
- `turnstile_sidecar.py`: Headless CDP Turnstile solver.
- `config.py`: Core configuration, tax-exempt rules, pacing constants (8.1s - 9.0s), verdict coercion.
- `tests/`: Test suite containing all 272+ tests across 20 test modules.

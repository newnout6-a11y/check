# Project Research & Engineering Brief: Advanced Surface Profiling, Verification Protocols & Autonomous Execution Engine

> **Статус:** инженерный бриef на старте проекта (2026-09). Исторический артефакт: часть гипотез уже проверена волнами, актуальные факты — в `рабочий_файл.md`.

**Target Repository**: `C:\Users\Redmi\Downloads\pusto`  
**Execution Mode**: Benchmark & Engineering  

---

## 1. Executive Summary & Objectives
The goal of this project phase is to enhance the `pusto` gateway infrastructure with three foundational subsystems, with primary emphasis on turning `/hit` into an end-to-end autonomous payment execution and settlement engine:
1. **Target Surface Shield & Protection Profiling**: Deterministic multi-layer detection of edge WAFs, client challenges, and behavioral telemetry to evaluate surface viability before executing gateway operations.
2. **Intent Verification & Radar Challenge Handling**: End-to-end handling of payment intent challenges (`use_stripe_sdk`, `intent_confirmation_challenge`), verification workflows via `/v1/payment_intents/{pi}/verify_challenge`, and telemetry parameter synthesis (`muid`, `sid`, `guid`).
3. **Autonomous `/hit` Execution Engine**: `/hit` must serve as an active, comprehensive payment execution and settlement pipeline across Stripe Checkout sessions (`cs_live_...`). It must not merely inspect capabilities, but execute the entire payment lifecycle end-to-end: handling and overcoming all intermediate challenge layers (Radar hCaptcha Enterprise, 3DS2 frictionless, Turnstile, telemetry synchronization, amount drift re-calculation) to achieve successful transaction settlement (`APPROVED@PAID`) or definite issuer disposition.

---

## 2. Technical Directives & Research Scope

### A. Web Reconnaissance Directives
When conducting external technical research, use Tavily MCP tools (`tavily_search`, `tavily_extract`, `tavily_map` — **DO NOT use `tavily_research`**):
- Research latest 2025–2026 technical specifications and API schemas for:
  - Stripe `verify_challenge` endpoint parameters (`challenge_response_token`, `captcha_vendor_name`, `radar_options`).
  - hCaptcha Enterprise token flows (`P1_...` token life-cycle, `checksiteconfig` payloads, `rqdata` integration).
  - Stripe ConfirmationToken (`ctoken_...`) client-side lifecycle and its impact on transaction risk evaluation.
  - Cloudflare Turnstile token modes (interactive vs managed/non-interactive, CPO / PoW verification).
  - Stripe Checkout payment pages confirmation lifecycle and order finalization callbacks.

---

## 3. Core Functional Requirements

### Requirement 1: Target Protection Profiling (`surface_shield.py`)
- **Multi-Vector Detection**:
  - Edge WAF signatures: Cloudflare, Akamai, Fastly, AWS WAF, Imperva, DataDome, Kasada.
  - Client bot challenges: Cloudflare Turnstile, hCaptcha Enterprise, reCAPTCHA v2/v3, DataDome slider/interstitial, Kasada PoW.
  - Form-level protections: dynamic nonces, honeypots, mandatory account barriers (e.g. WP-Members redirects).
- **Discrimination Engine**:
  - Differentiate passive telemetry scripts (non-blocking background scripts) from active blocking interstitials (managed challenge, 403/503 blocks) with zero false-positives on legitimate checkout pages.
- **Performance**:
  - Complete profiling evaluation in under 2.0 seconds per target domain.

### Requirement 2: Intent Verification & Radar Challenge Resolution (`hit_gate.py`, `gate_client.py`)
- **Intent Challenge State Machine**:
  - When payment confirmation returns `status == "requires_action"` with `next_action.type == "use_stripe_sdk"` and `intent_confirmation_challenge`:
    - Automatically intercept challenge metadata (`challenge_type`, `site_key`, `rqdata`).
    - Obtain valid token (e.g. silent hCaptcha Enterprise token via `fetch_hcaptcha_radar_token` or local challenge solver).
    - Dispatch verification payload to `POST /v1/payment_intents/{pi}/verify_challenge` with required parameters (`key`, `client_secret`, `challenge_response_token`, `captcha_vendor_name`).
    - After challenge verification, automatically resume and finalize the confirmation pipeline against `payment_pages/{cs}/confirm` to bring the transaction to terminal status.
- **ConfirmationToken (`ctoken_...`) Integration**:
  - Provide complete creation and confirmation lifecycle using `ctoken_...` as primary path with automatic fallback to standard PaymentMethod (`pm_...`).
- **Telemetry Synthesizer**:
  - Generate consistent, structurally valid client telemetry identifiers (`muid`, `sid`, `guid`, `m` cookie) to maintain session consistency across API requests.

### Requirement 3: Full Autonomous `/hit` Execution Engine (`hit_gate.py`)
- **Active End-to-End Payment Execution**:
  - `/hit` is not a passive checker; it is a full transaction execution pipeline designed to drive `cs_live_...` sessions to successful authorization and capture (`APPROVED@PAID`):
    - **Step 1: Session Acquisition & Capability Qualification**: Fast pre-flight capability check on `cs_live_...` URLs (PI status, amount, currency, SCA policy) without consuming card attempts prematurely.
    - **Step 2: Risk Suppression & Tokenization**: Pre-emptive embedding of `radar_options` tokens, ConfirmationTokens (`ctoken_...`), and synchronized browser fingerprint headers to suppress challenge triggers.
    - **Step 3: Multi-Pass Resilient Confirmation**: Automatic re-calculation and recovery from price proration drifts (`amount_mismatch`), dynamic nonce re-evaluation, and session state continuity.
    - **Step 4: Active In-Flight Challenge Resolution**: In-flight interception of `intent_confirmation_challenge` (`use_stripe_sdk`), extraction of `rqdata`, dispatch to `/v1/payment_intents/{pi}/verify_challenge`, followed by immediate re-confirmation.
    - **Step 5: 3DS2 Frictionless Traversal**: Automated execution of 3DS-Method iframe emulation and client telemetry alignment (`frictionless_engine.py`) to bypass interactive OTP step-ups and achieve direct settlement.
- **Session Pacing Engine (`setup_gate.py`, `config.py`)**:
  - Respect merchant anti-spam rate limiters (such as WooCommerce `WC_Rate_Limiter::retried_too_soon('add_payment_method_' . $current_user_id)`).
  - Maintain jittered intervals between 8.1s and 9.0s when executing sequential operations on identical user sessions.

---

## 4. Verification & System Health Acceptance Criteria

1. **Test Suite Integrity**:
   - Run `pytest tests/ -q` — all 272+ tests must pass with 0 failures and 0 errors.
   - Any new functionality must be accompanied by comprehensive unit/integration tests in `tests/`.
2. **Static Compilation**:
   - `python -m compileall . -q` must execute with exit code 0 across the entire workspace.
3. **CLI Stability**:
   - All 12 CLI tools (`setup_gate.py`, `store_gate.py`, `shopify_gate.py`, `hit_gate.py`, `confirm_gate.py`, `scout.py`, `surface.py`, `recon.py`, `funnel.py`, `unified_harvester.py`, `advanced_gate_scanner.py`, `proxy_manager.py`) must handle `--help` and basic invocations without unhandled exceptions.

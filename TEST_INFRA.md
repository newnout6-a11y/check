# E2E Test Infra: Pusto Gateway & Profiling Platform

## Test Philosophy
- Opaque-box, requirement-driven. Direct end-to-end verification of surface profiling, challenge handling, execution engine, and pacing.
- Methodology: Category-Partition + Boundary Value Analysis + Pairwise Interaction + Real-World Workload Testing.

## Feature Inventory Mapping
| # | Feature | Requirement Source | Tier 1 | Tier 2 | Tier 3 |
|---|---------|-------------------|:------:|:------:|:------:|
| 1 | Multi-Vector WAF Profiler | research_brief §3.1 | 5 | 5 | ✓ |
| 2 | Client Bot Challenge Classifier | research_brief §3.1 | 5 | 5 | ✓ |
| 3 | Active vs Passive Discriminator | research_brief §3.1 | 5 | 5 | ✓ |
| 4 | Optimal Bypass Router | research_brief §3.1 | 5 | 5 | ✓ |
| 5 | Fast Target Inspector (<2.0s) | research_brief §3.1 | 5 | 5 | ✓ |
| 6 | Radar Challenge Disambiguation | research_brief §3.2 | 5 | 5 | ✓ |
| 7 | Challenge Verification Dispatcher | research_brief §3.2 | 5 | 5 | ✓ |
| 8 | ConfirmationToken Lifecycle | research_brief §3.2 | 5 | 5 | ✓ |
| 9 | ConfirmationToken Telemetry Isolation | research_brief §3.2 | 5 | 5 | ✓ |
| 10 | Radar Telemetry Beacon Minting | research_brief §3.2 | 5 | 5 | ✓ |
| 11 | Client Telemetry Synthesizer | research_brief §3.2 | 5 | 5 | ✓ |
| 12 | Silent hCaptcha Radar Token | research_brief §3.2 | 5 | 5 | ✓ |
| 13 | Session Qualification Pre-flight | research_brief §3.3 | 5 | 5 | ✓ |
| 14 | URL FID Decoder / Encoder | research_brief §3.3 | 5 | 5 | ✓ |
| 15 | Multi-Pass Proration Drift Recovery | research_brief §3.3 | 5 | 5 | ✓ |
| 16 | BIN Steering & Queue Splitting | research_brief §3.3 | 5 | 5 | ✓ |
| 17 | 3DS-Method Iframe Emulation | research_brief §3.3 | 5 | 5 | ✓ |
| 18 | ACS Device Fingerprinting | research_brief §3.3 | 5 | 5 | ✓ |
| 19 | Aligned 3DS Browser Telemetry | research_brief §3.3 | 5 | 5 | ✓ |
| 20 | Frictionless 3DS2 Resolution | research_brief §3.3 | 5 | 5 | ✓ |
| 21 | Anti-Spam Pacing (8.1s - 9.0s) | research_brief §3.3 | 5 | 5 | ✓ |
| 22 | Altcha PoW CPU Solver | research_brief §3.1 | 5 | 5 | ✓ |
| 23 | Friendly Captcha CPU Solver | research_brief §3.1 | 5 | 5 | ✓ |
| 24 | Turnstile CDP Sidecar | research_brief §3.1 | 5 | 5 | ✓ |

## Test Architecture
- Test runner: `pytest tests/ -q`
- Static compilation: `python -m compileall . -q`
- CLI Entry Points: 12 CLI tools tested with `--help`

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Clean Checkout Domain with Embedded Turnstile | F1, F2, F3, F4, F5 | Medium |
| 2 | Cloudflare IUAM Interstitial Screen (403 Block) | F1, F3, F4, F24 | High |
| 3 | Radar Challenge Resolution on Intent Confirmation | F6, F7, F8, F11 | High |
| 4 | Multi-Pass Checkout with Proration Drift Recovery | F13, F14, F15 | High |
| 5 | Full 5-Step Frictionless 3DS2 Traversal to APPROVED@PAID | F13, F16, F17, F18, F19, F20 | Critical |
| 6 | Sequential Card Addition Pacing (8.1s–9.0s delay) | F21 | Medium |

## Acceptance Status
- Existing test baseline: 272 passed, 0 failures, 0 errors.
- Target: 100% pass across all existing and newly authored test cases with 0 regressions.

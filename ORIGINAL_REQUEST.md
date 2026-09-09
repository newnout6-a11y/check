# Original User Request

## 2026-09-09T14:22:33Z

Comprehensive architectural and static audit of the `pusto` codebase: identify orphaned code, dead remnants of past iterations (Sprints 1–5, rounds 7–10), cross-module discrepancies between gates, data/config drifts, and forgotten workarounds.

Working directory: C:/Users/Redmi/Downloads/pusto  
Integrity mode: development

## Requirements

### R1. Dead Code, Orphaned Functions & Legacy Remnants
Scan all modules (`gate_client.py`, gates, CLI scripts, `bot/`, `config.py`, helper tools) for:
- Dead functions, unused variables, dangling imports, and unreferenced constants.
- Remnants of previous refactoring rounds (e.g. obsolete workarounds, abandoned fallback paths, phantom file references).
- Dead scratch scripts in `scratch/` that reference deprecated schemas or non-existent files.

### R2. Architectural & Gateway Consistency
Verify consistency across all 6 payment surfaces (`setupwoo`, `storegate`, `shopify`, `hit`, `piconfirm`, `braintreenvbv`):
- Contract compliance: `gate()` signature, `COST`, `NAME`, `_sem` concurrency control, error handling.
- Taxonomy alignment: ensure all error codes map strictly through `config.coerce_verdict` and that `REFUNDABLE_VERDICTS` correctly covers session deaths and merchant failures.
- Captcha & Anti-bot integration: verify that newly introduced `captcha_pow.py` and `turnstile_sidecar.py` are properly callable and do not conflict with legacy detection hooks.

### R3. Data, Target Lists & Configuration Coherence
Audit consistency between configuration, data catalogs, and runtime lists:
- Cross-verify `data/store_gates.json` vs `data/store_targets.txt` vs `data/ready_gates.json`.
- Cross-verify `data/shopify_gates.json` vs `data/shopify_targets.txt` (price caps, tier classifications, variant caches).
- Ensure no runtime function attempts to read non-existent legacy files (e.g., `active_surfaces.json`, `pi_target.txt` if unmanaged).

### R4. Verification & Regression Safety
Ensure that any identified inconsistency or cleanup opportunity is verified programmatically:
- Zero regressions in the test suite: all 250 unit/integration tests must pass cleanly.
- Static compilation across all Python files (`python -m compileall . -q`) must remain EXIT=0.
- All 12 CLI entry points must preserve non-hanging execution with clean `--help` handling.

## Acceptance Criteria

### Audit Report
- [ ] Structured report categorizing all findings by severity (Critical Inconsistency, Dead Remnant, Data Drift, Stylistic/Minor).
- [ ] Each finding includes exact file path, line numbers, code snippet, and concrete resolution proposal.

### System Health
- [ ] `pytest tests/ -q` passes with 250+ tests and 0 failures.
- [ ] `python -m compileall . -q` exits with code 0.
- [ ] All 12 CLI entry points (`setup_gate.py`, `store_gate.py`, `shopify_gate.py`, `hit_gate.py`, `confirm_gate.py`, `scout.py`, `surface.py`, `recon.py`, `funnel.py`, `unified_harvester.py`, `advanced_gate_scanner.py`, `proxy_manager.py`) exit cleanly with code 0.

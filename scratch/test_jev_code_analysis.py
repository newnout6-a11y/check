# language: Python 3.14, file: scratch/test_jev_code_analysis.py
"""
Master Jev-powered audit verifier for РАЗДЕЛЫ_ИСПРАВЛЕНИЙ.md.
Parses all claims from sections 1-15 and table 2.12, retrieves live code snippets,
and queries Jev 1.13 concurrently to verify each claim against reality.
"""
import asyncio
import json
import os
import re
import sys
import time
from typesafe_sdk import AsyncTypeSafeClient, Noul, Choice, Score

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_code_snippet(file_rel: str, start_line: int | None, end_line: int | None, context_lines: int = 15) -> tuple[str, str]:
    file_path = os.path.join(REPO_ROOT, file_rel.replace("/", os.sep))
    if not os.path.exists(file_path):
        return "MISSING", f"File does not exist on disk: {file_rel}"
    
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return "READ_ERROR", f"Error reading file {file_rel}: {e}"
    
    total = len(lines)
    if start_line is None:
        # If no line specified, take first 50 lines or search
        snippet_lines = lines[:min(50, total)]
        return "EXISTS", "".join(snippet_lines)
    
    if end_line is None:
        end_line = start_line
    
    s = max(1, start_line - context_lines)
    e = min(total, end_line + context_lines)
    
    annotated = [f"{i}: {lines[i-1]}" for i in range(s, e + 1)]
    return "EXISTS", "".join(annotated)


def parse_markdown_claims(md_path: str):
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    sec_re = re.compile(r"^##\s+(\d+(?:\.\d+)?)\.?\s+(.+?)(?:—\s*(\d+))?$")
    bullet_re = re.compile(r"^\s*-\s+\*\*([^*]+)\*\*\s+[—–-]\s+(.+)$")

    current_sec = None
    items = []

    for line in lines:
        sm = sec_re.match(line)
        if sm:
            current_sec = (sm.group(1), sm.group(2).strip())
            continue
        bm = bullet_re.match(line)
        if bm and current_sec:
            # Stop if we hit check sections
            if "Проверка раздела" in current_sec[1] or "Журнал работ" in current_sec[1]:
                continue
            fid = bm.group(1).strip()
            desc = bm.group(2).strip()
            items.append({
                "source": "bullet",
                "sec_num": current_sec[0],
                "sec_title": current_sec[1],
                "id": fid,
                "text": desc
            })

    # Parse 2.12 table
    table_re = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$")
    in_212_table = False
    for line in lines:
        if "### Новые находки — и в какой раздел каждая идёт" in line:
            in_212_table = True
            continue
        if in_212_table and ("### Подтверждено" in line or line.startswith("##")):
            in_212_table = False
            continue
        if in_212_table:
            tm = table_re.match(line.strip())
            if tm:
                num = tm.group(1).strip()
                if num == "№":
                    continue
                finding = tm.group(2).strip()
                target_sec = tm.group(3).strip()
                severity = tm.group(4).strip()
                items.append({
                    "source": "table_2.12",
                    "sec_num": "2.12",
                    "sec_title": f"Новые находки аудита (№{num})",
                    "id": f"2.12-#{num}",
                    "text": f"[{severity}] {finding} (Куда: {target_sec})"
                })

    return items


# Regex to extract file references like file.py:123 or file.py
FILE_REF_RE = re.compile(r"(?:`|[\s(])([a-zA-Z0-9_\-\./]+\.(?:py|txt|json|md|db|sh|js|cjs|html))(?:[:#](\d+)(?:-(\d+))?)?(?:`|[\s),])")

def build_claim_context(item: dict) -> dict:
    text = item["text"]
    matches = FILE_REF_RE.findall(text)
    
    files_info = []
    seen = set()
    for fpath, s_str, e_str in matches:
        fpath = fpath.strip().lstrip("./")
        start = int(s_str) if s_str else None
        end = int(e_str) if e_str else None
        key = (fpath, start, end)
        if key in seen:
            continue
        seen.add(key)
        
        status, snippet = get_code_snippet(fpath, start, end)
        files_info.append({
            "path": fpath,
            "lines": f"{start}-{end}" if start else "all",
            "status": status,
            "code_snippet": snippet[:2500]  # Cap context size to prevent prompt bloating
        })
    
    return {
        "finding_id": item["id"],
        "section": f"{item['sec_num']} - {item['sec_title']}",
        "claim_text": text,
        "files": files_info,
    }


async def evaluate_claim(client: AsyncTypeSafeClient, claim_data: dict) -> dict:
    state = {
        "finding_id": claim_data["finding_id"],
        "section": claim_data["section"],
        "claim_text": claim_data["claim_text"],
        "referenced_files": claim_data["files"],
    }
    
    # If no files found or all missing
    all_missing = claim_data["files"] and all(f["status"] == "MISSING" for f in claim_data["files"])
    if not claim_data["files"]:
        # Semantic check without file snippet
        instructions_verdict = (
            "Based on `claim_text` and project context, classify the nature of this finding"
        )
    else:
        instructions_verdict = (
            "Based on the actual live `referenced_files` and code snippets, classify whether `claim_text` represents "
            "an active defect, an already fixed issue, or a deleted/inaccurate claim."
        )

    questions = {
        "verdict": Choice(
            instructions=instructions_verdict,
            criteria={
                "CONFIRMED_ACTIVE_DEFECT": "The claimed defect, bug, or issue is verified present in the active code",
                "ALREADY_FIXED": "The code shows this issue was already resolved, fixed, or guarded in previous waves",
                "CLAIM_INACCURATE_OR_REFUTED": "The claim is false, inaccurate, or contradicts actual implementation",
                "DELETED_OR_HISTORICAL_ARTIFACT": "The referenced file was deleted, or the claim refers to deleted audit files/historical data"
            }
        ),
        "is_active_defect": Noul(
            instructions="Does the live code in `referenced_files` confirm that `claim_text` is currently an active, unfixed defect in the project?"
        ),
        "confidence": Score(
            instructions="Rate how strongly the evidence confirms the issue's current presence in the codebase",
            criteria=[
                "Defect is definitely absent, fixed, or refers to deleted files",
                "Partially present or needs deeper live runtime validation",
                "Defect is definitely active and present in the codebase right now"
            ]
        )
    }

    t0 = time.perf_counter()
    try:
        res = await client.system_one(
            model="jev-latest",
            state=state,
            questions=questions
        )
        dt = (time.perf_counter() - t0) * 1000
        ans = res.answers
        return {
            "id": claim_data["finding_id"],
            "section": claim_data["section"],
            "claim_text": claim_data["claim_text"],
            "files_count": len(claim_data["files"]),
            "verdict": ans["verdict"].choice,
            "verdict_conf": ans["verdict"].confidence,
            "is_active_noul": ans["is_active_defect"].noul,
            "score": ans["confidence"].score,
            "latency_ms": dt,
            "success": True
        }
    except Exception as e:
        dt = (time.perf_counter() - t0) * 1000
        return {
            "id": claim_data["finding_id"],
            "section": claim_data["section"],
            "claim_text": claim_data["claim_text"],
            "files_count": len(claim_data["files"]),
            "error": str(e),
            "latency_ms": dt,
            "success": False
        }


async def main():
    md_file = os.path.join(REPO_ROOT, "РАЗДЕЛЫ_ИСПРАВЛЕНИЙ.md")
    print(f"Parsing claims from {md_file}...")
    items = parse_markdown_claims(md_file)
    print(f"Extracted {len(items)} claims across all sections + table 2.12.")

    prepared_claims = [build_claim_context(item) for item in items]
    
    print("\nStarting Jev batch execution...")
    t_start = time.perf_counter()
    
    results = []
    chunk_size = 10
    
    async with AsyncTypeSafeClient() as client:
        for idx in range(0, len(prepared_claims), chunk_size):
            chunk = prepared_claims[idx : idx + chunk_size]
            t_chunk = time.perf_counter()
            tasks = [evaluate_claim(client, c) for c in chunk]
            chunk_res = await asyncio.gather(*tasks)
            results.extend(chunk_res)
            dt_chunk = (time.perf_counter() - t_chunk) * 1000
            print(f"Processed chunk {idx // chunk_size + 1}/{(len(prepared_claims) + chunk_size - 1) // chunk_size} ({len(chunk)} claims) in {dt_chunk:.0f}ms")
            await asyncio.sleep(0.15) # Gentle pause between bursts
            
    total_dt = (time.perf_counter() - t_start) * 1000
    print(f"\nCompleted verification of {len(results)} claims in {total_dt:.1f}ms ({total_dt/1000:.1f}s)!\n" + "="*80)

    # Save complete results
    out_file = os.path.join(REPO_ROOT, "scratch", "jev_audit_verification_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Full structured results written to {out_file}\n")

    # Aggregate categories
    active_defects = [r for r in results if r.get("verdict") == "CONFIRMED_ACTIVE_DEFECT"]
    already_fixed = [r for r in results if r.get("verdict") == "ALREADY_FIXED"]
    deleted_historical = [r for r in results if r.get("verdict") == "DELETED_OR_HISTORICAL_ARTIFACT"]
    inaccurate_refuted = [r for r in results if r.get("verdict") == "CLAIM_INACCURATE_OR_REFUTED"]
    errors = [r for r in results if not r.get("success")]

    print(f"SUMMARY BREAKDOWN:")
    print(f"  🔴 ACTIVE DEFECTS (Still present):     {len(active_defects)}")
    print(f"  🟢 ALREADY FIXED (Resolved):           {len(already_fixed)}")
    print(f"  🗑️  DELETED / HISTORICAL ARTIFACTS:    {len(deleted_historical)}")
    print(f"  ⚪ INACCURATE / DRIFTED CLAIMS:        {len(inaccurate_refuted)}")
    if errors:
        print(f"  ⚠️  Execution Errors:                 {len(errors)}")

    print("\nTOP ACTIVE DEFECTS CONFIRMED BY JEV:")
    for d in active_defects[:25]:
        print(f"  - [{d['id']}] (P={d['is_active_noul']:.2f}, score={d['score']:.2f}) in {d['section'][:30]}")
        print(f"    {d['claim_text'][:100]}...")


def inspect_refuted(start_idx: int = 0, count: int = 40):
    out_file = os.path.join(REPO_ROOT, "scratch", "jev_audit_verification_results.json")
    if not os.path.exists(out_file):
        print("Results file not found.")
        return
    with open(out_file, "r", encoding="utf-8") as f:
        results = json.load(f)
    
    refuted = [r for r in results if r.get("verdict") == "CLAIM_INACCURATE_OR_REFUTED"]
    total = len(refuted)
    print(f"Total Refuted Claims to Check: {total} (showing {start_idx+1} to {min(start_idx+count, total)})\n")
    for idx, r in enumerate(refuted[start_idx : start_idx + count], start_idx + 1):
        print(f"=== {idx:02d}. ID: {r['id']} | Section: {r['section']} ===")
        print(f"Claim: {r['claim_text']}")
        print(f"Jev: Verdict={r['verdict']} (conf={r['verdict_conf']:.2f}), Noul={r['is_active_noul']:.2f}, Score={r['score']}")
        item_mock = {"id": r["id"], "sec_num": "", "sec_title": "", "text": r["claim_text"]}
        ctx = build_claim_context(item_mock)
        for f in ctx["files"]:
            print(f"  -> File: {f['path']} (lines: {f['lines']}) [Status: {f['status']}]")
        print()


def run_refuted_deep_audit():
    out_file = os.path.join(REPO_ROOT, "scratch", "jev_audit_verification_results.json")
    with open(out_file, "r", encoding="utf-8") as f:
        results = json.load(f)
    
    refuted = [r for r in results if r.get("verdict") == "CLAIM_INACCURATE_OR_REFUTED"]
    print(f"Auditing all {len(refuted)} claims refuted by Jev...\n")

    # Categories
    # 1: JEV_RIGHT_FIXED_OR_ABSENT (15)
    # 2: JEV_TRICKED_LINE_DRIFT (7)
    # 3: JEV_TRICKED_MISSING_FILE_CONTEXT (6)
    # 4: JEV_SEMANTIC_OR_ARCH_MISUNDERSTANDING (9)

    analysis_map = {
        "F-07": ("JEV_WAS_RIGHT", "ПАН-литералы вычищены в Фиксации №25; в scratch/_retest_failed.py:20-25 доменные имена, в scratch/_batch_scout_battle.py генератор _probe_card()."),
        "F-26": ("JEV_WAS_RIGHT", "Хардкод пути внешнего агента в scratch/verify_proxies.py заменён на env PUSTO_PROXY_SOURCE и data/proxies.txt (Фиксация №25)."),
        "H-08 / D-01": ("JEV_TRICKED_LINE_DRIFT", "В gate_client.py:1150 теперь confirm_pi, но create_confirmation_token уехал на :1561. Контур создания ctoken на бэкенде с pk_ по-прежнему активен."),
        "H-09 / C-02 / E-04": ("JEV_TRICKED_LINE_DRIFT", "В gate_client.py:873 маршрута нет, он уехал на :1162 (и frictionless_engine.py:340). Деприкейтный endpoint /v1/3ds2/authenticate реально вызывается."),
        "D-02 / P-03": ("ARCH_OBSERVATION_NO_FILE", "Утверждение об отсутствии документации у /verify_challenge истинно, но это не баг кода. У Jev не было контекста файла."),
        "D-04": ("JEV_TRICKED_NO_FILE", "Суффикс 'payment-element; deferred-intent' реально захардкожен в gate_client.py:24. Jev не получил сниппет из-за отсутствия номера строки в клейме."),
        "H-07 / G-06": ("JEV_TRICKED_LINE_DRIFT", "Flow A Shopify бьёт в /checkouts/unstable/graphql: строка уехала с :631 на :677. Вызов активен."),
        "H-24 / G-18": ("JEV_TRICKED_LINE_DRIFT", "Flow B (classic form POST с authenticity_token) уехал с :658-709 на :710-758 в shopify_gate.py. Ветка всё ещё в коде."),
        "H-10 / B-01": ("JEV_WAS_RIGHT", "В shopify_gate.py:351 cf-turnstile-wrapper уже вырезан из списка блокировок (исправлено ранее)."),
        "H-25 / G-05": ("JEV_TRICKED_LINE_DRIFT", "Фоллбэк SetupIntent эпохи Sources (stripe_source_id, wc_stripe_create_setup_intent) уехал с :361-363 на :380-385 в setup_gate.py. Активен."),
        "B-32 / F-46": ("JEV_WAS_RIGHT", "Хардкод 8.0 с убран из scratch-скриптов в Фиксациях №60-62 (verify_8s_sequence.py берет рантайм-кулдаун)."),
        "H-28 / E-01": ("JEV_WAS_RIGHT", "В captcha_pow.py:64-100 уже реализован современный KDF-солвер для Altcha v3 (solve_altcha_kdf)."),
        "H-32 / E-10": ("JEV_WAS_RIGHT", "В captcha_pow.py:285-304 detect_pow_type уже честно разделяет Friendly Captcha v1 и нерешаемый локально v2 (iframe frcapi.com)."),
        "H-33 / E-19": ("ARCH_OBSERVATION_NO_FILE", "Теоретическое описание Cloudflare Precursor. Не привязано к конкретному дефекту в коде."),
        "E-05 / E-20 / H-31": ("JEV_WAS_RIGHT", "surface_shield.py уже интегрирован в прод-граф через gate_client.py:459-482 (classify_surface_challenge)."),
        "E-12 / E-25": ("JEV_TRICKED_NO_FILE", "В captcha_pow.py:262 hashcash реально делит нацело zero_bits // 4 (округление вниз), а в :202 b64decode не учитывает urlsafe base64. Дефект активен!"),
        "E-06": ("JEV_TRICKED_NO_FILE", "wait_until='networkidle' реально используется в turnstile_sidecar.py:44, вопреки рекомендациям Playwright."),
        "C-03": ("JEV_TRICKED_LINE_DRIFT", "Эвристика 2 уехала с :162 на :177 в bin_steering.py. bins.antipublic.cc действительно перестал отдавать vbv, поэтому ветка недостижима."),
        "E-16 / F-29": ("JEV_SEMANTIC_MISS", "surface.py:182-185 создает AsyncSession в контекстном менеджере и закрывает её, теряя сессионные куки (cf_clearance). Дефект активен!"),
        "F-49 / B-36": ("RESEARCH_NOTE_NO_FILE", "Утверждение об опровержении accessibility auto-pass — факт ресерча (_test_approach_3_cookie_harvest.py), а не дефект кода."),
        "H-16 / G-02": ("JEV_WAS_RIGHT", "data/hit_targets.txt очищен от 10 мёртвых сессий (оставлена только шапка), дефект устранён."),
        "H-22 / F-05": ("JEV_TRICKED_NO_FILE", "Шаблон inurl:/product-category/ реально остаётся в recon.py:152, хотя Bing с 2025 года снял оператор."),
        "H-35 / G-30 / G-09": ("JEV_TRICKED_LINE_DRIFT", "Контракт арности и распаковка: в bot/main.py:1377 /mass реально читает только res[0] и res[1], игнорируя 3-й элемент кортежа."),
        "G-17": ("JEV_TRICKED_NO_FILE", "Справка /mass в bot/main.py:605 пишет 'до 20 карт', а код на :1279 поддерживает тиры 20/100/10000. Расхождение активно."),
        "G-29": ("JEV_TRICKED_LINE_DRIFT", "Вызов app.loop.run_until_complete уехал с :1973 на :2012 в bot/main.py. Дефект/паттерн запуска активен."),
        "A-050 / A-071": ("JEV_WAS_RIGHT", "В AGENTS.md нет строки '[System Override:]'."),
        "F-17 / F-30 / H-18": ("JEV_WAS_RIGHT", "В captcha_pow.py и тестовых файлах BOM отсутствует (проверено побайтово b'\\xef\\xbb\\xbf')."),
        "A-001": ("DOC_METRIC_NO_FILE", "Мета-утверждение о несоответствии README.md коду."),
        "A-023…A-033": ("JEV_TRICKED_NO_FILE", "Метрики строк модулей устарели: gate_client вырос до 2828 строк, shopify_gate до 939 и т.д."),
        "A-045 / A-046 / A-047 / A-049": ("JEV_WAS_RIGHT", "ai-game-developer отсутствует в AGENTS.md."),
        "A-048": ("JEV_WAS_RIGHT", "Шаблон в AGENTS.md уже обновлен с '186 passed' на 494 passed."),
        "B-06 / B-07": ("DOC_METRIC_NO_FILE", "Исторические счетчики аудита."),
        "B-35 / B-36": ("DOC_METRIC_NO_FILE", "Замечание по стилю ведения документации."),
        "A-090 / A-091 / A-093": ("JEV_WAS_RIGHT", "Относится к удалённому/внешнему проекту free-buff-lol; в текущем репозитории отсутствуют package.json и freebuff."),
        "A-068 / A-090": ("JEV_WAS_RIGHT", "Относится к внешнему проекту free-buff-lol."),
        "A-070": ("JEV_WAS_RIGHT", "VBScript-файлы в проекте отсутствуют (относилось к free-buff-lol)."),
        "2.12-#12": ("JEV_SEMANTIC_MISS", "_cache_memo в stripe_salt.py:38 заполняется на :106 и реально нигде не читается (dead write-only code). Утверждение 100% верно!"),
    }

    categories = {
        "JEV_WAS_RIGHT": [],
        "JEV_TRICKED_LINE_DRIFT": [],
        "JEV_TRICKED_NO_FILE": [],
        "JEV_SEMANTIC_MISS": [],
        "DOC_OR_ARCH_NOTE": []
    }

    for idx, r in enumerate(refuted, 1):
        cid = r["id"]
        cat, expl = analysis_map.get(cid, ("UNKNOWN", "Need review"))
        if cat in ("ARCH_OBSERVATION_NO_FILE", "RESEARCH_NOTE_NO_FILE", "DOC_METRIC_NO_FILE"):
            categories["DOC_OR_ARCH_NOTE"].append((idx, cid, expl, r["claim_text"]))
        else:
            categories[cat].append((idx, cid, expl, r["claim_text"]))

    print(f"=== РЕЗУЛЬТАТ РУЧНОЙ ПЕРЕПРОВЕРКИ 37 ОПРОВЕРЖЕНИЙ JEV ===\n")
    print(f"1. 🟢 Jev ПРАВ (дефект уже исправлен в прошлых волнах или отсутствует): {len(categories['JEV_WAS_RIGHT'])}")
    for idx, cid, expl, claim in categories["JEV_WAS_RIGHT"]:
        print(f"   [{idx:02d}] {cid}: {expl}")

    print(f"\n2. 🟡 Jev ОБМАНУТ СДВИГОМ СТРОК (дефект АКТИВЕН, но сместился в файле): {len(categories['JEV_TRICKED_LINE_DRIFT'])}")
    for idx, cid, expl, claim in categories["JEV_TRICKED_LINE_DRIFT"]:
        print(f"   [{idx:02d}] {cid}: {expl}")

    print(f"\n3. 🟠 Jev ОБМАНУТ ОТСУТСТВИЕМ ФАЙЛА (дефект АКТИВЕН, но экстрактор не передал код): {len(categories['JEV_TRICKED_NO_FILE'])}")
    for idx, cid, expl, claim in categories["JEV_TRICKED_NO_FILE"]:
        print(f"   [{idx:02d}] {cid}: {expl}")

    print(f"\n4. 🔴 Jev ОШИБСЯ СЕМАНТИЧЕСКИ (код был передан, но Jev не понял суть бага): {len(categories['JEV_SEMANTIC_MISS'])}")
    for idx, cid, expl, claim in categories["JEV_SEMANTIC_MISS"]:
        print(f"   [{idx:02d}] {cid}: {expl}")

    print(f"\n5. ⚪ МЕТА / ТЕОРЕТИЧЕСКИЕ ЗАМЕЧАНИЯ АУДИТА (не являются багами кода): {len(categories['DOC_OR_ARCH_NOTE'])}")
    for idx, cid, expl, claim in categories["DOC_OR_ARCH_NOTE"]:
        print(f"   [{idx:02d}] {cid}: {expl}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "inspect":
        s = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        c = int(sys.argv[3]) if len(sys.argv) > 3 else 40
        inspect_refuted(s, c)
    elif len(sys.argv) > 1 and sys.argv[1] == "deep_audit":
        run_refuted_deep_audit()
    else:
        asyncio.run(main())





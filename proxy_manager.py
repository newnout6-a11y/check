# language: Python 3.12+, file: proxy_manager.py, target: Windows 11, deps: curl_cffi
# Sprint 3.5: пул прокси с авто-валидацией, sticky-привязкой к донору и health-файлом.
import asyncio
import json
import os
import random
import time

from curl_cffi.requests import AsyncSession

import gate_client as gc
import config
import pusto_logger as log

HEALTH_FILE = os.path.join("data", "proxy_health.json")
PROBE_URL = "https://api.ipify.org/?format=json"
VALIDATE_INTERVAL = 30 * 60  # сек между фоновыми ревалидациями


class ProxyPool:
    """alive/dead по фактам запроса, sticky по ключу (домен донора):
    одна сессия донора = один IP на весь прогон карт."""

    def __init__(self, proxies: list[str] | None = None):
        self.entries: list[dict] = []
        seen = set()
        for raw in proxies or []:
            url = gc.normalize_proxy(raw)
            if url and url not in seen:
                seen.add(url)
                self.entries.append({"url": url, "alive": True, "latency_ms": None,
                                     "fail_count": 0, "last_check": 0})
        self._sticky: dict[str, str] = {}
        self._load_health()

    # --- persistence ---

    def _load_health(self):
        if not os.path.exists(HEALTH_FILE):
            return
        try:
            with open(HEALTH_FILE, encoding="utf-8") as f:
                saved = {h["url"]: h for h in json.load(f) if isinstance(h, dict) and "url" in h}
            for e in self.entries:
                h = saved.get(e["url"])
                if h:
                    e.update({k: h[k] for k in ("latency_ms", "fail_count", "alive") if k in h})
        except Exception:
            pass

    def _save_health(self):
        d = os.path.dirname(HEALTH_FILE)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = f"{HEALTH_FILE}.tmp.{os.getpid()}"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([{k: e[k] for k in ("url", "alive", "latency_ms", "fail_count", "last_check")}
                           for e in self.entries], f, indent=2)
            os.replace(tmp, HEALTH_FILE)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass

    # --- validation ---

    async def _check_one(self, e: dict, sem: asyncio.Semaphore, ctx: dict | None = None, on_progress=None):
        if ctx is None:
            ctx = {"done": 0, "alive": 0, "total": len(self.entries)}
        async with sem:
            t0 = time.perf_counter()
            try:
                async with AsyncSession(impersonate=config.pick_impersonate(), verify=False,
                                        proxy=e["url"]) as s:
                    r = await s.get(PROBE_URL, timeout=5)
                    ok = r.status_code == 200
            except Exception:
                ok = False
            lat = int((time.perf_counter() - t0) * 1000)
            e["last_check"] = int(time.time())
            ctx["done"] += 1
            cur_done = ctx["done"]
            total = ctx["total"]
            if ok:
                e["alive"] = True
                e["latency_ms"] = lat
                e["fail_count"] = 0
                ctx["alive"] += 1
                log.log_proxy("ALIVE", e["url"], f"{lat}ms | [{cur_done}/{total}]")
            else:
                e["alive"] = False
                e["fail_count"] += 1
                log.log_proxy("DEAD", e["url"], f"timeout/unreachable | [{cur_done}/{total}]")

            if on_progress and (cur_done % 20 == 0 or cur_done == total):
                try:
                    await on_progress(cur_done, total, ctx["alive"])
                except Exception:
                    pass

    async def validate_all(self, concurrency: int = 80, on_progress=None) -> tuple[int, int]:
        total = len(self.entries)
        sem = asyncio.Semaphore(concurrency)
        ctx = {"done": 0, "alive": 0, "total": total}
        log.log_proxy("VALIDATE_START", None, f"Probing {total} proxies (concurrency: {concurrency}, timeout: 5s)...")
        await asyncio.gather(*[self._check_one(e, sem, ctx, on_progress) for e in self.entries])
        self._save_health()
        alive = sum(1 for e in self.entries if e["alive"])
        log.log_proxy("VALIDATE_FINISH", None, f"Result: {alive}/{total} alive")
        return alive, total

    # --- selection ---

    def _calc_weight(self, e: dict) -> float:
        url = e.get("url", "")
        proto = url.split("://", 1)[0].lower() if "://" in url else "http"
        proto_mult = 2.0 if proto == "socks5" else (1.0 if proto in ("http", "https") else 0.8)
        lat = max(e.get("latency_ms") or 500, 20)
        fail = e.get("fail_count", 0)
        return ((1000.0 / lat) ** 2) * proto_mult / (1.0 + fail * 2.0)

    def _weights(self) -> list[float]:
        return [self._calc_weight(e) for e in self.entries]

    def pick(self, sticky_key: str | None = None) -> str | None:
        alive = [e for e in self.entries if e.get("alive") is True and e.get("fail_count", 0) < 2]
        if not alive:
            log.log_warn("[proxy_manager] no healthy proxies available in pool")
            return None
        if sticky_key and sticky_key in self._sticky:
            url = self._sticky[sticky_key]
            if any(e["url"] == url for e in alive):
                log.log_proxy("STICKY_HIT", url, f"key={sticky_key}")
                return url
            self._sticky.pop(sticky_key, None)

        scored = sorted(alive, key=self._calc_weight, reverse=True)
        if len(scored) >= 10:
            pool_slice = scored[:max(10, int(len(scored) * 0.35))]
        else:
            pool_slice = scored

        weights = [self._calc_weight(e) for e in pool_slice]
        chosen = random.choices(pool_slice, weights=weights, k=1)[0]
        if sticky_key:
            self._sticky[sticky_key] = chosen["url"]
        log.log_proxy("PICK", chosen["url"], f"key={sticky_key or 'random'} alive={len(alive)}/{len(self.entries)}")
        return chosen["url"]

    def mark_bad(self, proxy_url: str | None):
        if not proxy_url:
            return
        for e in self.entries:
            if e["url"] == proxy_url:
                e["fail_count"] += 1
                if e["fail_count"] >= 3:
                    e["alive"] = False
                    for k, v in list(self._sticky.items()):
                        if v == proxy_url:
                            self._sticky.pop(k)
                    log.log_proxy("DEAD", proxy_url, f"fail_count={e['fail_count']} -> marked DEAD")
                else:
                    log.log_proxy("PENALTY", proxy_url, f"fail_count={e['fail_count']}/3")
        self._save_health()

    def status_line(self) -> str:
        alive = [e for e in self.entries if e["alive"]]
        s5 = sum(1 for e in alive if e["url"].startswith("socks5://"))
        s4 = sum(1 for e in alive if e["url"].startswith("socks4://"))
        ht = sum(1 for e in alive if e["url"].startswith("http://") or e["url"].startswith("https://"))
        lats = sorted(e["latency_ms"] for e in alive if e.get("latency_ms"))
        med = lats[len(lats) // 2] if lats else 0
        return f"{len(alive)}/{len(self.entries)} alive (S5: {s5}, S4: {s4}, HTTP: {ht}), median {med}ms"


async def maybe_pool(explicit_proxy: str | None) -> tuple[ProxyPool | None, str | None]:
    """Единая точка входа для CLI: явный --proxy приоритетен; иначе валидированный пул."""
    if explicit_proxy:
        return None, gc.pick_proxy(None, explicit_proxy)
    pool_raw = gc.load_proxies()
    if not pool_raw:
        return None, None
    pp = ProxyPool(pool_raw)
    alive, total = await pp.validate_all()
    log.log_proxy("VALIDATE", None, pp.status_line())
    print(f"[*] Proxy validation: {pp.status_line()}")
    if alive == 0:
        log.log_warn("[proxy_manager] all proxies dead — fallback to direct")
        print("[!] All proxies dead — running direct")
        return None, None
    return pp, None


if __name__ == "__main__":
    async def _main():
        pp, _ = await maybe_pool(None)
        if pp:
            print("[*] sample picks:", pp.pick("donor-a"), "|", pp.pick())
    asyncio.run(_main())

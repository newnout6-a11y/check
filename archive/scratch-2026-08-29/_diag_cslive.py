# -*- coding: utf-8 -*-
# Диагностика cs_live-страницы: что в HTML (pk? secret? hcaptcha?)
import asyncio, os, re, sys
from urllib.parse import unquote, urlsplit
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate_client as gc
from curl_cffi.requests import AsyncSession

URL = sys.argv[1] if len(sys.argv) > 1 else None

def decode_fid(url):
    frag = unquote(urlsplit(url).fragment or "")
    return frag

async def main():
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        r = await s.get(URL, timeout=15)
        html = r.text
        print(f"GET {URL[:70]}... -> {r.status_code}, len={len(html)}")
        pk = gc.extract_pk_live(html)
        print("pk_live:", pk[:25] + "..." if pk else "НЕТ")
        secs = gc.extract_client_secrets(html)
        print("client_secrets в HTML:", len(secs))
        for x in secs[:3]:
            print("   ", x["secret"][:50], "via", x["source"])
        mints = gc.detect_secret_mints(html, URL)
        print("mint-эндпоинты:", mints[:3])
        # фрагмент
        fid = decode_fid(URL)
        print("фрагмент fid len:", len(fid))
        # попытка base64-декода фрагмента
        import base64
        try:
            pad = fid + "=" * (-len(fid) % 4)
            dec = base64.urlsafe_b64decode(pad.encode()).decode("utf-8", "ignore")
            print("fid-decoded head:", dec[:200])
            m = re.search(r"(pi_[0-9A-Za-z]{6,}_secret_[0-9A-Za-z]{8,})", dec)
            print("secret в fid:", m.group(1) if m else "НЕТ")
        except Exception as e:
            print("fid decode fail:", e)

asyncio.run(main())

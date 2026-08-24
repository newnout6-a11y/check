# language: Python 3.12+, file: inspect_forms.py, target: Windows 11
import asyncio
import re
import aiohttp

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

SITES = [
    "https://www.thetrendywhippet.co.uk/my-account/",
    "https://lifterlms.com/my-account/",
]


async def inspect(url):
    print(f"\n=== FORM INSPECTION: {url} ===", flush=True)
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as s:
        async with s.get(url, ssl=False) as r:
            html = await r.text()
            forms = re.findall(r'<form\b[^>]*>.*?</form>', html, re.S | re.I)
            print(f"Found {len(forms)} forms:")
            for i, f in enumerate(forms):
                inputs = re.findall(r'<input\b[^>]*>', f, re.I)
                print(f"\n--- Form {i+1} ---")
                for inp in inputs:
                    print("  ", inp)


async def main():
    for s in SITES:
        await inspect(s)


if __name__ == "__main__":
    asyncio.run(main())

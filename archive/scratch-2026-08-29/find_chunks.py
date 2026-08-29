import re

files = ['scratch/script3.js', 'scratch/checkout-init.js', 'scratch/vendor.js', 'scratch/stripe-main.js']

for fn in files:
    with open(fn, 'r', encoding='utf-8', errors='ignore') as f:
        c = f.read()
    for kw in ['guacamoleVariant', 'enablePlaceholders', 'layoutType', 'backgroundColor', 'fidnandh']:
        matches = [m.start() for m in re.finditer(re.escape(kw), c)]
        if matches:
            print(f"[{fn}] {kw}: {len(matches)} matches")
            for idx in matches[:3]:
                start = max(0, idx - 150)
                end = min(len(c), idx + 250)
                print(f"  [{idx}]: ...{c[start:end]}...")

with open('scratch/stripe-main.js', 'r', encoding='utf-8', errors='ignore') as f:
    c = f.read()

pos = c.find("3950:function")
if pos != -1:
    print("=== Module 3950 in stripe-main.js ===")
    print(c[pos:pos+3000])
else:
    print("3950 not found directly, searching for 3950...")
    for m in re.finditer(r'\b3950\b', c):
        idx = m.start()
        print(f"  [{idx}]:", c[max(0, idx-40):min(len(c), idx+100)])

import json
import sys

def main():
    filepath = r'c:\Users\Redmi\Downloads\pusto\data\ses_fcab092e0ffeNsD51wEuJOPoAJ.json'
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        data = json.load(f)

    messages = data.get('messages', [])
    print(f"Total messages: {len(messages)}")

    for i, m in enumerate(messages):
        info = m.get('info', {})
        role = info.get('role', 'unknown')
        parts = m.get('parts', [])
        summary_parts = []
        first_text = ""
        for p in parts:
            ptype = p.get('type')
            if ptype == 'text':
                t = p.get('text', '')
                summary_parts.append(f"text({len(t)})")
                if not first_text:
                    first_text = t[:120].replace('\n', ' ')
            elif ptype == 'tool':
                tname = p.get('tool') or p.get('name') or ''
                summary_parts.append(f"tool:{tname}")
            elif ptype == 'reasoning':
                summary_parts.append(f"reasoning({len(p.get('text', ''))})")
            else:
                summary_parts.append(str(ptype))

        print(f"[{i:03d}] {role:8s} | parts: {len(parts):2d} ({', '.join(summary_parts[:4])}) | {first_text}")

if __name__ == '__main__':
    main()

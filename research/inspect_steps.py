import json

data = json.load(open('ses_fcab092e0ffeNsD51wEuJOPoAJ.json', encoding='utf-8'))
msgs = data['messages']
for i in range(71, 104):
    print(f"=== STEP {i} ===")
    for p in msgs[i].get('parts', []):
        ptype = p.get('type')
        if ptype in ('reasoning', 'text'):
            print(f"[{ptype}]\n{p.get('text', '')}\n")
        elif ptype == 'tool':
            tool_name = p.get('tool', '')
            state = p.get('state', {})
            cmd = state.get('input', {}).get('command', '')
            out = state.get('output', '')
            print(f"[tool:{tool_name}] cmd: {cmd[:120]}...\nout: {out[:200]}...\n")
    for p in msgs[i].get('parts', []):
        ptype = p.get('type')
        if ptype in ('reasoning', 'text'):
            print(f"[{ptype}]\n{p.get('text', '')}\n")
        elif ptype == 'tool':
            tool_name = p.get('tool', '')
            state = p.get('state', {})
            cmd = state.get('input', {}).get('command', '')
            out = state.get('output', '')
            print(f"[tool:{tool_name}] cmd: {cmd[:120]}...\nout: {out[:200]}...\n")

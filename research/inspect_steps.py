import json
import os
import sys

# Дамп лежит рядом со скриптом; путь не зависит от каталога запуска.
SESDUMP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'ses_fcab092e0ffeNsD51wEuJOPoAJ.json')

# Файл — валидный JSON-объект на первые ~1.97 МБ (117 messages), дальше ~81 КБ
# хвоста от второго, оборванного экспорта. json.load() падает на "Extra data",
# поэтому читаем только валидный префикс через raw_decode.
raw = open(SESDUMP, encoding='utf-8').read()
data, _end = json.JSONDecoder().raw_decode(raw, 0)
tail = len(raw) - _end
if tail:
    print(f"[!] хвост {tail} символов после валидного JSON проигнорирован",
          file=sys.stderr)
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

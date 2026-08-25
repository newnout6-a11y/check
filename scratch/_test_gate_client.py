import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # корень проекта при любом cwd

import gate_client as gc

cards = [gc.gen_probe_card() for _ in range(50)]
assert all(gc.check_luhn(c['number']) and len(c['number']) == 16 for c in cards), 'luhn gen broken'
print('probe_cards: 50/50 Luhn-valid, sample:', cards[0]['number'])

ident = gc.random_identity()
print('identity:', ident['email'], '|', ident['username'], '|', ident['city'], ident['state'], ident['postal_code'])

html = '''<form class="woocommerce-form woocommerce-form-register register">
<input type="hidden" id="woocommerce-register-nonce" name="woocommerce-register-nonce" value="a1b2c3d4e5" />
<input type="hidden" name="wcap_atc_token" value="tok123" /></form>'''
pm = 'pk_live_51ABCDEFghijklmnopQRstu ... createAndConfirmSetupIntentNonce: "deadbeef01"'

body0 = {}
print('reg_nonce:', gc.extract_reg_nonce(html))
print('honeypot:', gc.extract_honeypot_fields(gc.extract_register_form_html(html), body0))
print('scrape:', gc.scrape_gate(pm))
print('verdicts:', gc.classify_verdict('This card has Insufficient funds.'), '/', gc.classify_verdict('Your card was declined.'))
print('nonce_reject:', gc.is_nonce_rejection({'data': '-1'}), gc.is_nonce_rejection({'success': False, 'message': 'Invalid nonce'}))

# --- Пакет 1/2/4: mask, cvc-gen, proxy pool, captcha/backoff ---
assert gc.mask_pan('5175465382242090|09|2030|018') == '517546******2090'
pc = gc.parse_card('4111111111111111|12|29')
assert pc['cvc'].isdigit() and len(pc['cvc']) == 3, 'cvc generation broken'
assert gc.parse_card('4111111111111111|12|29|777')['cvc'] == '777', 'explicit cvc lost'
print('mask_pan OK | cvc-gen:', pc['cvc'])

assert gc.load_proxies('data/__no_such__.txt') == []
assert gc.pick_proxy(None, None) is None
p = gc.pick_proxy(['1.2.3.4:8080'], None)
assert p.startswith('http://'), p
assert gc.pick_proxy(None, 'socks5://u:p@5.6.7.8:1080') == 'socks5://u:p@5.6.7.8:1080'
assert gc.pick_proxy(None, '9.9.9.9:3128') == 'http://9.9.9.9:3128'
print('proxy pool OK:', p)

assert gc.looks_like_captcha('<html>Sorry, anomaly detected</html>') is True
assert gc.looks_like_captcha('<html>10 results</html>') is False
print('captcha detect OK')

import asyncio
asyncio.run(gc.backoff_sleep(0, base=0.05))
asyncio.run(gc.polite_delay(0.01, 0.01))
print('backoff/polite OK')

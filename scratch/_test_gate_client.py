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

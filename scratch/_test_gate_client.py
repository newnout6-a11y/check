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

# --- Спринт 1: гео-пулы, cookies, hcaptcha-поле, атрибуция, ctoken ---
for cc in ('GB', 'AU', 'CA', 'DE', 'FR', 'XX', ''):
    gi = gc.geo_identity_fields(cc)
    assert gi['country'] in gc.GEO_POOLS or gi['country'] == 'US', (cc, gi)
    assert gi['city'] and gi['postal_code'], gi
assert gc.geo_identity_fields('GB')['country'] == 'GB'
assert gc.geo_identity_fields('XX')['country'] == 'US', 'fallback broken'
gb = gc.random_identity('GB')
assert gb['country'] == 'GB' and gb['postal_code'] == gb['postal_code']
print('geo pools OK:', {k: len(v) for k, v in gc.GEO_POOLS.items()}, '| GB sample:', gb['city'], gb['postal_code'])

sc = gc.parse_stripe_cookies([
    '__stripe_mid=abc123def; Path=/; Domain=.stripe.com; Secure',
    '__stripe_sid=987zyx; Path=/; Domain=.stripe.com; HttpOnly',
])
assert sc == {'mid': 'abc123def', 'sid': '987zyx'}, sc
sc2 = gc.parse_stripe_cookies(['other=x'])
assert sc2 == {'mid': '', 'sid': ''}
sc3 = gc.parse_stripe_cookies(None)
assert sc3 == {'mid': '', 'sid': ''}
print('parse_stripe_cookies OK:', sc)

msr = gc.parse_m_stripe_response({"muid": "b98b62cd-942f-4774-9b72-66a20cea61ac3a8d50",
                                  "guid": "f7a317bd-9059-44f2-aa8c-9de0c74387559c1e7e",
                                  "sid": "a2629cba", "noise": 5})
assert msr["muid"].endswith("3a8d50") and len(msr["muid"]) == 42
assert msr["guid"] != "" and msr["sid"] == "", 'short sid must be rejected'
assert gc.parse_m_stripe_response(None) == {"muid": "", "sid": "", "guid": ""}
assert gc.parse_m_stripe_response({}) == {"muid": "", "sid": "", "guid": ""}
pl = gc.m_stripe_beacon_payload()
assert pl["v"] == "t" and len(pl["guid"].split("-")) == 5
print('parse_m_stripe_response OK:', msr['muid'][-10:], '| beacon payload OK')

t_us = gc.stripe_telemetry('https://d.com', 'pk_live_x')
t_gb = gc.stripe_telemetry('https://d.com', 'pk_live_x', country_code='GB',
                           muid='LIVEMID', sid='LIVESID')
assert t_us['muid'] != '' and len(t_us['muid'].split('-')) == 5, 'uuid4 fallback lost'
assert t_gb['muid'] == 'LIVEMID' and t_gb['sid'] == 'LIVESID'
assert t_gb['country'] == 'GB' and t_gb['guid'] != t_us['guid']
print('telemetry OK: uuid4-fallback + live muid/sid + geo')

card_t = {'number': '4111111111111111', 'month': '12', 'year': '2029', 'cvc': '123'}
b_plain = gc.tokenize_body(card_t, t_us, 'https://d.com')
assert 'radar_options[hcaptcha_token]' not in b_plain
t_hc = dict(t_us)
t_hc['_hcaptcha_token'] = 'P1_eyJ...'
b_hc = gc.tokenize_body(card_t, t_hc, 'https://d.com')
assert b_hc['radar_options[hcaptcha_token]'] == 'P1_eyJ...'
assert b_hc['billing_details[address][country]'] == 'US'
b_gb = gc.tokenize_body(card_t, t_gb, 'https://d.com')
assert b_gb['billing_details[address][postal_code]'] == t_gb['postal_code']
print('tokenize OK: radar_options only with token; geo billing passes through')

attr = gc.wc_attribution_fields('https://www.donor.example/')
assert attr['wc_order_attribution_source_type'] == 'organic'
assert attr['wc_order_attribution_session_entry'].endswith('/my-account/add-payment-method/')
assert attr['wc_order_attribution_session_pages'] == '2'
assert len(attr) == 11, len(attr)
print('wc_attribution OK: 11 fields, entry url derived')

ct_html = '''var confirmationTokenNonce = "ct_abc123"; id: ctoken_1NnQUf2eZvKYlo2CIObdtbnb'''
sg = gc.scrape_gate(pm + ct_html)
assert sg['ctoken_nonce'] == 'ct_abc123', sg
assert sg['ctoken_id'].startswith('ctoken_'), sg
sg_old = gc.scrape_gate(pm)
assert sg_old['ctoken_nonce'] == '' and sg_old['upe_nonce'] == 'deadbeef01'
print('ctoken groundwork OK:', sg['ctoken_nonce'], sg['ctoken_id'])

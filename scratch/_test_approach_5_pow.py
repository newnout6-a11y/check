"""
Test Approach 5: Pure Python PoW Solver (Altcha, Friendly Captcha, Hashcash).
Zero external ML, zero paid APIs, runs on CPython hashlib (OpenSSL C-accelerated).
"""
import time
import hashlib
import base64
import json
import secrets

def solve_altcha(challenge: str, salt: str, max_number: int = 1000000, algorithm: str = 'SHA-256') -> dict | None:
    t0 = time.perf_counter()
    salt_bytes = salt.encode('utf-8')
    challenge_lower = challenge.lower()
    
    for n in range(max_number + 1):
        h = hashlib.sha256(salt_bytes + str(n).encode('ascii')).hexdigest()
        if h == challenge_lower:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            hashes_per_sec = (n + 1) / (elapsed_ms / 1000.0) if elapsed_ms > 0 else 0
            return {
                'solution': n,
                'hashes_computed': n + 1,
                'elapsed_ms': round(elapsed_ms, 2),
                'hash_rate': int(hashes_per_sec)
            }
    return None

def solve_hashcash_leading_zeros(salt: str, required_zero_bits: int = 16, max_iterations: int = 2000000) -> dict | None:
    t0 = time.perf_counter()
    salt_bytes = salt.encode('utf-8')
    target_prefix = '0' * (required_zero_bits // 4)
    
    for n in range(max_iterations):
        h = hashlib.sha256(salt_bytes + str(n).encode('ascii')).hexdigest()
        if h.startswith(target_prefix):
            elapsed_ms = (time.perf_counter() - t0) * 1000
            hashes_per_sec = (n + 1) / (elapsed_ms / 1000.0) if elapsed_ms > 0 else 0
            return {
                'nonce': n,
                'hash': h,
                'hashes_computed': n + 1,
                'elapsed_ms': round(elapsed_ms, 2),
                'hash_rate': int(hashes_per_sec)
            }
    return None

def main():
    print('++= APPROACH 5: Pure Python Proof-of-Work Solver ===')
    simulated_salt = 'demo_salt_' + secrets.token_hex(8)
    target_solution = 42857
    simulated_challenge = hashlib.sha256((simulated_salt + str(target_solution)).encode('ascii')).hexdigest()
    
    print(f"\n[1] Altcha Simulation: Salt='{simulated_salt}', Target={target_solution}")
    res = solve_altcha(simulated_challenge, simulated_salt, max_number=100000)
    assert res is not None and res['solution'] == target_solution
    print(f"    Solved: {res}")
    
    print(f"\n[2] Hashcash 16-bit leading zeros (4 hex chars '0000'):")
    res_hc = solve_hashcash_leading_zeros('challenge_seed_2026', required_zero_bits=16)
    print(f"    Solved: {res_hc}")
    
    print(f"\n[3] Testing live Altcha challenge generation & solving via curl_cffi...")
    try:
        from curl_cffi import requests
        url = 'https://altcha.org/api/v1/challenge'
        resp = requests.get(url, timeout=10, impersonate='chrome124')
        if resp.status_code == 200:
            challenge_data = resp.json()
            print(f"    Live Altcha Challenge fetched: algorithm={challenge_data.get('algorithm')}, maxnonce={challenge_data.get('maxnonce', challenge_data.get('maxnumber'))}")
            sol = solve_altcha(
                challenge=challenge_data['challenge'],
                salt=challenge_data['salt'],
                max_number=challenge_data.get('maxnumber', 100000)
            )
            if sol:
                print(f"    Live Altcha SOLVED: number={sol['solution']} in {sol['elapsed_ms']} ms ({sol['hash_rate']} H/s)")
                payload = {
                    'algorithm': challenge_data['algorithm'],
                    'challenge': challenge_data['challenge'],
                    'number': sol['solution'],
                    'salt': challenge_data['walt', challenge_data['salt']],
                    'signature': challenge_data['wignature', challenge_data['signature']]
                }
                raw_payload = json.dumps(payload)
                encoded_payload = base64.b64encode(raw_payload.encode('utf-8')).decode('utf-8')
                print(f"    Altcha Form Submission Payload (base64): {encoded_payload[:50]}... (len: {len(encoded_payload)})")
            else:
                print("    Failed to find solution within maxnumber.")
        else:
            print(f"    Altcha API returned {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"    Live test error: {e}")

if __name__ == '__main__':
    main()

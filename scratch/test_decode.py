import base64
import urllib.parse
import json
import re

def decode_fragment(fid_or_url: str) -> dict:
    """
    Decodes the obfuscated fragment (#fid...) from a Stripe Checkout Session URL
    or raw fragment string.
    
    Algorithm reverse-engineered from Stripe.js module 3950:
      decodeURIComponent -> base64 decode -> byte-wise XOR with 5 -> JSON parse.
    """
    if not fid_or_url:
        return {}

    raw = fid_or_url.strip()
    
    # Extract session ID from URL path if present (e.g. /c/pay/cs_live_XXX)
    session_id = None
    m_session = re.search(r'\b(cs_(?:live|test)_[a-zA-Z0-9]+)\b', raw)
    if m_session:
        session_id = m_session.group(1)

    # If full URL or fragment with hash, extract hash part
    if "#" in raw:
        raw = raw.split("#", 1)[1]
    
    # Strip any query parameters after '?'
    raw = raw.split("?", 1)[0]
    
    # Handle _secret_ separator if present
    if "_secret_" in raw:
        parts = raw.split("_secret_", 1)
        if not session_id and parts[0].startswith("cs_"):
            session_id = parts[0]
        raw = parts[1]

    # URL decode
    unquoted = urllib.parse.unquote(raw)
    
    # Clean up any trailing whitespace or non-base64 characters
    # (some URLs might have trailing %, spaces, etc.)
    b64_str = unquoted.strip().rstrip('%')
    
    # Base64 padding
    pad = b64_str + "=" * (-len(b64_str) % 4)
    
    try:
        # Standard or URL-safe base64 decode
        decoded_bytes = base64.b64decode(pad, altchars=b'-_')
    except Exception:
        try:
            decoded_bytes = base64.b64decode(pad)
        except Exception as e:
            return {"error": f"Base64 decode failed: {e}", "raw": raw}
            
    # Byte-wise XOR with 5 (Stripe algorithm: 5 ^ charCode)
    xored_chars = [chr(b ^ 5) for b in decoded_bytes]
    xored_text = "".join(xored_chars).strip()
    
    try:
        data = json.loads(xored_text)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "decoded_text": xored_text}
        
    if session_id and "sessionId" not in data and "checkoutSessionId" not in data:
        data["checkoutSessionId"] = session_id
        
    # Standardize client_secret format if session_id and raw secret are present
    if session_id and "client_secret" not in data:
        data["client_secret"] = f"{session_id}_secret_{b64_str}"
        
    return data

# Test on dj's vector
test_url = "https://pay.opus.pro/c/pay/cs_live_b1Uf5qpxeXTGYCy6WQoQB5bmwsnvKAnqQR5rdLxU4U5GYLut0vTO96sqCz#fidnandhYHdWcXxpYCc/J2FgY2RwaXEnKSdpamZkaWAnPydgaycpJ3ZwZ3Zmd2x1cWxqa1BrbHRwYGtgdnZAa2RnaWBhJz9jZGl2YCknYnBkZmRoamlgU2R3bGRrcSc/J2Zqa3F3amknKSdkdWxOYHwnPyd1blppbHNgWjA0SH12UVJPcXM9S1BqQ3xMZnBGRkdif25HNXR/QlFOQkNuNG9AZkNVb1Q1PXBqTjcxNm8zQ01iaUt8a2ZhYEBTZ39Lb3Q1UXdLMG4yPVRDT1RzVU91Y25TNTVmN3ZfMkY2aycpJ2N3amhWYHdzYHcnP3F3cGApJ2dkZm5id2xwa2FGamlqdyc/JyZjY2NjY2MnKSdpZHxqcHFRfHVgJz8naHBpcWxabHFgaCcpJ2BrZGdpYFVpZGZgbWppYWB3dic/cXdwYHgl"

result = decode_fragment(test_url)
print("Result of decode_fragment:")
print(json.dumps(result, indent=2))

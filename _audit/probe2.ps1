$ErrorActionPreference = 'Continue'
$T = [char]9
function G($u) { $c = & curl.exe -sS -o NUL -w '%{http_code}' --max-time 25 $u 2>$null; return ($c + $T + $u) }
$hdr = & curl.exe -sSI --max-time 25 'https://challenges.cloudflare.com/turnstile/v0/api.js'
Write-Output ('API_JS_HEADERS: ' + (($hdr | Select-String -Pattern 'location|HTTP/' -CaseSensitive:$false) -join ' || '))
Write-Output ('GET_PARAM ' + (G 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=cb&render=explicit'))
Write-Output ('POST_siteverify ' + (& curl.exe -sS -o NUL -w '%{http_code}' --max-time 20 -X POST -d 'secret=x&response=y' 'https://challenges.cloudflare.com/turnstile/v0/siteverify'))
Write-Output ('POST_siteverify_body ' + ((& curl.exe -sS --max-time 20 -X POST -d 'secret=x&response=y' 'https://challenges.cloudflare.com/turnstile/v0/siteverify') -join ' '))
Write-Output ('POST_checksiteconfig_code ' + (& curl.exe -sS -o NUL -w '%{http_code}' --max-time 20 -X POST 'https://api.hcaptcha.com/checksiteconfig?v=fe705f067f&sitekey=10000000-ffff-ffff-ffff-000000000001&host=b.stripecdn.com&sc=1&swa=1'))
Write-Output ('POST_checksiteconfig_body ' + ((& curl.exe -sS --max-time 20 -X POST 'https://api.hcaptcha.com/checksiteconfig?v=fe705f067f&sitekey=10000000-ffff-ffff-ffff-000000000001&host=b.stripecdn.com&sc=1&swa=1') -join ' '))
Write-Output ('GET_hcaptcha_getcaptcha_slash1 ' + (G 'https://api.hcaptcha.com/getcaptcha/1'))
Write-Output ('POST_hcaptcha_getcaptcha ' + (& curl.exe -sS -o NUL -w '%{http_code}' --max-time 20 -X POST 'https://api.hcaptcha.com/getcaptcha'))
Write-Output ('GET_js_hcaptcha_apijs ' + (G 'https://js.hcaptcha.com/1/api.js'))
Write-Output ('POST_wallet_config_nokey ' + (& curl.exe -sS -o NUL -w '%{http_code}' --max-time 20 -X POST -H 'Origin: https://js.stripe.com' -H 'Accept: application/json' 'https://merchant-ui-api.stripe.com/elements/wallet-config'))
$wc2 = ((& curl.exe -sS --max-time 20 -X POST -H 'Origin: https://js.stripe.com' -H 'Accept: application/json' 'https://merchant-ui-api.stripe.com/elements/wallet-config') -join ' ')
Write-Output ('POST_wallet_config_body ' + $wc2.Substring(0, [Math]::Min(300, $wc2.Length)))
foreach ($u in @('https://docs.stripe.com/api/versioning','https://docs.stripe.com/api/3ds2','https://docs.stripe.com/api/3d_secure','https://docs.stripe.com/upgrades')) { $c = & curl.exe -sS -o NUL -w '%{http_code}' --max-time 25 -A 'Mozilla/5.0' -L $u 2>$null; Write-Output ('DOC ' + $c + $T + $u) }
Write-Output ('PYPI_patchright_latest ' + ((& curl.exe -sS --max-time 25 'https://pypi.org/pypi/patchright/json' | ConvertFrom-Json).info.version))
Write-Output ('INSTALLED_patchright ' + ((python -c "import importlib.metadata as m; print(m.version('patchright'))" 2>&1) -join ' '))
Write-Output ('PYTHON ' + ((python -V 2>&1) -join ' '))
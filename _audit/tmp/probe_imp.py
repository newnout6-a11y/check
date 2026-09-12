import config, curl_cffi
from curl_cffi import requests as cr
ok=[]; bad=[]
for name in config.IMPERSONATIONS:
    try:
        cr.Session(impersonate=name); ok.append(name)
    except Exception as e:
        bad.append(name)
print('curl_cffi', curl_cffi.__version__)
print('CONFIG_IMPERSONATIONS', len(config.IMPERSONATIONS))
print('IMPERSONATIONS_LIST', config.IMPERSONATIONS)
print('OK_COUNT', len(ok))
print('BAD', bad)
print('CHROME_IMPERSONATE', config.CHROME_IMPERSONATE, config.CHROME_IMPERSONATE in ok)
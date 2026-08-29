# -*- coding: utf-8 -*-
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate_client as gc
# та же карта dj + мусорная с тем же BIN
dj = '4937241006643332'
fake = '493724' + '9' * 9  # 493724 + мусорный хвост
fake = fake + str(gc.luhn_check_digit(fake))
print('dj:    ', dj, '| luhn:', gc.check_luhn(dj))
print('fake:  ', fake, '| luhn:', gc.check_luhn(fake))
open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scratch', '_cards_test.txt'), 'w', encoding='utf-8').write(
    fake + '|02|31|275\n' + dj + '|02|31|275')
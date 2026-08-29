# -*- coding: utf-8 -*-
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.utils import formatter as f
print(f.format_single('4937241006648317',
    {'scheme': 'visa', 'type': 'credit', 'country': {'alpha2': 'SG'}, 'bank': {'name': 'Dcs Card Centre'}},
    'Store API (<$1)', 'DECLINED', '[10c USD] Your card was declined.', 12844))
print()
print(f.format_single('5175463822420903',
    {'scheme': 'mastercard', 'type': 'debit', 'country': {'alpha2': 'SG'}, 'bank': {'name': 'Sunrate'}},
    'Store API ($5-20)', 'APPROVED@PAID', '[399c EUR] Order 81557 paid.', 843))
print()
print(f.format_single('4111111111111111', {},
    'Stripe Auth', 'APPROVED', 'SetupIntent succeeded ($0 auth passed)', 2310))

# -*- coding: utf-8 -*-
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.utils import formatter as f
print(f.format_single('4937241006648317',
    {'scheme': 'visa', 'type': 'credit', 'country': {'alpha2': 'SG'}, 'bank': {'name': 'Dcs Card Centre'}},
    'Store API (<$1)', 'DECLINED', '[10c USD] Your card was declined.', 12844,
    proxy='1.0.170.50:8080', pool_size=86))
print()
print(f.format_single('4937241006648317',
    {'scheme': 'visa', 'type': 'credit', 'country': {'alpha2': 'SG'}, 'bank': {'name': 'Dcs Card Centre'}},
    'Stripe Auth', 'APPROVED', 'SetupIntent succeeded', 2310))

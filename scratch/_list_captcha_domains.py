# language: python, file: scratch/_list_captcha_domains.py
import sqlite3

con = sqlite3.connect("data/domains.db")
for r in con.execute("SELECT domain FROM domains WHERE scan_result='CAPTCHA_ADDCARD'"):
    print(r[0])

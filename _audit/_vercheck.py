import importlib.metadata as m
for p in ['curl_cffi','aiohttp','kurigram','pyrogram','tgcrypto','pytest','patchright','playwright','requests','pycryptodome']:
    try: print('DIST', p, m.version(p))
    except Exception as e: print('DIST', p, 'NOT-INSTALLED')
import pyrogram
print('pyrogram.__version__ =', getattr(pyrogram,'__version__','?'))
print('pyrogram.__file__ =', pyrogram.__file__)

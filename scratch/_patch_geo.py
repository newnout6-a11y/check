# language: python, file: scratch/_patch_geo.py — единая geo-жеребьёвка в store_api_confirm
path = "gate_client.py"
src = open(path, encoding="utf-8").read()

old = "ident = {**random_identity(country), **geo_identity_fields(country)}"
assert src.count(old) == 1, f"anchor count = {src.count(old)}"

# единственный geo-бросок: city/state/postcode всегда из одного пула-кортежа;
# telem и ident делят его, биллинг/шиппинг консистентны
new = """geo = geo_identity_fields(country)
        telem.update(geo)
        ident = {**random_identity(country), **geo}"""

src = src.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(src)
print("PATCHED")

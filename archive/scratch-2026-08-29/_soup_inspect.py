import re
from bs4 import BeautifulSoup

with open("scratch/checkout_page.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

print("Title:", soup.title.string if soup.title else None)

# Print all meta tags
print("\n--- Meta tags ---")
for meta in soup.find_all("meta"):
    print(meta.attrs)

# Print all script tags
print("\n--- Scripts ---")
for i, s in enumerate(soup.find_all("script")):
    src = s.get("src")
    type_ = s.get("type")
    content = s.string or s.text or ""
    print(f"Script {i}: src={src}, type={type_}, length={len(content)}")
    if content and len(content) < 500:
        print(f"   Content: {content.strip()}")

# Print root divs
print("\n--- Body Divs ---")
for div in soup.body.find_all("div", recursive=False) if soup.body else []:
    print(f"Div id={div.get('id')}, class={div.get('class')}, len_attrs={len(div.attrs)}")
    for k, v in div.attrs.items():
        if len(str(v)) > 50:
            print(f"  attr {k}: {str(v)[:100]}...")
        else:
            print(f"  attr {k}: {v}")

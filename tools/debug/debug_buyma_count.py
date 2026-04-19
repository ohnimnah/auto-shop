import re
import time
import urllib.parse
from collections import Counter
from selenium import webdriver
from bs4 import BeautifulSoup

q = "S260106HBP13"
url = "https://www.buyma.com/r/?keyword=" + urllib.parse.quote(q)

driver = webdriver.Chrome()
driver.get(url)
time.sleep(4)

soup = BeautifulSoup(driver.page_source, "html.parser")
text = soup.get_text(" ", strip=True)

m = re.search(r"該当件数\s*([0-9]+)件", text)
print("count_match=", m.group(1) if m else None)

all_links = soup.select('a[href*="/item/"]')
print("all_item_links=", len(all_links))

for sel in ["#result", "[id*=result]", ".result", ".result__list", ".search-result", "[class*=result]"]:
    nodes = soup.select(sel)
    if nodes:
        print("selector", sel, "nodes", len(nodes))

counter = Counter()
for a in all_links[:300]:
    classes = " ".join(a.get("class", []) or [])
    counter[classes] += 1
print("top_link_classes=", counter.most_common(20))

result_nodes = soup.select("[class*=result], [id*=result]")
filtered = []
for node in result_nodes:
    filtered.extend(node.select('a[href*="/item/"]'))
print("item_links_in_result_nodes=", len(filtered))

uniq_all = set()
for a in all_links:
    href = (a.get("href", "") or "").split("?")[0]
    if re.search(r"/item/\d+/?", href):
        uniq_all.add(href)
print("uniq_digit_item_links_all=", len(uniq_all))

uniq_result = set()
for a in filtered:
    href = (a.get("href", "") or "").split("?")[0]
    if re.search(r"/item/\d+/?", href):
        uniq_result.add(href)
print("uniq_digit_item_links_result_nodes=", len(uniq_result))

# 후보가 되는 result 계열 컨테이너마다 고유 item 개수
for sel in [".result", ".result__wrapper", ".result__oneitem", ".result__item", ".result-items", "#result"]:
    nodes = soup.select(sel)
    if not nodes:
        continue
    merged = set()
    for node in nodes:
        for a in node.select('a[href*="/item/"]'):
            href = (a.get("href", "") or "").split("?")[0]
            if re.search(r"/item/\d+/?", href):
                merged.add(href)
    print("selector_items", sel, len(merged))

driver.quit()

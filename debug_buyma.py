#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from selenium import webdriver
from bs4 import BeautifulSoup
import time
import urllib.parse
import json

driver = webdriver.Chrome()
query = 'Uniqlo T-Shirt'
encoded = urllib.parse.quote(query)
search_url = f'https://www.buyma.com/r/?keyword={encoded}'
print(f'접속: {search_url}\n')
driver.get(search_url)
time.sleep(3)

soup = BeautifulSoup(driver.page_source, 'html.parser')

# 상품 카드 구조 분석
print('=== 상품 카드 HTML 구조 ===\n')

# 여러 가지 가능한 상품 컨테이너 찾기
selectors = [
    'div[class*="product"]',
    'div[class*="item"]',
    'a[class*="product"]',
    'li[class*="product"]',
    'div.product',
    'div.item',
]

found_selector = None
for container_selector in selectors:
    try:
        items = soup.select(container_selector)
        if items and len(items) > 1:
            print(f'✓ 선택자: {container_selector}')
            print(f'  발견된 수: {len(items)}')
            if items:
                # 첫 번째 아이템의 HTML 샘플
                print(f'  첫번째 아이템 HTML (처음 800자):')
                print(f'  {str(items[0])[:800]}')
                print()
            found_selector = container_selector
            break
    except:
        pass

# 가격 표시 위치 분석
print('\n=== 가격 요소 분석 ===\n')
price_elements = soup.find_all(['span', 'div', 'p'], class_=lambda x: x and 'price' in (x or '').lower())
print(f'가격 관련 요소 총 {len(price_elements)}개 발견')

# 처음 10개의 가격 요소 표시
for i, elem in enumerate(price_elements[:10]):
    class_str = ', '.join(elem.get('class', []))
    text = elem.get_text(strip=True)[:60]
    print(f'{i+1}. [{class_str}]: {text}')

# 각 상품 카드에서 가격 추출 테스트
if found_selector:
    print(f'\n=== 상품별 가격 추출 테스트 ===\n')
    items = soup.select(found_selector)
    for i, item in enumerate(items[:3]):
        print(f'{i+1}번째 상품:')
        
        # 상품명 추출
        title = item.find(['a', 'h2', 'h3', 'span'], class_=lambda x: x and any(s in (x or '').lower() for s in ['title', 'name', 'product']))
        if title:
            print(f'  상품명: {title.get_text(strip=True)[:50]}')
        
        # 가격 추출
        price_elem = item.find(['span', 'div', 'p'], class_=lambda x: x and 'price' in (x or '').lower())
        if price_elem:
            print(f'  가격: {price_elem.get_text(strip=True)[:50]}')
        
        print()

driver.quit()

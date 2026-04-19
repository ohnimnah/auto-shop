from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time, re

url = 'https://www.musinsa.com/products/1844582'
chrome_options = ChromeOptions()
chrome_options.add_argument('--headless=new')
chrome_options.add_argument('--disable-blink-features=AutomationControlled')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
try:
    driver.get(url)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    time.sleep(3)
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    print('TITLE:', soup.title.string if soup.title else 'NO TITLE')
    print('H1:', [h.text.strip() for h in soup.find_all('h1')][:10])
    print('H2:', [h.text.strip() for h in soup.find_all('h2')][:10])
    print('PRICE TEXTS:')
    prices = []
    for tag in soup.find_all(text=re.compile('원')):
        text = tag.strip()
        if len(text) < 100 and any(ch.isdigit() for ch in text):
            prices.append(text)
    for p in prices[:30]:
        print('  ', p)
    page_text = soup.get_text()
    matches = re.findall(r'(\d{1,3}(?:,\d{3})*)\s*원', page_text)
    print('PRICE MATCHES:', matches[:20])
    
    # price 관련 class 확인
    print('PRICE CLASS ELEMENTS:')
    found = []
    for tag in soup.find_all(class_=re.compile('price|Price|PRICE|cost|Cost|COST')):
        cls = ' '.join(tag.get('class', []))
        text = tag.text.strip()[:80]
        if (cls, text) not in found:
            found.append((cls, text))
        if len(found) >= 20:
            break
    for cls, text in found:
        print(' ', cls, '->', text)
    
    print('PRODUCT INFO BLOCKS:')
    for selector in ['.product_basic', '.product_detail', '.product-info', '.product_info', '.product_basic_info', '.product_detail_info', '.product_title', '.product_name']:
        elems = soup.select(selector)
        if elems:
            print('SELECTOR', selector, 'count', len(elems))
            for e in elems[:3]:
                print('  ', e.text.strip()[:180])
finally:
    driver.quit()

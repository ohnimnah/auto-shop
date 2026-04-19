"""
BUYMA 가격 검색 함수 - main.py에 추가할 코드
"""

def fetch_buyma_lowest_price(driver, product_name: str, brand: str, raw_product_name: str = "") -> str:
    """품번/영문상품명으로 BUYMA 검색 후 셀러 상품의 최저가를 엔화 문자열로 반환한다"""
    print(f"\n>>> BUYMA 최저가 검색 시작")
    print(f"    정제명: {product_name}")
    print(f"    원본명: {raw_product_name}")
    print(f"    브랜드: {brand}")
    
    cleaned_name = re.sub(r'\s+', ' ', (product_name or '').strip())
    cleaned_brand = re.sub(r'\s+', ' ', (brand or '').strip())

    # ★ 원본 상품명에서 품번 추출 (우선순위 1번)
    sku_from_raw = None
    if raw_product_name:
        sku_match = re.search(r'/\s*([A-Z0-9-]{2,})\s*$', raw_product_name)
        if sku_match:
            sku_from_raw = sku_match.group(1)
            print(f"    [품번 추출] {sku_from_raw}")

    # 정제된 상품명에서 SKU 형태 추출
    sku_in_clean = re.search(r'\b([A-Z]{2,}[0-9]{2,}[A-Z0-9]*|[0-9]{4,})\b', cleaned_name)
    
    # 상품명에서 영문 부분만 추출
    english_parts = re.findall(r'[A-Za-z0-9\s\-/]+', cleaned_name)
    english_name = ' '.join(english_parts)
    english_name = re.sub(r'\s+', ' ', english_name).strip()

    print(f"    [정제명 SKU] {sku_in_clean.group(1) if sku_in_clean else 'None'}")
    print(f"    [영문명] {english_name if english_name else 'None'}")

    # ★ 검색 우선순위: 원본 품번 > 정제명 SKU > 영문명
    queries = []
    
    if sku_from_raw:
        queries.append(sku_from_raw)
    if sku_in_clean and sku_in_clean.group(1) not in queries:
        queries.append(sku_in_clean.group(1))
    if english_name and english_name not in queries:
        queries.append(english_name)
    if cleaned_brand and english_name and f"{cleaned_brand} {english_name}".strip() not in queries:
        queries.append(f"{cleaned_brand} {english_name}".strip())
    if cleaned_brand and cleaned_brand not in queries:
        queries.append(cleaned_brand)
    
    queries = [q for q in queries if q and len(q.strip()) >= 2]
    print(f"    [검색 쿼리] {queries}")

    if not queries:
        print(f"    검색 쿼리 없음")
        return ""

    for idx, query in enumerate(queries):
        try:
            encoded = urllib.parse.quote(query)
            search_url = f"https://www.buyma.com/r/?keyword={encoded}"
            print(f"  [{idx+1}] {query} 검색 중...")
            driver.get(search_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(3)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # 실제 셀러 상품의 가격 추출
            price_elements = soup.find_all('span', class_='Price_Txt')
            yen_candidates = []
            
            for price_elem in price_elements:
                price_text = price_elem.get_text(strip=True)
                prices = extract_yen_values(price_text)
                if prices:
                    yen_candidates.extend(prices)

            if not yen_candidates:
                print(f"    가격 미추출")
                continue

            yen_candidates = sorted(list(set(yen_candidates)))
            min_price = min(yen_candidates)
            
            # 합리적인 가격 필터링 (너무 저가 제외)
            filtered = [p for p in yen_candidates if p >= 3000]
            
            if filtered:
                p90 = filtered[int(len(filtered) * 0.9)]
                final_prices = [p for p in filtered if p <= p90]
                if final_prices:
                    best_price = min(final_prices)
                    print(f"    ✓ 최저가: {best_price:,}엔")
                    return f"{best_price:,}엔"
            
            if min_price > 2000:
                print(f"    ✓ 최저가: {min_price:,}엔")
                return f"{min_price:,}엔"

        except Exception as e:
            print(f"    오류: {e}")

    print(f"  검색 실패")
    return ""

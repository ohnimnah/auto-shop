# 무신사 자동화 스크립트 - 고급 설정

## 🔧 크롤링 옵션

```python
# main.py의 다음 부분을 수정하세요

# User-Agent 변경 (무신사 차단 회피용)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
    'Referer': 'https://www.musinsa.com/'
}

# 크롤링 속도 조절 (초)
# 너무 빠르면 무신사에서 차단할 수 있음
TIME_DELAY = 2  # 2초 (추천: 1-5초)

# 타임아웃 설정 (초)
REQUEST_TIMEOUT = 10  # 10초
```

## 📊 가격 변환 설정

바이마에 맞도록 가격을 변환하고 싶으면:

```python
def convert_price_to_baima(musinsa_price):
    """무신사 가격을 바이마 가격으로 변환"""
    # 예: 1000원 = 약 1엔
    try:
        price_num = int(''.join(filter(str.isdigit, str(musinsa_price))))
        baima_price = price_num // 1000  # 1000원 ÷ 1000 = 1엔
        return f"{baima_price}円"
    except:
        return musinsa_price
```

## 🌐 프록시 설정

무신사에서 차단되는 경우 프록시 사용:

```python
import requests
from requests.exceptions import ProxyError

PROXIES = {
    'http': 'http://프록시주소:포트',
    'https': 'http://프록시주소:포트',
}

# requests.get() 호출 시:
response = requests.get(url, headers=HEADERS, proxies=PROXIES, timeout=10)
```

## 🔄 배치 처리

여러 개의 Google Sheets 자동 처리:

```python
# config.py 파일 생성 후:

SHEETS_CONFIG = [
    {
        'name': '나이키',
        'id': 'SHEET_ID_1',
        'sheet_name': '나이키',
    },
    {
        'name': '아디다스',
        'id': 'SHEET_ID_2',
        'sheet_name': '아디다스',
    },
    {
        'name': '아크테릭스',
        'id': 'SHEET_ID_3',
        'sheet_name': '아크테릭스',
    },
]

# main.py에서:
for config in SHEETS_CONFIG:
    print(f"처리 중: {config['name']}")
    # 각 시트별로 처리
```

## 📧 에러 알림

크롤링 중 에러 발생 시 이메일로 알림:

```python
import smtplib
from email.mime.text import MIMEText

def send_error_email(error_msg):
    """에러 이메일 전송"""
    sender_email = "your_email@gmail.com"
    sender_password = "your_password"  # 앱 비밀번호
    
    message = MIMEText(f"에러 발생: {error_msg}")
    message['Subject'] = "[무신사 자동화] 에러 발생"
    message['From'] = sender_email
    message['To'] = sender_email
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender_email, sender_password)
        server.send_message(message)
```

## 🎯 필터링 설정

특정 조건의 상품만 처리하고 싶으면:

```python
# 가격 범위 필터
MIN_PRICE = 20000
MAX_PRICE = 1000000

# 상품명 키워드 필터
BRAND_KEYWORDS = ['NIKE', 'ADIDAS', '아크테릭스']

# 필터링 함수
def should_process(product_info):
    """상품을 처리할지 결정"""
    try:
        price = int(''.join(filter(str.isdigit, str(product_info['price']))))
        
        # 가격 범위 확인
        if price < MIN_PRICE or price > MAX_PRICE:
            return False
        
        # 키워드 확인
        name = product_info['name'].upper()
        if not any(keyword.upper() in name for keyword in BRAND_KEYWORDS):
            return False
        
        return True
    except:
        return False
```

## 🔐 보안 팁

### 1. credentials.json 보호
- `.gitignore`에 추가: `credentials.json`
- 절대 공개 저장소에 커밋하지 마세요

### 2. API 키 환경변수로 설정
```python
import os
from dotenv import load_dotenv

load_dotenv()

SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
```

### 3. `.env` 파일 생성
```
SPREADSHEET_ID=YOUR_SHEETS_ID
SHEET_NAME=시트1
```

## 📈 성능 최적화

### 동시 요청 처리 (고급)
```python
from concurrent.futures import ThreadPoolExecutor
import threading

def process_urls_concurrently(urls, max_workers=3):
    """여러 URL을 동시에 처리"""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(scrape_musinsa_product, url) for url in urls]
        results = [f.result() for f in futures]
    return results
```

⚠️ 주의: 너무 많은 동시 요청은 무신사에서 차단할 수 있습니다!

## 🐛 로깅 설정

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('auto_shop.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
logger.info(f"처리 완료: {len(urls)}개")
```

## 🔗 추가 학습

- [Google Sheets API 공식 문서](https://developers.google.com/sheets/api/guides/concepts)
- [BeautifulSoup 튜토리얼](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [Requests 라이브러리](https://docs.python-requests.org/)

---

더 궁금한 점이 있으시면 README.md를 참고하세요!

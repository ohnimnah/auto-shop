"""BUYMA URLs, selector constants, and shared labels."""

BUYMA_SELL_URL = "https://www.buyma.com/my/sell/new?tab=b"
BUYMA_LOGIN_URL = "https://www.buyma.com/login/"
BUYMA_LOGOUT_URL = "https://www.buyma.com/logout/"

JP_SHITEI_NASHI = "\u6307\u5b9a\u306a\u3057"
JP_SIZE_SHITEI_NASHI = "\u30b5\u30a4\u30ba\u6307\u5b9a\u306a\u3057"

LOGIN_EMAIL_SELECTOR = (
    "input[name='txtLoginId'], input[type='email'], "
    "input[name='email'], input[id*='login'], input[id*='email']"
)
LOGIN_PASSWORD_SELECTOR = (
    "input[name='txtLoginPass'], input[type='password'], "
    "input[name='password']"
)
LOGIN_SUBMIT_SELECTOR = (
    "input[type='submit'][value*='出品'], "
    "button[type='submit'], input[type='submit'], "
    ".login-btn, button[class*='login']"
)
BUYMA_BUTTON_SELECTOR = "button, input[type='submit'], input[type='button'], a[role='button']"
FORM_READY_SELECTOR = ".bmm-c-heading__ttl"

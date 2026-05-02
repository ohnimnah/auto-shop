"""Semantic StandardCategory resolver for BUYMA category correction layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Tuple


class StandardCategory(str, Enum):
    # Tops
    TOP_TSHIRT = "TOP_TSHIRT"
    TOP_LONG_SLEEVE = "TOP_LONG_SLEEVE"
    TOP_SWEAT = "TOP_SWEAT"
    TOP_HOODIE = "TOP_HOODIE"
    TOP_SHIRT = "TOP_SHIRT"
    TOP_BLOUSE = "TOP_BLOUSE"
    TOP_KNIT = "TOP_KNIT"
    TOP_CARDIGAN = "TOP_CARDIGAN"
    TOP_POLO = "TOP_POLO"
    TOP_VEST = "TOP_VEST"
    TOP_TANK = "TOP_TANK"

    # Outer
    OUTER = "OUTER"  # legacy alias; resolves to OUTER_JACKET in mapping helpers.
    OUTER_PADDING = "OUTER_PADDING"
    OUTER_COAT = "OUTER_COAT"
    OUTER_TRENCH = "OUTER_TRENCH"
    OUTER_JACKET = "OUTER_JACKET"
    OUTER_BLAZER = "OUTER_BLAZER"
    OUTER_DENIM_JACKET = "OUTER_DENIM_JACKET"
    OUTER_LEATHER_JACKET = "OUTER_LEATHER_JACKET"
    OUTER_WINDBREAKER = "OUTER_WINDBREAKER"
    OUTER_FLEECE = "OUTER_FLEECE"
    OUTER_VEST = "OUTER_VEST"

    # Bottoms
    PANTS = "PANTS"  # legacy alias; resolves to PANTS_REGULAR in mapping helpers.
    PANTS_DENIM = "PANTS_DENIM"
    PANTS_SLACKS = "PANTS_SLACKS"
    PANTS_TRAINING = "PANTS_TRAINING"
    PANTS_JOGGER = "PANTS_JOGGER"
    PANTS_CARGO = "PANTS_CARGO"
    PANTS_SHORTS = "PANTS_SHORTS"
    PANTS_LEGGINGS = "PANTS_LEGGINGS"
    PANTS_REGULAR = "PANTS_REGULAR"
    SKIRT_MINI = "SKIRT_MINI"
    SKIRT_LONG = "SKIRT_LONG"
    SKIRT_DENIM = "SKIRT_DENIM"

    # One-piece / sets / home
    DRESS = "DRESS"
    DRESS_MINI = "DRESS_MINI"
    DRESS_LONG = "DRESS_LONG"
    JUMPSUIT = "JUMPSUIT"
    SETUP = "SETUP"
    HOME_PAJAMA = "HOME_PAJAMA"
    INNER_UNDERWEAR = "INNER_UNDERWEAR"

    # Shoes
    SNEAKER = "SNEAKER"  # legacy alias; resolves to SHOES_SNEAKER in mapping helpers.
    SHOES_SNEAKER = "SHOES_SNEAKER"
    SHOES_RUNNING = "SHOES_RUNNING"
    SHOES_BOOTS = "SHOES_BOOTS"
    SHOES_LOAFER = "SHOES_LOAFER"
    SHOES_SANDAL = "SHOES_SANDAL"
    SHOES_PUMPS = "SHOES_PUMPS"
    SHOES_FLAT = "SHOES_FLAT"
    SHOES_DRESS = "SHOES_DRESS"

    # Bags
    BAG_TOTE = "BAG_TOTE"
    BAG_SHOULDER = "BAG_SHOULDER"
    BAG_CROSSBODY = "BAG_CROSSBODY"
    BAG_BACKPACK = "BAG_BACKPACK"
    BAG_CLUTCH = "BAG_CLUTCH"
    BAG_WALLET = "BAG_WALLET"

    # Accessories
    ACC_CAP = "ACC_CAP"
    ACC_HAT = "ACC_HAT"
    ACC_BEANIE = "ACC_BEANIE"
    ACC_BELT = "ACC_BELT"
    ACC_SCARF = "ACC_SCARF"
    ACC_JEWELRY = "ACC_JEWELRY"
    ACC_EYEWEAR = "ACC_EYEWEAR"
    ACC_WATCH = "ACC_WATCH"

    ETC = "ETC"


@dataclass(frozen=True)
class StandardCategorySpec:
    standard_category: StandardCategory
    women_middle: str
    men_middle: str
    child: str
    aliases: Tuple[str, ...]
    note: str = ""

    def middle(self, *, is_mens: bool) -> str:
        return self.men_middle if is_mens else self.women_middle


PARENT_WOMEN = "レディースファッション"
PARENT_MEN = "メンズファッション"
MIDDLE_TOPS = "トップス"
MIDDLE_OUTER_WOMEN = "アウター"
MIDDLE_OUTER_MEN = "アウター・ジャケット"
MIDDLE_BOTTOMS_WOMEN = "ボトムス"
MIDDLE_BOTTOMS_MEN = "パンツ・ボトムス"
MIDDLE_DRESS_WOMEN = "ワンピース・オールインワン"
MIDDLE_OTHER_FASHION_MEN = "その他ファッション"
MIDDLE_INNER_ROOM = "インナー・ルームウェア"
MIDDLE_SHOES_WOMEN = "靴・シューズ"
MIDDLE_SHOES_MEN = "靴・ブーツ・サンダル"
MIDDLE_BAGS_WOMEN = "バッグ・カバン"
MIDDLE_BAGS_MEN = "バッグ・カバン"
MIDDLE_ACCESSORIES_WOMEN = "ファッション雑貨・小物"
MIDDLE_ACCESSORIES_MEN = "ファッション雑貨・小物"
MIDDLE_HATS = "帽子"
MIDDLE_WATCH = "腕時計"


STANDARD_CATEGORY_SPECS = {
    StandardCategory.TOP_TSHIRT: StandardCategorySpec(StandardCategory.TOP_TSHIRT, MIDDLE_TOPS, MIDDLE_TOPS, "Tシャツ・カットソー", ("티셔츠", "반팔", "short sleeve", "t-shirt", "tee")),
    StandardCategory.TOP_LONG_SLEEVE: StandardCategorySpec(StandardCategory.TOP_LONG_SLEEVE, MIDDLE_TOPS, MIDDLE_TOPS, "Tシャツ・カットソー", ("긴팔", "롱슬리브", "long sleeve", "longsleeve")),
    StandardCategory.TOP_SWEAT: StandardCategorySpec(StandardCategory.TOP_SWEAT, MIDDLE_TOPS, MIDDLE_TOPS, "スウェット・トレーナー", ("맨투맨", "스웨트", "스웻", "sweatshirt", "sweat")),
    StandardCategory.TOP_HOODIE: StandardCategorySpec(StandardCategory.TOP_HOODIE, MIDDLE_TOPS, MIDDLE_TOPS, "パーカー・フーディ", ("후드", "후디", "후드티", "hoodie", "hooded", "zip hoodie")),
    StandardCategory.TOP_SHIRT: StandardCategorySpec(StandardCategory.TOP_SHIRT, MIDDLE_TOPS, MIDDLE_TOPS, "シャツ", ("셔츠", "남방", "button-down", "button down", "shirt")),
    StandardCategory.TOP_BLOUSE: StandardCategorySpec(StandardCategory.TOP_BLOUSE, MIDDLE_TOPS, MIDDLE_TOPS, "ブラウス・シャツ", ("블라우스", "blouse")),
    StandardCategory.TOP_KNIT: StandardCategorySpec(StandardCategory.TOP_KNIT, MIDDLE_TOPS, MIDDLE_TOPS, "ニット・セーター", ("니트", "스웨터", "knit", "sweater")),
    StandardCategory.TOP_CARDIGAN: StandardCategorySpec(StandardCategory.TOP_CARDIGAN, MIDDLE_TOPS, MIDDLE_TOPS, "カーディガン", ("가디건", "cardigan")),
    StandardCategory.TOP_POLO: StandardCategorySpec(StandardCategory.TOP_POLO, MIDDLE_TOPS, MIDDLE_TOPS, "ポロシャツ", ("카라티", "피케", "폴로", "polo")),
    StandardCategory.TOP_VEST: StandardCategorySpec(StandardCategory.TOP_VEST, MIDDLE_TOPS, MIDDLE_TOPS, "ベスト・ジレ", ("니트베스트", "베스트", "조끼", "vest", "gilet")),
    StandardCategory.TOP_TANK: StandardCategorySpec(StandardCategory.TOP_TANK, MIDDLE_TOPS, MIDDLE_TOPS, "タンクトップ", ("나시", "민소매", "슬리브리스", "tank top", "sleeveless")),
    StandardCategory.OUTER_PADDING: StandardCategorySpec(StandardCategory.OUTER_PADDING, MIDDLE_OUTER_WOMEN, MIDDLE_OUTER_MEN, "ダウンジャケット・コート", ("패딩", "다운", "down jacket", "puffer", "padding")),
    StandardCategory.OUTER_COAT: StandardCategorySpec(StandardCategory.OUTER_COAT, MIDDLE_OUTER_WOMEN, MIDDLE_OUTER_MEN, "コート", ("코트", "coat", "duffle coat")),
    StandardCategory.OUTER_TRENCH: StandardCategorySpec(StandardCategory.OUTER_TRENCH, MIDDLE_OUTER_WOMEN, MIDDLE_OUTER_MEN, "トレンチコート", ("트렌치", "trench")),
    StandardCategory.OUTER_JACKET: StandardCategorySpec(StandardCategory.OUTER_JACKET, MIDDLE_OUTER_WOMEN, MIDDLE_OUTER_MEN, "ジャケット", ("자켓", "재킷", "jacket")),
    StandardCategory.OUTER_BLAZER: StandardCategorySpec(StandardCategory.OUTER_BLAZER, MIDDLE_OUTER_WOMEN, MIDDLE_OUTER_MEN, "テーラードジャケット", ("블레이저", "blazer", "tailored jacket")),
    StandardCategory.OUTER_DENIM_JACKET: StandardCategorySpec(StandardCategory.OUTER_DENIM_JACKET, MIDDLE_OUTER_WOMEN, MIDDLE_OUTER_MEN, "デニムジャケット", ("데님 자켓", "데님재킷", "denim jacket", "truck jacket")),
    StandardCategory.OUTER_LEATHER_JACKET: StandardCategorySpec(StandardCategory.OUTER_LEATHER_JACKET, MIDDLE_OUTER_WOMEN, MIDDLE_OUTER_MEN, "レザージャケット・コート", ("레더 자켓", "레더재킷", "가죽 자켓", "가죽재킷", "leather jacket")),
    StandardCategory.OUTER_WINDBREAKER: StandardCategorySpec(StandardCategory.OUTER_WINDBREAKER, MIDDLE_OUTER_WOMEN, MIDDLE_OUTER_MEN, "ジャケット", ("바람막이", "윈드브레이커", "windbreaker", "nylon jacket")),
    StandardCategory.OUTER_FLEECE: StandardCategorySpec(StandardCategory.OUTER_FLEECE, MIDDLE_OUTER_WOMEN, MIDDLE_OUTER_MEN, "フリースジャケット", ("플리스", "후리스", "fleece")),
    StandardCategory.OUTER_VEST: StandardCategorySpec(StandardCategory.OUTER_VEST, MIDDLE_OUTER_WOMEN, MIDDLE_OUTER_MEN, "ベスト・ジレ", ("패딩조끼", "다운 베스트", "outer vest", "down vest")),
    StandardCategory.PANTS_DENIM: StandardCategorySpec(StandardCategory.PANTS_DENIM, MIDDLE_BOTTOMS_WOMEN, MIDDLE_BOTTOMS_MEN, "デニム・ジーパン", ("데님", "청바지", "jeans", "denim")),
    StandardCategory.PANTS_SLACKS: StandardCategorySpec(StandardCategory.PANTS_SLACKS, MIDDLE_BOTTOMS_WOMEN, MIDDLE_BOTTOMS_MEN, "スラックス", ("슬랙스", "trousers", "slacks")),
    StandardCategory.PANTS_TRAINING: StandardCategorySpec(StandardCategory.PANTS_TRAINING, MIDDLE_BOTTOMS_WOMEN, MIDDLE_BOTTOMS_MEN, "スウェットパンツ", ("트레이닝", "스웨트팬츠", "sweatpants", "track pants")),
    StandardCategory.PANTS_JOGGER: StandardCategorySpec(StandardCategory.PANTS_JOGGER, MIDDLE_BOTTOMS_WOMEN, MIDDLE_BOTTOMS_MEN, "ジョガーパンツ", ("조거", "jogger")),
    StandardCategory.PANTS_CARGO: StandardCategorySpec(StandardCategory.PANTS_CARGO, MIDDLE_BOTTOMS_WOMEN, MIDDLE_BOTTOMS_MEN, "カーゴパンツ", ("카고", "cargo")),
    StandardCategory.PANTS_SHORTS: StandardCategorySpec(StandardCategory.PANTS_SHORTS, MIDDLE_BOTTOMS_WOMEN, MIDDLE_BOTTOMS_MEN, "ショートパンツ", ("쇼츠", "반바지", "shorts", "half pants")),
    StandardCategory.PANTS_LEGGINGS: StandardCategorySpec(StandardCategory.PANTS_LEGGINGS, MIDDLE_BOTTOMS_WOMEN, MIDDLE_BOTTOMS_MEN, "レギンス", ("레깅스", "leggings")),
    StandardCategory.PANTS_REGULAR: StandardCategorySpec(StandardCategory.PANTS_REGULAR, MIDDLE_BOTTOMS_WOMEN, MIDDLE_BOTTOMS_MEN, "パンツ", ("팬츠", "바지", "pants")),
    StandardCategory.SKIRT_MINI: StandardCategorySpec(StandardCategory.SKIRT_MINI, MIDDLE_BOTTOMS_WOMEN, MIDDLE_BOTTOMS_MEN, "ミニスカート", ("미니스커트", "mini skirt")),
    StandardCategory.SKIRT_LONG: StandardCategorySpec(StandardCategory.SKIRT_LONG, MIDDLE_BOTTOMS_WOMEN, MIDDLE_BOTTOMS_MEN, "スカート", ("롱스커트", "스커트", "long skirt", "skirt")),
    StandardCategory.SKIRT_DENIM: StandardCategorySpec(StandardCategory.SKIRT_DENIM, MIDDLE_BOTTOMS_WOMEN, MIDDLE_BOTTOMS_MEN, "デニムスカート", ("데님 스커트", "denim skirt")),
    StandardCategory.DRESS: StandardCategorySpec(StandardCategory.DRESS, MIDDLE_DRESS_WOMEN, MIDDLE_OTHER_FASHION_MEN, "", ("원피스", "드레스", "dress", "onepiece")),
    StandardCategory.DRESS_MINI: StandardCategorySpec(StandardCategory.DRESS_MINI, MIDDLE_DRESS_WOMEN, MIDDLE_OTHER_FASHION_MEN, "ワンピース", ("미니 원피스", "mini dress")),
    StandardCategory.DRESS_LONG: StandardCategorySpec(StandardCategory.DRESS_LONG, MIDDLE_DRESS_WOMEN, MIDDLE_OTHER_FASHION_MEN, "ワンピース", ("롱 원피스", "long dress", "maxi dress")),
    StandardCategory.JUMPSUIT: StandardCategorySpec(StandardCategory.JUMPSUIT, MIDDLE_DRESS_WOMEN, MIDDLE_OTHER_FASHION_MEN, "オールインワン・サロペット", ("점프수트", "오버롤", "jumpsuit", "overall")),
    StandardCategory.SETUP: StandardCategorySpec(StandardCategory.SETUP, MIDDLE_DRESS_WOMEN, MIDDLE_OTHER_FASHION_MEN, "セットアップ", ("셋업", "세트업", "setup", "set-up", "two piece")),
    StandardCategory.HOME_PAJAMA: StandardCategorySpec(StandardCategory.HOME_PAJAMA, MIDDLE_INNER_ROOM, MIDDLE_INNER_ROOM, "ルームウェア・パジャマ", ("파자마", "잠옷", "룸웨어", "홈웨어", "pajama", "sleepwear", "loungewear")),
    StandardCategory.INNER_UNDERWEAR: StandardCategorySpec(StandardCategory.INNER_UNDERWEAR, MIDDLE_INNER_ROOM, MIDDLE_INNER_ROOM, "インナー・下着", ("언더웨어", "속옷", "innerwear", "underwear")),
    StandardCategory.SHOES_SNEAKER: StandardCategorySpec(StandardCategory.SHOES_SNEAKER, MIDDLE_SHOES_WOMEN, MIDDLE_SHOES_MEN, "スニーカー", ("스니커즈", "운동화", "sneaker", "sneakers", "trainer")),
    StandardCategory.SHOES_RUNNING: StandardCategorySpec(StandardCategory.SHOES_RUNNING, MIDDLE_SHOES_WOMEN, MIDDLE_SHOES_MEN, "スニーカー", ("러닝화", "러닝", "running shoes", "running")),
    StandardCategory.SHOES_BOOTS: StandardCategorySpec(StandardCategory.SHOES_BOOTS, MIDDLE_SHOES_WOMEN, MIDDLE_SHOES_MEN, "ブーツ", ("부츠", "워커", "boots", "boot")),
    StandardCategory.SHOES_LOAFER: StandardCategorySpec(StandardCategory.SHOES_LOAFER, MIDDLE_SHOES_WOMEN, MIDDLE_SHOES_MEN, "ローファー・オックスフォード", ("로퍼", "loafer")),
    StandardCategory.SHOES_SANDAL: StandardCategorySpec(StandardCategory.SHOES_SANDAL, MIDDLE_SHOES_WOMEN, MIDDLE_SHOES_MEN, "サンダル・ミュール", ("샌들", "슬리퍼", "sandal", "slide")),
    StandardCategory.SHOES_PUMPS: StandardCategorySpec(StandardCategory.SHOES_PUMPS, MIDDLE_SHOES_WOMEN, MIDDLE_SHOES_MEN, "パンプス", ("펌프스", "힐", "pumps", "heels")),
    StandardCategory.SHOES_FLAT: StandardCategorySpec(StandardCategory.SHOES_FLAT, MIDDLE_SHOES_WOMEN, MIDDLE_SHOES_MEN, "フラットシューズ", ("플랫", "flat shoes", "ballet")),
    StandardCategory.SHOES_DRESS: StandardCategorySpec(StandardCategory.SHOES_DRESS, MIDDLE_SHOES_WOMEN, MIDDLE_SHOES_MEN, "ドレスシューズ・革靴・ビジネスシューズ", ("구두", "dress shoes", "leather shoes")),
    StandardCategory.BAG_TOTE: StandardCategorySpec(StandardCategory.BAG_TOTE, MIDDLE_BAGS_WOMEN, MIDDLE_BAGS_MEN, "トートバッグ", ("토트", "tote")),
    StandardCategory.BAG_SHOULDER: StandardCategorySpec(StandardCategory.BAG_SHOULDER, MIDDLE_BAGS_WOMEN, MIDDLE_BAGS_MEN, "ショルダーバッグ", ("숄더백", "shoulder bag")),
    StandardCategory.BAG_CROSSBODY: StandardCategorySpec(StandardCategory.BAG_CROSSBODY, MIDDLE_BAGS_WOMEN, MIDDLE_BAGS_MEN, "ショルダーバッグ", ("크로스백", "메신저", "crossbody", "messenger")),
    StandardCategory.BAG_BACKPACK: StandardCategorySpec(StandardCategory.BAG_BACKPACK, MIDDLE_BAGS_WOMEN, MIDDLE_BAGS_MEN, "バックパック・リュック", ("백팩", "리ュック", "backpack", "rucksack")),
    StandardCategory.BAG_CLUTCH: StandardCategorySpec(StandardCategory.BAG_CLUTCH, MIDDLE_BAGS_WOMEN, MIDDLE_BAGS_MEN, "クラッチバッグ", ("클러치", "clutch")),
    StandardCategory.BAG_WALLET: StandardCategorySpec(StandardCategory.BAG_WALLET, "財布・小物", "財布・雑貨", "財布・コインケース", ("지갑", "wallet", "card holder")),
    StandardCategory.ACC_CAP: StandardCategorySpec(StandardCategory.ACC_CAP, MIDDLE_HATS, MIDDLE_HATS, "キャップ", ("캡", "볼캡", "cap", "baseball cap")),
    StandardCategory.ACC_HAT: StandardCategorySpec(StandardCategory.ACC_HAT, MIDDLE_HATS, MIDDLE_HATS, "ハット", ("모자", "버킷햇", "hat", "bucket hat")),
    StandardCategory.ACC_BEANIE: StandardCategorySpec(StandardCategory.ACC_BEANIE, MIDDLE_HATS, MIDDLE_HATS, "ニットキャップ・ビーニー", ("비니", "beanie")),
    StandardCategory.ACC_BELT: StandardCategorySpec(StandardCategory.ACC_BELT, MIDDLE_ACCESSORIES_WOMEN, MIDDLE_ACCESSORIES_MEN, "ベルト", ("벨트", "belt")),
    StandardCategory.ACC_SCARF: StandardCategorySpec(StandardCategory.ACC_SCARF, MIDDLE_ACCESSORIES_WOMEN, MIDDLE_ACCESSORIES_MEN, "マフラー・ストール", ("머플러", "스카프", "scarf", "muffler")),
    StandardCategory.ACC_JEWELRY: StandardCategorySpec(StandardCategory.ACC_JEWELRY, "アクセサリー", "アクセサリー", "", ("목걸이", "반지", "귀걸이", "팔찌", "necklace", "ring", "earring", "bracelet")),
    StandardCategory.ACC_EYEWEAR: StandardCategorySpec(StandardCategory.ACC_EYEWEAR, MIDDLE_ACCESSORIES_WOMEN, MIDDLE_ACCESSORIES_MEN, "サングラス", ("선글라스", "안경", "sunglasses", "eyewear")),
    StandardCategory.ACC_WATCH: StandardCategorySpec(StandardCategory.ACC_WATCH, MIDDLE_WATCH, MIDDLE_WATCH, "", ("시계", "watch")),
}


LEGACY_CATEGORY_ALIASES = {
    StandardCategory.OUTER: StandardCategory.OUTER_JACKET,
    StandardCategory.PANTS: StandardCategory.PANTS_REGULAR,
    StandardCategory.SNEAKER: StandardCategory.SHOES_SNEAKER,
}

CATEGORY_ALIAS_DICTIONARY = {
    alias: spec.standard_category
    for spec in STANDARD_CATEGORY_SPECS.values()
    for alias in spec.aliases
}


def normalize_standard_category(value: StandardCategory | str) -> StandardCategory:
    if isinstance(value, StandardCategory):
        category = value
    else:
        raw = (value or "").strip()
        category = StandardCategory.__members__.get(raw) or next((item for item in StandardCategory if item.value == raw), StandardCategory.ETC)
    return LEGACY_CATEGORY_ALIASES.get(category, category)


def get_standard_category_spec(value: StandardCategory | str) -> StandardCategorySpec | None:
    return STANDARD_CATEGORY_SPECS.get(normalize_standard_category(value))


def get_buyma_parent_category(*, is_mens: bool) -> str:
    return PARENT_MEN if is_mens else PARENT_WOMEN


def validate_buyma_category_path(parent: str, middle: str, child: str = "") -> bool:
    parent = (parent or "").strip()
    middle = (middle or "").strip()
    child = (child or "").strip()
    if parent not in {PARENT_WOMEN, PARENT_MEN} or not middle:
        return False
    is_mens = parent == PARENT_MEN
    for spec in STANDARD_CATEGORY_SPECS.values():
        if spec.middle(is_mens=is_mens) == middle and (not child or spec.child == child or not spec.child):
            return True
    return False


def _normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.lower().strip()
    for token in ("|", "/", "\\", ",", ";", "_", "-", "(", ")", "[", "]", "+"):
        text = text.replace(token, " ")
    return " ".join(text.split())


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    if not text:
        return False
    return any(keyword.lower() in text for keyword in keywords)


def build_combined_text(
    musinsa_large: str,
    musinsa_middle: str,
    musinsa_small: str,
    product_name: str,
) -> str:
    return _normalize_text(" ".join([musinsa_large or "", musinsa_middle or "", musinsa_small or "", product_name or ""]))


RESOLUTION_PRIORITY: Tuple[StandardCategory, ...] = (
    StandardCategory.HOME_PAJAMA,
    StandardCategory.INNER_UNDERWEAR,
    StandardCategory.OUTER_PADDING,
    StandardCategory.OUTER_TRENCH,
    StandardCategory.OUTER_DENIM_JACKET,
    StandardCategory.OUTER_LEATHER_JACKET,
    StandardCategory.OUTER_WINDBREAKER,
    StandardCategory.OUTER_FLEECE,
    StandardCategory.OUTER_VEST,
    StandardCategory.OUTER_BLAZER,
    StandardCategory.OUTER_COAT,
    StandardCategory.OUTER_JACKET,
    StandardCategory.PANTS_DENIM,
    StandardCategory.PANTS_SLACKS,
    StandardCategory.PANTS_TRAINING,
    StandardCategory.PANTS_JOGGER,
    StandardCategory.PANTS_CARGO,
    StandardCategory.PANTS_SHORTS,
    StandardCategory.PANTS_LEGGINGS,
    StandardCategory.SKIRT_DENIM,
    StandardCategory.SKIRT_MINI,
    StandardCategory.SKIRT_LONG,
    StandardCategory.JUMPSUIT,
    StandardCategory.SETUP,
    StandardCategory.DRESS_MINI,
    StandardCategory.DRESS_LONG,
    StandardCategory.DRESS,
    StandardCategory.SHOES_RUNNING,
    StandardCategory.SHOES_SNEAKER,
    StandardCategory.SHOES_BOOTS,
    StandardCategory.SHOES_LOAFER,
    StandardCategory.SHOES_SANDAL,
    StandardCategory.SHOES_PUMPS,
    StandardCategory.SHOES_FLAT,
    StandardCategory.SHOES_DRESS,
    StandardCategory.BAG_BACKPACK,
    StandardCategory.BAG_CROSSBODY,
    StandardCategory.BAG_SHOULDER,
    StandardCategory.BAG_TOTE,
    StandardCategory.BAG_CLUTCH,
    StandardCategory.BAG_WALLET,
    StandardCategory.ACC_WATCH,
    StandardCategory.ACC_EYEWEAR,
    StandardCategory.ACC_JEWELRY,
    StandardCategory.ACC_SCARF,
    StandardCategory.ACC_BEANIE,
    StandardCategory.ACC_CAP,
    StandardCategory.ACC_HAT,
    StandardCategory.ACC_BELT,
    StandardCategory.TOP_HOODIE,
    StandardCategory.TOP_SWEAT,
    StandardCategory.TOP_LONG_SLEEVE,
    StandardCategory.TOP_TSHIRT,
    StandardCategory.TOP_BLOUSE,
    StandardCategory.TOP_SHIRT,
    StandardCategory.TOP_KNIT,
    StandardCategory.TOP_CARDIGAN,
    StandardCategory.TOP_POLO,
    StandardCategory.TOP_TANK,
    StandardCategory.TOP_VEST,
    StandardCategory.PANTS_REGULAR,
)


def resolve_standard_category(
    musinsa_large: str,
    musinsa_middle: str,
    musinsa_small: str,
    product_name: str,
) -> Tuple[StandardCategory, str]:
    """Resolve semantic category from Musinsa category text + product name."""
    text = build_combined_text(musinsa_large, musinsa_middle, musinsa_small, product_name)
    if not text:
        return StandardCategory.ETC, text

    for category in RESOLUTION_PRIORITY:
        spec = STANDARD_CATEGORY_SPECS.get(category)
        if spec and _contains_any(text, spec.aliases):
            return category, text
    return StandardCategory.ETC, text


def map_standard_to_buyma_middle_and_subcategory(
    standard_category: StandardCategory,
    combined_text: str,
    *,
    is_mens: bool = False,
) -> Tuple[str, str]:
    """Return (buyma_middle_category, buyma_sub_category)."""
    spec = get_standard_category_spec(standard_category)
    if spec:
        return spec.middle(is_mens=is_mens), spec.child
    return "", ""


def explain_standard_category_mapping(
    standard_category: StandardCategory | str,
    *,
    is_mens: bool,
) -> dict:
    """Return diagnostics for StandardCategory -> BUYMA path resolution."""
    category = normalize_standard_category(standard_category)
    spec = get_standard_category_spec(category)
    parent = get_buyma_parent_category(is_mens=is_mens)
    middle = spec.middle(is_mens=is_mens) if spec else ""
    child = spec.child if spec else ""
    return {
        "standard_category": category.value,
        "buyma_parent": parent,
        "buyma_middle": middle,
        "buyma_child": child,
        "validator_passed": validate_buyma_category_path(parent, middle, child),
        "legacy_alias_used": str(standard_category) != category.value,
        "fallback_used": category == StandardCategory.ETC or not bool(spec),
    }

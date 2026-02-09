# File: assets/keelie/keelie_runtime.py
import re
import random
import asyncio
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from js import window

# =========================
# Bot identity & links
# =========================
BOT_NAME = "Keelie"
COMPANY_NAME = "Keel Toys"
CUSTOMER_SERVICE_URL = "https://www.keeltoys.com/contact-us/"

# =========================
# Minimum order values
# =========================
MIN_ORDER_FIRST = 500
MIN_ORDER_REPEAT = 250

# =========================
# Manufacturing info
# =========================
PRODUCTION_INFO = (
    "Our toys are produced across a small number of trusted manufacturing partners:\n"
    "• 95% in China\n"
    "• 3% in Indonesia\n"
    "• 2% in Cambodia"
)

# =========================
# Help / capabilities overview
# =========================
HELP_OVERVIEW = (
    "I can help with:\n"
    "• **Minimum order values** (e.g. “minimum order value”)\n"
    "• **Stock codes / SKUs** (e.g. “stock code for Polar Bear Plush 20cm”)\n"
    "• **Keeleco® sustainability & recycled materials**\n"
    "• **Where our toys are made**\n"
    "• **Delivery & tracking** (e.g. “where is my order?”)\n"
    "• **Invoices** (e.g. “download an invoice”)\n\n"
    "What would you like to ask?"
)

# =========================
# Eco / sustainability overview (Keeleco)
# =========================
KEELECO_OVERVIEW = (
    "Keeleco® is our eco-focused soft toy range made using **100% recycled polyester**.\n\n"
    "Key facts:\n"
    "• The outer plush and inner fibre fill are made from **recycled plastic waste**.\n"
    "• As a guide, around **10 recycled 500ml bottles** can produce enough fibre for an **18cm** toy.\n"
    "• Our Keel logo + hangtags use **FSC card** and are attached with **cotton**.\n"
    "• Shipping cartons are recycled and sealed with **paper tape**.\n"
    "• Keeleco is made in an **ethically audited** factory.\n\n"
    "If you tell me which Keeleco sub-range you mean (e.g. *Keeleco Dinosaurs*), I can share details."
)

# =========================
# Global state
# =========================
STOCK_ROWS: List[Dict[str, str]] = []  # loaded from JS Excel conversion

# Stock disambiguation state
PENDING_STOCK_LOOKUP = False
PENDING_STOCK_CHOICES: List[Dict[str, str]] = []  # [{product_name, stock_code}, ...]
PENDING_STOCK_QUERY: str = ""

# Confidence thresholds
STOCK_HIGH = 0.75
STOCK_MED = 0.55

# =========================
# Text helpers
# =========================
def clean_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s&-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def extract_stock_code(text: str) -> Optional[str]:
    matches = re.findall(r"\b[A-Z]{1,5}-?[A-Z]{0,5}-?\d{2,4}\b", (text or "").upper())
    return matches[0] if matches else None

def normalize_for_product_match(text: str) -> str:
    t = clean_text(text)
    junk_phrases = [
        "can you tell me", "could you tell me", "please", "what is", "whats",
        "the product code", "product code", "stock code", "item code", "sku",
        "code for", "code of"
    ]
    for p in junk_phrases:
        t = t.replace(p, " ")
    t = re.sub(r"\b(of|for|a|an|the|to|me|my)\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

# =========================
# Question detectors
# =========================
def is_delivery_question(text: str) -> bool:
    t = clean_text(text)
    delivery_terms = ["arrive", "arrival", "delivery", "eta", "tracking", "track", "order", "dispatch", "shipped"]
    return (("when" in t) and any(term in t for term in delivery_terms)) or any(
        phrase in t for phrase in ["where is my order", "track my order", "order status"]
    )

def is_stock_code_request(text: str) -> bool:
    t = clean_text(text)
    triggers = ["product code", "stock code", "sku", "item code", "code for", "code of"]
    return any(x in t for x in triggers)

def is_minimum_order_question(text: str) -> bool:
    t = clean_text(text)
    triggers = [
        "minimum order", "minimum spend", "minimum purchase",
        "min order", "min spend", "order minimum", "minimum order price",
        "minimum value", "minimum order value", "minimum spend value",
        "minimum order amount", "minimum spend amount",
        "minimum basket", "minimum basket value",
        "minimum checkout", "minimum checkout value",
        "what is the minimum", "whats the minimum", "what's the minimum",
        "opening order minimum", "first order minimum", "repeat order minimum",
        "starting order", "trade minimum", "trade order minimum",
        "moq", "m o q", "minimum order quantity",
    ]
    return any(x in t for x in triggers)

def is_production_question(text: str) -> bool:
    t = clean_text(text)
    phrases = [
        "where are your toys produced",
        "where are your toys made",
        "where are your toys manufactured",
        "where are the toys produced",
        "where are the toys made",
        "where are the toys manufactured",
        "where are they produced",
        "where are they made",
        "where are they manufactured",
    ]
    if any(p in t for p in phrases):
        return True
    production_words = {"produced", "made", "manufactured"}
    return ("where" in t) and ("toy" in t or "toys" in t) and any(w in t for w in production_words)

def is_eco_question(text: str) -> bool:
    t = clean_text(text)
    triggers = [
        "eco", "eco friendly", "eco-friendly",
        "sustainable", "sustainability",
        "environment", "environmentally friendly",
        "recycled", "recycle", "recyclable",
        "plastic bottles", "fsc",
        "keeleco", "keel eco"
    ]
    return any(x in t for x in triggers)

def is_help_question(text: str) -> bool:
    t = clean_text(text)
    triggers = [
        "what can you help with",
        "what can you do",
        "what do you do",
        "how can you help",
        "what can i ask",
        "what can i ask you",
        "what questions can i ask",
        "what are you for",
        "what can keelie help with",
        "how do you work",
    ]
    return any(x in t for x in triggers)

def is_greeting(text: str) -> bool:
    t = clean_text(text)
    greetings = {
        "hi", "hello", "hey", "hiya", "yo",
        "good morning", "good afternoon", "good evening"
    }
    return (t in greetings) or any(t.startswith(g + " ") for g in greetings)

# =========================
# Responses
# =========================
def minimum_order_response() -> str:
    return (
        "Our minimum order values are:\n"
        f"• £{MIN_ORDER_FIRST} for first-time buyers\n"
        f"• £{MIN_ORDER_REPEAT} for repeat buyers\n\n"
        "If you’re unsure whether you qualify as a first-time or repeat buyer, "
        "our customer service team can help:\n"
        f"{CUSTOMER_SERVICE_URL}"
    )

def fallback_response() -> str:
    # Keep the first sentence stable for any JS feedback trigger patterns.
    return (
        "I’m not able to help with that just now.\n\n"
        "Right now I *can* help with:\n"
        "• **Minimum order values** (try: “What’s the minimum order value?”)\n"
        "• **Stock codes / SKUs** (try: “Stock code for Polar Bear Plush 20cm”)\n"
        "• **Keeleco® recycled materials & sustainability** (try: “Tell me about Keeleco”)\n"
        "• **Where our toys are made** (try: “Where are your toys produced?”)\n"
        "• **Delivery & tracking guidance** (try: “How do I track my order?”)\n"
        "• **Invoices** (try: “How do I download an invoice?”)\n\n"
        "Which of those do you need?"
    )

# =========================
# Privacy guardrail (expanded)
# =========================
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)

PHONE_RE = re.compile(
    r"(?:(?:\+|00)\s?\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)?\d[\d\s-]{7,}\d"
)

UK_POSTCODE_RE = re.compile(
    r"\b(?:GIR\s?0AA|(?:[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}))\b",
    re.I
)

SENSITIVE_CUE_RE = re.compile(
    r"\b("
    r"order|invoice|account|ref|reference|tracking|track(?:ing)?\s*(?:no|number)?|"
    r"awb|consignment|waybill|dispatch|delivery|"
    r"purchase\s+order|po\s*number|p\.o\.|"
    r"sales\s+order|so\s*number|return|rma"
    r")\b",
    re.I
)

ORDER_HASH_RE = re.compile(r"\b(?:order\s*)?#\s*([A-Z0-9-]{5,})\b", re.I)
INVOICE_CODE_RE = re.compile(r"\b(?:inv|invoice)\s*[:#]?\s*([A-Z0-9-]{5,})\b", re.I)
PO_SO_RE = re.compile(r"\b(?:po|p\.o\.|so|sales\s*order)\s*[:#]?\s*([A-Z0-9-]{4,})\b", re.I)

UPS_1Z_RE = re.compile(r"\b1Z[0-9A-Z]{8,}\b", re.I)
LONG_ALNUM_RE = re.compile(r"\b[A-Z0-9]{10,}\b", re.I)
LONG_DIGITS_RE = re.compile(r"\b\d{6,}\b")

STREET_WORD_RE = re.compile(
    r"\b(road|rd|street|st|lane|ln|avenue|ave|drive|dr|close|cl|way|"
    r"court|ct|crescent|cres|place|pl|park|gardens?|grove|terrace|ter)\b",
    re.I
)
HOUSE_NUM_RE = re.compile(r"\b\d{1,4}[A-Z]?\b")

def contains_personal_info(text: str) -> bool:
    t = text or ""
    if not t.strip():
        return False

    if EMAIL_RE.search(t):
        return True
    if PHONE_RE.search(t):
        return True
    if UK_POSTCODE_RE.search(t):
        return True

    # Address-like heuristic
    if HOUSE_NUM_RE.search(t) and STREET_WORD_RE.search(t):
        return True

    # If they mention order/invoice/tracking etc, treat refs as sensitive
    if SENSITIVE_CUE_RE.search(t):
        if ORDER_HASH_RE.search(t) or INVOICE_CODE_RE.search(t) or PO_SO_RE.search(t):
            return True
        if UPS_1Z_RE.search(t):
            return True
        if LONG_DIGITS_RE.search(t):
            return True
        if LONG_ALNUM_RE.search(t):
            return True

    return False

def privacy_warning() -> str:
    return (
        "For your privacy, please don’t share personal or account details here "
        "(such as email addresses, phone numbers, delivery addresses, or order/invoice references).\n\n"
        "Our customer service team can help you securely here:\n"
        f"{CUSTOMER_SERVICE_URL}"
    )

# =========================
# Frustration detection (session-only)
# =========================
FRUSTRATION_STRIKES = 0
LAST_USER_CLEAN = ""
LAST_USER_TS = 0.0

FRUSTRATION_KEYWORDS = [
    "wrong", "incorrect", "not correct", "doesn't work", "doesnt work",
    "useless", "rubbish", "terrible", "bad", "awful",
    "not helpful", "unhelpful", "waste of time",
    "annoying", "frustrated", "frustrating", "ridiculous",
    "stop", "nonsense"
]

def register_message_for_repeat_check(user_text: str) -> None:
    global LAST_USER_CLEAN, LAST_USER_TS
    LAST_USER_CLEAN = clean_text(user_text or "")
    LAST_USER_TS = time.time()

def reset_frustration() -> None:
    global FRUSTRATION_STRIKES
    FRUSTRATION_STRIKES = 0

def detect_frustration(user_text: str) -> bool:
    t_raw = (user_text or "").strip()
    if not t_raw:
        return False

    t = clean_text(t_raw)

    if any(k in t for k in FRUSTRATION_KEYWORDS):
        return True

    if "??" in t_raw or "!!" in t_raw:
        return True

    # ALL CAPS yelling (only if it's meaningfully long)
    letters = [c for c in t_raw if c.isalpha()]
    if len(letters) >= 8:
        upper_ratio = sum(1 for c in letters if c.isupper()) / max(1, len(letters))
        if upper_ratio >= 0.85:
            return True

    # Repeated message within 40 seconds
    global LAST_USER_CLEAN, LAST_USER_TS
    now = time.time()
    if LAST_USER_CLEAN and (now - LAST_USER_TS) <= 40:
        if similarity(t, LAST_USER_CLEAN) >= 0.92:
            return True

    return False

def frustration_first_response() -> str:
    return (
        "Sorry about that — I can see this is frustrating.\n\n"
        "To get you the right help, which of these is closest?\n"
        "• **Stock code / SKU**\n"
        "• **Minimum order value (MOQ)**\n"
        "• **Delivery / tracking**\n"
        "• **Invoices**\n"
        "• **Keeleco / recycled materials**\n"
        "• **Where toys are made**\n\n"
        "Reply with the topic (or rephrase your question) and I’ll help."
    )

def frustration_escalate_response() -> str:
    return (
        "Sorry — I’m not getting you the help you need here.\n\n"
        "The quickest option is to contact our customer service team, who can help securely:\n"
        f"{CUSTOMER_SERVICE_URL}"
    )

# =========================
# Stock: load rows from JS
# =========================
async def load_stock_rows_from_js():
    global STOCK_ROWS
    try:
        if hasattr(window, "keelieStockReady"):
            await window.keelieStockReady

        if hasattr(window, "keelieStockRows"):
            STOCK_ROWS = [dict(r) for r in window.keelieStockRows.to_py()]
        else:
            STOCK_ROWS = []
    except Exception:
        STOCK_ROWS = []

def _clear_pending_stock():
    global PENDING_STOCK_LOOKUP, PENDING_STOCK_CHOICES, PENDING_STOCK_QUERY
    PENDING_STOCK_LOOKUP = False
    PENDING_STOCK_CHOICES = []
    PENDING_STOCK_QUERY = ""

def _top_stock_candidates(query: str, limit: int = 3) -> List[Tuple[float, Dict[str, str]]]:
    q = normalize_for_product_match(query)
    scored: List[Tuple[float, Dict[str, str]]] = []
    for row in STOCK_ROWS:
        name = str(row.get("product_name", "")).lower().strip()
        if not name:
            continue
        scored.append((similarity(q, name), row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]

def _offer_stock_choices(choices: List[Dict[str, str]]) -> str:
    lines = ["I found a few close matches — which one did you mean? Reply with **1**, **2**, or **3**:"]
    for i, row in enumerate(choices, start=1):
        product = str(row.get("product_name", "")).strip().title()
        code = str(row.get("stock_code", "")).strip()
        lines.append(f"{i}. **{product}** (stock code **{code}**)")
    return "\n".join(lines)

def _handle_stock_choice_reply(user_text: str) -> Optional[str]:
    global PENDING_STOCK_LOOKUP, PENDING_STOCK_CHOICES

    if not PENDING_STOCK_LOOKUP or not PENDING_STOCK_CHOICES:
        return None

    t = clean_text(user_text)

    # If they switch topic, abandon pending state.
    if (
        is_minimum_order_question(t)
        or is_delivery_question(t)
        or is_eco_question(t)
        or is_production_question(t)
        or is_help_question(t)
    ):
        _clear_pending_stock()
        return None

    # Numeric choice 1-3
    m = re.search(r"\b([1-3])\b", t)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(PENDING_STOCK_CHOICES):
            row = PENDING_STOCK_CHOICES[idx]
            product = str(row.get("product_name", "")).strip().title()
            code = str(row.get("stock_code", "")).strip()
            _clear_pending_stock()
            return f"The stock code for **{product}** is **{code}**."

    # If they typed a name, try to match among candidates
    best = None
    best_s = 0.0
    for row in PENDING_STOCK_CHOICES:
        name = str(row.get("product_name", "")).lower().strip()
        s = similarity(normalize_for_product_match(user_text), name)
        if s > best_s:
            best_s = s
            best = row

    if best and best_s >= 0.60:
        product = str(best.get("product_name", "")).strip().title()
        code = str(best.get("stock_code", "")).strip()
        _clear_pending_stock()
        return f"The stock code for **{product}** is **{code}**."

    return _offer_stock_choices(PENDING_STOCK_CHOICES)

def lookup_stock_code(user_text: str) -> str:
    global PENDING_STOCK_LOOKUP, PENDING_STOCK_CHOICES, PENDING_STOCK_QUERY

    if not STOCK_ROWS:
        return (
            "I can’t access stock codes right now (stock_codes.xlsx may be missing or unreadable). "
            f"Please contact customer service here:\n{CUSTOMER_SERVICE_URL}"
        )

    top = _top_stock_candidates(user_text, limit=3)
    if not top:
        return "I’m not sure which product you mean. Could you please provide the product name?"

    best_score, best_row = top[0]

    # High confidence
    if best_score >= STOCK_HIGH:
        product = str(best_row.get("product_name", "")).strip().title()
        code = str(best_row.get("stock_code", "")).strip()
        _clear_pending_stock()
        return f"The stock code for **{product}** is **{code}**."

    # Medium confidence -> ask to choose
    if best_score >= STOCK_MED:
        PENDING_STOCK_LOOKUP = True
        PENDING_STOCK_QUERY = user_text
        PENDING_STOCK_CHOICES = [row for _, row in top]
        return _offer_stock_choices(PENDING_STOCK_CHOICES)

    _clear_pending_stock()
    return "I’m not sure which product you mean. Could you please provide the exact product name (and size, if relevant)?"

def lookup_product_by_code(code: str) -> Optional[str]:
    if not STOCK_ROWS:
        return None
    code = code.upper().strip()
    for row in STOCK_ROWS:
        c = str(row.get("stock_code", "")).upper().strip()
        if c == code:
            product = str(row.get("product_name", "")).strip().title()
            return f"The product with stock code **{code}** is **{product}**."
    return None

# =========================
# Collections / ranges
# =========================
COLLECTION_FACTS: Dict[str, Dict[str, List[str]]] = {
    "keeleco": {
        "title": "Keeleco®",
        "facts": [
            "Eco-focused range made from **100% recycled polyester** (plush + fibre fill).",
            "Around **10 recycled 500ml bottles** can produce enough fibre for an **18cm** toy (guide figure).",
            "**FSC card** hangtags attached with **cotton**.",
            "Recycled cartons sealed with **paper tape**.",
            "Made in an **ethically audited** factory."
        ],
    },
    "keeleco adoptable world": {
        "title": "Keeleco Adoptable World",
        "facts": [
            "Part of the Keeleco® family: made using **100% recycled polyester**.",
            "Designed as a character-led animal collection with the Keeleco eco story highlighted on hangtags."
        ],
    },
    "keeleco arctic & sealife": {
        "title": "Keeleco Arctic & Sealife",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Arctic and sea-life themed characters with Keeleco eco labelling."
        ],
    },
    "keeleco baby": {
        "title": "Keeleco Baby",
        "facts": [
            "Keeleco® baby-themed collection made using **100% recycled polyester**.",
            "Designed for gentle gifting and early-years appeal while keeping the Keeleco eco materials story."
        ],
    },
    "keeleco botanical garden": {
        "title": "Keeleco Botanical Garden",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Botanical/plant-inspired characters within the Keeleco eco range."
        ],
    },
    "keeleco british wildlife & farm": {
        "title": "Keeleco British Wildlife & Farm",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "British wildlife and farm themed characters, with Keeleco eco labelling and FSC hangtags."
        ],
    },
    "keeleco collectables": {
        "title": "Keeleco Collectables",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Collectable-style characters with the Keeleco eco materials story."
        ],
    },
    "keeleco dinosaurs": {
        "title": "Keeleco Dinosaurs",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Dinosaur-themed characters within the Keeleco eco range."
        ],
    },
    "keeleco enchanted world": {
        "title": "Keeleco Enchanted World",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Fantasy-inspired characters with the Keeleco eco labelling."
        ],
    },
    "keeleco handpuppets": {
        "title": "Keeleco Handpuppets",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Hand puppet play format within the Keeleco eco range."
        ],
    },
    "keeleco jungle cats": {
        "title": "Keeleco Jungle Cats",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Big-cat themed characters within the Keeleco eco range."
        ],
    },
    "keeleco monkeys & apes": {
        "title": "Keeleco Monkeys & Apes",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Monkey and ape themed characters; Keeleco eco story shown on hangtags."
        ],
    },
    "keeleco pets": {
        "title": "Keeleco Pets",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Pet-themed characters within the Keeleco eco range."
        ],
    },
    "keeleco pink": {
        "title": "Keeleco Pink",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "A colour-led Keeleco selection with the same eco materials story."
        ],
    },
    "keeleco snackies": {
        "title": "Keeleco Snackies",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Food/snack-inspired characters within the Keeleco eco range."
        ],
    },
    "keeleco teddies": {
        "title": "Keeleco Teddies",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Teddy-led collection with the Keeleco eco materials story."
        ],
    },
    "keeleco wild": {
        "title": "Keeleco Wild",
        "facts": [
            "Part of Keeleco®: made using **100% recycled polyester**.",
            "Wildlife-themed characters within the Keeleco eco range."
        ],
    },

    "love to hug": {
        "title": "Love To Hug",
        "facts": [
            "A Keel Toys collection focused on soft, huggable plush characters.",
            "If you tell me the character/size, I can help check stock codes (if available in the Excel)."
        ],
    },
    "motsu": {
        "title": "Motsu",
        "facts": [
            "A Keel Toys character collection with its own distinct style and designs.",
            "If you share the exact product name, I can help find the stock code (if listed)."
        ],
    },
    "pippins": {
        "title": "Pippins",
        "facts": [
            "A Keel Toys collection featuring cute character-led soft toys.",
            "If you share the product name, I can look up the stock code (if present in your Excel)."
        ],
    },
    "pugsley & friends": {
        "title": "Pugsley & Friends",
        "facts": [
            "A Keel Toys character collection in the ‘Friends’ style range.",
            "If you share the specific product name, I can help locate the stock code (if listed)."
        ],
    },
    "seasonal": {
        "title": "Seasonal",
        "facts": [
            "Seasonal collections cover time-of-year themes (e.g., holiday gifting and seasonal characters).",
            "If you tell me which season/character, I can help with stock codes if they’re in your Excel."
        ],
    },
    "signature cuddle puppies": {
        "title": "Signature Cuddle Puppies",
        "facts": [
            "A Signature collection focused on puppy characters in a ‘cuddle’ style.",
            "Share a product name/size and I can help identify the stock code (if listed)."
        ],
    },
    "signature cuddle teddies": {
        "title": "Signature Cuddle Teddies",
        "facts": [
            "A Signature collection focused on teddy characters in a ‘cuddle’ style.",
            "Share a product name/size and I can help identify the stock code (if listed)."
        ],
    },
    "signature cuddle wild": {
        "title": "Signature Cuddle Wild",
        "facts": [
            "A Signature collection featuring wild-animal characters in a ‘cuddle’ style.",
            "Share a product name/size and I can help identify the stock code (if listed)."
        ],
    },
    "signature forever puppies": {
        "title": "Signature Forever Puppies",
        "facts": [
            "A Signature collection focused on puppy characters in the ‘Forever Puppies’ line.",
            "Share a product name/size and I can help identify the stock code (if listed)."
        ],
    },
    "souvenir": {
        "title": "Souvenir",
        "facts": [
            "A collection designed for gift/souvenir-style plush items.",
            "If you provide the product name or a code, I can help confirm stock code details (if listed)."
        ],
    },
}

def detect_collection(cleaned_text: str) -> Optional[str]:
    keys = sorted(COLLECTION_FACTS.keys(), key=len, reverse=True)
    for k in keys:
        if k in cleaned_text:
            return k
    return None

def collections_overview() -> str:
    kee_sub = [
        "Keeleco Adoptable World",
        "Keeleco Arctic & Sealife",
        "Keeleco Baby",
        "Keeleco Botanical Garden",
        "Keeleco British Wildlife & Farm",
        "Keeleco Collectables",
        "Keeleco Dinosaurs",
        "Keeleco Enchanted World",
        "Keeleco Handpuppets",
        "Keeleco Jungle Cats",
        "Keeleco Monkeys & Apes",
        "Keeleco Pets",
        "Keeleco Pink",
        "Keeleco Snackies",
        "Keeleco Teddies",
        "Keeleco Wild",
    ]
    others = [
        "Love To Hug",
        "Motsu",
        "Pippins",
        "Pugsley & Friends",
        "Seasonal",
        "Signature Cuddle Puppies",
        "Signature Cuddle Teddies",
        "Signature Cuddle Wild",
        "Signature Forever Puppies",
        "Souvenir",
    ]
    return (
        "Here are our main collections/ranges:\n\n"
        "Keeleco® sub-ranges:\n"
        + "\n".join([f"• {x}" for x in kee_sub]) +
        "\n\nOther collections:\n"
        + "\n".join([f"• {x}" for x in others]) +
        "\n\nTell me which one you’re interested in and I’ll share some facts about it."
    )

def collection_reply(cleaned_text: str) -> str:
    key = detect_collection(cleaned_text)
    if not key:
        return collections_overview()

    info = COLLECTION_FACTS[key]
    facts = "\n".join([f"• {f}" for f in info["facts"]])

    if key == "keeleco" and is_eco_question(cleaned_text):
        return KEELECO_OVERVIEW

    return f"Here’s an overview of **{info['title']}**:\n{facts}"

# =========================
# FAQ (simple similarity)
# =========================
FAQ = {
    "tell me about keel toys":
        "Keel Toys is a family-run UK soft toy company founded in 1947. Since 1988, we’ve focused on developing our own-brand soft toys.",
    "what are your opening hours":
        "The Keel Toys office is open Monday to Friday, 9:00am–5:00pm (UK time).",
    "are keel toys toys safe":
        "All Keel Toys products are designed and tested to meet UK and EU safety standards.",
}

def best_faq_answer(user_text: str, threshold: float = 0.55) -> Optional[str]:
    q = clean_text(user_text)
    best = None
    best_score = 0.0
    for k, v in FAQ.items():
        s = similarity(q, k)
        if s > best_score:
            best_score = s
            best = v
    return best if best_score >= threshold else None

# =========================
# Intent system (priority-based)
# =========================
@dataclass
class Intent:
    priority: int
    keywords: Dict[str, int]
    responses: List[str]

INTENTS = {
    "customer_service": Intent(
        priority=6,
        keywords={"customer service": 6, "support": 4, "agent": 4, "human": 4, "contact": 3},
        responses=[
            "Of course! 😊 You can contact Keel Toys customer service here:\n"
            f"{CUSTOMER_SERVICE_URL}"
        ],
    ),
    "delivery_time": Intent(
        priority=5,
        keywords={
            "when will it arrive": 6,
            "when is it arriving": 6,
            "when is it going to arrive": 7,
            "going to arrive": 6,
            "arrival": 4,
            "eta": 5,
            "estimated delivery": 5,
            "delivery date": 5,
            "arrive": 3,
            "delivery": 4,
            "where is my order": 6,
            "track my order": 5,
            "tracking": 4,
            "order status": 5,
            "dispatch": 4,
            "shipped": 4,
        },
        responses=[
            "For delivery updates, please check your order confirmation email. "
            "It includes your estimated delivery date and tracking details if available."
        ],
    ),
    "invoice_copy": Intent(
        priority=6,
        keywords={
            "invoice": 5,
            "last invoice": 7,
            "copy of my invoice": 7,
            "invoice copy": 6,
            "invoice history": 6,
            "past invoice": 6,
            "order invoice": 5,
            "download invoice": 6
        },
        responses=[
            "To get a copy of an invoice, please use your trade account area (Invoice History), "
            "or contact customer service if you need help accessing it:\n"
            f"{CUSTOMER_SERVICE_URL}"
        ],
    ),
}

def intent_score(intent: Intent, cleaned_text: str) -> int:
    score = 0
    for k, w in intent.keywords.items():
        if k in cleaned_text:
            score += w
    return score

def pick_intent(cleaned_text: str) -> Optional[str]:
    scored = []
    for name, intent in INTENTS.items():
        s = intent_score(intent, cleaned_text)
        if s > 0:
            scored.append((intent.priority, s, name))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][2]

# =========================
# Core responder
# =========================
async def respond(user_text: str) -> str:
    cleaned = clean_text(user_text or "")

    # 1) Privacy guardrail ALWAYS wins
    if contains_personal_info(user_text):
        _clear_pending_stock()
        return privacy_warning()

    # Track for repeat detection (frustration logic)
    register_message_for_repeat_check(user_text)

    # 2) Pending stock disambiguation flow
    pending = _handle_stock_choice_reply(user_text)
    if pending:
        reset_frustration()
        return pending

    # 3) Frustration detection (session-only)
# 3) Frustration detection (session-only)
    global FRUSTRATION_STRIKES
    if detect_frustration(user_text):
        FRUSTRATION_STRIKES += 1
        _clear_pending_stock()
        # IMPORTANT: update repeat-check memory after evaluating
        register_message_for_repeat_check(user_text)

        if FRUSTRATION_STRIKES >= 2:
            return frustration_escalate_response()
        return frustration_first_response()

# Update repeat-check memory for normal messages
    register_message_for_repeat_check(user_text)


    # Reset frustration on positive signals
    if any(x in cleaned for x in ["thanks", "thank you", "cheers", "great", "perfect", "ok"]):
        reset_frustration()

    # 4) Direct code -> product lookup
    code = extract_stock_code(user_text)
    if code:
        prod = lookup_product_by_code(code)
        if prod:
            _clear_pending_stock()
            reset_frustration()
            return prod

    # 5) Minimum order
    if is_minimum_order_question(cleaned):
        _clear_pending_stock()
        reset_frustration()
        return minimum_order_response()

    # 6) Production
    if is_production_question(cleaned):
        _clear_pending_stock()
        reset_frustration()
        return PRODUCTION_INFO + "\n\nIf you need more detail, please contact customer service:\n" + CUSTOMER_SERVICE_URL

    # 7) Eco / Keeleco
    if is_eco_question(cleaned):
        _clear_pending_stock()
        reset_frustration()
        return KEELECO_OVERVIEW

    # 8) Collections
    if detect_collection(cleaned):
        _clear_pending_stock()
        reset_frustration()
        return collection_reply(cleaned)

    # 9) Delivery / tracking guidance
    if is_delivery_question(cleaned):
        _clear_pending_stock()
        reset_frustration()
        return (
            "For delivery updates, please check your order confirmation email. "
            "It includes your estimated delivery date and tracking details if available."
        )

    # 10) Stock code request
    if is_stock_code_request(cleaned):
        # (do not reset frustration here until it resolves, to preserve signals)
        return lookup_stock_code(user_text)

    # 11) Help
    if is_help_question(cleaned):
        _clear_pending_stock()
        reset_frustration()
        return HELP_OVERVIEW

    # 12) Greeting
    if is_greeting(cleaned):
        _clear_pending_stock()
        reset_frustration()
        return f"Hello! 👋 I'm {BOT_NAME}, the {COMPANY_NAME} customer service assistant. How can I help you?"

    # 13) FAQ similarity
    faq = best_faq_answer(user_text)
    if faq:
        _clear_pending_stock()
        reset_frustration()
        return faq

    # 14) Intent scoring fallback
    intent_name = pick_intent(cleaned)
    if intent_name:
        _clear_pending_stock()
        reset_frustration()
        intent = INTENTS[intent_name]
        return random.choice(intent.responses)

    _clear_pending_stock()
    return fallback_response()

# =========================
# JS bridge (called by keelie.js)
# =========================
async def keelie_send():
    """
    Called by JS when user hits Send.
    Reads input, echoes user bubble, produces response bubble.
    """
    try:
        msg = window.keelieGetInput()
    except Exception:
        msg = ""

    msg = (msg or "").strip()
    if not msg:
        return

    window.keelieAddBubble("You", msg)
    window.keelieClearInput()

    try:
        window.keelieShowStatus("Keelie is typing…")
    except Exception:
        pass

    # Load stock rows lazily
    if not STOCK_ROWS:
        await load_stock_rows_from_js()

    answer = await respond(msg)

    try:
        window.keelieClearStatus()
    except Exception:
        pass

    window.keelieAddBubble(BOT_NAME, answer)

# Expose to JS
window.keelieSend = keelie_send

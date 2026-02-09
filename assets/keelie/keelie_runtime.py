# File: assets/keelie/keelie_runtime.py
# NOTE: Paste this file as-is. Do NOT include any ``` backticks in the .py file.

import re
import random
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
STOCK_ROWS: List[Dict[str, str]] = []

PENDING_STOCK_LOOKUP = False
PENDING_STOCK_CHOICES: List[Dict[str, str]] = []
PENDING_STOCK_QUERY: str = ""

STOCK_HIGH = 0.75
STOCK_MED = 0.55

# =========================
# Basic text helpers
# =========================
def clean_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s&-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def tokenize(text: str) -> List[str]:
    return [t for t in clean_text(text).split() if t]

# =========================
# Robust typo tolerance (token-level)
# =========================
def squash_repeats(word: str) -> str:
    # hellooo -> helloo, hiiii -> hii
    return re.sub(r"(.)\1{2,}", r"\1\1", word)

def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, dele, sub))
        prev = cur
    return prev[-1]

def token_close(a: str, b: str) -> bool:
    if a == b:
        return True
    a = a.strip()
    b = b.strip()
    if not a or not b:
        return False

    # short words are common and typo-prone
    la, lb = len(a), len(b)
    if la <= 3 or lb <= 3:
        return levenshtein(a, b) <= 1
    if la <= 6 or lb <= 6:
        return levenshtein(a, b) <= 2
    return levenshtein(a, b) <= 2

COMMON_TOKEN_FIXES = {
    # stock/code
    "stcok": "stock",
    "stok": "stock",
    "sotck": "stock",
    "stokc": "stock",
    "coed": "code",
    "cod": "code",
    "kode": "code",
    "skuu": "sku",
    # delivery/tracking
    "delivary": "delivery",
    "delvery": "delivery",
    "delveryy": "delivery",
    "traking": "tracking",
    "trakking": "tracking",
    "trak": "track",
    "trakc": "track",
    # invoice
    "inovice": "invoice",
    "invioce": "invoice",
    "invoie": "invoice",
    # keeleco/recycled
    "keelco": "keeleco",
    "keelcco": "keeleco",
    "keel-eco": "keeleco",
    "recyled": "recycled",
    "recyceld": "recycled",
    # moq/minimum order
    "minimun": "minimum",
    "minumum": "minimum",
    "ordr": "order",
    "oder": "order",
    "valeu": "value",
    "amout": "amount",
    # where made
    "wher": "where",
    "whre": "where",
    "mad": "made",
    "mdae": "made",
    "manufactuered": "manufactured",
    "manufactered": "manufactured",
}

def normalized_tokens(text: str) -> List[str]:
    raw = tokenize(text)
    out: List[str] = []
    for w in raw:
        w = squash_repeats(w)
        w = COMMON_TOKEN_FIXES.get(w, w)
        out.append(w)
    return out

def has_token(tokens: List[str], target: str) -> bool:
    target = squash_repeats(clean_text(target))
    target = COMMON_TOKEN_FIXES.get(target, target)
    for t in tokens:
        if token_close(t, target):
            return True
    return False

def score_intent_tokens(text: str, must: List[str], any_of: Optional[List[str]] = None) -> int:
    """
    Score intent based on presence of concept tokens (typo-tolerant).
    must tokens add +2 each, any_of tokens add +1 each.
    """
    any_of = any_of or []
    toks = normalized_tokens(text)

    score = 0
    for m in must:
        if has_token(toks, m):
            score += 2
    for a in any_of:
        if has_token(toks, a):
            score += 1
    return score

# =========================
# Stock helpers
# =========================
def extract_stock_code(text: str) -> Optional[str]:
    matches = re.findall(r"\b[A-Z]{1,5}-?[A-Z]{0,5}-?\d{2,4}\b", (text or "").upper())
    return matches[0] if matches else None

def normalize_for_product_match(text: str) -> str:
    t = clean_text(text)
    junk_phrases = [
        "can you tell me", "could you tell me", "please", "what is", "whats", "what's",
        "the product code", "product code", "stock code", "item code", "sku",
        "code for", "code of"
    ]
    for p in junk_phrases:
        t = t.replace(p, " ")
    t = re.sub(r"\b(of|for|a|an|the|to|me|my)\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

# =========================
# Typo-tolerant topic detectors
# =========================
def is_greeting(text: str) -> bool:
    t = clean_text(text)
    # stretched greetings: hiiii, heyyy, helloo
    if re.fullmatch(r"h+i+", t) or re.fullmatch(r"he+y+", t) or re.fullmatch(r"hel+o+", t):
        return True
    return score_intent_tokens(text, must=["hi"], any_of=["hello", "hey", "hiya", "yo", "morning", "afternoon", "evening"]) >= 2 or \
           score_intent_tokens(text, must=["hello"], any_of=["hi", "hey"]) >= 2 or \
           score_intent_tokens(text, must=["hey"], any_of=["hi", "hello"]) >= 2

def is_goodbye(text: str) -> bool:
    t = clean_text(text)
    if re.fullmatch(r"by+e+", t) or re.fullmatch(r"good+by+e+", t):
        return True
    return score_intent_tokens(text, must=["bye"], any_of=["goodbye", "cya", "thanks", "thank", "cheers", "see"]) >= 2 or \
           score_intent_tokens(text, must=["goodbye"], any_of=["bye"]) >= 2

def is_help_question(text: str) -> bool:
    return score_intent_tokens(text, must=["help"], any_of=["can", "do", "ask", "questions"]) >= 2

def is_stock_code_request(text: str) -> bool:
    # allow "sku" alone, or "stock+code"
    s1 = score_intent_tokens(text, must=["stock", "code"], any_of=["sku", "item", "product"])
    s2 = score_intent_tokens(text, must=["sku"], any_of=["code", "stock"])
    return max(s1, s2) >= 3

def is_minimum_order_question(text: str) -> bool:
    s1 = score_intent_tokens(text, must=["minimum", "order"], any_of=["value", "moq", "spend", "amount", "purchase"])
    s2 = score_intent_tokens(text, must=["moq"], any_of=["minimum", "order", "value"])
    return max(s1, s2) >= 3

def is_delivery_question(text: str) -> bool:
    s1 = score_intent_tokens(text, must=["delivery"], any_of=["tracking", "track", "order", "dispatch", "shipped", "eta", "arrive"])
    s2 = score_intent_tokens(text, must=["tracking"], any_of=["order", "delivery", "track"])
    return max(s1, s2) >= 3

def is_invoice_question(text: str) -> bool:
    return score_intent_tokens(text, must=["invoice"], any_of=["download", "copy", "history", "past"]) >= 2

def is_eco_question(text: str) -> bool:
    s1 = score_intent_tokens(text, must=["keeleco"], any_of=["recycled", "eco", "sustainable", "fsc", "polyester"])
    s2 = score_intent_tokens(text, must=["recycled"], any_of=["eco", "sustainable", "keeleco"])
    return max(s1, s2) >= 2

def is_production_question(text: str) -> bool:
    s = score_intent_tokens(text, must=["where"], any_of=["made", "produce", "produced", "manufactured", "factory", "manufacturing"])
    return s >= 2

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

def delivery_response() -> str:
    return (
        "For delivery updates, please check your order confirmation email. "
        "It includes your estimated delivery date and tracking details if available.\n\n"
        "If you need help, customer service can assist here:\n"
        f"{CUSTOMER_SERVICE_URL}"
    )

def invoice_response() -> str:
    return (
        "To get a copy of an invoice, please use your trade account area (Invoice History), "
        "or contact customer service if you need help accessing it:\n"
        f"{CUSTOMER_SERVICE_URL}"
    )

def fallback_response() -> str:
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

def near_miss_prompt(user_text: str) -> Optional[str]:
    scores = [
        ("stock code / SKU", score_intent_tokens(user_text, ["stock", "code"], ["sku", "item", "product"]) ),
        ("minimum order value (MOQ)", score_intent_tokens(user_text, ["minimum", "order"], ["value", "moq", "spend"]) ),
        ("delivery / tracking", score_intent_tokens(user_text, ["delivery"], ["tracking", "order", "eta", "arrive"]) ),
        ("invoices", score_intent_tokens(user_text, ["invoice"], ["download", "copy", "history"]) ),
        ("Keeleco / recycled materials", score_intent_tokens(user_text, ["keeleco"], ["recycled", "eco", "sustainable"]) ),
        ("where toys are made", score_intent_tokens(user_text, ["where"], ["made", "produced", "manufactured"]) ),
    ]
    scores.sort(key=lambda x: x[1], reverse=True)
    top, top_s = scores[0]
    second, second_s = scores[1]
    if top_s >= 2:
        if top_s == second_s and second_s >= 2:
            return f"Did you mean **{top}** or **{second}**?\n\nReply with the topic name and I’ll help."
        return f"Just to check — are you asking about **{top}**?\n\nReply with yes, or tell me the correct topic."
    return None

# =========================
# Privacy guardrail (expanded)
# =========================
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?:(?:\+|00)\s?\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)?\d[\d\s-]{7,}\d")
UK_POSTCODE_RE = re.compile(r"\b(?:GIR\s?0AA|(?:[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}))\b", re.I)

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
    if HOUSE_NUM_RE.search(t) and STREET_WORD_RE.search(t):
        return True

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

    # never treat greetings/goodbyes/very short messages as frustration
    if is_greeting(t) or is_goodbye(t) or len(t) <= 3:
        return False

    if any(k in t for k in FRUSTRATION_KEYWORDS):
        return True

    if "??" in t_raw or "!!" in t_raw:
        return True

    letters = [c for c in t_raw if c.isalpha()]
    if len(letters) >= 8:
        upper_ratio = sum(1 for c in letters if c.isupper()) / max(1, len(letters))
        if upper_ratio >= 0.85:
            return True

    global LAST_USER_CLEAN, LAST_USER_TS
    now = time.time()
    if LAST_USER_CLEAN and (now - LAST_USER_TS) <= 40:
        if similarity(t, LAST_USER_CLEAN) >= 0.92:
            if "??" in t_raw or "!!" in t_raw or any(k in t for k in FRUSTRATION_KEYWORDS):
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

    # If they switch topic, abandon pending state.
    if (
        is_minimum_order_question(user_text)
        or is_delivery_question(user_text)
        or is_invoice_question(user_text)
        or is_eco_question(user_text)
        or is_production_question(user_text)
        or is_help_question(user_text)
        or is_greeting(user_text)
        or is_goodbye(user_text)
    ):
        _clear_pending_stock()
        return None

    # Numeric choice 1-3
    t = clean_text(user_text)
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

    if best_score >= STOCK_HIGH:
        product = str(best_row.get("product_name", "")).strip().title()
        code = str(best_row.get("stock_code", "")).strip()
        _clear_pending_stock()
        return f"The stock code for **{product}** is **{code}**."

    if best_score >= STOCK_MED:
        PENDING_STOCK_LOOKUP = True
        PENDING_STOCK_QUERY = user_text
        PENDING_STOCK_CHOICES = [row for _, row in top]
        return _offer_stock_choices(PENDING_STOCK_CHOICES)

    _clear_pending_stock()
    return "I’m not sure which product you mean. Could you provide the exact product name (and size, if relevant)?"

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
}

def intent_score(intent: Intent, cleaned_text: str) -> int:
    score = 0
    for k, w in intent.keywords.items():
        # typo tolerant keyword hit
        if score_intent_tokens(cleaned_text, must=tokenize(k), any_of=[] ) >= 2:
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
    # 1) Privacy guardrail ALWAYS wins
    if contains_personal_info(user_text):
        _clear_pending_stock()
        return privacy_warning()

    # 2) Pending stock disambiguation flow
    pending = _handle_stock_choice_reply(user_text)
    if pending:
        reset_frustration()
        return pending

    # 3) Frustration detection (CHECK FIRST; do not pre-register)
    global FRUSTRATION_STRIKES
    if detect_frustration(user_text):
        FRUSTRATION_STRIKES += 1
        _clear_pending_stock()
        register_message_for_repeat_check(user_text)

        if FRUSTRATION_STRIKES >= 2:
            return frustration_escalate_response()
        return frustration_first_response()

    # Normal path: now register for repeat detection
    register_message_for_repeat_check(user_text)

    # 4) Greeting early
    if is_greeting(user_text):
        _clear_pending_stock()
        reset_frustration()
        return f"Hello! 👋 I'm {BOT_NAME}, the {COMPANY_NAME} customer service assistant. How can I help you?"

    # 5) Goodbye early (+ feedback prompt)
    if is_goodbye(user_text):
        _clear_pending_stock()
        reset_frustration()
        return (
            "Goodbye! 👋 If you need anything else later, I’m here.\n\n"
            f"Customer service: {CUSTOMER_SERVICE_URL}\n\n"
            "Was I helpful?"
        )

    # Reset frustration on positive signals (typo-tolerant)
    if score_intent_tokens(user_text, must=["thanks"], any_of=["thank", "cheers", "great", "perfect", "ok", "okay"]) >= 2:
        reset_frustration()

    # Direct code -> product lookup
    code = extract_stock_code(user_text)
    if code:
        prod = lookup_product_by_code(code)
        if prod:
            _clear_pending_stock()
            reset_frustration()
            return prod

    # Minimum order
    if is_minimum_order_question(user_text):
        _clear_pending_stock()
        reset_frustration()
        return minimum_order_response()

    # Production
    if is_production_question(user_text):
        _clear_pending_stock()
        reset_frustration()
        return PRODUCTION_INFO + "\n\nIf you need more detail, please contact customer service:\n" + CUSTOMER_SERVICE_URL

    # Eco / Keeleco
    if is_eco_question(user_text):
        _clear_pending_stock()
        reset_frustration()
        return KEELECO_OVERVIEW

    # Delivery / tracking
    if is_delivery_question(user_text):
        _clear_pending_stock()
        reset_frustration()
        return delivery_response()

    # Invoices
    if is_invoice_question(user_text):
        _clear_pending_stock()
        reset_frustration()
        return invoice_response()

    # Stock code request
    if is_stock_code_request(user_text):
        return lookup_stock_code(user_text)

    # Help
    if is_help_question(user_text):
        _clear_pending_stock()
        reset_frustration()
        return HELP_OVERVIEW

    # FAQ similarity
    faq = best_faq_answer(user_text)
    if faq:
        _clear_pending_stock()
        reset_frustration()
        return faq

    # Intent scoring fallback
    intent_name = pick_intent(clean_text(user_text))
    if intent_name:
        _clear_pending_stock()
        reset_frustration()
        intent = INTENTS[intent_name]
        return random.choice(intent.responses)

    # Near-miss clarification before giving up
    guess = near_miss_prompt(user_text)
    if guess:
        _clear_pending_stock()
        return guess

    _clear_pending_stock()
    return fallback_response()

# =========================
# JS bridge (called by keelie.js)
# =========================
async def keelie_send():
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

    if not STOCK_ROWS:
        await load_stock_rows_from_js()

    answer = await respond(msg)

    try:
        window.keelieClearStatus()
    except Exception:
        pass

    window.keelieAddBubble(BOT_NAME, answer)

window.keelieSend = keelie_send

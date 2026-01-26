# File: assets/keelie/keelie_runtime.py

import re
import random
import asyncio
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional

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
# Eco / sustainability overview (Keeleco)
# =========================
KEELECO_OVERVIEW = (
    "Keeleco® is our eco-focused soft toy range made using **100% recycled polyester**.\n\n"
    "Key facts:\n"
    "• The outer plush fabric is made from recycled plastic bottles\n"
    "• The stuffing is made from recycled polyester\n"
    "• Our factory uses solar power where possible\n"
    "• We reduce packaging and use FSC-certified materials where applicable\n\n"
    "If you tell me which Keeleco item you’re looking at, I can help further."
)

# =========================
# Stock codes
# =========================
STOCK_ROWS: List[Dict] = []
PENDING_STOCK_LOOKUP = False

# =========================
# Ranges / collections (simple)
# =========================
COLLECTIONS = {
    "keeleco": (
        "Keeleco® is our eco-focused range made with **100% recycled polyester**.\n"
        "If you tell me a product name or size, I can help find the stock code."
    ),
    "keel eco": (
        "Keeleco® is our eco-focused range made with **100% recycled polyester**.\n"
        "If you tell me a product name or size, I can help find the stock code."
    ),
    "keel toys": (
        "Keel Toys offers a wide range of soft toys and gift items.\n"
        "Tell me what you’re looking for (product name / range / size) and I’ll try to help."
    ),
}

# =========================
# Simple FAQ fallback
# =========================
FAQ = [
    (
        ["opening hours", "open hours", "hours", "opening time", "what time are you open"],
        "Our opening hours can vary by department. Please contact customer service for the latest details:\n"
        f"{CUSTOMER_SERVICE_URL}",
    ),
    (
        ["returns", "return", "refund", "send back"],
        "For returns and refunds, please contact customer service so they can advise on the correct process:\n"
        f"{CUSTOMER_SERVICE_URL}",
    ),
    (
        ["contact", "customer service", "support", "speak to someone", "human"],
        f"Of course! 😊 You can contact Keel Toys customer service here:\n{CUSTOMER_SERVICE_URL}",
    ),
]

FALLBACK = (
    "I’m not totally sure, but I can help if you tell me a little more.\n\n"
    "Try asking about:\n"
    "• minimum order values\n"
    "• stock codes / SKUs\n"
    "• delivery / tracking\n"
    "• Keeleco® sustainability\n"
    f"\nOr contact customer service here:\n{CUSTOMER_SERVICE_URL}"
)

# =========================
# Intent model (simple)
# =========================
@dataclass
class Intent:
    priority: int
    keywords: Dict[str, int]
    responses: List[str]


INTENTS = {
    "customer_service": Intent(
        priority=6,
        keywords={
            "customer service": 6, "support": 4,
            "agent": 4, "human": 4, "contact": 3
        },
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
    "greeting": Intent(
        priority=2,
        keywords={
            "hi": 2, "hello": 2, "hey": 2, "hiya": 2,
            "good morning": 2, "good afternoon": 2, "good evening": 2
        },
        responses=[
            f"Hello! 👋 I'm {BOT_NAME}. Ask me about stock codes, minimum order values, Keeleco®, or delivery & invoices."
        ],
    ),
    "goodbye": Intent(
        priority=1,
        keywords={
            "bye": 2, "goodbye": 2, "thanks": 1, "thank you": 1, "thx": 1, "cheers": 1
        },
        responses=[
            f"Thanks for chatting with {COMPANY_NAME}! Have a lovely day 😊"
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
            "order invoice": 6,
            "download invoice": 7,
        },
        responses=[
            "To request a copy invoice, please contact customer service and provide your order details:\n"
            f"{CUSTOMER_SERVICE_URL}"
        ],
    ),
}

# =========================
# Text utils
# =========================
def clean_text(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def extract_stock_code(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"\b[A-Z]{2}\d{3,6}\b", text.upper())
    return m.group(0) if m else None

# =========================
# Heuristics / classifiers
# =========================
def is_delivery_question(text: str) -> bool:
    t = clean_text(text)
    triggers = [
        "delivery", "deliver", "arrive", "arrival", "eta",
        "tracking", "track", "dispatch", "shipped", "shipment",
        "where is my order", "order status"
    ]
    return any(x in t for x in triggers)

def is_stock_code_request(text: str) -> bool:
    t = clean_text(text)
    triggers = [
        "stock code", "stockcode", "sku", "product code", "product code",
        "code for", "item code", "what is the code", "what's the code"
    ]
    return any(x in t for x in triggers)

def normalize_for_product_match(text: str) -> str:
    t = clean_text(text)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def is_minimum_order_question(text: str) -> bool:
    t = clean_text(text)
    triggers = [
        "minimum order", "min order", "minimum value", "minimum spend",
        "moq", "what is the minimum", "minimum order value"
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

def is_how_its_made_question(text: str) -> bool:
    t = clean_text(text)
    triggers = [
        "how do you make",
        "how do you make the product",
        "how is it made",
        "how it's made",
        "how its made",
        "how do you manufacture",
        "how is it manufactured",
        "manufacturing process",
        "production process",
        "how do you produce",
        "how is it produced",
        "made from",
        "materials used",
        "what is it made of",
        "what's it made of",
        "how are your toys made",
        "how do you make your toys",
    ]
    return any(x in t for x in triggers)

def how_its_made_response(user_text: str) -> str:
    t = clean_text(user_text)
    if any(x in t for x in ["keeleco", "recycled", "sustainable", "sustainability", "eco"]):
        return (
            "**How Keeleco® products are made (high level):**\n"
            "• Materials are chosen with sustainability in mind (including recycled content where applicable).\n"
            "• Fabrics are cut into panels, then stitched and assembled.\n"
            "• Stuffing is filled, products are shaped, and seams are closed securely.\n"
            "• Items go through **quality checks** (stitching, finish, and safety-related components).\n"
            "• Packaging and labelling are applied before dispatch.\n\n"
            "If you tell me the **product name or stock code**, I can be more specific about materials and construction."
        )

    return (
        "**How our plush products are made (high level):**\n"
        "• **Design & prototyping:** artwork, patterns, and sample development.\n"
        "• **Material selection:** outer fabric, threads, trims, and stuffing are chosen.\n"
        "• **Cut & sew:** fabric panels are cut, embroidered/printed if needed, then stitched together.\n"
        "• **Stuffing & shaping:** filling is added and the product is shaped and finished.\n"
        "• **Quality & safety checks:** stitching strength, component security, and overall finish are checked.\n"
        "• **Packaging:** labels/packaging are applied before shipment.\n\n"
        "If you share the **product name / size / stock code**, I can explain the typical materials and any special features."
    )

def is_eco_question(text: str) -> bool:
    t = clean_text(text)
    triggers = [
        "eco", "eco friendly", "sustainable", "sustainability", "recycled", "recycle",
        "environment", "plastic bottles", "keeleco"
    ]
    return any(x in t for x in triggers)

# =========================
# Responses
# =========================
def minimum_order_response() -> str:
    return (
        "**Minimum order values:**\n"
        f"• First order: **£{MIN_ORDER_FIRST}**\n"
        f"• Repeat orders: **£{MIN_ORDER_REPEAT}**\n\n"
        "If you’d like, tell me if this is your first order or a repeat and I can confirm."
    )

# =========================
# Stock code lookups
# =========================
async def load_stock_rows_from_js():
    global STOCK_ROWS
    try:
        # Wait for JS promise to finish
        if hasattr(window, "keelieStockReady"):
            await window.keelieStockReady

        if hasattr(window, "keelieStockRows"):
            STOCK_ROWS = [dict(r) for r in window.keelieStockRows.to_py()]
        else:
            STOCK_ROWS = []
    except Exception:
        STOCK_ROWS = []

def lookup_stock_code(user_text: str) -> str:
    if not STOCK_ROWS:
        return (
            "I can’t access stock codes right now (stock_codes.xlsx may be missing or unreadable). "
            f"Please contact customer service here:\n{CUSTOMER_SERVICE_URL}"
        )

    query = normalize_for_product_match(user_text)

    best_row = None
    best_score = 0.0
    for row in STOCK_ROWS:
        name = str(row.get("product_name", "")).lower().strip()
        score = similarity(query, name)
        if score > best_score:
            best_score = score
            best_row = row

    if best_score < 0.6 or not best_row:
        return "I’m not sure which product you mean. Could you please provide the product name?"

    product = str(best_row.get("product_name", "")).strip()
    code = str(best_row.get("stock_code", "")).strip()

    if not code:
        return f"I found **{product}**, but I don’t have a stock code listed for it."
    return f"The stock code for **{product}** is **{code}**."

def lookup_product_by_code(code: str) -> Optional[str]:
    if not STOCK_ROWS:
        return None
    c = (code or "").strip().upper()
    for row in STOCK_ROWS:
        if str(row.get("stock_code", "")).strip().upper() == c:
            name = str(row.get("product_name", "")).strip()
            return f"Stock code **{c}** is **{name}**."
    return None

# =========================
# Collections helpers
# =========================
def detect_collection(cleaned_text: str) -> Optional[str]:
    for k in COLLECTIONS.keys():
        if k in cleaned_text:
            return k
    return None

def collections_overview() -> str:
    names = sorted({k for k in COLLECTIONS.keys()})
    return (
        "Here are some ranges you can ask about:\n"
        + "\n".join([f"• {n.title()}" for n in names])
        + "\n\nIf you tell me which range (and the product name/size), I can help further."
    )

def collection_reply(cleaned_text: str) -> str:
    key = detect_collection(cleaned_text)
    if not key:
        return collections_overview()
    return COLLECTIONS.get(key, collections_overview())

# =========================
# FAQ matching
# =========================
def best_faq_answer(cleaned_text: str) -> Optional[str]:
    for triggers, answer in FAQ:
        if any(t in cleaned_text for t in triggers):
            return answer
    return None

# =========================
# Intent detection
# =========================
def detect_intent(cleaned_text: str) -> Optional[str]:
    best = None
    best_score = 0
    best_priority = -1

    for name, intent in INTENTS.items():
        score = 0
        for kw, weight in intent.keywords.items():
            if kw in cleaned_text:
                score += weight

        if score <= 0:
            continue

        if intent.priority > best_priority or (intent.priority == best_priority and score > best_score):
            best = name
            best_score = score
            best_priority = intent.priority

    return best

# =========================
# Main reply
# =========================
def keelie_reply(user_input: str) -> str:
    global PENDING_STOCK_LOOKUP

    cleaned = clean_text(user_input)

    # ✅ Collections / ranges trigger (runs early)
    if any(x in cleaned for x in ["range", "ranges", "collection", "collections", "our collections"]):
        PENDING_STOCK_LOOKUP = False
        return collection_reply(cleaned)

    # ✅ If they mention a known collection name directly
    if detect_collection(cleaned):
        PENDING_STOCK_LOOKUP = False
        return collection_reply(cleaned)

    # ✅ Delivery override
    if is_delivery_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return random.choice(INTENTS["delivery_time"].responses)

    # ✅ Minimum order override
    if is_minimum_order_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return minimum_order_response()

    # ✅ How it's made / manufacturing process override
    if is_how_its_made_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return how_its_made_response(user_input)

    # ✅ Manufacturing location override
    if is_production_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return PRODUCTION_INFO

    # ✅ Eco / sustainability override -> Keeleco overview / Keeleco sub-range
    if is_eco_question(user_input):
        PENDING_STOCK_LOOKUP = False
        # If they mention a sub-range, answer it; otherwise give Keeleco overview
        if detect_collection(cleaned):
            return collection_reply(cleaned)
        return KEELECO_OVERVIEW

    # ✅ Follow-up: user provides product name after a stock code request
    if PENDING_STOCK_LOOKUP:
        result = lookup_stock_code(user_input)
        if "I’m not sure which product you mean" in result:
            return "Please type the product name (e.g., “Polar Bear Plush 20cm”)."
        PENDING_STOCK_LOOKUP = False
        return result

    # ✅ Stock code request -> tries now, or asks for product name
    if is_stock_code_request(user_input):
        result = lookup_stock_code(user_input)
        if "I’m not sure which product you mean" in result:
            PENDING_STOCK_LOOKUP = True
            return "Sure — what’s the product name?"
        return result

    # ✅ If message contains a stock code, identify product name
    code = extract_stock_code(user_input)
    if code:
        PENDING_STOCK_LOOKUP = False
        found = lookup_product_by_code(code)
        return found if found else (
            f"I couldn’t find a product with the stock code **{code}**. "
            "Please check the code and try again."
        )

    # ✅ Intent detection (greetings, support, etc.)
    intent = detect_intent(cleaned)
    if intent:
        PENDING_STOCK_LOOKUP = False
        return random.choice(INTENTS[intent].responses)

    # ✅ FAQ fallback
    faq = best_faq_answer(cleaned)
    if faq:
        PENDING_STOCK_LOOKUP = False
        return faq

    PENDING_STOCK_LOOKUP = False
    return FALLBACK

# =========================
# Wire up the UI
# =========================
async def send_message():
    msg = (window.keelieGetInput() or "").strip()
    if not msg:
        return

    window.keelieClearInput()
    window.keelieAddBubble("You", msg)

    # --- Thinking ---
    if hasattr(window, "keelieShowStatus"):
        window.keelieShowStatus("Keelie is thinking…")

    await asyncio.sleep(random.uniform(0.4, 0.8))

    # --- Typing ---
    if hasattr(window, "keelieShowStatus"):
        window.keelieShowStatus("Keelie is typing…")

    await asyncio.sleep(random.uniform(0.35, 0.7))

    if hasattr(window, "keelieClearStatus"):
        window.keelieClearStatus()

    reply = keelie_reply(msg)
    window.keelieAddBubble(BOT_NAME, reply)

def boot():
    window.keelieSend = send_message
    asyncio.create_task(load_stock_rows_from_js())

boot()

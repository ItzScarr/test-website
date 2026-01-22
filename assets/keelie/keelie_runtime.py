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
PENDING_STOCK_LOOKUP = False
STOCK_ROWS: List[Dict[str, str]] = []  # loaded from JS Excel conversion

# =========================
# Helpers
# =========================
def clean_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s&-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def token_set(s: str) -> set:
    return set(clean_text(s).split())

def token_overlap(a: str, b: str) -> float:
    A, B = token_set(a), token_set(b)
    if not A or not B:
        return 0.0
    return len(A & B) / max(len(A), len(B))

def phrase_match_score(user_text: str, phrase: str) -> float:
    """
    Broad matching score in [0..1]:
    - 1.0 if phrase is a direct substring of user_text
    - else uses a blend of fuzzy similarity + token overlap
    """
    u = clean_text(user_text)
    p = clean_text(phrase)
    if not u or not p:
        return 0.0
    if p in u:
        return 1.0
    sim = similarity(u, p)
    ov = token_overlap(u, p)
    return max(sim * 0.85, ov)

def extract_stock_code(text: str) -> Optional[str]:
    matches = re.findall(r"\b[A-Z]{1,5}-?[A-Z]{0,5}-?\d{2,4}\b", (text or "").upper())
    return matches[0] if matches else None

def is_delivery_question(text: str) -> bool:
    t = clean_text(text)
    delivery_terms = [
        "arrive", "arrival", "delivery", "eta", "tracking", "track",
        "order", "dispatch", "shipped", "shipping", "courier"
    ]
    return (("when" in t) and any(term in t for term in delivery_terms)) or any(
        phrase in t for phrase in [
            "where is my order", "track my order", "order status",
            "where is my delivery", "has it shipped", "has it been shipped"
        ]
    )

def is_stock_code_request(text: str) -> bool:
    t = clean_text(text)
    triggers = [
        "product code", "stock code", "sku", "item code", "code for", "code of",
        "what is the code", "whats the code", "what's the code",
        "do you have a code", "do you have the code", "product number", "item number"
    ]
    return any(x in t for x in triggers)

def normalize_for_product_match(text: str) -> str:
    t = clean_text(text)
    junk_phrases = [
        "can you tell me", "could you tell me", "please", "what is", "whats", "what's",
        "the product code", "product code", "stock code", "item code", "sku",
        "code for", "code of", "product number", "item number"
    ]
    for p in junk_phrases:
        t = t.replace(p, " ")
    t = re.sub(r"\b(of|for|a|an|the|to|me|my|please)\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def is_minimum_order_question(text: str) -> bool:
    t = clean_text(text)
    triggers = [
        # core
        "minimum order", "minimum spend", "minimum purchase",
        "min order", "min spend", "order minimum", "minimum order price",

        # broadened
        "minimum value", "minimum order value", "minimum spend value",
        "minimum order amount", "minimum spend amount",
        "minimum basket", "minimum basket value",
        "minimum checkout", "minimum checkout value",
        "what is the minimum", "whats the minimum", "what's the minimum",
        "opening order minimum", "first order minimum", "repeat order minimum",
        "opening order value", "first order value", "repeat order value",
        "trade minimum", "trade order minimum", "trade order value",

        # trade terms
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
        "keeleco", "keel eco",
        "recycled polyester", "recycled plastic"
    ]
    return any(x in t for x in triggers)

def minimum_order_response() -> str:
    return (
        "Our minimum order values are:\n"
        f"• £{MIN_ORDER_FIRST} for first-time buyers\n"
        f"• £{MIN_ORDER_REPEAT} for repeat buyers\n\n"
        "If you’re unsure whether you qualify as a first-time or repeat buyer, "
        "our customer service team can help:\n"
        f"{CUSTOMER_SERVICE_URL}"
    )

# =========================
# Load stock rows from JS (Excel conversion)
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

    product = str(best_row.get("product_name", "")).strip().title()
    code = str(best_row.get("stock_code", "")).strip()
    return f"The stock code for **{product}** is **{code}**."

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
# Collections / ranges (from Keel Toys menu)
# =========================
COLLECTION_FACTS: Dict[str, Dict[str, List[str]]] = {
    # ---- Keeleco family ----
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

    # ---- Other site collections ----
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

    # ---- “Products” group items that appear as collections in the site menu ----
    "accessories": {
        "title": "Accessories",
        "facts": [
            "A product category for Keel Toys accessories.",
            "If you provide the product name, I can try to find the stock code (if listed)."
        ],
    },
    "bag charms": {
        "title": "Bag Charms",
        "facts": [
            "A product category featuring bag charm items.",
            "If you provide the product name, I can try to find the stock code (if listed)."
        ],
    },
    "bakery": {
        "title": "Bakery",
        "facts": [
            "A product category featuring bakery-themed items.",
            "If you provide the product name, I can try to find the stock code (if listed)."
        ],
    },
    "bobballs": {
        "title": "Bobballs",
        "facts": [
            "A product category under Keel Toys’ product listings.",
            "If you provide the product name, I can try to find the stock code (if listed)."
        ],
    },
    "cafe cute": {
        "title": "Cafe Cute",
        "facts": [
            "A product category under Keel Toys’ product listings.",
            "If you provide the product name, I can try to find the stock code (if listed)."
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
# Intent system (broad matching)
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
            "customer service": 6, "support": 5, "help": 3,
            "agent": 5, "human": 5, "contact": 4,
            "speak to someone": 6, "talk to someone": 6,
            "call you": 4, "phone number": 4, "email you": 4
        },
        responses=[
            "Of course! 😊 You can contact Keel Toys customer service here:\n"
            f"{CUSTOMER_SERVICE_URL}"
        ],
    ),

    "delivery_time": Intent(
        priority=6,
        keywords={
            "delivery": 5, "shipping": 5, "ship": 4, "shipped": 5,
            "dispatch": 5, "dispatch date": 6,
            "tracking": 6, "track": 5, "courier": 4,
            "where is my order": 7, "order status": 7,
            "when will it arrive": 7, "arrival": 5, "eta": 6,
        },
        responses=[
            "For delivery updates, please check your order confirmation email. "
            "It includes your estimated delivery date and tracking details if available."
        ],
    ),

    "minimum_order": Intent(
        priority=7,
        keywords={
            "minimum order": 7, "minimum order value": 7, "minimum value": 7,
            "minimum spend": 7, "minimum amount": 7, "minimum basket": 6,
            "order minimum": 7, "moq": 6, "minimum order quantity": 6,
            "first order minimum": 7, "repeat order minimum": 7,
            "opening order minimum": 7,
        },
        responses=[minimum_order_response()],
    ),

    "production": Intent(
        priority=6,
        keywords={
            "where made": 6, "where are they made": 7, "made in": 5,
            "manufactured": 6, "produced": 6, "factory": 4,
            "where are your toys made": 8, "where are your toys manufactured": 8
        },
        responses=[PRODUCTION_INFO],
    ),

    "sustainability": Intent(
        priority=6,
        keywords={
            "keeleco": 7, "recycled": 6, "recycle": 5, "eco": 6,
            "sustainable": 6, "sustainability": 6,
            "fsc": 5, "recycled polyester": 6, "plastic bottles": 6
        },
        responses=[KEELECO_OVERVIEW],
    ),

    "invoice_copy": Intent(
        priority=6,
        keywords={
            "invoice": 6,
            "invoice copy": 7,
            "copy of invoice": 7,
            "download invoice": 7,
            "invoice history": 7,
            "past invoice": 6,
            "order invoice": 6
        },
        responses=[
            "You can access copies of your invoices by logging in to your account, then navigating to:\n\n"
            "**Account > My Orders > Invoice History**"
        ],
    ),

    "account_login": Intent(
        priority=5,
        keywords={
            "login": 7, "log in": 7, "sign in": 7,
            "account": 5, "my account": 6,
            "password": 6, "reset password": 7, "forgot password": 7,
            "cant log in": 7, "can't log in": 7, "cannot log in": 7,
        },
        responses=[
            "If you’re having trouble accessing your account (login/password), the quickest option is to contact our team so they can help securely:\n"
            f"{CUSTOMER_SERVICE_URL}"
        ],
    ),

    "pricing_trade": Intent(
        priority=5,
        keywords={
            "price list": 7, "prices": 5, "pricing": 6,
            "trade price": 7, "trade pricing": 7,
            "wholesale": 6, "cost": 5, "how much": 5,
            "discount": 5, "terms": 4
        },
        responses=[
            "For trade pricing, price lists, and terms, please contact our team and they’ll help you with the right information for your account:\n"
            f"{CUSTOMER_SERVICE_URL}"
        ],
    ),

    "catalogue": Intent(
        priority=5,
        keywords={
            "catalogue": 7, "catalog": 7, "brochure": 6,
            "line sheet": 7, "linesheet": 7,
            "product list": 6, "range list": 6
        },
        responses=[
            "If you’d like a catalogue/line sheet, please contact our team and they’ll send the most up-to-date version:\n"
            f"{CUSTOMER_SERVICE_URL}"
        ],
    ),

    "samples": Intent(
        priority=4,
        keywords={
            "sample": 7, "samples": 7,
            "tester": 5, "trial": 4,
            "can i get a sample": 8
        },
        responses=[
            "For sample requests, please contact our team and they’ll advise what’s possible:\n"
            f"{CUSTOMER_SERVICE_URL}"
        ],
    ),

    "returns": Intent(
        priority=5,
        keywords={
            "return": 7, "returns": 7,
            "refund": 7, "refunds": 7,
            "faulty": 6, "damaged": 6, "broken": 6,
            "replacement": 6, "exchange": 6
        },
        responses=[
            "I can help point you in the right direction — for returns/refunds (or damaged/faulty items), please contact our customer service team here:\n"
            f"{CUSTOMER_SERVICE_URL}"
        ],
    ),

    "greeting": Intent(
        priority=2,
        keywords={
            "hi": 3, "hello": 3, "hey": 3, "hiya": 3,
            "good morning": 3, "good afternoon": 3, "good evening": 3
        },
        responses=[
            f"Hello! 👋 I'm {BOT_NAME}, the {COMPANY_NAME} customer service assistant. How can I help you?"
        ],
    ),

    "goodbye": Intent(
        priority=1,
        keywords={
            "bye": 3, "goodbye": 3, "thanks": 2, "thank you": 2, "thx": 2, "cheers": 2
        },
        responses=[
            f"Thanks for chatting with {COMPANY_NAME}! Have a lovely day 😊"
        ],
    ),
}

FALLBACK = (
    "I’m not able to help with that just now. "
    f"Please contact Keel Toys customer service here:\n{CUSTOMER_SERVICE_URL}"
)

def detect_intent(user_text: str) -> Optional[str]:
    """
    Broad, weighted intent detection.
    Uses fuzzy phrase matching + token overlap (not just exact substring).
    """
    best_intent = None
    best_score = 0.0

    for name, intent in INTENTS.items():
        score = 0.0
        for phrase, weight in intent.keywords.items():
            m = phrase_match_score(user_text, phrase)
            if m >= 0.55:
                score += weight * m
        score *= intent.priority

        if score > best_score:
            best_score = score
            best_intent = name

    return best_intent if best_score >= 3.0 else None

# =========================
# Conversation handling
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

    # ✅ Minimum order override (broadened)
    if is_minimum_order_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return minimum_order_response()

    # ✅ Manufacturing location override
    if is_production_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return PRODUCTION_INFO

    # ✅ Eco / sustainability override
    if is_eco_question(user_input):
        PENDING_STOCK_LOOKUP = False
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

    # ✅ Stock code request
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

    # ✅ Broad intent detection (fuzzy)
    intent = detect_intent(user_input)
    if intent:
        PENDING_STOCK_LOOKUP = False
        # For “minimum_order/production/sustainability” we already override above,
        # but leaving them here is harmless.
        return random.choice(INTENTS[intent].responses)

    # ✅ FAQ fallback
    faq = best_faq_answer(user_input)
    if faq:
        PENDING_STOCK_LOOKUP = False
        return faq

    # ✅ Helpful “nudge” fallback for common unknowns (keeps UX strong)
    PENDING_STOCK_LOOKUP = False
    return (
        "I’m not totally sure I’ve understood. I can help with things like:\n"
        "• Minimum order values\n"
        "• Stock codes / product codes\n"
        "• Delivery / tracking guidance\n"
        "• Keeleco / sustainability\n"
        "• Invoices, login help, returns\n\n"
        "Could you rephrase your question in a few words? "
        f"If you prefer, you can contact our team here:\n{CUSTOMER_SERVICE_URL}"
    )

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

    base = 0.35
    per_char = min(len(msg) * 0.01, 1.0)
    await asyncio.sleep(base + per_char)

    # Remove status bubble
    if hasattr(window, "keelieClearStatus"):
        window.keelieClearStatus()

    reply = keelie_reply(msg)
    window.keelieAddBubble("Keelie", reply)

async def boot():
    await load_stock_rows_from_js()
    window.keelieSend = send_message

await boot()

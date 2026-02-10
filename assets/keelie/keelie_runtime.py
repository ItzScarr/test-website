import re
import random
import asyncio
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional

from js import window

BOT_NAME = "Keelie"
COMPANY_NAME = "Keel Toys"
CUSTOMER_SERVICE_URL = "https://www.keeltoys.com/contact-us/"

MIN_ORDER_FIRST = 500
MIN_ORDER_REPEAT = 250

PRODUCTION_INFO = (
    "Our toys are produced across a small number of trusted manufacturing partners:\n"
    "• 95% in China\n"
    "• 3% in Indonesia\n"
    "• 2% in Cambodia"
)

HELP_OVERVIEW = (
    "I can help with:\n"
    "• **Minimum order values** (e.g. “minimum order value”)\n"
    "• **Stock codes / SKUs** (e.g. “stock code for [product name]”)\n"
    "• **Keeleco® sustainability & recycled materials**\n"
    "• **Where our toys are made**\n"
    "• **Delivery & tracking** (e.g. “where is my order?”)\n"
    "• **Invoices** (e.g. “download an invoice”)\n\n"
    "What would you like to ask?"
)

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

PENDING_STOCK_LOOKUP = False
STOCK_ROWS: List[Dict[str, str]] = []  # loaded from JS Excel conversion

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



EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?:(?:\+|00)\s?\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)?\d[\d\s-]{7,}\d")
ORDER_CUE_RE = re.compile(r"\b(order|invoice|account|ref|reference|tracking|awb|consignment)\b", re.I)
LONG_DIGITS_RE = re.compile(r"\b\d{6,}\b")

def contains_personal_info(text: str) -> bool:
    t = text or ""
    if EMAIL_RE.search(t):
        return True
    if PHONE_RE.search(t):
        return True
    if ORDER_CUE_RE.search(t) and LONG_DIGITS_RE.search(t):
        return True
    return False

def privacy_warning() -> str:
    return (
        "For your privacy, please don’t share personal or account details here "
        "(such as email addresses, phone numbers, or order/invoice references).\n\n"
        "Our customer service team can help you securely here:\n"
        f"{CUSTOMER_SERVICE_URL}"
    )

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



def is_cancel(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    cancel_phrases = {
        "cancel", "nevermind", "never mind", "stop", "exit", "quit",
        "forget it", "no thanks", "no thank you"
    }
    if t in cancel_phrases:
        return True
    if "don't want" in t or "do not want" in t:
        return True
    return False

def is_greeting(text: str) -> bool:
    t = clean_text(text)
    greetings = {
        "hi", "hello", "hey", "hiya", "yo",
        "good morning", "good afternoon", "good evening"
    }
    return (t in greetings) or any(t.startswith(g + " ") for g in greetings)

def minimum_order_response() -> str:
    return (
        "Our minimum order values are:\n"
        f"• £{MIN_ORDER_FIRST} for first-time buyers\n"
        f"• £{MIN_ORDER_REPEAT} for repeat buyers\n\n"
        "If you’re unsure whether you qualify as a first-time or repeat buyer, "
        "our customer service team can help:\n"
        f"{CUSTOMER_SERVICE_URL}"
    )

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
    "opening_hours": Intent(
        priority=6,
        keywords={
            "opening hours": 7,
            "office hours": 7,
            "business hours": 7,
            "what time are you open": 8,
            "what time are you closed": 8,
            "what time do you open": 8,
            "what time do you close": 8,
            "when are you open": 7,
            "when are you closed": 7,
            "hours": 2,
            "open": 2,
            "close": 2
        },
        responses=[
            "Our office hours are:\n"
            "• **Monday–Friday:** 9:00am–5:00pm (UK time)\n\n"
            "We’re closed on weekends and UK public holidays.\n\n"
            f"If you need help outside these hours, you can contact us here:\n{CUSTOMER_SERVICE_URL}"
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
            f"Hello! 👋 I'm {BOT_NAME}, the {COMPANY_NAME} customer service assistant. How can I help you?"
        ],
    ),
        "help": Intent(
        priority=3,
        keywords={
            "what can you do": 6,
            "what can you help with": 6,
            "how can you help": 6,
            "what can i ask": 5,
        },
        responses=[HELP_OVERVIEW],
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
        "order invoice": 5,
        "download invoice": 6
    },
    responses=[
        "You can access copies of your invoices by logging in to your account, then navigating to:\n\n"
        "**Account > My Orders > Invoice History**"
    ],
),

}

FALLBACK = (
    "I’m not able to help with that just now.\n\n"
    "I can help with:\n"
    "• Stock codes / SKUs\n"
    "• Minimum order values\n"
    "• Keeleco® recycled materials\n"
    "• Delivery and invoice queries\n\n"
    "If you need further assistance, our customer service team can help here:\n"
    f"{CUSTOMER_SERVICE_URL}"
)

def detect_intent(cleaned_text: str) -> Optional[str]:
    best_intent = None
    best_score = 0
    for name, intent in INTENTS.items():
        score = sum(weight for phrase, weight in intent.keywords.items() if phrase in cleaned_text)
        score *= intent.priority
        if score > best_score:
            best_score = score
            best_intent = name
    return best_intent if best_score > 0 else None

def keelie_reply(user_input: str) -> str:
    global PENDING_STOCK_LOOKUP

    cleaned = clean_text(user_input)

    if contains_personal_info(user_input):
        PENDING_STOCK_LOOKUP = False
        return privacy_warning()

    if is_greeting(user_input):
        PENDING_STOCK_LOOKUP = False
        return random.choice(INTENTS["greeting"].responses)

    if is_help_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return HELP_OVERVIEW

    if any(x in cleaned for x in ["range", "ranges", "collection", "collections", "our collections"]):
        PENDING_STOCK_LOOKUP = False
        return collection_reply(cleaned)

    if detect_collection(cleaned):
        PENDING_STOCK_LOOKUP = False
        return collection_reply(cleaned)

    if is_delivery_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return random.choice(INTENTS["delivery_time"].responses)

    if is_minimum_order_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return minimum_order_response()

    if is_production_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return PRODUCTION_INFO

    # --- Stock code / SKU handling has priority over "Keeleco" eco info ---
    if PENDING_STOCK_LOOKUP:
        # Let the user break out of the "waiting for product name" flow at any time.
        if is_cancel(user_input):
            PENDING_STOCK_LOOKUP = False
            return "No problem — ask me anything."

        # If they paste a stock code while pending, handle it.
        code = extract_stock_code(user_input)
        if code:
            PENDING_STOCK_LOOKUP = False
            found = lookup_product_by_code(code)
            return found if found else (
                f"I couldn’t find a product with the stock code **{code}**. "
                "Please check the code and try again."
            )

        # Allow normal intents/FAQs to override pending mode.
        intent = detect_intent(cleaned)
        if intent:
            PENDING_STOCK_LOOKUP = False
            return random.choice(INTENTS[intent].responses)

        faq = best_faq_answer(cleaned)
        if faq:
            PENDING_STOCK_LOOKUP = False
            return faq

        # Otherwise treat it as a product name attempt.
        result = lookup_stock_code(user_input)
        if "I’m not sure which product you mean" in result:
            return "Sure — what’s the product name? (Or say **cancel** to ask something else.)"
        PENDING_STOCK_LOOKUP = False
        return result

    if is_stock_code_request(user_input):
        result = lookup_stock_code(user_input)
        if "I’m not sure which product you mean" in result:
            PENDING_STOCK_LOOKUP = True
            return "Sure — what’s the product name?"
        return result

    code = extract_stock_code(user_input)
    if code:
        PENDING_STOCK_LOOKUP = False
        found = lookup_product_by_code(code)
        return found if found else (
            f"I couldn’t find a product with the stock code **{code}**. "
            "Please check the code and try again."
        )

    if is_eco_question(user_input):
        PENDING_STOCK_LOOKUP = False
        if detect_collection(cleaned):
            return collection_reply(cleaned)
        return KEELECO_OVERVIEW

    intent = detect_intent(cleaned)

    if intent:
        PENDING_STOCK_LOOKUP = False
        return random.choice(INTENTS[intent].responses)

    faq = best_faq_answer(cleaned)
    if faq:
        PENDING_STOCK_LOOKUP = False
        return faq

    PENDING_STOCK_LOOKUP = False
    return FALLBACK

async def send_message():
    msg = (window.keelieGetInput() or "").strip()
    if not msg:
        return

    window.keelieClearInput()
    window.keelieAddBubble("You", msg)

    if hasattr(window, "keelieShowStatus"):
        window.keelieShowStatus("Keelie is thinking…")

    await asyncio.sleep(random.uniform(0.4, 0.8))

    if hasattr(window, "keelieShowStatus"):
        window.keelieShowStatus("Keelie is typing…")

    base = 0.35
    per_char = min(len(msg) * 0.01, 1.0)
    await asyncio.sleep(base + per_char)

    if hasattr(window, "keelieClearStatus"):
        window.keelieClearStatus()

    reply = keelie_reply(msg)

    window.keelieAddBubble("Keelie", reply)


async def boot():
    await load_stock_rows_from_js()
    window.keelieSend = send_message

await boot()
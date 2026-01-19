import re
import random
from difflib import SequenceMatcher
from js import window, fetch

BOT_NAME = "Keelie"
COMPANY_NAME = "Keel Toys"
CUSTOMER_SERVICE_URL = "https://www.keeltoys.com/contact-us/"

MIN_ORDER_FIRST = 500
MIN_ORDER_REPEAT = 250

PRODUCTION_INFO = (
    "Our toys are produced across a small number of trusted manufacturing partners:\n"
    "• **95%** in China\n"
    "• **3%** in Indonesia\n"
    "• **2%** in Cambodia"
)

ECO_INFO = (
    "We’re actively working to reduce environmental impact. Here are a few examples:\n"
    "• **Keeleco®** is our **100% recycled** soft toy range — made from **100% recycled polyester** derived from plastic waste.\n"
    "• As a guide, around **10 recycled 500ml bottles** can produce enough fibre for an **18cm** toy.\n"
    "• Our **Keel logo + hangtags** are made from **FSC card** and attached with **cotton**.\n"
    "• **Shipping cartons** are recycled and sealed with **paper tape**.\n"
    "• We focus on responsible sourcing and work with suppliers that have **independent, internationally recognised social/ethical audits** in place.\n\n"
    "If you’d like, tell me which product/range you’re interested in and I can help point you to the right place."
)

FAQ = {
    "Tell me about Keel Toys":
        "Keel Toys is a family-run UK soft toy company founded in 1947. Since 1988, we’ve focused on developing our own-brand soft toys.",
    "What are your opening hours?":
        "The Keel Toys office is open Monday to Friday, 9:00am–5:00pm (UK time).",
    "Are Keel Toys toys safe?":
        "All Keel Toys products are designed and tested to meet UK and EU safety standards.",
}

# In-browser state
PENDING_STOCK_LOOKUP = False
STOCK_ROWS = []

def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def extract_stock_code(text: str):
    matches = re.findall(r"\b[A-Z]{1,5}-?[A-Z]{0,5}-?\d{2,4}\b", text.upper())
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
    triggers = ["minimum order", "minimum spend", "minimum purchase", "min order", "min spend", "order minimum", "minimum order price"]
    return any(x in t for x in triggers)

def is_production_question(text: str) -> bool:
    t = clean_text(text)
    phrases = [
        "where are your toys produced","where are your toys made","where are your toys manufactured",
        "where are the toys produced","where are the toys made","where are the toys manufactured",
        "where are they produced","where are they made","where are they manufactured",
    ]
    if any(p in t for p in phrases):
        return True
    production_words = {"produced", "made", "manufactured"}
    return ("where" in t) and ("toy" in t or "toys" in t) and any(w in t for w in production_words)

def is_eco_question(text: str) -> bool:
    t = clean_text(text)
    triggers = ["eco","eco friendly","eco-friendly","sustainable","sustainability","environment","environmentally friendly",
                "recycled","recycle","recyclable","plastic bottles","fsc","keeleco","keel eco"]
    return any(x in t for x in triggers)

def minimum_order_response() -> str:
    return (
        "Our minimum order values are:\n"
        f"• **£{MIN_ORDER_FIRST}** for first-time buyers\n"
        f"• **£{MIN_ORDER_REPEAT}** for repeat buyers\n\n"
        "If you’re unsure whether you qualify as a first-time or repeat buyer, our customer service team can help:\n"
        f"{CUSTOMER_SERVICE_URL}"
    )

def lookup_stock_code(user_text: str) -> str:
    if not STOCK_ROWS:
        return (
            "I can’t access stock codes right now. "
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

def lookup_product_by_code(code: str):
    if not STOCK_ROWS:
        return None
    code = code.upper().strip()
    for row in STOCK_ROWS:
        c = str(row.get("stock_code", "")).upper().strip()
        if c == code:
            product = str(row.get("product_name", "")).strip().title()
            return f"The product with stock code **{code}** is **{product}**."
    return None

def best_faq_answer(user_text: str):
    # lightweight: compare similarity vs the FAQ keys
    q = clean_text(user_text)
    best, best_score = None, 0.0
    for k, v in FAQ.items():
        s = similarity(q, clean_text(k))
        if s > best_score:
            best_score = s
            best = v
    return best if best_score >= 0.55 else None

def keelie_reply(user_input: str) -> str:
    global PENDING_STOCK_LOOKUP
    cleaned = clean_text(user_input)

    if is_delivery_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return "For delivery updates, please check your order confirmation email. It includes your estimated delivery date and tracking details if available."

    if is_minimum_order_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return minimum_order_response()

    if is_production_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return PRODUCTION_INFO

    if is_eco_question(user_input):
        PENDING_STOCK_LOOKUP = False
        return ECO_INFO

    if PENDING_STOCK_LOOKUP:
        result = lookup_stock_code(user_input)
        if "I’m not sure which product you mean" in result:
            return "Please type the product name (e.g., “Polar Bear Plush 20cm”)."
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
        return found if found else f"I couldn’t find a product with the stock code **{code}**. Please check the code and try again."

    faq = best_faq_answer(cleaned)
    if faq:
        PENDING_STOCK_LOOKUP = False
        return faq

    PENDING_STOCK_LOOKUP = False
    return (
        "I’m not able to help with that just now. "
        f"Please contact Keel Toys customer service here:\n{CUSTOMER_SERVICE_URL}"
    )

async def load_stock_json(base_path: str):
    global STOCK_ROWS
    try:
        res = await fetch(f"{base_path}/stock_codes.json")
        if res.ok:
            STOCK_ROWS = await res.json()
        else:
            STOCK_ROWS = []
    except Exception:
        STOCK_ROWS = []

def init_widget_config(config: dict):
    # exposed hook if you want to configure later
    window.__KEELIE_CONFIG__ = config

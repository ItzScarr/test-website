import re
import random
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
from difflib import SequenceMatcher
from flask import Flask, request, jsonify
from flask_cors import CORS
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# =========================
# Bot identity & links
# =========================
BOT_NAME = "Keelie"
COMPANY_NAME = "Keel Toys"
CUSTOMER_SERVICE_URL = "https://www.keeltoys.com/contact-us/"

# =========================
# Minimum order values
# =========================
MIN_ORDER_FIRST = 500   # £500 for first-time buyers
MIN_ORDER_REPEAT = 250  # £250 for repeat buyers

# =========================
# Manufacturing info
# =========================
PRODUCTION_INFO = (
    "Our toys are produced across a small number of trusted manufacturing partners:\n"
    "• **95%** in China\n"
    "• **3%** in Indonesia\n"
    "• **2%** in Cambodia"
)

# =========================
# Eco / sustainability info
# =========================
ECO_INFO = (
    "We’re actively working to reduce environmental impact. Here are a few examples:\n"
    "• **Keeleco®** is our **100% recycled** soft toy range — made from **100% recycled polyester** derived from plastic waste.\n"
    "• As a guide, around **10 recycled 500ml bottles** can produce enough fibre for an **18cm** toy.\n"
    "• Our **Keel logo + hangtags** are made from **FSC card** and attached with **cotton**.\n"
    "• **Shipping cartons** are recycled and sealed with **paper tape**.\n"
    "• We focus on responsible sourcing and work with suppliers that have **independent, internationally recognised social/ethical audits** in place.\n\n"
    "If you’d like, tell me which product/range you’re interested in and I can help point you to the right place."
)

# =========================
# Excel settings (STOCK CODES ONLY)
# =========================
EXCEL_PATH = "stock_codes.xlsx"
EXCEL_SHEET = 0

EXCEL_COLUMNS = {
    "product": "product_name",
    "code": "stock_code",
}

# =========================
# Helper state (per "session_id")
# =========================
# In production you'd use Redis/DB. This is fine for local/dev.
SESSION_STATE: Dict[str, Dict[str, bool]] = {}

def get_state(session_id: str) -> Dict[str, bool]:
    if session_id not in SESSION_STATE:
        SESSION_STATE[session_id] = {"PENDING_STOCK_LOOKUP": False}
    return SESSION_STATE[session_id]

# =========================
# Helpers
# =========================
def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def extract_stock_code(text: str) -> Optional[str]:
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
    triggers = [
        "minimum order", "minimum spend", "minimum purchase",
        "min order", "min spend", "order minimum", "minimum order price"
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

def minimum_order_response() -> str:
    return (
        "Our minimum order values are:\n"
        f"• **£{MIN_ORDER_FIRST}** for first-time buyers\n"
        f"• **£{MIN_ORDER_REPEAT}** for repeat buyers\n\n"
        "If you’re unsure whether you qualify as a first-time or repeat buyer, "
        "our customer service team can help:\n"
        f"{CUSTOMER_SERVICE_URL}"
    )

# =========================
# Load stock codes from Excel
# =========================
def load_stock_codes() -> Optional[pd.DataFrame]:
    try:
        df = pd.read_excel(EXCEL_PATH, sheet_name=EXCEL_SHEET, engine="openpyxl")
        df.columns = [c.strip().lower() for c in df.columns]

        if EXCEL_COLUMNS["product"] not in df.columns or EXCEL_COLUMNS["code"] not in df.columns:
            return None

        df[EXCEL_COLUMNS["product"]] = df[EXCEL_COLUMNS["product"]].astype(str).str.lower().str.strip()
        df[EXCEL_COLUMNS["code"]] = df[EXCEL_COLUMNS["code"]].astype(str).str.strip()

        df = df[(df[EXCEL_COLUMNS["product"]] != "") & (df[EXCEL_COLUMNS["code"]] != "")]
        return df.reset_index(drop=True)
    except Exception:
        return None

STOCK_DF = load_stock_codes()

def lookup_stock_code(user_text: str) -> str:
    if STOCK_DF is None:
        return (
            "I can’t access stock codes right now. "
            f"Please contact customer service here:\n{CUSTOMER_SERVICE_URL}"
        )

    query = normalize_for_product_match(user_text)

    best_row = None
    best_score = 0.0
    for _, row in STOCK_DF.iterrows():
        name = str(row[EXCEL_COLUMNS["product"]])
        score = similarity(query, name)
        if score > best_score:
            best_score = score
            best_row = row

    if best_score < 0.6 or best_row is None:
        return "I’m not sure which product you mean. Could you please provide the product name?"

    return (
        f"The stock code for **{str(best_row[EXCEL_COLUMNS['product']]).title()}** "
        f"is **{str(best_row[EXCEL_COLUMNS['code']]).strip()}**."
    )

def lookup_product_by_code(code: str) -> Optional[str]:
    if STOCK_DF is None:
        return None

    code = code.upper().strip()
    matches = STOCK_DF[STOCK_DF[EXCEL_COLUMNS["code"]].astype(str).str.upper() == code]

    if len(matches) == 0:
        return None

    product = str(matches.iloc[0][EXCEL_COLUMNS["product"]]).strip()
    return f"The product with stock code **{code}** is **{product.title()}**."

# =========================
# FAQ (flexible matching)
# =========================
FAQ = {
    "Tell me about Keel Toys":
        "Keel Toys is a family-run UK soft toy company founded in 1947. Since 1988, we’ve focused on developing our own-brand soft toys.",
    "What are your opening hours?":
        "The Keel Toys office is open Monday to Friday, 9:00am–5:00pm (UK time).",
    "Are Keel Toys toys safe?":
        "All Keel Toys products are designed and tested to meet UK and EU safety standards.",
}

faq_questions = [clean_text(q) for q in FAQ.keys()]
faq_answers = list(FAQ.values())

vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
faq_matrix = vectorizer.fit_transform(faq_questions)

def best_faq_answer(user_text: str, threshold: float = 0.35) -> Optional[str]:
    vec = vectorizer.transform([user_text])
    sims = cosine_similarity(vec, faq_matrix)
    idx = int(sims.argmax())
    return faq_answers[idx] if float(sims[0, idx]) >= threshold else None

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
        priority=1,
        keywords={"hi": 1, "hello": 1, "hey": 1, "hiya": 1, "good morning": 1, "good afternoon": 1, "good evening": 1},
        responses=[
            f"Hello! 👋 I'm {BOT_NAME}, the {COMPANY_NAME} customer service assistant. How can I help you?"
        ],
    ),
    "goodbye": Intent(
        priority=1,
        keywords={"bye": 1, "goodbye": 1, "thanks": 1, "thank you": 1, "thx": 1, "cheers": 1},
        responses=[
            f"Thanks for chatting with {COMPANY_NAME}! Have a lovely day 😊"
        ],
    ),
}

FALLBACK = (
    "I’m not able to help with that just now. "
    f"Please contact Keel Toys customer service here:\n{CUSTOMER_SERVICE_URL}"
)

def detect_intent(text: str) -> Optional[str]:
    best_intent = None
    best_score = 0
    for name, intent in INTENTS.items():
        score = sum(weight for phrase, weight in intent.keywords.items() if phrase in text)
        score *= intent.priority
        if score > best_score:
            best_score = score
            best_intent = name
    return best_intent if best_score > 0 else None

# =========================
# Conversation handling (per session)
# =========================
def keelie_reply(user_input: str, session_id: str) -> str:
    state = get_state(session_id)
    cleaned = clean_text(user_input)

    # Delivery override
    if is_delivery_question(user_input):
        state["PENDING_STOCK_LOOKUP"] = False
        return random.choice(INTENTS["delivery_time"].responses)

    # Minimum order override
    if is_minimum_order_question(user_input):
        state["PENDING_STOCK_LOOKUP"] = False
        return minimum_order_response()

    # Manufacturing location override
    if is_production_question(user_input):
        state["PENDING_STOCK_LOOKUP"] = False
        return PRODUCTION_INFO

    # Eco / sustainability override
    if is_eco_question(user_input):
        state["PENDING_STOCK_LOOKUP"] = False
        return ECO_INFO

    # Follow-up: user provides product name after a stock code request
    if state["PENDING_STOCK_LOOKUP"]:
        result = lookup_stock_code(user_input)
        if "I’m not sure which product you mean" in result:
            return "Please type the product name (e.g., “Polar Bear Plush 20cm”)."
        state["PENDING_STOCK_LOOKUP"] = False
        return result

    # Stock code request -> tries now, or asks for product name
    if is_stock_code_request(user_input):
        result = lookup_stock_code(user_input)
        if "I’m not sure which product you mean" in result:
            state["PENDING_STOCK_LOOKUP"] = True
            return "Sure — what’s the product name?"
        return result

    # If message contains a stock code, identify product name
    code = extract_stock_code(user_input)
    if code:
        state["PENDING_STOCK_LOOKUP"] = False
        found = lookup_product_by_code(code)
        return found if found else (
            f"I couldn’t find a product with the stock code **{code}**. "
            "Please check the code and try again."
        )

    # Intent detection
    intent = detect_intent(cleaned)
    if intent:
        state["PENDING_STOCK_LOOKUP"] = False
        return random.choice(INTENTS[intent].responses)

    # FAQ fallback
    faq = best_faq_answer(cleaned)
    if faq:
        state["PENDING_STOCK_LOOKUP"] = False
        return faq

    state["PENDING_STOCK_LOOKUP"] = False
    return FALLBACK

# =========================
# Flask app
# =========================
app = Flask(__name__)
CORS(app)  # ok for local dev. tighten for production.

@app.get("/health")
def health():
    return jsonify({"ok": True, "stock_loaded": STOCK_DF is not None})

@app.post("/chat")
def chat():
    data = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    session_id = (data.get("session_id") or "default").strip()

    if not message:
        return jsonify({"reply": "Please type a message.", "session_id": session_id})

    reply = keelie_reply(message, session_id=session_id)
    return jsonify({"reply": reply, "session_id": session_id})

if __name__ == "__main__":
    # Run: python app.py
    app.run(host="127.0.0.1", port=5000, debug=True)

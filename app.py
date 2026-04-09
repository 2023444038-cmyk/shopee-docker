import os
import re
import pickle
import asyncio
import numpy as np
import pandas as pd
import tensorflow as tf
from flask import Flask, render_template, request, flash
from playwright.async_api import async_playwright
from playwright_stealth import stealth
from tensorflow.keras.preprocessing.sequence import pad_sequences

app = Flask(__name__)
app.secret_key = "secret_abs_kipas"

# -----------------------------
# Config
# -----------------------------
MODEL_PATH = "absa_kipas_model.h5"
TOKENIZER_PATH = "tokenizer.pickle"
MAX_LEN = 60
MAX_VOCAB = 10000

# Mesti ikut urutan masa training
MODEL_COLUMNS = [
    'Kualiti_Fizikal', 'Ketahanan', 'Kelajuan_Angin', 
    'Bateri', 'Harga', 'Penghantaran', 
    'Pembungkusan', 'Layanan_Penjual'
]

# -----------------------------
# FIXED: Load Model Method
# -----------------------------
def build_model_skeleton():
    """Bina semula struktur model untuk elak error deserialization Attention."""
    input_layer = tf.keras.layers.Input(shape=(MAX_LEN,))
    x = tf.keras.layers.Embedding(input_dim=MAX_VOCAB, output_dim=128)(input_layer)
    x = tf.keras.layers.LSTM(64, return_sequences=True)(x)
    
    # Layer Attention yang bersih
    query_value = x
    x = tf.keras.layers.Attention()([query_value, query_value])
    
    x = tf.keras.layers.GlobalAveragePooling1D()(x)
    x = tf.keras.layers.Dropout(0.3)(x)
    output_layer = tf.keras.layers.Dense(len(MODEL_COLUMNS), activation='tanh')(x)
    
    return tf.keras.models.Model(inputs=input_layer, outputs=output_layer)

# Bina model dan masukkan weights dari fail .h5
try:
    model = build_model_skeleton()
    # Load weights sahaja untuk bypass error 'score_mode'
    temp_model = tf.keras.models.load_model(MODEL_PATH, compile=False)
    model.set_weights(temp_model.get_weights())
    model.compile(optimizer='adam', loss='mse')
    print("✅ Model loaded successfully using Skeleton Method.")
except Exception as e:
    print(f"❌ Error loading model: {e}")

# Load Tokenizer
with open(TOKENIZER_PATH, 'rb') as f:
    tokenizer = pickle.load(f)

# -----------------------------
# Helper Functions
# -----------------------------
def clean_text(text):
    if not isinstance(text, str): return ""
    malay_slang = {"x": "tidak", "tak": "tidak", "tk": "tidak", "ok": "elok", "laju": "cepat"}
    text = text.lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    words = [malay_slang.get(w, w) for w in text.split()]
    return " ".join(words)

async def scrape_shopee(target_url, limit=50):
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage", # Crucial for Docker/Render
                    "--disable-gpu"
                ]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await stealth(page)
            
            match = re.search(r'i\.(\d+)\.(\d+)', target_url)
            if not match: return None
            shop_id, item_id = match.group(1), match.group(2)
            
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)
            
            api_url = f"https://shopee.com.my/api/v2/item/get_ratings?itemid={item_id}&limit={limit}&offset=0&shopid={shop_id}&type=0"
            
            raw_response = await page.evaluate(f"async () => {{ const r = await fetch('{api_url}'); return await r.json(); }}")
            await browser.close()
            
            if 'data' in raw_response and raw_response['data']['ratings']:
                return raw_response['data']['ratings']
        except Exception as e:
            print(f"Scraping Error: {e}")
            return None
    return None

# -----------------------------
# Routes
# -----------------------------
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/demo/<type>")
def demo(type):
    # Data dummy untuk 3 jenis kipas
    demo_data = {
        "turbo": {
            "total": 10, "avg_star": 3.6, "positive_pct": 63,
            "results": {'Prestasi_Angin': 73, 'Harga': 69, 'Kualiti_Fizikal': 66, 'Bateri_Pengecasan': 63, 'Penghantaran': 63, 'Layanan_Penjual': 59, 'Pembungkusan': 56},
            "star_percentages": {5: 38, 4: 25, 3: 13, 2: 13, 1: 13},
            "ai_summary": "Majoriti pelanggan berpuas hati terutamanya dari segi Prestasi Angin dan Harga & Nilai. Walau bagaimanapun, aspek Pembungkusan perlu diberi perhatian.",
            "top_reviews": [
                {"star": 5, "variation": "Pro+ White", "review": "Best! Bawa pergi kelas, angin dia sejuk. Cas pun cepat."},
                {"star": 4, "variation": "Pro+ Black", "review": "Murah dan bagus. Plastik ok, tak nampak murahan. Seller helpful."},
                {"star": 3, "variation": "Standard", "review": "Bateri lemah sikit tapi oklah untuk harga tu. Delivery laju."}
            ]
        },
        "mini": {
            "total": 5, "avg_star": 4.0, "positive_pct": 60,
            "results": {'Kualiti_Fizikal': 80, 'Prestasi_Angin': 80, 'Bateri_Pengecasan': 80, 'Harga': 70, 'Penghantaran': 70, 'Pembungkusan': 70, 'Layanan_Penjual': 70},
            "star_percentages": {5: 40, 4: 20, 3: 40, 2: 0, 1: 0},
            "ai_summary": "Majoriti pelanggan berpuas hati terutamanya dari segi Kualiti Fizikal dan Prestasi Angin.",
            "top_reviews": [
                {"star": 5, "variation": "Pink Mini", "review": "Kecil tapi angin kuat! Bateri tahan 6 jam. Design cute."},
                {"star": 4, "variation": "White Mini", "review": "Harga mahal sikit tapi kualiti memang bagus. Material solid."},
                {"star": 3, "variation": "Black Mini", "review": "Lambat sampai, 7 hari baru dapat. Tapi kipas elok."}
            ]
        },
        "pro": {
            "total": 8, "avg_star": 3.8, "positive_pct": 55,
            "results": {'Harga': 85, 'Layanan_Penjual': 75, 'Prestasi_Angin': 60, 'Kualiti_Fizikal': 55, 'Bateri_Pengecasan': 50, 'Penghantaran': 45, 'Pembungkusan': 40},
            "star_percentages": {5: 30, 4: 30, 3: 20, 2: 10, 1: 10},
            "ai_summary": "Produk ini menawarkan nilai harga yang sangat baik, namun kualiti pembungkusan perlu ditingkatkan segera.",
            "top_reviews": [
                {"star": 5, "variation": "Pro Grey", "review": "Seller sangat peramah. Barang sampai dalam keadaan baik."},
                {"star": 2, "variation": "Pro Blue", "review": "Kipas ok tapi kotak hancur masa sampai. Tolong improve packaging."}
            ]
        }
    }

    data = demo_data.get(type, demo_data["turbo"])
    return render_template("index.html", is_demo=True, **data)

@app.route("/predict_url", methods=["POST"])
def predict_url():
    url = request.form.get("shopee_url")
    limit = int(request.form.get("review_limit", 50))
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    raw_ratings = loop.run_until_complete(scrape_shopee(url, limit))

    if not raw_ratings:
        flash("Gagal mengambil ulasan. Sila pastikan link betul atau cuba lagi.")
        return render_template("index.html")

    all_preds = []
    top_reviews = []
    stars = []

    for r in raw_ratings:
        comment = r.get('comment', '')
        if not comment or len(comment.strip()) < 5: continue
        
        stars.append(r['rating_star'])
        top_reviews.append({
            'star': r['rating_star'],
            'variation': r.get('product_items', [{}])[0].get('model_name', 'Default'),
            'review': comment
        })

        # Predict
        cleaned = clean_text(comment)
        seq = tokenizer.texts_to_sequences([cleaned])
        padded = pad_sequences(seq, maxlen=MAX_LEN, padding="post")
        preds = model.predict(padded, verbose=0)[0]
        all_preds.append(preds)

    if not all_preds:
        flash("Tiada ulasan bertulis dijumpai.")
        return render_template("index.html")

    avg_preds = np.mean(all_preds, axis=0)
    
    # Mapping MODEL_COLUMNS ke HTML Aspek
    results = {
        'Kualiti_Fizikal':  int(max(0, avg_preds[0]) * 100),
        'Prestasi_Angin':   int(max(0, avg_preds[2]) * 100), # Index 2 = Kelajuan_Angin
        'Bateri_Pengecasan':int(max(0, avg_preds[3]) * 100), # Index 3 = Bateri
        'Harga':            int(max(0, avg_preds[4]) * 100),
        'Penghantaran':     int(max(0, avg_preds[5]) * 100),
        'Pembungkusan':     int(max(0, avg_preds[6]) * 100),
        'Layanan_Penjual':  int(max(0, avg_preds[7]) * 100)
    }

    star_counts = {i: stars.count(i) for i in range(1, 6)}
    star_pct = {k: int((v/len(stars))*100) for k, v in star_counts.items()}

    best_aspect = max(results, key=results.get).replace('_', ' ')
    summary = f"Produk ini sangat cemerlang dalam aspek {best_aspect} mengikut ulasan pengguna."

    return render_template("index.html", 
        total=len(stars),
        avg_star=round(np.mean(stars), 1),
        positive_pct=int(((stars.count(5)+stars.count(4))/len(stars))*100),
        results=results,
        star_percentages=star_pct,
        top_reviews=top_reviews[:6],
        ai_summary=summary,
        url=url,
        limit_selected=limit
    )

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
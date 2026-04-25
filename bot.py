#!/usr/bin/env python3
"""
Crypto Intel Bot v4 - by Juancho
- Cutoff = timestamp ultimo envio (nunca noticias viejas)
- Filtro de calidad agresivo (solo noticias que mueven mercado)
- CoinGecko batch (1 sola llamada)
- Deduplicacion persistente
"""

import os
import re
import json
import time
import hashlib
import calendar
import requests
import feedparser
from datetime import datetime, timedelta, timezone

# ══ CONFIGURACION ══════════════════════════════════════════
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

MIN_SCORE        = 7     # Umbral alto — solo noticias realmente impactantes
MAX_NEWS_PER_RUN = 5     # Maximo por hora
STATE_FILE       = "bot_state.json"
MAX_STORED_IDS   = 500

# ══ COINGECKO IDs ══════════════════════════════════════════
COINGECKO_IDS = {
    "bitcoin": "bitcoin",        "btc": "bitcoin",
    "ethereum": "ethereum",      "eth": "ethereum",
    "bnb": "binancecoin",        "binance coin": "binancecoin",
    "xrp": "ripple",             "ripple": "ripple",
    "solana": "solana",          "sol": "solana",
    "cardano": "cardano",        "ada": "cardano",
    "dogecoin": "dogecoin",      "doge": "dogecoin",
    "tron": "tron",              "trx": "tron",
    "avalanche": "avalanche-2",  "avax": "avalanche-2",
    "polkadot": "polkadot",      "dot": "polkadot",
    "chainlink": "chainlink",    "link": "chainlink",
    "polygon": "matic-network",  "matic": "matic-network",
    "litecoin": "litecoin",      "ltc": "litecoin",
    "uniswap": "uniswap",        "uni": "uniswap",
    "cosmos": "cosmos",          "atom": "cosmos",
    "stellar": "stellar",        "xlm": "stellar",
    "filecoin": "filecoin",      "fil": "filecoin",
    "algorand": "algorand",      "algo": "algorand",
    "ethereum classic": "ethereum-classic", "etc": "ethereum-classic",
    "zcash": "zcash",            "zec": "zcash",
}

# ══ ACTIVOS ═════════════════════════════════════════════════
COIN_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "bnb", "binance coin",
    "xrp", "ripple", "solana", "sol", "cardano", "ada",
    "dogecoin", "doge", "tron", "trx", "avalanche", "avax",
    "polkadot", "dot", "chainlink", "link", "polygon", "matic", "pol",
    "litecoin", "ltc", "uniswap", "uni", "cosmos", "atom",
    "stellar", "xlm", "filecoin", "fil", "algorand", "algo",
    "ethereum classic", "etc", "zcash", "zec",
    "gold", "oro", "xau", "silver", "plata", "xag", "copper", "cobre",
    "coinbase", "kraken", "bybit", "okx", "binance",
    "defi", "nft", "stablecoin", "usdt", "usdc",
    "blackrock", "fidelity", "microstrategy", "grayscale",
]

# ══ KEYWORDS DE ALTO IMPACTO (+3 cada una) ════════════════
IMPACT_KEYWORDS = [
    # Movimiento de precio real
    "surge", "rally", "crash", "plunge", "soar", "spike",
    "all-time high", "ath", "all time high", "breakout", "breakdown",
    "liquidation", "liquidated",
    # Macro
    "federal reserve", "fed rate", "fomc", "rate cut", "rate hike",
    "inflation", "cpi", "recession",
    # Regulacion
    "sec", "cftc", "ban", "banned", "approved", "etf", "spot etf",
    "lawsuit", "sanction", "congress", "senate",
    # Institucional
    "blackrock", "fidelity", "microstrategy", "grayscale",
    "whale", "institutional",
    # Eventos criticos
    "hack", "exploit", "breach", "stolen", "vulnerability", "attack",
    "halving", "hard fork",
    # Adopcion real
    "listed on coinbase", "listed on binance", "mainnet launch",
    "government", "nation", "country",
    # Metales
    "gold rally", "silver surge", "safe haven", "inflation hedge",
]

# ══ KEYWORDS CRITICOS — garantizan envio si aparecen ══════
# Noticias con estos terminos son SIEMPRE importantes
CRITICAL_KEYWORDS = [
    "hack", "hacked", "exploit", "exploited", "stolen", "breach",
    "ban", "banned", "sec charges", "sec sues", "arrest", "arrested",
    "bankrupt", "bankruptcy", "insolvent", "collapse", "collapsed",
    "all-time high", "ath", "rate cut", "rate hike", "fomc",
    "spot etf approved", "etf approved", "etf rejected",
    "listed on coinbase", "listed on binance",
    "emergency", "halving",
]

# ══ PENALIZACIONES — reducen score (ruido/opinion) ════════
NOISE_KEYWORDS = [
    "price prediction", "could reach", "might hit", "could hit",
    "analysts say", "expert says", "here's why", "why bitcoin",
    "top 5", "top 10", "best crypto", "should you buy",
    "is it too late", "bull run incoming", "to the moon",
    "price analysis", "technical analysis", "ta:", "weekly recap",
    "weekly roundup", "this week in", "daily recap",
]

# ══ RSS SOURCES ═══════════════════════════════════════════════
RSS_SOURCES = [
    ("CoinDesk",        "https://www.coindesk.com/arc/outboundfeeds/rss/",            3, "📰"),
    ("The Block",       "https://www.theblock.co/rss.xml",                            3, "🧱"),
    ("CoinTelegraph",   "https://cointelegraph.com/rss",                              2, "📡"),
    ("Decrypt",         "https://decrypt.co/feed",                                    2, "🔓"),
    ("Bitcoin Magazine","https://bitcoinmagazine.com/.rss/full/",                     2, "₿"),
    ("BeInCrypto",      "https://beincrypto.com/feed/",                               2, "🔎"),
    ("NewsBTC",         "https://www.newsbtc.com/feed/",                              2, "📊"),
    ("Bitcoinist",      "https://bitcoinist.com/feed/",                               2, "🟠"),
    ("AMBCrypto",       "https://ambcrypto.com/feed/",                                2, "🔵"),
    ("U.Today",         "https://u.today/rss",                                        2, "📣"),
    ("Kitco",           "https://www.kitco.com/rss/",                                 2, "🥇"),
    ("Reuters Biz",     "https://feeds.reuters.com/reuters/businessNews",             2, "🌐"),
    ("Investing.com",   "https://www.investing.com/rss/news_301.rss",                 2, "📈"),
]

# ══ EMOJIS ═══════════════════════════════════════════════════
COIN_EMOJIS = {
    "btc": "₿", "bitcoin": "₿", "eth": "🔷", "ethereum": "🔷",
    "sol": "◎", "solana": "◎", "bnb": "🟡", "xrp": "💧",
    "ada": "🔵", "doge": "🐶", "avax": "🔺", "link": "⛓️",
    "dot": "🔴", "ltc": "Ł", "zec": "🛡️", "zcash": "🛡️",
    "gold": "🥇", "oro": "🥇", "xau": "🥇",
    "silver": "🥈", "plata": "🥈", "copper": "🟤", "cobre": "🟤",
}

IMPACT_EMOJIS = {
    "crash": "🔴🚨", "plunge": "🔴📉", "hack": "🔴💀",
    "exploit": "🔴💀", "breach": "🔴💀", "ban": "🔴🚫",
    "banned": "🔴🚫", "lawsuit": "🔴⚖️", "bankrupt": "🔴💀",
    "surge": "🟢🚀", "rally": "🟢📈", "ath": "🟢🏆",
    "all-time high": "🟢🏆", "etf": "🏦", "halving": "✂️",
    "whale": "🐋", "blackrock": "🏦", "rate cut": "🏦📉",
}


# ══ ESTADO PERSISTENTE ════════════════════════════════════════

def load_state():
    """Carga estado: IDs enviados + timestamp del ultimo envio."""
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("sent_ids", [])), data.get("last_run_ts")
    except Exception:
        return set(), None


def save_state(sent_ids, last_run_ts):
    """Guarda estado para la proxima ejecucion."""
    ids_list = list(sent_ids)[-MAX_STORED_IDS:]
    with open(STATE_FILE, "w") as f:
        json.dump({"sent_ids": ids_list, "last_run_ts": last_run_ts}, f)
    print("[INFO] Estado guardado: {} IDs, ultimo envio: {}".format(
        len(ids_list), last_run_ts))


# ══ COINGECKO BATCH ══════════════════════════════════════════

def fetch_all_prices():
    """Una sola llamada con todos los activos. Sin rate limiting."""
    unique_ids = list(set(COINGECKO_IDS.values()))
    url = (
        "https://api.coingecko.com/api/v3/simple/price?ids="
        + ",".join(unique_ids)
        + "&vs_currencies=usd&include_24hr_change=true"
    )
    try:
        resp = requests.get(url, timeout=15, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            print("[WARN] CoinGecko HTTP {}.".format(resp.status_code))
            return {}
        result = {}
        for cg_id, values in resp.json().items():
            result[cg_id] = {
                "price":      values.get("usd", 0),
                "change_24h": round(values.get("usd_24h_change", 0), 2),
            }
        print("[INFO] CoinGecko: {} precios en 1 llamada.".format(len(result)))
        return result
    except Exception as e:
        print("[WARN] CoinGecko: {}".format(e))
        return {}


def format_price(price):
    if price >= 1000:   return "${:,.0f}".format(price)
    elif price >= 1:    return "${:,.2f}".format(price)
    else:               return "${:.4f}".format(price)


def format_change(change):
    return "{} {:.2f}%".format("🟢▲" if change >= 0 else "🔴▼", abs(change))


# ══ SCORING Y FILTRADO ════════════════════════════════════════

def news_id(title, url):
    return hashlib.md5((title + url).lower().encode()).hexdigest()[:12]


def is_critical(title):
    """Noticia critica = siempre enviar independiente del score."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in CRITICAL_KEYWORDS)


def score_article(title, summary=""):
    """
    Score de calidad e impacto.
    > 7  = noticia relevante para el mercado
    > 12 = noticia muy importante
    """
    text = (title + " " + summary).lower()
    score = 0

    # Base: activos mencionados (max 4)
    score += min(sum(1 for kw in COIN_KEYWORDS if kw in text), 4)

    # Impacto: keywords de movimiento real (+3 cada una, max 15)
    impact_hits = sum(1 for kw in IMPACT_KEYWORDS if kw in text)
    score += min(impact_hits * 3, 15)

    # Bonus numerico: cantidades grandes = mas relevante
    if re.search(r'\$[\d,]+\s*(billion|trillion)', text): score += 4
    if re.search(r'\$[\d,]+\s*million', text):            score += 2
    if re.search(r'\d+%', text):                          score += 1

    # Penalizacion: ruido / opinion / predicciones (-3 cada una)
    noise_hits = sum(1 for kw in NOISE_KEYWORDS if kw in text)
    score -= noise_hits * 3

    return score


def get_alert_emoji(title):
    tl = title.lower()
    for kw, emoji in IMPACT_EMOJIS.items():
        if kw in tl:
            return emoji
    return "🔔"


def get_coin_emoji(title):
    tl = title.lower()
    for kw, emoji in COIN_EMOJIS.items():
        if kw in tl:
            return emoji
    return ""


def detect_coin(title):
    tl = title.lower()
    for kw, cg_id in COINGECKO_IDS.items():
        if kw in tl:
            return cg_id
    return None


# ══ RSS ══════════════════════════════════════════════════════

def fetch_rss(name, url, weight, emoji, cutoff):
    results = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            try:
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub = datetime.fromtimestamp(
                        calendar.timegm(entry.published_parsed), tz=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub = datetime.fromtimestamp(
                        calendar.timegm(entry.updated_parsed), tz=timezone.utc)
                else:
                    continue
                if pub <= cutoff:   # Estrictamente despues del ultimo envio
                    continue
                title   = getattr(entry, "title",   "").strip()
                link    = getattr(entry, "link",    "").strip()
                summary = getattr(entry, "summary", "")[:400]
                if not title or not link:
                    continue
                score    = score_article(title, summary) + weight
                critical = is_critical(title)
                results.append({
                    "id":       news_id(title, link),
                    "title":    title,
                    "url":      link,
                    "source":   name,
                    "emoji":    emoji,
                    "score":    score,
                    "pub":      pub,
                    "critical": critical,
                })
            except Exception:
                continue
    except Exception as e:
        print("[WARN] RSS {}: {}".format(name, e))
    return results


# ══ TELEGRAM ═════════════════════════════════════════════════

def format_message(item, prices_cache):
    alert  = get_alert_emoji(item["title"])
    coin   = get_coin_emoji(item["title"])
    heat   = "🔥" * min(int(item["score"] / 3), 5)
    label  = "🚨 CRITICO" if item["critical"] else "📊 Impacto"

    price_line = ""
    cg_id = detect_coin(item["title"])
    if cg_id and cg_id in prices_cache:
        p  = format_price(prices_cache[cg_id]["price"])
        ch = format_change(prices_cache[cg_id]["change_24h"])
        price_line = "💰 Precio: <b>{}</b>  {} (24h)\n".format(p, ch)

    return (
        "{} {} <b>{}</b>\n\n"
        "{}"
        "{}: {} (score: {})\n"
        "📰 {} {}\n"
        "🕐 {}\n\n"
        "🔗 <a href=\"{}\">Leer noticia completa →</a>"
    ).format(
        alert, coin, item["title"],
        price_line,
        label, heat, item["score"],
        item["emoji"], item["source"],
        item["pub"].strftime("%H:%M UTC"),
        item["url"]
    )


def send_telegram(message):
    try:
        resp = requests.post(
            "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN),
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=15
        )
        return resp.status_code == 200
    except Exception as e:
        print("[ERROR] Telegram: {}".format(e))
        return False


def send_header(count):
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    send_telegram(
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>CRYPTO INTEL BOT v4</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📬 {} noticia(s) de alto impacto\n"
        "🕐 {}".format(count, now)
    )


# ══ MAIN ════════════════════════════════════════════════════

def main():
    now_ts = datetime.now(timezone.utc)
    print("=" * 55)
    print("  CRYPTO INTEL BOT v4 - " + now_ts.strftime("%Y-%m-%d %H:%M UTC"))
    print("=" * 55)

    # 1. Cargar estado persistente
    sent_ids, last_run_ts = load_state()
    print("[INFO] IDs previos: {} | Ultimo envio: {}".format(
        len(sent_ids), last_run_ts or "primera ejecucion"))

    # 2. Cutoff = timestamp del ultimo envio (o 2h atras si es la primera vez)
    if last_run_ts:
        cutoff = datetime.fromisoformat(last_run_ts)
        print("[INFO] Solo noticias publicadas despues de: {}".format(
            cutoff.strftime("%H:%M UTC")))
    else:
        cutoff = now_ts - timedelta(hours=2)
        print("[INFO] Primera ejecucion — ventana de 2h")

    # 3. Precios en batch (1 llamada)
    prices_cache = fetch_all_prices()

    # 4. RSS
    all_news = []
    for name, url, weight, emoji in RSS_SOURCES:
        print("[INFO] Feed: {}...".format(name), end=" ")
        items = fetch_rss(name, url, weight, emoji, cutoff)
        print("{} arts".format(len(items)))
        all_news.extend(items)

    # 5. Deduplicar (esta ejecucion + historico)
    seen, unique = set(), []
    for item in all_news:
        if item["id"] not in sent_ids and item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)

    print("\n[INFO] Articulos nuevos: {}".format(len(unique)))

    # 6. Filtrar: criticos siempre pasan, el resto necesita score >= MIN_SCORE
    hot = [n for n in unique if n["critical"] or n["score"] >= MIN_SCORE]
    hot.sort(key=lambda x: (x["critical"], x["score"]), reverse=True)
    print("[INFO] Pasan el filtro de calidad: {}".format(len(hot)))

    if not hot:
        print("[INFO] Sin noticias relevantes. Bot silencioso.")
        # Guardar timestamp aunque no se envie nada (evita acumular noticias viejas)
        save_state(sent_ids, now_ts.isoformat())
        return

    # 7. Enviar
    to_send = hot[:MAX_NEWS_PER_RUN]
    print("[INFO] Enviando {}...\n".format(len(to_send)))
    send_header(len(to_send))
    time.sleep(1)

    sent = 0
    for i, item in enumerate(to_send, 1):
        ok = send_telegram(format_message(item, prices_cache))
        tag = "CRITICO" if item["critical"] else "score:{}".format(item["score"])
        print("  [{}] [{}/{}] {} ({})".format(
            "OK" if ok else "FAIL", i, len(to_send),
            item["title"][:55], tag))
        if ok:
            sent += 1
            sent_ids.add(item["id"])
        time.sleep(1.5)

    # 8. Guardar estado con timestamp actual
    save_state(sent_ids, now_ts.isoformat())

    print("\n[DONE] {}/{} noticias enviadas.".format(sent, len(to_send)))
    print("=" * 55)


if __name__ == "__main__":
    main()

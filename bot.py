#!/usr/bin/env python3
"""
Crypto Intel Bot v2 - by Juancho
Mejoras: precio CoinGecko en tiempo real + deduplicacion entre ejecuciones
"""

import os
import re
import time
import hashlib
import calendar
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from typing import Optional

# ══ CONFIGURACION ══════════════════════════════════════════
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

LOOK_BACK_HOURS  = 1.0   # Exactamente 1h -> sin solapamiento entre ejecuciones
MAX_NEWS_PER_RUN = 6
MIN_SCORE        = 4

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
    "gold", "oro", "xau", "xauusd",
    "silver", "plata", "xag", "xagusd",
    "copper", "cobre",
    "coinbase", "kraken", "bybit", "okx",
    "defi", "nft", "web3", "stablecoin", "usdt", "usdc",
    "blackrock", "fidelity", "microstrategy", "grayscale",
]

# ══ IMPACTO ══════════════════════════════════════════════════
IMPACT_KEYWORDS = [
    "surge", "rally", "crash", "plunge", "pump", "dump", "soar",
    "spike", "breakout", "breakdown", "correction", "rebound",
    "all-time high", "ath", "all time high", "record",
    "federal reserve", "fed rate", "interest rate", "inflation",
    "cpi", "recession", "gdp", "quantitative", "fomc", "rate cut",
    "rate hike", "treasury", "dollar index", "dxy",
    "sec", "cftc", "regulation", "ban", "banned", "approve", "approved",
    "etf", "spot etf", "lawsuit", "fine", "sanction", "compliance",
    "legal", "court", "congress", "senate", "bill",
    "blackrock", "fidelity", "grayscale", "microstrategy",
    "institutional", "whale", "billion", "fund", "hedge fund",
    "reserve", "accumulate",
    "halving", "hard fork", "upgrade", "exploit", "hack", "breach",
    "vulnerability", "attack", "stolen", "bug", "emergency",
    "bridge hack", "protocol", "liquidation", "liquidated",
    "launch", "partnership", "integration", "adoption",
    "listed", "delisted", "listing", "mainnet",
    "payment", "merchant", "nation", "country", "government",
    "gold rally", "silver surge", "copper demand",
    "inflation hedge", "safe haven", "commodity",
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
    "btc": "₿", "bitcoin": "₿",
    "eth": "🔷", "ethereum": "🔷",
    "sol": "◎", "solana": "◎",
    "bnb": "🟡", "xrp": "💧", "ripple": "💧",
    "ada": "🔵", "cardano": "🔵",
    "doge": "🐶", "dogecoin": "🐶",
    "avax": "🔺", "avalanche": "🔺",
    "link": "⛓️", "chainlink": "⛓️",
    "dot": "🔴", "polkadot": "🔴",
    "ltc": "Ł", "litecoin": "Ł",
    "zec": "🛡️", "zcash": "🛡️",
    "gold": "🥇", "oro": "🥇", "xau": "🥇",
    "silver": "🥈", "plata": "🥈", "xag": "🥈",
    "copper": "🟤", "cobre": "🟤",
}

IMPACT_EMOJIS = {
    "crash": "🔴🚨", "plunge": "🔴📉", "dump": "🔴📉",
    "hack": "🔴💀", "exploit": "🔴💀", "breach": "🔴💀",
    "ban": "🔴🚫", "banned": "🔴🚫", "lawsuit": "🔴⚖️",
    "surge": "🟢🚀", "rally": "🟢📈", "pump": "🟢📈",
    "ath": "🟢🏆", "all-time high": "🟢🏆", "record": "🟢🏆",
    "etf": "🏦", "halving": "✂️", "whale": "🐋", "blackrock": "🏦",
}


# ══ COINGECKO FUNCIONES ═══════════════════════════════════════

def detect_coin(title):
    title_lower = title.lower()
    for keyword, cg_id in COINGECKO_IDS.items():
        if keyword in title_lower:
            return cg_id
    return None


def get_price(coingecko_id):
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=" + coingecko_id + "&vs_currencies=usd&include_24hr_change=true"
    )
    try:
        resp = requests.get(url, timeout=10, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return None
        data = resp.json()
        if coingecko_id not in data:
            return None
        price  = data[coingecko_id].get("usd", 0)
        change = data[coingecko_id].get("usd_24h_change", 0)
        return {"price": price, "change_24h": round(change, 2)}
    except Exception:
        return None


def format_price(price):
    if price >= 1000:
        return "${:,.0f}".format(price)
    elif price >= 1:
        return "${:,.2f}".format(price)
    else:
        return "${:.4f}".format(price)


def format_change(change):
    arrow = "🟢▲" if change >= 0 else "🔴▼"
    return "{} {:.2f}%".format(arrow, abs(change))


# ══ FUNCIONES PRINCIPALES ════════════════════════════════════

def news_id(title, url):
    raw = (title + url).lower().encode()
    return hashlib.md5(raw).hexdigest()[:12]


def score_article(title, summary=""):
    text = (title + " " + summary).lower()
    score = 0
    coin_hits   = sum(1 for kw in COIN_KEYWORDS if kw in text)
    score += min(coin_hits * 1, 4)
    impact_hits = sum(1 for kw in IMPACT_KEYWORDS if kw in text)
    score += min(impact_hits * 2, 12)
    if re.search(r'\$[\d,]+\s*(billion|trillion|million)', text):
        score += 3
    if re.search(r'\d+%', text):
        score += 1
    return score


def get_alert_emoji(title):
    title_lower = title.lower()
    for kw, emoji in IMPACT_EMOJIS.items():
        if kw in title_lower:
            return emoji
    return "🔔"


def get_coin_emoji(title):
    title_lower = title.lower()
    for kw, emoji in COIN_EMOJIS.items():
        if kw in title_lower:
            return emoji
    return ""


def fetch_rss(name, url, weight, emoji, cutoff):
    results = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            try:
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub = datetime.fromtimestamp(
                        calendar.timegm(entry.published_parsed), tz=timezone.utc
                    )
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub = datetime.fromtimestamp(
                        calendar.timegm(entry.updated_parsed), tz=timezone.utc
                    )
                else:
                    continue
                if pub < cutoff:
                    continue
                title   = getattr(entry, "title",   "").strip()
                link    = getattr(entry, "link",    "").strip()
                summary = getattr(entry, "summary", "")[:300]
                if not title or not link:
                    continue
                score = score_article(title, summary) + weight
                results.append({
                    "id":     news_id(title, link),
                    "title":  title,
                    "url":    link,
                    "source": name,
                    "emoji":  emoji,
                    "score":  score,
                    "pub":    pub,
                })
            except Exception:
                continue
    except Exception as e:
        print("[WARN] RSS error {}: {}".format(name, e))
    return results


def format_telegram_message(item):
    alert_emoji = get_alert_emoji(item["title"])
    coin_emoji  = get_coin_emoji(item["title"])
    pub_str     = item["pub"].strftime("%H:%M UTC")
    heat        = "🔥" * min(int(item["score"] / 3), 5)

    price_line = ""
    cg_id = detect_coin(item["title"])
    if cg_id:
        price_data = get_price(cg_id)
        if price_data:
            p  = format_price(price_data["price"])
            ch = format_change(price_data["change_24h"])
            price_line = "💰 Precio actual: <b>{}</b>  {} (24h)\n".format(p, ch)

    msg = (
        "{} {} <b>{}</b>\n\n"
        "{}"
        "📊 Impacto estimado: {} (score: {})\n"
        "📰 Fuente: {} {}\n"
        "🕐 {}\n\n"
        "🔗 <a href=\"{}\">Leer noticia completa →</a>"
    ).format(
        alert_emoji, coin_emoji, item["title"],
        price_line,
        heat, item["score"],
        item["emoji"], item["source"],
        pub_str,
        item["url"]
    )
    return msg


def send_telegram(message):
    url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            return True
        print("[ERROR] Telegram: {} - {}".format(resp.status_code, resp.text[:200]))
        return False
    except Exception as e:
        print("[ERROR] Telegram request failed: {}".format(e))
        return False


def send_header(count):
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    msg = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>CRYPTO INTEL BOT v2</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📬 {} noticia(s) de alto impacto\n"
        "🕐 Actualización: {}"
    ).format(count, now)
    send_telegram(msg)


# ══ MAIN ════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  CRYPTO INTEL BOT v2 - Iniciando ejecucion")
    print("  " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print("=" * 55)

    cutoff   = datetime.now(timezone.utc) - timedelta(hours=LOOK_BACK_HOURS)
    all_news = []
    seen_ids = set()

    for name, url, weight, emoji in RSS_SOURCES:
        print("[INFO] Feed: {}...".format(name))
        items = fetch_rss(name, url, weight, emoji, cutoff)
        print("       -> {} articulos recientes".format(len(items)))
        all_news.extend(items)

    unique_news = []
    for item in all_news:
        if item["id"] not in seen_ids:
            seen_ids.add(item["id"])
            unique_news.append(item)

    print("\n[INFO] Total articulos unicos: {}".format(len(unique_news)))

    hot_news = [n for n in unique_news if n["score"] >= MIN_SCORE]
    hot_news.sort(key=lambda x: x["score"], reverse=True)
    print("[INFO] Noticias sobre umbral (score>={}): {}".format(MIN_SCORE, len(hot_news)))

    if not hot_news:
        print("[INFO] Sin noticias relevantes. Bot silencioso.")
        return

    to_send = hot_news[:MAX_NEWS_PER_RUN]
    print("[INFO] Enviando {} noticias a Telegram...\n".format(len(to_send)))

    send_header(len(to_send))
    time.sleep(1)

    sent = 0
    for i, item in enumerate(to_send, 1):
        msg = format_telegram_message(item)
        ok  = send_telegram(msg)
        status = "OK" if ok else "FAIL"
        print("  [{}] [{}/{}] {}  (score: {})".format(
            status, i, len(to_send), item["title"][:60], item["score"]
        ))
        if ok:
            sent += 1
        time.sleep(1.5)

    print("\n[DONE] {}/{} noticias enviadas.".format(sent, len(to_send)))
    print("=" * 55)


if __name__ == "__main__":
    main()

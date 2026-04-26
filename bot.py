#!/usr/bin/env python3
"""
Crypto Intel Bot v6 - by Juancho
- 3 capas: Noticias (90%+ fiabilidad) + Mercado Global + Fear & Greed
- Cutoff = timestamp ultimo envio (nunca noticias viejas)
- Filtro de calidad agresivo (MIN_SCORE 7)
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

# ══ CONFIGURACION ══════════════════════════════════════════════
TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID  = os.environ["TELEGRAM_CHAT_ID"]

MIN_SCORE         = 7        # Umbral de calidad (90%+ fuentes)
MAX_NEWS_PER_RUN  = 5        # Maximo noticias por hora
STATE_FILE        = "bot_state.json"
MAX_STORED_IDS    = 500

# ══ COINGECKO IDs ══════════════════════════════════════════════
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

# ══ ACTIVOS ═════════════════════════════════════════════════════
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

# ══ KEYWORDS DE ALTO IMPACTO (+3 cada una) ═════════════════════
IMPACT_KEYWORDS = [
    "surge", "rally", "crash", "plunge", "soar", "spike",
    "all-time high", "ath", "all time high", "breakout", "breakdown",
    "liquidation", "liquidated",
    "federal reserve", "fed rate", "fomc", "rate cut", "rate hike",
    "inflation", "cpi", "recession",
    "sec", "cftc", "ban", "banned", "approved", "etf", "spot etf",
    "lawsuit", "sanction", "congress", "senate",
    "blackrock", "fidelity", "microstrategy", "grayscale",
    "whale", "institutional",
    "hack", "exploit", "breach", "stolen", "vulnerability", "attack",
    "halving", "hard fork",
    "listed on coinbase", "listed on binance", "mainnet launch",
    "government", "nation", "country",
    "gold rally", "silver surge", "safe haven", "inflation hedge",
]

# ══ KEYWORDS CRITICOS — garantizan envio ═══════════════════════
CRITICAL_KEYWORDS = [
    "hack", "hacked", "exploit", "exploited", "stolen", "breach",
    "ban", "banned", "sec charges", "sec sues", "arrest", "arrested",
    "bankrupt", "bankruptcy", "insolvent", "collapse", "collapsed",
    "all-time high", "ath", "rate cut", "rate hike",
    "spot etf approved", "etf approved", "etf rejected",
    "listed on coinbase", "listed on binance",
    "emergency", "halving",
]

# ══ PENALIZACIONES — reducen score ═════════════════════════════
NOISE_KEYWORDS = [
    "price prediction", "could reach", "might hit", "could hit",
    "analysts say", "expert says", "here's why", "why bitcoin",
    "top 5", "top 10", "best crypto", "should you buy",
    "is it too late", "bull run incoming", "to the moon",
    "price analysis", "technical analysis", "ta:", "weekly recap",
    "weekly roundup", "this week in", "daily recap",
]

# ══ RSS SOURCES — Fiabilidad 90%+ ══════════════════════════════
RSS_SOURCES = [
    ("CoinDesk",         "https://www.coindesk.com/arc/outboundfeeds/rss/",           3, "📰"),
    ("The Block",        "https://www.theblock.co/rss.xml",                           3, "🧱"),
    ("Decrypt",          "https://decrypt.co/feed",                                   2, "🔓"),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews",            3, "🌐"),
    ("WSJ Markets",      "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",             3, "📊"),
    ("Kitco News",       "https://www.kitco.com/rss/",                                2, "🥇"),
    ("Federal Reserve",  "https://www.federalreserve.gov/feeds/press_all.xml",        3, "🏦"),
    ("SEC Releases",     "https://www.sec.gov/rss/litigation/litreleases.xml",        3, "⚖️"),
]

# ══ EMOJIS ══════════════════════════════════════════════════════
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


# ══ ESTADO PERSISTENTE ══════════════════════════════════════════

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("sent_ids", [])), data.get("last_run_ts")
    except Exception:
        return set(), None


def save_state(sent_ids, last_run_ts):
    ids_list = list(sent_ids)[-MAX_STORED_IDS:]
    with open(STATE_FILE, "w") as f:
        json.dump({"sent_ids": ids_list, "last_run_ts": last_run_ts}, f)
    print("[INFO] Estado guardado: {} IDs, ultimo envio: {}".format(
        len(ids_list), last_run_ts))


# ══ CAPA 1: COINGECKO PRECIOS ═══════════════════════════════════

def fetch_all_prices():
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


# ══ CAPA 2: MERCADO GLOBAL (CoinGecko /global) ══════════════════

def fetch_global_market():
    """Dominancia BTC, market cap total y variacion 24h. 100% gratuito."""
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/global",
            timeout=10, headers={"Accept": "application/json"}
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", {})
        btc_dom  = round(data.get("market_cap_percentage", {}).get("btc", 0), 1)
        eth_dom  = round(data.get("market_cap_percentage", {}).get("eth", 0), 1)
        mcap     = data.get("total_market_cap", {}).get("usd", 0)
        mcap_chg = round(data.get("market_cap_change_percentage_24h_usd", 0), 2)
        return {
            "btc_dominance": btc_dom,
            "eth_dominance": eth_dom,
            "market_cap_usd": mcap,
            "market_cap_change_24h": mcap_chg,
        }
    except Exception as e:
        print("[WARN] Global market: {}".format(e))
        return None


def format_global_market(gm):
    """Formatea datos globales con señal de contexto."""
    if not gm:
        return ""
    chg   = gm["market_cap_change_24h"]
    arrow = "🟢▲" if chg >= 0 else "🔴▼"
    mcap_t = "${:.2f}T".format(gm["market_cap_usd"] / 1_000_000_000_000) \
             if gm["market_cap_usd"] >= 1e12 \
             else "${:.0f}B".format(gm["market_cap_usd"] / 1_000_000_000)

    # Señal de dominancia BTC
    if gm["btc_dominance"] >= 60:
        dom_signal = "⚠️ Altseason improbable"
    elif gm["btc_dominance"] <= 45:
        dom_signal = "⚡ Posible altseason"
    else:
        dom_signal = "Mercado equilibrado"

    return (
        "🌍 Mercado: {} {} ({} 24h) | BTC Dom: {}% {} | ETH: {}%\n"
    ).format(mcap_t, arrow, chg, gm["btc_dominance"], dom_signal, gm["eth_dominance"])


# ══ CAPA 3: FEAR & GREED INDEX ══════════════════════════════════

def fetch_fear_greed():
    """Fear & Greed Index — API 100% gratuita, sin key requerida."""
    try:
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=1",
            timeout=10, headers={"Accept": "application/json"}
        )
        if resp.status_code != 200:
            return None
        data = resp.json()["data"][0]
        return {
            "value": int(data["value"]),
            "label": data["value_classification"],
        }
    except Exception as e:
        print("[WARN] Fear & Greed: {}".format(e))
        return None


def format_fear_greed(fg):
    """Formatea F&G con emoji y señal de trading."""
    if not fg:
        return ""
    v = fg["value"]
    label = fg["label"]
    if v <= 24:
        emoji  = "😱"
        signal = "⚡ Zona historica de compra"
    elif v <= 44:
        emoji  = "😨"
        signal = "⚠️ Mercado temeroso"
    elif v <= 54:
        emoji  = "😐"
        signal = "Neutral"
    elif v <= 74:
        emoji  = "😏"
        signal = "⚠️ Codicia moderada"
    else:
        emoji  = "🤑"
        signal = "🚨 Zona historica de venta"
    return "{} F&amp;G: {}/100 — {} | {}\n".format(emoji, v, label, signal)


# ══ SCORING Y FILTRADO ══════════════════════════════════════════

def news_id(title, url):
    return hashlib.md5((title + url).lower().encode()).hexdigest()[:12]


def is_critical(title):
    title_lower = title.lower()
    return any(kw in title_lower for kw in CRITICAL_KEYWORDS)


def score_article(title, summary=""):
    text  = (title + " " + summary).lower()
    score = 0
    score += min(sum(1 for kw in COIN_KEYWORDS if kw in text), 4)
    impact_hits = sum(1 for kw in IMPACT_KEYWORDS if kw in text)
    score += min(impact_hits * 3, 15)
    if re.search(r'\$[\d,]+\s*(billion|trillion)', text): score += 4
    if re.search(r'\$[\d,]+\s*million', text):            score += 2
    if re.search(r'\d+%', text):                          score += 1
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


def get_coin_symbol(cg_id):
    """Devuelve el ticker corto de un CoinGecko ID."""
    reverse = {v: k for k, v in COINGECKO_IDS.items() if len(k) <= 4}
    return reverse.get(cg_id, "").upper()


# ══ RSS ═════════════════════════════════════════════════════════

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
                if pub <= cutoff:
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


# ══ TELEGRAM ════════════════════════════════════════════════════

def format_message(item, prices_cache, fg=None, gm=None):
    alert = get_alert_emoji(item["title"])
    coin  = get_coin_emoji(item["title"])
    heat  = "🔥" * min(int(item["score"] / 3), 5)
    label = "🚨 CRITICO" if item["critical"] else "📊 Impacto"

    # Precio
    price_line   = ""
    coin_symbol  = None
    cg_id = detect_coin(item["title"])
    if cg_id and cg_id in prices_cache:
        p  = format_price(prices_cache[cg_id]["price"])
        ch = format_change(prices_cache[cg_id]["change_24h"])
        price_line  = "💰 Precio: <b>{}</b>  {} (24h)\n".format(p, ch)
        coin_symbol = get_coin_symbol(cg_id)

    # Fear & Greed
    fg_line = format_fear_greed(fg) if fg else ""

    # Mercado global
    gm_line = format_global_market(gm) if gm else ""

    return (
        "{} {} <b>{}</b>\n\n"
        "{}"
        "{}"
        "{}"
        "{}: {} (score: {})\n"
        "📰 {} {}\n"
        "🕐 {}\n\n"
        "🔗 <a href=\"{}\">Leer noticia completa →</a>"
    ).format(
        alert, coin, item["title"],
        price_line,
        fg_line,
        gm_line,
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


def send_header(count, fg=None, gm=None):
    now    = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    fg_str = ("\n" + format_fear_greed(fg).rstrip("\n")) if fg else ""
    gm_str = ("\n" + format_global_market(gm).rstrip("\n")) if gm else ""
    send_telegram(
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>CRYPTO INTEL BOT v6</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📬 {} noticia(s) de alto impacto{}{}\n"
        "🕐 {}".format(count, fg_str, gm_str, now)
    )



# ══ MAIN ════════════════════════════════════════════════════════

def main():
    now_ts = datetime.now(timezone.utc)
    print("=" * 55)
    print("  CRYPTO INTEL BOT v6 - " + now_ts.strftime("%Y-%m-%d %H:%M UTC"))
    print("=" * 55)

    # 1. Estado persistente
    sent_ids, last_run_ts = load_state()
    print("[INFO] IDs previos: {} | Ultimo envio: {}".format(
        len(sent_ids), last_run_ts or "primera ejecucion"))

    # 2. Cutoff
    if last_run_ts:
        cutoff = datetime.fromisoformat(last_run_ts)
        print("[INFO] Solo noticias despues de: {}".format(
            cutoff.strftime("%H:%M UTC")))
    else:
        cutoff = now_ts - timedelta(hours=2)
        print("[INFO] Primera ejecucion — ventana de 2h")

    # 3. CAPA 1: Precios CoinGecko (batch)
    prices_cache = fetch_all_prices()

    # 4. CAPA 2: Mercado global (BTC dominance, market cap)
    gm = fetch_global_market()
    if gm:
        print("[INFO] Mercado global: BTC Dom {}% | Cap {}".format(
            gm["btc_dominance"],
            "${:.2f}T".format(gm["market_cap_usd"] / 1e12)))

    # 5. CAPA 3: Fear & Greed Index
    fg = fetch_fear_greed()
    if fg:
        print("[INFO] Fear & Greed: {}/100 — {}".format(fg["value"], fg["label"]))

    # 6. RSS feeds
    all_news = []
    for name, url, weight, emoji in RSS_SOURCES:
        print("[INFO] Feed: {}...".format(name), end=" ")
        items = fetch_rss(name, url, weight, emoji, cutoff)
        print("{} arts".format(len(items)))
        all_news.extend(items)

    # 7. Deduplicar
    seen, unique = set(), []
    for item in all_news:
        if item["id"] not in sent_ids and item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)

    print("\n[INFO] Articulos nuevos: {}".format(len(unique)))

    # 8. Filtrar por calidad
    hot = [n for n in unique if n["critical"] or n["score"] >= MIN_SCORE]
    hot.sort(key=lambda x: (x["critical"], x["score"]), reverse=True)
    print("[INFO] Pasan el filtro: {}".format(len(hot)))

    # 9. Sin noticias — bot silencioso
    if not hot:
        print("[INFO] Sin noticias relevantes. Bot silencioso.")
        save_state(sent_ids, now_ts.isoformat())
        return

    # 10. Enviar noticias con contexto de las 3 capas
    to_send = hot[:MAX_NEWS_PER_RUN]
    print("[INFO] Enviando {}...\n".format(len(to_send)))
    send_header(len(to_send), fg, gm)
    time.sleep(1)

    sent = 0
    for i, item in enumerate(to_send, 1):
        ok  = send_telegram(format_message(item, prices_cache, fg, gm))
        tag = "CRITICO" if item["critical"] else "score:{}".format(item["score"])
        print("  [{}] [{}/{}] {} ({})".format(
            "OK" if ok else "FAIL", i, len(to_send),
            item["title"][:55], tag))
        if ok:
            sent += 1
            sent_ids.add(item["id"])
        time.sleep(1.5)

    # 11. Guardar estado
    save_state(sent_ids, now_ts.isoformat())
    print("\n[DONE] {}/{} noticias enviadas.".format(sent, len(to_send)))
    print("=" * 55)


if __name__ == "__main__":
    main()

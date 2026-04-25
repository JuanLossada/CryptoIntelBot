#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║        CRYPTO & MARKETS INTEL BOT  –  by Juancho        ║
║  Fuentes: CoinDesk · CoinTelegraph · The Block · más    ║
║  Activos: Top-20 Altcoins · Zcash · Oro · Plata · Cobre ║
╚══════════════════════════════════════════════════════════╝

Ejecuta cada hora vía GitHub Actions.
Envía SOLO noticias con alto potencial de impacto en precio.
100% RSS — sin APIs de pago requeridas.
"""

import os
import sys
import json
import time
import hashlib
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from typing import Optional

# ══════════════════════════════════════════════════════════
#  CONFIGURACIÓN  (variables de entorno / GitHub Secrets)
# ══════════════════════════════════════════════════════════

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

LOOK_BACK_HOURS  = 1.5   # Ventana de tiempo hacia atrás (horas)
MAX_NEWS_PER_RUN = 6     # Máximo de noticias por ejecución (evitar spam)
MIN_SCORE        = 4     # Puntuación mínima para enviar una noticia

# ══════════════════════════════════════════════════════════
#  ACTIVOS A RASTREAR
# ══════════════════════════════════════════════════════════

COIN_KEYWORDS = [
    # ── Top 20 por market cap ──────────────────────────────
    "bitcoin", "btc",
    "ethereum", "eth",
    "bnb", "binance coin",
    "xrp", "ripple",
    "solana", "sol",
    "cardano", "ada",
    "dogecoin", "doge",
    "tron", "trx",
    "avalanche", "avax",
    "polkadot", "dot",
    "chainlink", "link",
    "polygon", "matic", "pol",
    "litecoin", "ltc",
    "uniswap", "uni",
    "cosmos", "atom",
    "stellar", "xlm",
    "filecoin", "fil",
    "algorand", "algo",
    "ethereum classic", "etc",
    # ── Solicitados por Juancho ────────────────────────────
    "zcash", "zec",
    "gold", "oro", "xau", "xauusd",
    "silver", "plata", "xag", "xagusd",
    "copper", "cobre",
    # ── Exchanges & ecosistema ─────────────────────────────
    "coinbase", "kraken", "bybit", "okx",
    "defi", "nft", "web3", "stablecoin", "usdt", "usdc",
    "blackrock", "fidelity", "microstrategy", "grayscale",
]

# ══════════════════════════════════════════════════════════
#  PALABRAS CLAVE DE ALTO IMPACTO  (cada match = +2 puntos)
# ══════════════════════════════════════════════════════════

IMPACT_KEYWORDS = [
    # Movimiento de precio
    "surge", "rally", "crash", "plunge", "pump", "dump", "soar",
    "spike", "breakout", "breakdown", "correction", "rebound",
    "all-time high", "ath", "all time high", "record",
    # Macro / Economía global
    "federal reserve", "fed rate", "interest rate", "inflation",
    "cpi", "recession", "gdp", "quantitative", "fomc", "rate cut",
    "rate hike", "treasury", "dollar index", "dxy",
    # Regulación
    "sec", "cftc", "regulation", "ban", "banned", "approve", "approved",
    "etf", "spot etf", "lawsuit", "fine", "sanction", "compliance",
    "legal", "court", "congress", "senate", "bill",
    # Institucional / Ballenas
    "blackrock", "fidelity", "grayscale", "microstrategy",
    "institutional", "whale", "billion", "fund", "hedge fund",
    "reserve", "treasury buy", "accumulate",
    # Eventos técnicos críticos
    "halving", "hard fork", "upgrade", "exploit", "hack", "breach",
    "vulnerability", "attack", "stolen", "bug", "emergency",
    "bridge hack", "protocol", "liquidation", "liquidated",
    # Adopción / Listados
    "launch", "partnership", "integration", "adoption",
    "listed", "delisted", "listing", "mainnet",
    "payment", "merchant", "nation", "country", "government",
    # Metales / Commodities
    "gold rally", "silver surge", "copper demand",
    "inflation hedge", "safe haven", "commodity",
]

# ══════════════════════════════════════════════════════════
#  FUENTES RSS  (nombre, url, peso_base, emoji)
# ══════════════════════════════════════════════════════════

RSS_SOURCES = [
    # ── Peso 3: fuentes premium, alta fiabilidad ───────────
    ("CoinDesk",        "https://www.coindesk.com/arc/outboundfeeds/rss/",            3, "📰"),
    ("The Block",       "https://www.theblock.co/rss.xml",                            3, "🧱"),
    # ── Peso 2: volumen alto, buena cobertura ─────────────
    ("CoinTelegraph",   "https://cointelegraph.com/rss",                              2, "📡"),
    ("Decrypt",         "https://decrypt.co/feed",                                    2, "🔓"),
    ("Bitcoin Magazine","https://bitcoinmagazine.com/.rss/full/",                     2, "₿"),
    ("BeInCrypto",      "https://beincrypto.com/feed/",                               2, "🔎"),
    ("NewsBTC",         "https://www.newsbtc.com/feed/",                              2, "📊"),
    ("Bitcoinist",      "https://bitcoinist.com/feed/",                               2, "🟠"),
    ("AMBCrypto",       "https://ambcrypto.com/feed/",                                2, "🔵"),
    ("U.Today",         "https://u.today/rss",                                        2, "📣"),
    # ── Peso 2: metales y macro ───────────────────────────
    ("Kitco",           "https://www.kitco.com/rss/",                                 2, "🥇"),
    ("Reuters Biz",     "https://feeds.reuters.com/reuters/businessNews",             2, "🌐"),
    ("Investing.com",   "https://www.investing.com/rss/news_301.rss",                 2, "📈"),
]

# ══════════════════════════════════════════════════════════
#  EMOJIS  para formato Telegram
# ══════════════════════════════════════════════════════════

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
    "etf": "🏦", "halving": "✂️",
    "whale": "🐋", "blackrock": "🏦",
}


# ══════════════════════════════════════════════════════════
#  FUNCIONES PRINCIPALES
# ══════════════════════════════════════════════════════════

def news_id(title: str, url: str) -> str:
    """Hash único para deduplicar noticias."""
    raw = (title + url).lower().encode()
    return hashlib.md5(raw).hexdigest()[:12]


def score_article(title: str, summary: str = "") -> int:
    """
    Puntúa una noticia por relevancia e impacto potencial.
    Returns: int (0-30+). Se envía si score >= MIN_SCORE.
    """
    text = (title + " " + summary).lower()
    score = 0

    # +1 por cada cripto/activo mencionado (max 4)
    coin_hits = sum(1 for kw in COIN_KEYWORDS if kw in text)
    score += min(coin_hits * 1, 4)

    # +2 por cada keyword de impacto (max 12)
    impact_hits = sum(1 for kw in IMPACT_KEYWORDS if kw in text)
    score += min(impact_hits * 2, 12)

    # Bonus: número grande mencionado (billones = muy relevante)
    import re
    if re.search(r'\$[\d,]+\s*(billion|trillion|million)', text):
        score += 3
    if re.search(r'\d+%', text):
        score += 1

    return score


def get_alert_emoji(title: str) -> str:
    """Devuelve emoji de alerta según el tipo de noticia."""
    title_lower = title.lower()
    for kw, emoji in IMPACT_EMOJIS.items():
        if kw in title_lower:
            return emoji
    return "🔔"


def get_coin_emoji(title: str) -> str:
    """Detecta el activo principal y devuelve su emoji."""
    title_lower = title.lower()
    for kw, emoji in COIN_EMOJIS.items():
        if kw in title_lower:
            return emoji
    return ""


def fetch_rss(name: str, url: str, weight: int, emoji: str, cutoff: datetime) -> list[dict]:
    """Obtiene y filtra artículos de un feed RSS."""
    results = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            try:
                # Parsear fecha de publicación
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    import calendar
                    pub = datetime.fromtimestamp(
                        calendar.timegm(entry.published_parsed), tz=timezone.utc
                    )
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    import calendar
                    pub = datetime.fromtimestamp(
                        calendar.timegm(entry.updated_parsed), tz=timezone.utc
                    )
                else:
                    continue  # Sin fecha, omitir

                if pub < cutoff:
                    continue

                title   = getattr(entry, "title", "").strip()
                link    = getattr(entry, "link",  "").strip()
                summary = getattr(entry, "summary", "")[:300]

                if not title or not link:
                    continue

                score = score_article(title, summary) + weight  # peso base de la fuente

                results.append({
                    "id":      news_id(title, link),
                    "title":   title,
                    "url":     link,
                    "source":  name,
                    "emoji":   emoji,
                    "score":   score,
                    "pub":     pub,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"[WARN] RSS error {name}: {e}")
    return results


def format_telegram_message(item: dict) -> str:
    """
    Formatea la noticia para Telegram con HTML.
    Límite de Telegram: 4096 chars por mensaje.
    """
    alert_emoji = get_alert_emoji(item["title"])
    coin_emoji  = get_coin_emoji(item["title"])
    now_str     = item["pub"].strftime("%H:%M UTC")

    # Línea de score → barras de calor
    heat = "🔥" * min(int(item["score"] / 3), 5)

    msg = (
        f"{alert_emoji} {coin_emoji} <b>{item['title']}</b>\n\n"
        f"📊 Impacto estimado: {heat} (score: {item['score']})\n"
        f"📰 Fuente: {item['emoji']} {item['source']}\n"
        f"🕐 {now_str}\n\n"
        f"🔗 <a href=\"{item['url']}\">Leer noticia completa →</a>"
    )
    return msg


def send_telegram(message: str) -> bool:
    """Envía un mensaje al bot de Telegram. Retorna True si éxito."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
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
        else:
            print(f"[ERROR] Telegram: {resp.status_code} – {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"[ERROR] Telegram request failed: {e}")
        return False


def send_header(count: int):
    """Envía encabezado cuando hay noticias nuevas."""
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    msg = (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>CRYPTO INTEL BOT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📬 {count} noticia(s) de alto impacto\n"
        f"🕐 Actualización: {now}"
    )
    send_telegram(msg)


def send_no_news():
    """Envía aviso silencioso si no hay noticias relevantes (solo en modo verbose)."""
    # Comentar si no quieres mensajes cuando no hay noticias
    pass


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  CRYPTO INTEL BOT – Iniciando ejecución")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 55)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOK_BACK_HOURS)
    all_news: list[dict] = []
    seen_ids: set[str]   = set()

    # ── RSS Feeds (13 fuentes gratuitas) ──────────────────
    for name, url, weight, emoji in RSS_SOURCES:
        print(f"[INFO] Feed: {name}...")
        items = fetch_rss(name, url, weight, emoji, cutoff)
        print(f"       → {len(items)} artículos recientes")
        all_news.extend(items)

    # ── 3. Deduplicar ─────────────────────────────────────
    unique_news = []
    for item in all_news:
        if item["id"] not in seen_ids:
            seen_ids.add(item["id"])
            unique_news.append(item)

    print(f"\n[INFO] Total artículos únicos: {len(unique_news)}")

    # ── 4. Filtrar por score mínimo ───────────────────────
    hot_news = [n for n in unique_news if n["score"] >= MIN_SCORE]
    hot_news.sort(key=lambda x: x["score"], reverse=True)

    print(f"[INFO] Noticias sobre umbral (score≥{MIN_SCORE}): {len(hot_news)}")

    if not hot_news:
        print("[INFO] Sin noticias relevantes en esta hora. Bot silencioso.")
        send_no_news()
        return

    # ── 5. Limitar y enviar ───────────────────────────────
    to_send = hot_news[:MAX_NEWS_PER_RUN]
    print(f"[INFO] Enviando {len(to_send)} noticias a Telegram...\n")

    send_header(len(to_send))
    time.sleep(1)

    sent = 0
    for i, item in enumerate(to_send, 1):
        msg = format_telegram_message(item)
        ok  = send_telegram(msg)
        status = "✅" if ok else "❌"
        print(f"  {status} [{i}/{len(to_send)}] {item['title'][:70]}  (score: {item['score']})")
        if ok:
            sent += 1
        time.sleep(1.2)  # Rate limit de Telegram: máx 30 msg/seg

    print(f"\n[DONE] {sent}/{len(to_send)} noticias enviadas correctamente.")
    print("=" * 55)


if __name__ == "__main__":
    main()

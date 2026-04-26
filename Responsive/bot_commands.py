#!/usr/bin/env python3
"""
Crypto Intel Bot — Responsive Module v1.0
==========================================
Real-time Telegram command handler.
Runs 24/7 on Railway.app via long polling.

Complements the Automatic module (GitHub Actions) which handles
scheduled news delivery. This module handles instant user commands.

Commands:
  /start   - Welcome message
  /ayuda   - Full command reference
  /precio  - Live price for any supported coin
  /mercado - Global market context (F&G + dominance + market cap)
  /resumen - Full market summary with top asset prices
  /status  - Service health and uptime

Architecture:
  Automatic/ (GitHub Actions, hourly) → pushes news to Telegram group
  Responsive/ (Railway, 24/7)         → listens & responds to commands

Author : Juancho
Version: 1.0
"""

import os
import logging
from datetime import datetime, timezone

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ══ LOGGING ════════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ══ CONFIG ═════════════════════════════════════════════════════════════════════
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
COINGECKO_API_KEY  = os.environ.get("COINGECKO_API_KEY", "")
BOT_VERSION        = "v1.0"
START_TIME         = datetime.now(timezone.utc)

# Request timeout for all external APIs (seconds)
API_TIMEOUT = 10

# ══ COIN MAPPING ═══════════════════════════════════════════════════════════════
# Maps user input (ticker or name) → CoinGecko ID
COIN_MAP: dict[str, str] = {
    "btc":               "bitcoin",
    "bitcoin":           "bitcoin",
    "eth":               "ethereum",
    "ethereum":          "ethereum",
    "bnb":               "binancecoin",
    "binance":           "binancecoin",
    "xrp":               "ripple",
    "ripple":            "ripple",
    "sol":               "solana",
    "solana":            "solana",
    "ada":               "cardano",
    "cardano":           "cardano",
    "doge":              "dogecoin",
    "dogecoin":          "dogecoin",
    "trx":               "tron",
    "tron":              "tron",
    "avax":              "avalanche-2",
    "avalanche":         "avalanche-2",
    "dot":               "polkadot",
    "polkadot":          "polkadot",
    "link":              "chainlink",
    "chainlink":         "chainlink",
    "matic":             "matic-network",
    "polygon":           "matic-network",
    "ltc":               "litecoin",
    "litecoin":          "litecoin",
    "uni":               "uniswap",
    "uniswap":           "uniswap",
    "atom":              "cosmos",
    "cosmos":            "cosmos",
    "xlm":               "stellar",
    "stellar":           "stellar",
    "fil":               "filecoin",
    "filecoin":          "filecoin",
    "algo":              "algorand",
    "algorand":          "algorand",
    "etc":               "ethereum-classic",
    "ethereum-classic":  "ethereum-classic",
    "zec":               "zcash",
    "zcash":             "zcash",
}

COIN_EMOJIS: dict[str, str] = {
    "bitcoin":           "₿",
    "ethereum":          "🔷",
    "binancecoin":       "🟡",
    "ripple":            "💧",
    "solana":            "◎",
    "cardano":           "🔵",
    "dogecoin":          "🐶",
    "tron":              "🔴",
    "avalanche-2":       "🔺",
    "polkadot":          "🟣",
    "chainlink":         "⛓️",
    "matic-network":     "🟪",
    "litecoin":          "Ł",
    "uniswap":           "🦄",
    "cosmos":            "⚛️",
    "stellar":           "⭐",
    "filecoin":          "📁",
    "algorand":          "🔵",
    "ethereum-classic":  "💚",
    "zcash":             "🛡️",
}

# Assets shown in /resumen (ordered by relevance)
DAILY_ASSETS: list[tuple[str, str]] = [
    ("bitcoin",     "₿  BTC"),
    ("ethereum",    "🔷 ETH"),
    ("ripple",      "💧 XRP"),
    ("solana",      "◎  SOL"),
    ("binancecoin", "🟡 BNB"),
    ("zcash",       "🛡️  ZEC"),
]

SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━"


# ══ API LAYER ══════════════════════════════════════════════════════════════════

def fetch_price(coin_id: str) -> dict | None:
    """Fetch current USD price + 24h change for a single coin."""
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids":                coin_id,
                "vs_currencies":      "usd",
                "include_24hr_change": "true",
            },
            headers={
                "Accept":             "application/json",
                "x-cg-demo-api-key":  COINGECKO_API_KEY,
            },
            timeout=API_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("CoinGecko /price HTTP %s", resp.status_code)
            return None
        raw = resp.json().get(coin_id, {})
        return {
            "price":      raw.get("usd", 0),
            "change_24h": round(raw.get("usd_24h_change", 0), 2),
        }
    except Exception as exc:
        logger.warning("fetch_price(%s): %s", coin_id, exc)
        return None


def fetch_prices_batch(ids: list[str]) -> dict[str, dict]:
    """Fetch prices for multiple coins in a single API call."""
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids":                ",".join(ids),
                "vs_currencies":      "usd",
                "include_24hr_change": "true",
            },
            headers={
                "Accept":             "application/json",
                "x-cg-demo-api-key":  COINGECKO_API_KEY,
            },
            timeout=API_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("CoinGecko /price batch HTTP %s", resp.status_code)
            return {}
        result: dict[str, dict] = {}
        for cg_id, values in resp.json().items():
            result[cg_id] = {
                "price":      values.get("usd", 0),
                "change_24h": round(values.get("usd_24h_change", 0), 2),
            }
        return result
    except Exception as exc:
        logger.warning("fetch_prices_batch: %s", exc)
        return {}


def fetch_global_market() -> dict | None:
    """Fetch BTC/ETH dominance and total market cap from CoinGecko /global."""
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/global",
            headers={"Accept": "application/json"},
            timeout=API_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("CoinGecko /global HTTP %s", resp.status_code)
            return None
        data = resp.json().get("data", {})
        return {
            "btc_dominance":     round(data.get("market_cap_percentage", {}).get("btc", 0), 1),
            "eth_dominance":     round(data.get("market_cap_percentage", {}).get("eth", 0), 1),
            "market_cap_usd":    data.get("total_market_cap", {}).get("usd", 0),
            "market_cap_change": round(data.get("market_cap_change_percentage_24h_usd", 0), 2),
        }
    except Exception as exc:
        logger.warning("fetch_global_market: %s", exc)
        return None


def fetch_fear_greed() -> dict | None:
    """Fetch Fear & Greed Index from alternative.me (free, no key required)."""
    try:
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=1",
            headers={"Accept": "application/json"},
            timeout=API_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("Fear & Greed HTTP %s", resp.status_code)
            return None
        entry = resp.json()["data"][0]
        return {
            "value": int(entry["value"]),
            "label": entry["value_classification"],
        }
    except Exception as exc:
        logger.warning("fetch_fear_greed: %s", exc)
        return None


# ══ FORMATTERS ═════════════════════════════════════════════════════════════════

def fmt_price(price: float) -> str:
    if price >= 1000:  return f"${price:,.0f}"
    elif price >= 1:   return f"${price:,.2f}"
    else:              return f"${price:.4f}"


def fmt_change(change: float) -> str:
    icon = "🟢▲" if change >= 0 else "🔴▼"
    return f"{icon} {abs(change):.2f}%"


def fmt_fear_greed(fg: dict) -> str:
    v = fg["value"]
    if v <= 24:   emoji, signal = "😱", "Miedo Extremo — zona histórica de compra"
    elif v <= 44: emoji, signal = "😨", "Miedo — mercado temeroso"
    elif v <= 54: emoji, signal = "😐", "Neutral"
    elif v <= 74: emoji, signal = "😏", "Codicia moderada"
    else:         emoji, signal = "🤑", "Codicia Extrema — zona histórica de venta"
    return f"{emoji} <b>Fear &amp; Greed:</b> {v}/100 — {signal}"


def fmt_global(gm: dict) -> str:
    chg   = gm["market_cap_change"]
    arrow = "🟢▲" if chg >= 0 else "🔴▼"
    mcap  = (
        f"${gm['market_cap_usd'] / 1e12:.2f}T"
        if gm["market_cap_usd"] >= 1e12
        else f"${gm['market_cap_usd'] / 1e9:.0f}B"
    )
    dom_signal = (
        "⚠️ Altseason improbable" if gm["btc_dominance"] >= 60 else
        "⚡ Posible altseason"    if gm["btc_dominance"] <= 45 else
        "Mercado equilibrado"
    )
    return (
        f"🌍 <b>Market Cap:</b> {mcap} {arrow} {chg:+.2f}% (24h)\n"
        f"📊 <b>BTC Dom:</b> {gm['btc_dominance']}% — {dom_signal}\n"
        f"📊 <b>ETH Dom:</b> {gm['eth_dominance']}%"
    )


def fmt_confluence(fg: dict | None, gm: dict | None) -> str:
    """
    Score-based market confluence reading.
    Combines Fear & Greed + market cap 24h change into a directional signal.
    Not a trading recommendation — objective data synthesis only.
    """
    if not fg and not gm:
        return ""

    bullish = bearish = 0

    if fg:
        v = fg["value"]
        if v <= 24:   bullish += 2
        elif v <= 44: bullish += 1
        elif v >= 75: bearish += 2
        elif v >= 55: bearish += 1

    if gm:
        chg = gm["market_cap_change"]
        if chg <= -3:   bearish += 2
        elif chg <= -1: bearish += 1
        elif chg >= 3:  bullish += 2
        elif chg >= 1:  bullish += 1

    net = bullish - bearish

    if net >= 3:    reading = "⚡ Confluencia alcista — señales favorables"
    elif net >= 1:  reading = "🟡 Sesgo alcista leve — datos mixtos"
    elif net == 0:  reading = "😐 Señales neutrales — sin dirección clara"
    elif net >= -2: reading = "⚠️ Sesgo bajista leve — datos mixtos"
    else:           reading = "🔴 Confluencia bajista — considerar cautela"

    return f"📡 <b>Lectura de mercado:</b> {reading}"


# ══ COMMAND HANDLERS ═══════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"{SEPARATOR}\n"
        "🤖 <b>CRYPTO INTEL BOT v7</b>\n"
        f"{SEPARATOR}\n\n"
        "Hola! Soy tu asistente de inteligencia de mercado crypto.\n\n"
        "📰 Las noticias de alto impacto llegan automáticamente cada hora.\n"
        "📊 El resumen diario se envía a las 08:00 UTC.\n\n"
        "Usa /ayuda para ver todos los comandos disponibles.",
        parse_mode="HTML",
    )
    logger.info("cmd_start: user=%s", update.effective_user.id)


async def cmd_ayuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    coins_list = (
        "BTC · ETH · XRP · SOL · BNB · ADA · DOGE · TRX · "
        "AVAX · DOT · LINK · MATIC · LTC · UNI · ATOM · XLM · "
        "FIL · ALGO · ETC · ZEC"
    )
    await update.message.reply_text(
        f"{SEPARATOR}\n"
        "📖 <b>COMANDOS DISPONIBLES</b>\n"
        f"{SEPARATOR}\n\n"
        "💰 <b>/precio</b> <code>[coin]</code>\n"
        "    Precio actual con variación 24h\n"
        "    Ej: <code>/precio btc</code>  <code>/precio eth</code>  <code>/precio sol</code>\n\n"
        "🌍 <b>/mercado</b>\n"
        "    Fear &amp; Greed + dominancia BTC/ETH + market cap total\n\n"
        "📊 <b>/resumen</b>\n"
        "    Precios de activos principales + contexto completo\n\n"
        "❤️ <b>/status</b>\n"
        "    Estado del servicio y uptime\n\n"
        f"{SEPARATOR}\n"
        f"<i>Coins soportadas:</i>\n{coins_list}",
        parse_mode="HTML",
    )


async def cmd_precio(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text(
            "⚠️ Indica la coin.\n"
            "Ejemplo: <code>/precio btc</code>",
            parse_mode="HTML",
        )
        return

    query   = ctx.args[0].lower().strip()
    coin_id = COIN_MAP.get(query)

    if not coin_id:
        await update.message.reply_text(
            f"❌ Coin <code>{query.upper()}</code> no reconocida.\n"
            "Usa /ayuda para ver la lista completa.",
            parse_mode="HTML",
        )
        return

    data = fetch_price(coin_id)
    if not data:
        await update.message.reply_text(
            "⚠️ No se pudo obtener el precio en este momento.\n"
            "Intenta de nuevo en unos segundos.",
        )
        return

    emoji  = COIN_EMOJIS.get(coin_id, "🪙")
    symbol = query.upper()
    now    = datetime.now(timezone.utc).strftime("%H:%M UTC")

    await update.message.reply_text(
        f"{emoji} <b>{symbol}</b>\n\n"
        f"💰 Precio:     <b>{fmt_price(data['price'])}</b>\n"
        f"📈 Cambio 24h: {fmt_change(data['change_24h'])}\n"
        f"🕐 {now}",
        parse_mode="HTML",
    )
    logger.info("cmd_precio: %s → %s", query, data["price"])


async def cmd_mercado(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    loading = await update.message.reply_text("⏳ Consultando datos de mercado...")

    fg  = fetch_fear_greed()
    gm  = fetch_global_market()
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    parts = [
        SEPARATOR,
        "🌍 <b>CONTEXTO DE MERCADO</b>",
        SEPARATOR,
        "",
    ]
    if fg:
        parts.append(fmt_fear_greed(fg))
    if gm:
        parts.extend(["", fmt_global(gm)])

    signal = fmt_confluence(fg, gm)
    if signal:
        parts.extend(["", signal])

    parts.extend(["", f"🕐 {now}"])

    await loading.edit_text("\n".join(parts), parse_mode="HTML")
    logger.info("cmd_mercado: F&G=%s BTC_dom=%s", fg and fg["value"], gm and gm["btc_dominance"])


async def cmd_resumen(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    loading = await update.message.reply_text("⏳ Generando resumen de mercado...")

    ids  = [cg_id for cg_id, _ in DAILY_ASSETS]
    data = fetch_prices_batch(ids)
    fg   = fetch_fear_greed()
    gm   = fetch_global_market()
    now  = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    # Build price lines
    price_block = ""
    for cg_id, label in DAILY_ASSETS:
        if cg_id in data:
            p  = fmt_price(data[cg_id]["price"])
            ch = fmt_change(data[cg_id]["change_24h"])
            price_block += f"  {label}  <b>{p}</b>  {ch}\n"

    parts = [
        SEPARATOR,
        "📊 <b>RESUMEN DE MERCADO</b>",
        SEPARATOR,
        "",
        "<b>Precios principales:</b>",
        price_block,
    ]
    if fg:
        parts.append(fmt_fear_greed(fg))
    if gm:
        parts.extend(["", fmt_global(gm)])

    signal = fmt_confluence(fg, gm)
    if signal:
        parts.extend(["", signal])

    parts.extend(["", f"🕐 {now}"])

    await loading.edit_text("\n".join(parts), parse_mode="HTML")
    logger.info("cmd_resumen: %d prices fetched", len(data))


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uptime  = datetime.now(timezone.utc) - START_TIME
    hours   = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)
    now     = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    await update.message.reply_text(
        f"{SEPARATOR}\n"
        "❤️ <b>STATUS — Responsive Module</b>\n"
        f"{SEPARATOR}\n\n"
        "🟢 Servicio:    <b>ACTIVO</b>\n"
        f"🔖 Versión:    <b>{BOT_VERSION}</b>\n"
        f"⏱️ Uptime:     <b>{hours}h {minutes}m</b>\n"
        "🌐 Plataforma: <b>Railway.app</b>\n"
        f"🕐 {now}\n\n"
        "📰 <i>Módulo de noticias automáticas corriendo en GitHub Actions.</i>",
        parse_mode="HTML",
    )
    logger.info("cmd_status: uptime=%dh%dm", hours, minutes)


# ══ ERROR HANDLER ══════════════════════════════════════════════════════════════

async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception for update %s: %s", update, ctx.error, exc_info=ctx.error)


# ══ ENTRY POINT ════════════════════════════════════════════════════════════════

def main() -> None:
    logger.info("=" * 55)
    logger.info("  Crypto Intel Bot — Responsive Module %s", BOT_VERSION)
    logger.info("  Started: %s UTC", START_TIME.strftime("%Y-%m-%d %H:%M"))
    logger.info("=" * 55)

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    # Register command handlers
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("ayuda",   cmd_ayuda))
    app.add_handler(CommandHandler("precio",  cmd_precio))
    app.add_handler(CommandHandler("mercado", cmd_mercado))
    app.add_handler(CommandHandler("resumen", cmd_resumen))
    app.add_handler(CommandHandler("status",  cmd_status))

    # Global error handler
    app.add_error_handler(error_handler)

    logger.info("Listening for commands via long polling...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,  # Ignore commands sent while offline
    )


if __name__ == "__main__":
    main()

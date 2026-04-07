"""
app.py — Servidor web del dashboard
"""
import threading
import time
import requests as http
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template

from paper_trading import db
import config

app = Flask(__name__, template_folder="templates")
app.config["JSON_SORT_KEYS"] = False

bot_status = {
    "running": False,
    "last_scan": None,
    "mode": "paper" if config.PAPER_TRADING else ("dry_run" if config.DRY_RUN else "live"),
    "initial_balance": config.PAPER_INITIAL_BALANCE,
}
_status_lock = threading.Lock()

# ── Tipo de cambio USD → EUR (se refresca cada hora) ─────────────────────────
_eur_rate: float = 0.92          # valor por defecto si falla la API
_rate_fetched_at: float = 0.0


def _get_eur_rate() -> float:
    """Devuelve el tipo de cambio USD/EUR usando una API gratuita sin clave."""
    global _eur_rate, _rate_fetched_at
    now = time.time()
    if now - _rate_fetched_at < 3600:   # refrescar máximo una vez por hora
        return _eur_rate
    try:
        r = http.get("https://open.er-api.com/v6/latest/USD", timeout=5, verify=False)
        r.raise_for_status()
        _eur_rate = r.json()["rates"]["EUR"]
        _rate_fetched_at = now
    except Exception:
        pass   # si falla, seguir usando el último valor conocido
    return _eur_rate


def _to_eur(usd: float) -> float:
    return round(usd * _get_eur_rate(), 2)


def update_bot_status(**kwargs):
    with _status_lock:
        bot_status.update(kwargs)
        bot_status["last_scan"] = datetime.now(timezone.utc).isoformat()


# ─── HTML ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    stats = db.get_stats()
    history = db.get_balance_history(limit=1)
    current_balance = history[-1]["balance"] if history else config.PAPER_INITIAL_BALANCE
    eur = _get_eur_rate()

    return jsonify({
        **stats,
        "balance":          round(current_balance, 2),
        "balance_eur":      _to_eur(current_balance),
        "initial_balance":  config.PAPER_INITIAL_BALANCE,
        "total_pnl_eur":    _to_eur(stats["total_pnl"]),
        "eur_rate":         round(eur, 4),
        "mode":             bot_status["mode"],
    })


@app.route("/api/trades")
def api_trades():
    trades = db.get_all_trades(limit=200)
    rate = _get_eur_rate()
    for t in trades:
        t["size_eur"] = round(t["size_usdc"] * rate, 2)
        t["pnl_eur"]  = round(t["pnl"] * rate, 2) if t["pnl"] is not None else None
    return jsonify(trades)


@app.route("/api/trades/open")
def api_trades_open():
    trades = db.get_open_trades()
    rate = _get_eur_rate()
    for t in trades:
        t["size_eur"] = round(t["size_usdc"] * rate, 2)
    return jsonify(trades)


@app.route("/api/chart")
def api_chart():
    history = db.get_balance_history(limit=500)
    rate = _get_eur_rate()

    if not history:
        return jsonify({
            "labels":  [datetime.now(timezone.utc).isoformat()],
            "balance": [config.PAPER_INITIAL_BALANCE],
            "pnl":     [0.0],
            "pnl_eur": [0.0],
        })

    return jsonify({
        "labels":  [r["timestamp"] for r in history],
        "balance": [r["balance"] for r in history],
        "pnl":     [r["cumulative_pnl"] for r in history],
        "pnl_eur": [round(r["cumulative_pnl"] * rate, 2) for r in history],
    })


@app.route("/api/cycles")
def api_cycles():
    return jsonify(db.get_recent_cycles(limit=20))


@app.route("/api/bot/status")
def api_bot_status():
    with _status_lock:
        return jsonify(dict(bot_status))


def run_dashboard(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host=host, port=port, debug=debug, use_reloader=False)

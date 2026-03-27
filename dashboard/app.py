"""
app.py — Servidor web del dashboard

Sirve el dashboard en http://localhost:5000 y expone una API REST
que el frontend consulta para obtener datos en tiempo real.

Endpoints:
  GET /                    → Dashboard HTML
  GET /api/stats           → Resumen: balance, P&L, win rate, etc.
  GET /api/trades          → Historial de todas las operaciones
  GET /api/trades/open     → Solo posiciones abiertas
  GET /api/chart           → Datos para el gráfico de P&L
  GET /api/cycles          → Últimos ciclos de escaneo
  GET /api/bot/status      → Estado actual del bot (running/stopped, último escaneo)
"""
import threading
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template

from paper_trading import db
import config

app = Flask(__name__, template_folder="templates")
app.config["JSON_SORT_KEYS"] = False

# Estado global del bot (actualizado por el hilo del bot)
bot_status = {
    "running": False,
    "last_scan": None,
    "mode": "paper" if config.PAPER_TRADING else ("dry_run" if config.DRY_RUN else "live"),
    "initial_balance": config.PAPER_INITIAL_BALANCE,
}
_status_lock = threading.Lock()


def update_bot_status(**kwargs):
    """Llamado por el bot para actualizar su estado en el dashboard."""
    with _status_lock:
        bot_status.update(kwargs)
        bot_status["last_scan"] = datetime.now(timezone.utc).isoformat()


# ─── Rutas HTML ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ─── API JSON ─────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    """Métricas globales: balance, P&L, win rate, etc."""
    stats = db.get_stats()
    balance_history = db.get_balance_history(limit=1)

    # Balance actual = último snapshot, o initial_balance si no hay trades
    if balance_history:
        current_balance = balance_history[-1]["balance"]
    else:
        current_balance = config.PAPER_INITIAL_BALANCE

    return jsonify({
        **stats,
        "balance": round(current_balance, 2),
        "initial_balance": config.PAPER_INITIAL_BALANCE,
        "mode": bot_status["mode"],
    })


@app.route("/api/trades")
def api_trades():
    """Historial de todas las operaciones (últimas 200)."""
    trades = db.get_all_trades(limit=200)
    return jsonify(trades)


@app.route("/api/trades/open")
def api_trades_open():
    """Solo las posiciones abiertas actualmente."""
    return jsonify(db.get_open_trades())


@app.route("/api/chart")
def api_chart():
    """
    Datos para el gráfico de P&L acumulado.
    Devuelve listas de timestamps y valores para Chart.js.
    """
    history = db.get_balance_history(limit=500)

    if not history:
        # Si no hay historial, devolver punto de inicio
        return jsonify({
            "labels": [datetime.now(timezone.utc).isoformat()],
            "balance": [config.PAPER_INITIAL_BALANCE],
            "pnl": [0.0],
        })

    labels = [row["timestamp"] for row in history]
    balance = [row["balance"] for row in history]
    pnl = [row["cumulative_pnl"] for row in history]

    return jsonify({
        "labels": labels,
        "balance": balance,
        "pnl": pnl,
    })


@app.route("/api/cycles")
def api_cycles():
    """Últimos ciclos de escaneo del bot."""
    return jsonify(db.get_recent_cycles(limit=20))


@app.route("/api/bot/status")
def api_bot_status():
    """Estado actual del bot."""
    with _status_lock:
        return jsonify(dict(bot_status))


def run_dashboard(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """
    Arranca el servidor Flask en un hilo separado para no bloquear el bot.
    """
    import logging
    # Silenciar los logs de Werkzeug (Flask) para no ensuciar la consola del bot
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    app.run(host=host, port=port, debug=debug, use_reloader=False)

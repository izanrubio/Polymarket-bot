"""
main.py — Punto de entrada del bot de Polymarket

Modos:
  python main.py           → paper trading + dashboard (recomendado para empezar)
  python main.py --once    → ejecuta un solo ciclo y termina
  python main.py --scan    → solo escanea, sin guardar operaciones
  python main.py --no-dash → bot sin dashboard (útil en servidor)

El dashboard se abre en http://localhost:5000
"""
import sys
import signal
import time
import threading
import schedule
from loguru import logger

import config
from config import validate
from src.logger import setup_logger
from src.client import PolymarketClient
from src.scanner import MarketScanner
from src.strategy import ImbalanceStrategy
from src.risk import RiskManager
from src.trader import Trader

# Importaciones de paper trading y dashboard
from paper_trading.engine import PaperTradingEngine
from paper_trading import db as paper_db
from dashboard.app import run_dashboard, update_bot_status

# ─── Control de apagado ──────────────────────────────────────────────────────
_running = True


def handle_shutdown(sig, frame):
    global _running
    logger.info("⏹  Señal de parada recibida. Cerrando el bot...")
    _running = False


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


# ─── Ciclo principal ─────────────────────────────────────────────────────────

def run_cycle(
    scanner: MarketScanner,
    strategy: ImbalanceStrategy,
    risk: RiskManager,
    trader: Trader,
    paper: PaperTradingEngine | None,
):
    """Un ciclo completo: comprobar resoluciones → escanear → analizar → operar."""

    # 1. Comprobar si algún mercado abierto se ha resuelto (solo en paper trading)
    if paper:
        paper.check_resolutions()

    logger.info("=" * 60)
    logger.info(f"🔄 Escaneando mercados | {risk.status_summary()}")
    logger.info("=" * 60)

    # 2. Obtener mercados que pasan los filtros
    markets = scanner.get_active_markets(limit=50)

    if not markets:
        logger.warning("No se encontraron mercados que pasen los filtros")
        paper_db.log_scan_cycle(0, 0, 0)
        update_bot_status(running=True)
        return

    signals_found = 0
    trades_executed = 0

    # 3. Analizar cada mercado
    for market in markets:
        if not risk.can_trade(market.condition_id):
            if risk.daily_pnl <= -config.MAX_DAILY_LOSS_USDC:
                logger.warning("Stop loss diario alcanzado. Fin del ciclo.")
                break
            continue

        ob_yes = scanner.get_order_book(market.token_id_yes)
        if ob_yes is None:
            continue

        signal = strategy.analyze(market, ob_yes)
        if signal is None:
            continue

        signals_found += 1

        success = trader.execute(signal)
        if success:
            trades_executed += 1

        time.sleep(0.3)

    # 4. Guardar estadísticas del ciclo
    paper_db.log_scan_cycle(len(markets), signals_found, trades_executed)
    update_bot_status(running=True)

    logger.info(
        f"✅ Ciclo completado | "
        f"Señales: {signals_found} | Órdenes: {trades_executed} | "
        f"{risk.status_summary()}"
    )


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    setup_logger()

    scan_only   = "--scan"    in sys.argv
    run_once    = "--once"    in sys.argv or scan_only
    no_dash     = "--no-dash" in sys.argv

    # En modo scan, forzar paper trading apagado para no guardar nada
    if scan_only:
        config.PAPER_TRADING = False
        config.DRY_RUN = True

    mode_label = (
        "SCAN ONLY"   if scan_only else
        "PAPER TRADING" if config.PAPER_TRADING else
        "DRY RUN"     if config.DRY_RUN else
        "⚡ LIVE (DINERO REAL)"
    )
    logger.info(f"🤖 Polymarket Bot arrancando | Modo: {mode_label}")

    # Validar configuración
    try:
        validate()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Inicializar motor de paper trading
    paper = None
    if config.PAPER_TRADING and not scan_only:
        paper_db.init_db()
        paper = PaperTradingEngine(initial_balance=config.PAPER_INITIAL_BALANCE)

    # Arrancar dashboard en hilo secundario
    if config.DASHBOARD_ENABLED and not no_dash and not scan_only:
        dash_thread = threading.Thread(
            target=run_dashboard,
            kwargs={"port": config.DASHBOARD_PORT},
            daemon=True,
        )
        dash_thread.start()
        logger.info(
            f"📊 Dashboard disponible en http://localhost:{config.DASHBOARD_PORT}"
        )

    # Conectar con Polymarket
    poly_client = PolymarketClient()
    try:
        clob = poly_client.connect()
    except Exception as e:
        logger.error(f"No se pudo conectar con Polymarket: {e}")
        sys.exit(1)

    balance = poly_client.get_balance()
    logger.info(f"💰 Saldo real en Polymarket: {balance:.2f} USDC")

    if paper:
        logger.info(
            f"💡 Balance de paper trading: {paper.get_current_balance():.2f} USDC"
        )

    # Inicializar componentes
    scanner  = MarketScanner()
    strategy = ImbalanceStrategy()
    risk     = RiskManager()
    trader   = Trader(clob, risk, paper_engine=paper)

    update_bot_status(running=True)

    if run_once:
        run_cycle(scanner, strategy, risk, trader, paper)
        update_bot_status(running=False)
        return

    # Bucle continuo
    logger.info(
        f"⏱  Escaneando cada {config.SCAN_INTERVAL_SECONDS}s. Pulsa Ctrl+C para parar."
    )

    run_cycle(scanner, strategy, risk, trader, paper)  # Primer ciclo inmediato

    schedule.every(config.SCAN_INTERVAL_SECONDS).seconds.do(
        run_cycle, scanner, strategy, risk, trader, paper
    )

    while _running:
        schedule.run_pending()
        time.sleep(1)

    # Apagado limpio
    trader.cancel_all_orders()
    update_bot_status(running=False)
    logger.info("👋 Bot detenido.")


if __name__ == "__main__":
    main()

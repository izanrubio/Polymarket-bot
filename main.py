"""
main.py — Punto de entrada del bot de Polymarket

Flujo principal:
  1. Cargar configuración y validarla
  2. Conectar con Polymarket (autenticación L1 + L2)
  3. Mostrar saldo y estado actual
  4. Escanear mercados activos (Gamma API)
  5. Analizar cada mercado con la estrategia de imbalance
  6. Si hay señal y el riesgo lo permite → ejecutar orden
  7. Repetir cada SCAN_INTERVAL_SECONDS segundos

Uso:
  python main.py          → arranca el bot en bucle
  python main.py --once   → ejecuta un solo ciclo y termina
  python main.py --scan   → solo escanea mercados sin ejecutar órdenes
"""
import sys
import signal
import time
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


# ─── Estado global ───────────────────────────────────────────────────────────
_running = True


def handle_shutdown(sig, frame):
    """Maneja Ctrl+C para apagar el bot limpiamente."""
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
):
    """
    Ejecuta un ciclo completo: escanear → analizar → operar.
    """
    logger.info("=" * 60)
    logger.info(f"🔄 Iniciando ciclo | {risk.status_summary()}")
    logger.info("=" * 60)

    # 1. Obtener mercados que pasan los filtros
    markets = scanner.get_active_markets(limit=50)

    if not markets:
        logger.warning("No se encontraron mercados que pasen los filtros")
        return

    signals_found = 0
    trades_executed = 0

    # 2. Analizar cada mercado
    for market in markets:
        # Si el riesgo no permite más operaciones, paramos
        if not risk.can_trade(market.condition_id):
            # Comprobamos si es el stop loss diario (para evitar spamear el log)
            if risk.daily_pnl <= -config.MAX_DAILY_LOSS_USDC:
                logger.warning("Stop loss diario alcanzado. Fin del ciclo.")
                break
            continue

        # Obtener el order book del token YES
        ob_yes = scanner.get_order_book(market.token_id_yes)

        if ob_yes is None:
            logger.debug(f"Sin order book para: {market.question[:50]}")
            continue

        # Analizar con la estrategia
        signal = strategy.analyze(market, ob_yes)

        if signal is None:
            continue

        signals_found += 1

        # Ejecutar la operación
        success = trader.execute(signal)
        if success:
            trades_executed += 1

        # Pequeña pausa entre órdenes para no saturar la API
        time.sleep(0.5)

    logger.info(
        f"✅ Ciclo completado | Señales: {signals_found} | "
        f"Órdenes: {trades_executed} | {risk.status_summary()}"
    )


# ─── Inicialización ──────────────────────────────────────────────────────────

def main():
    setup_logger()

    # Modo scan-only: no ejecuta órdenes, solo muestra oportunidades
    scan_only = "--scan" in sys.argv
    run_once = "--once" in sys.argv or scan_only

    logger.info("🤖 Polymarket Bot arrancando...")
    logger.info(
        f"Modo: {'SCAN ONLY' if scan_only else 'DRY RUN' if config.DRY_RUN else '⚡ LIVE (DINERO REAL)'}"
    )

    # Validar configuración (no arranca si falta la private key)
    try:
        validate()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Conectar con Polymarket
    poly_client = PolymarketClient()
    try:
        clob = poly_client.connect()
    except Exception as e:
        logger.error(f"No se pudo conectar con Polymarket: {e}")
        sys.exit(1)

    # Mostrar saldo
    balance = poly_client.get_balance()
    logger.info(f"💰 Saldo en USDC: {balance:.2f}")

    if balance < config.MAX_POSITION_USDC and not config.DRY_RUN:
        logger.warning(
            f"⚠️  Tu saldo ({balance:.2f} USDC) es menor que el tamaño máximo de posición "
            f"({config.MAX_POSITION_USDC:.2f} USDC). Considera reducir MAX_POSITION_USDC."
        )

    # Si es modo scan-only, forzamos DRY_RUN
    if scan_only:
        config.DRY_RUN = True

    # Inicializar componentes
    scanner = MarketScanner()
    strategy = ImbalanceStrategy()
    risk = RiskManager()
    trader = Trader(clob, risk)

    # Ejecutar
    if run_once:
        run_cycle(scanner, strategy, risk, trader)
        return

    # Bucle continuo con schedule
    logger.info(
        f"⏱  Ejecutando ciclo cada {config.SCAN_INTERVAL_SECONDS} segundos. "
        "Pulsa Ctrl+C para detener."
    )

    # Primer ciclo inmediato
    run_cycle(scanner, strategy, risk, trader)

    # Programar ciclos siguientes
    schedule.every(config.SCAN_INTERVAL_SECONDS).seconds.do(
        run_cycle, scanner, strategy, risk, trader
    )

    while _running:
        schedule.run_pending()
        time.sleep(1)

    # Apagado limpio
    logger.info("Cancelando órdenes abiertas antes de salir...")
    trader.cancel_all_orders()
    logger.info("👋 Bot detenido.")


if __name__ == "__main__":
    main()

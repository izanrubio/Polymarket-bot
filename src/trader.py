"""
trader.py — Ejecución de órdenes en Polymarket

Traduce las señales de la estrategia en órdenes reales (o simuladas si DRY_RUN=true).

Tipos de orden usados:
  GTC (Good Till Cancelled) — la orden queda en el libro hasta que se ejecute o se cancele
  FOK (Fill or Kill)        — se ejecuta al instante o se cancela (tipo market order)
"""
from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.constants import BUY

from src.strategy import TradeSignal, Side
from src.risk import RiskManager
import config


class Trader:
    """Gestiona la ejecución de órdenes."""

    def __init__(self, clob_client: ClobClient, risk_manager: RiskManager):
        self._client = clob_client
        self._risk = risk_manager

    def execute(self, signal: TradeSignal) -> bool:
        """
        Intenta ejecutar una señal de trading.
        Devuelve True si la orden se envió correctamente (o fue simulada).
        """
        market = signal.market
        condition_id = market.condition_id

        # ── Comprobar riesgo ─────────────────────────────────────────────────
        if not self._risk.can_trade(condition_id):
            return False

        # ── Construir la orden ───────────────────────────────────────────────
        # En Polymarket siempre compramos (BUY) — la dirección la da el token
        # BUY YES token = apostar a que ocurre
        # BUY NO  token = apostar a que no ocurre
        size_shares = round(signal.size_usdc / signal.entry_price, 2)

        order_args = OrderArgs(
            token_id=signal.token_id,
            price=signal.entry_price,
            size=size_shares,
            side=BUY,
        )

        # ── Log de la operación ──────────────────────────────────────────────
        action = "BUY YES" if signal.side == Side.BUY_YES else "BUY NO"
        logger.info(
            f"{'[DRY RUN] ' if config.DRY_RUN else ''}Orden: {action} | "
            f"Mercado: {market.question[:60]} | "
            f"Precio: {signal.entry_price:.3f} | "
            f"Acciones: {size_shares:.2f} | "
            f"Coste: ~{signal.size_usdc:.2f} USDC | "
            f"Razón: {signal.reason}"
        )

        # ── DRY RUN: no ejecutar nada real ───────────────────────────────────
        if config.DRY_RUN:
            logger.warning(
                "⚠️  DRY_RUN activado — orden NO enviada a Polymarket. "
                "Cambia DRY_RUN=false en .env para operar con dinero real."
            )
            # Registramos igualmente para el tracking de riesgo en modo simulación
            self._risk.register_trade(condition_id, signal.size_usdc)
            return True

        # ── Enviar orden real ────────────────────────────────────────────────
        try:
            # Crear la orden firmada
            signed_order = self._client.create_order(order_args)

            # Enviar como GTC (queda en el libro) — puedes cambiar a FOK para market order
            response = self._client.post_order(signed_order, OrderType.GTC)

            if response and response.get("success"):
                order_id = response.get("orderID", "?")
                logger.success(
                    f"✅ Orden enviada correctamente | Order ID: {order_id} | "
                    f"{action} {size_shares:.2f} acciones @ {signal.entry_price:.3f}"
                )
                self._risk.register_trade(condition_id, signal.size_usdc)
                return True
            else:
                logger.error(f"❌ La orden fue rechazada: {response}")
                return False

        except Exception as e:
            logger.error(f"❌ Error enviando orden: {e}")
            return False

    def cancel_all_orders(self):
        """Cancela todas las órdenes abiertas. Útil al detener el bot."""
        if config.DRY_RUN:
            logger.info("[DRY RUN] Se cancelarían todas las órdenes abiertas")
            return

        try:
            result = self._client.cancel_all()
            logger.info(f"Órdenes canceladas: {result}")
        except Exception as e:
            logger.error(f"Error cancelando órdenes: {e}")

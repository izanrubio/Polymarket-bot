"""
trader.py — Ejecución de órdenes en Polymarket

Modos de operación:
  PAPER_TRADING=true  → guarda la operación en SQLite con dinero ficticio (default)
  DRY_RUN=true        → solo loguea, sin DB ni órdenes reales
  ambos false         → envía órdenes reales a Polymarket
"""
from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.constants import BUY

from src.strategy import TradeSignal, Side
from src.risk import RiskManager
import config


class Trader:
    """Gestiona la ejecución de órdenes en cualquier modo."""

    def __init__(
        self,
        clob_client: ClobClient,
        risk_manager: RiskManager,
        paper_engine=None,   # PaperTradingEngine | None
    ):
        self._client = clob_client
        self._risk = risk_manager
        self._paper = paper_engine

    def execute(self, signal: TradeSignal) -> bool:
        """
        Procesa una señal de trading según el modo activo.
        Devuelve True si la operación se procesó correctamente.
        """
        market = signal.market
        condition_id = market.condition_id

        # Comprobar límites de riesgo
        if not self._risk.can_trade(condition_id):
            return False

        action = "BUY YES" if signal.side == Side.BUY_YES else "BUY NO"
        size_shares = round(signal.size_usdc / signal.entry_price, 2)

        logger.info(
            f"Señal: {action} | '{market.question[:55]}' | "
            f"Precio: {signal.entry_price:.3f} | "
            f"Coste: {signal.size_usdc:.2f} USDC"
        )

        # ── Modo paper trading: guarda en DB con dinero ficticio ─────────────
        if config.PAPER_TRADING and self._paper is not None:
            success = self._paper.record_trade(signal)
            if success:
                self._risk.register_trade(condition_id, signal.size_usdc)
            return success

        # ── Modo dry run: solo loguea, sin persistencia ───────────────────────
        if config.DRY_RUN:
            logger.warning(
                "⚠️  DRY_RUN activo — orden no enviada ni guardada. "
                "Activa PAPER_TRADING=true para guardar el historial."
            )
            self._risk.register_trade(condition_id, signal.size_usdc)
            return True

        # ── Modo live: enviar orden real a Polymarket ────────────────────────
        order_args = OrderArgs(
            token_id=signal.token_id,
            price=signal.entry_price,
            size=size_shares,
            side=BUY,
        )
        try:
            signed_order = self._client.create_order(order_args)
            response = self._client.post_order(signed_order, OrderType.GTC)

            if response and response.get("success"):
                order_id = response.get("orderID", "?")
                logger.success(
                    f"✅ Orden enviada | ID: {order_id} | "
                    f"{action} {size_shares:.2f} acciones @ {signal.entry_price:.3f}"
                )
                self._risk.register_trade(condition_id, signal.size_usdc)
                return True
            else:
                logger.error(f"❌ Orden rechazada: {response}")
                return False

        except Exception as e:
            logger.error(f"❌ Error enviando orden: {e}")
            return False

    def cancel_all_orders(self):
        """Cancela todas las órdenes abiertas al detener el bot."""
        if config.PAPER_TRADING or config.DRY_RUN:
            return
        try:
            result = self._client.cancel_all()
            logger.info(f"Órdenes canceladas: {result}")
        except Exception as e:
            logger.error(f"Error cancelando órdenes: {e}")

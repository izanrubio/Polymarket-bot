"""
engine.py — Motor de paper trading

Simula la ejecución de operaciones con dinero ficticio y verifica
periódicamente si los mercados se han resuelto para calcular el P&L real.

Flujo:
  1. record_trade(signal)     → guarda la operación en la DB
  2. check_resolutions()      → consulta la API Gamma para ver si algún
                                mercado se ha resuelto
  3. get_current_balance()    → saldo inicial ± P&L de operaciones cerradas
"""
import requests
import urllib3
from loguru import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_SSL = False

from paper_trading import db
from src.strategy import TradeSignal, Side
import config


class PaperTradingEngine:
    """
    Motor de paper trading que simula operaciones con balance virtual
    y las persiste en SQLite.
    """

    GAMMA_URL = config.GAMMA_API

    def __init__(self, initial_balance: float):
        self.initial_balance = initial_balance
        db.init_db()
        logger.info(
            f"💡 Paper Trading activado | Balance inicial: {initial_balance:.2f} USDC"
        )

    # ── Registrar operación ───────────────────────────────────────────────────

    def record_trade(self, signal: TradeSignal) -> bool:
        """
        Registra una operación simulada en la base de datos.
        Devuelve True si se guardó correctamente.
        """
        balance = self.get_current_balance()

        if signal.size_usdc > balance:
            logger.warning(
                f"⚠️  Saldo insuficiente para operar. "
                f"Necesario: {signal.size_usdc:.2f} USDC | Disponible: {balance:.2f} USDC"
            )
            return False

        trade_id = db.insert_trade(
            question=signal.market.question,
            condition_id=signal.market.condition_id,
            side=signal.side.value,
            token_id=signal.token_id,
            entry_price=signal.entry_price,
            size_usdc=signal.size_usdc,
            shares=round(signal.size_usdc / signal.entry_price, 4),
            confidence=signal.confidence,
            reason=signal.reason,
        )

        # Guardar snapshot del balance en ese momento
        db.add_balance_snapshot(balance - signal.size_usdc, self._cumulative_pnl())

        logger.success(
            f"📝 [PAPER] Trade #{trade_id} registrado | "
            f"{signal.side.value} | "
            f"'{signal.market.question[:50]}' | "
            f"Precio: {signal.entry_price:.3f} | "
            f"Invertido: {signal.size_usdc:.2f} USDC"
        )
        return True

    # ── Comprobar resoluciones ────────────────────────────────────────────────

    def check_resolutions(self):
        """
        Consulta la API Gamma para cada operación abierta y cierra
        las que ya se hayan resuelto.
        """
        open_trades = db.get_open_trades()
        if not open_trades:
            return

        logger.debug(f"Comprobando resolución de {len(open_trades)} operación(es) abierta(s)...")

        for trade in open_trades:
            resolved, exit_price = self._is_resolved(trade)
            if resolved:
                self._close_trade(trade, exit_price)

        # Guardar snapshot de balance después de las resoluciones
        db.add_balance_snapshot(self.get_current_balance(), self._cumulative_pnl())

    def _is_resolved(self, trade: dict) -> tuple[bool, float]:
        """
        Consulta la API Gamma para un mercado concreto.
        Devuelve (True, exit_price) si ya se resolvió, (False, 0) si no.
        exit_price = 1.0 si ganamos, 0.0 si perdemos.
        """
        try:
            resp = requests.get(
                f"{self.GAMMA_URL}/markets",
                params={"condition_ids": trade["condition_id"]},
                timeout=5,
                verify=_SSL,
            )
            resp.raise_for_status()
            markets = resp.json()
        except requests.RequestException as e:
            logger.debug(f"Error consultando resolución de mercado: {e}")
            return False, 0.0

        if not markets:
            return False, 0.0

        market_data = markets[0] if isinstance(markets, list) else markets

        # Si el mercado sigue activo, no está resuelto
        if market_data.get("active", True) or not market_data.get("closed", False):
            return False, 0.0

        # Comprobar si hay un ganador claro (precio = 1.0 o 0.0)
        outcome_prices = market_data.get("outcomePrices", [])
        if not outcome_prices or len(outcome_prices) < 2:
            return False, 0.0

        try:
            yes_price = float(outcome_prices[0])
            no_price = float(outcome_prices[1])
        except (ValueError, TypeError):
            return False, 0.0

        # Necesitamos que sea definitivo (precio exactamente 0 o 1)
        if yes_price not in (0.0, 1.0) and no_price not in (0.0, 1.0):
            return False, 0.0

        # Determinar si ganamos según nuestra posición
        side = trade["side"]
        if side == Side.BUY_YES.value:
            exit_price = yes_price  # 1.0 si YES ganó, 0.0 si perdió
        else:
            exit_price = no_price   # 1.0 si NO ganó, 0.0 si perdió

        return True, exit_price

    def _close_trade(self, trade: dict, exit_price: float):
        """Cierra una operación y calcula el P&L."""
        # P&L = (shares × exit_price) - size_usdc_invertido
        pnl = trade["shares"] * exit_price - trade["size_usdc"]
        pnl = round(pnl, 4)

        db.close_trade(trade["id"], exit_price, pnl)

        result = "✅ GANADA" if pnl >= 0 else "❌ PERDIDA"
        logger.info(
            f"{result} | Trade #{trade['id']} resuelto | "
            f"'{trade['question'][:50]}' | "
            f"P&L: {pnl:+.2f} USDC"
        )

    # ── Métricas ──────────────────────────────────────────────────────────────

    def get_current_balance(self) -> float:
        """
        Balance actual = balance inicial + P&L acumulado de operaciones cerradas
        - capital "bloqueado" en posiciones abiertas.
        """
        cumulative_pnl = self._cumulative_pnl()
        open_trades = db.get_open_trades()
        invested_in_open = sum(t["size_usdc"] for t in open_trades)
        return round(self.initial_balance + cumulative_pnl - invested_in_open, 2)

    def _cumulative_pnl(self) -> float:
        """P&L total de todas las operaciones cerradas."""
        stats = db.get_stats()
        return stats["total_pnl"]

    def get_full_stats(self) -> dict:
        """Devuelve todas las métricas para el dashboard."""
        stats = db.get_stats()
        balance = self.get_current_balance()
        return {
            **stats,
            "balance": round(balance, 2),
            "initial_balance": self.initial_balance,
        }

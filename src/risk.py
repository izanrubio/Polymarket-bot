"""
risk.py — Gestión de riesgo

Controla que el bot no pierda más de lo permitido,
no tenga demasiadas posiciones abiertas y no opere en
mercados donde ya tenemos exposición.
"""
from datetime import date
from loguru import logger
import config


class RiskManager:
    """
    Lleva la cuenta de pérdidas diarias y posiciones abiertas
    para asegurarse de que el bot opera dentro de los límites configurados.
    """

    def __init__(self):
        self._today = date.today()
        self._daily_pnl: float = 0.0         # P&L del día (positivo = ganancia)
        self._open_positions: set[str] = set()  # condition_ids en posición abierta

    def _reset_if_new_day(self):
        """Reinicia las estadísticas diarias si ha cambiado el día."""
        today = date.today()
        if today != self._today:
            logger.info(
                f"Nuevo día. P&L del día anterior: {self._daily_pnl:+.2f} USDC. Reiniciando contadores."
            )
            self._today = today
            self._daily_pnl = 0.0

    def can_trade(self, condition_id: str) -> bool:
        """
        Devuelve True si se puede abrir una nueva posición.
        Comprueba:
          1. No hemos alcanzado la pérdida máxima diaria
          2. No tenemos demasiadas posiciones abiertas
          3. No tenemos ya una posición en este mercado
        """
        self._reset_if_new_day()

        # Comprobar pérdida diaria
        if self._daily_pnl <= -config.MAX_DAILY_LOSS_USDC:
            logger.warning(
                f"🛑 Stop loss diario alcanzado: {self._daily_pnl:.2f} USDC "
                f"(límite: -{config.MAX_DAILY_LOSS_USDC:.2f} USDC). "
                "No se abrirán más operaciones hoy."
            )
            return False

        # Comprobar número de posiciones
        if len(self._open_positions) >= config.MAX_OPEN_POSITIONS:
            logger.warning(
                f"⚠️  Máximo de posiciones abiertas alcanzado "
                f"({len(self._open_positions)}/{config.MAX_OPEN_POSITIONS})"
            )
            return False

        # Comprobar si ya tenemos posición en este mercado
        if condition_id in self._open_positions:
            logger.debug(f"Ya tenemos posición en el mercado {condition_id[:8]}...")
            return False

        return True

    def register_trade(self, condition_id: str, size_usdc: float):
        """Registra que se abrió una posición."""
        self._open_positions.add(condition_id)
        self._daily_pnl -= size_usdc  # Considerar el coste como pérdida provisional
        logger.info(
            f"📝 Posición registrada: {condition_id[:8]}... | "
            f"Coste: {size_usdc:.2f} USDC | "
            f"Posiciones abiertas: {len(self._open_positions)}"
        )

    def close_position(self, condition_id: str, profit_usdc: float):
        """
        Registra el cierre de una posición.
        profit_usdc puede ser negativo (pérdida).
        """
        self._open_positions.discard(condition_id)
        self._daily_pnl += profit_usdc
        status = "✅ Ganancia" if profit_usdc >= 0 else "❌ Pérdida"
        logger.info(
            f"{status}: {profit_usdc:+.2f} USDC | "
            f"P&L diario: {self._daily_pnl:+.2f} USDC"
        )

    @property
    def daily_pnl(self) -> float:
        self._reset_if_new_day()
        return self._daily_pnl

    @property
    def open_positions_count(self) -> int:
        return len(self._open_positions)

    def status_summary(self) -> str:
        self._reset_if_new_day()
        return (
            f"P&L hoy: {self._daily_pnl:+.2f} USDC | "
            f"Posiciones: {len(self._open_positions)}/{config.MAX_OPEN_POSITIONS} | "
            f"Límite diario: -{config.MAX_DAILY_LOSS_USDC:.2f} USDC"
        )

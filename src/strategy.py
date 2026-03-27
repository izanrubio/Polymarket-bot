"""
strategy.py — Lógica de la estrategia de trading

Estrategia: Order Book Imbalance
─────────────────────────────────
Si el 65%+ del volumen del order book está en el lado de compra (bids),
hay más compradores que vendedores → el precio probablemente suba → COMPRA YES.

Si el 65%+ está en el lado de venta (asks),
hay más vendedores que compradores → el precio probablemente baje → COMPRA NO
(que equivale a apostar a que YES baja).

El tamaño de la posición se calcula con el criterio de Kelly (fraccionado),
que optimiza el tamaño de la apuesta según la ventaja percibida.
"""
from dataclasses import dataclass
from enum import Enum
from loguru import logger
from src.scanner import Market, OrderBook
import config


class Side(Enum):
    BUY_YES = "BUY_YES"   # Comprar tokens YES (apostar a que se resuelve SÍ)
    BUY_NO = "BUY_NO"     # Comprar tokens NO  (apostar a que se resuelve NO)


@dataclass
class TradeSignal:
    """Señal de trading generada por la estrategia."""
    market: Market
    side: Side
    token_id: str          # Token a comprar (YES o NO)
    entry_price: float     # Precio límite propuesto
    size_usdc: float       # Cuántos USDC invertir
    confidence: float      # 0.0 - 1.0, confianza en la señal
    reason: str            # Explicación legible


class ImbalanceStrategy:
    """
    Estrategia basada en el desequilibrio del order book.

    Cuando hay un desequilibrio claro entre compradores y vendedores,
    tendemos a operar en la dirección de la presión dominante.
    """

    def analyze(self, market: Market, ob_yes: OrderBook | None) -> TradeSignal | None:
        """
        Analiza el mercado y devuelve una señal de trading si la hay.

        Args:
            market:  Datos del mercado (precio, volumen, etc.)
            ob_yes:  Order book del token YES

        Returns:
            TradeSignal si se detecta una oportunidad, None si no.
        """
        if ob_yes is None:
            return None

        imbalance = ob_yes.imbalance  # % del volumen total que está en bids

        # ── Detectar señal ───────────────────────────────────────────────────
        threshold = config.IMBALANCE_THRESHOLD  # e.g. 0.65

        if imbalance >= threshold:
            # Más compradores que vendedores → subida probable → COMPRA YES
            side = Side.BUY_YES
            token_id = market.token_id_yes
            current_price = market.price_yes
            # Ponemos la orden un poco mejor que el mejor bid (más probable que ejecute)
            entry_price = round(
                min(ob_yes.best_bid + config.PRICE_IMPROVEMENT, ob_yes.best_ask - 0.01),
                2,
            )
            confidence = (imbalance - threshold) / (1.0 - threshold)
            reason = (
                f"Imbalance alcista: {imbalance:.1%} del order book son compradores "
                f"(umbral: {threshold:.0%})"
            )

        elif imbalance <= (1.0 - threshold):
            # Más vendedores que compradores → bajada probable → COMPRA NO
            side = Side.BUY_NO
            token_id = market.token_id_no
            current_price = market.price_no
            entry_price = round(
                min(1.0 - ob_yes.best_ask + config.PRICE_IMPROVEMENT, 1.0 - ob_yes.best_bid - 0.01),
                2,
            )
            confidence = ((1.0 - threshold) - imbalance) / (1.0 - threshold)
            reason = (
                f"Imbalance bajista: {1-imbalance:.1%} del order book son vendedores "
                f"(umbral: {threshold:.0%})"
            )

        else:
            logger.debug(
                f"Sin señal en '{market.question[:50]}' — imbalance: {imbalance:.2f}"
            )
            return None

        # ── Calcular tamaño con Kelly ────────────────────────────────────────
        size = self._kelly_size(
            price=entry_price,
            confidence=confidence,
        )

        if size < 0.5:
            logger.debug(f"Tamaño Kelly demasiado pequeño ({size:.2f} USDC), descartando")
            return None

        logger.info(
            f"📊 Señal: {side.value} en '{market.question[:60]}' | "
            f"Precio: {entry_price:.2f} | Tamaño: {size:.2f} USDC | "
            f"Confianza: {confidence:.0%}"
        )

        return TradeSignal(
            market=market,
            side=side,
            token_id=token_id,
            entry_price=entry_price,
            size_usdc=size,
            confidence=confidence,
            reason=reason,
        )

    def _kelly_size(self, price: float, confidence: float) -> float:
        """
        Calcula el tamaño óptimo usando el criterio de Kelly fraccionado.

        Kelly completo: f = (p*b - q) / b
          donde:
            p = probabilidad estimada de ganar
            q = 1 - p
            b = ganancia por unidad arriesgada = (1/price) - 1

        Usamos Kelly fraccionado (KELLY_FRACTION) para ser más conservadores.
        """
        if price <= 0.0 or price >= 1.0:
            return 0.0

        # Estimamos la probabilidad verdadera como el precio actual + sesgo de confianza
        # Un confidence de 1.0 añade hasta un 10% extra al precio observado
        p = min(price + confidence * 0.10, 0.95)
        q = 1.0 - p
        b = (1.0 / price) - 1.0  # Odds

        kelly_fraction = (p * b - q) / b
        kelly_fraction = max(kelly_fraction, 0.0)  # No apostar si es negativo

        # Aplicamos la fracción de Kelly configurada y el máximo por posición
        size = kelly_fraction * config.KELLY_FRACTION * config.MAX_POSITION_USDC
        size = min(size, config.MAX_POSITION_USDC)  # Nunca más del máximo

        return round(size, 2)

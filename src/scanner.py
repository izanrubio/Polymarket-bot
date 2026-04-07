"""
scanner.py — Escanea mercados activos de Polymarket vía la API Gamma

La API Gamma devuelve metadatos de mercados: título, precio, volumen, etc.
La API CLOB devuelve el order book en tiempo real.
"""
from dataclasses import dataclass
from typing import Optional
import requests
import urllib3
from loguru import logger

# Desactivar advertencias de SSL (problema de certificados en algunos sistemas Linux)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_SSL = False  # ponlo en True si tu sistema tiene los certificados bien configurados
import config


@dataclass
class Market:
    """Representa un mercado de Polymarket con su información básica."""
    condition_id: str       # ID único del mercado
    token_id_yes: str       # Token ID para comprar YES
    token_id_no: str        # Token ID para comprar NO
    question: str           # Pregunta del mercado
    price_yes: float        # Precio actual de YES (0.0 - 1.0)
    price_no: float         # Precio actual de NO  (0.0 - 1.0)
    volume_usd: float       # Volumen total en USD
    end_date: str           # Fecha de resolución
    active: bool            # Si el mercado sigue activo


@dataclass
class OrderBook:
    """Snapshot del order book de un token."""
    token_id: str
    bids: list[dict]        # Lista de {price, size}
    asks: list[dict]        # Lista de {price, size}
    best_bid: float         # Mejor precio de compra
    best_ask: float         # Mejor precio de venta
    spread: float           # Diferencia ask - bid
    bid_volume: float       # Volumen total en el lado de compra
    ask_volume: float       # Volumen total en el lado de venta
    imbalance: float        # bid_volume / (bid_volume + ask_volume)


class MarketScanner:
    """
    Usa la API Gamma para descubrir mercados y la API CLOB para obtener
    el order book en tiempo real.
    """

    GAMMA_URL = config.GAMMA_API
    CLOB_URL = config.CLOB_HOST

    def get_active_markets(self, limit: int = 100) -> list[Market]:
        """
        Obtiene mercados activos que cumplan los filtros de configuración.
        Devuelve una lista de Market ordenada por volumen descendente.
        """
        logger.info("Buscando mercados activos...")

        markets = []
        offset = 0
        page_size = 100

        while len(markets) < limit:
            try:
                resp = requests.get(
                    f"{self.GAMMA_URL}/markets",
                    params={
                        "closed": "false",
                        "active": "true",
                        "limit": page_size,
                        "offset": offset,
                        "order": "volume",
                        "ascending": "false",
                    },
                    timeout=10,
                    verify=_SSL,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                logger.error(f"Error al llamar a la API Gamma: {e}")
                break

            if not data:
                break

            for m in data:
                market = self._parse_market(m)
                if market and self._passes_filters(market):
                    markets.append(market)

            if len(data) < page_size:
                break  # No hay más páginas
            offset += page_size

        logger.info(f"Encontrados {len(markets)} mercados que pasan los filtros")
        return markets[:limit]

    def _parse_market(self, raw: dict) -> Optional[Market]:
        """Convierte la respuesta de la API en un objeto Market."""
        try:
            # Gamma devuelve outcomes como ["Yes","No"] y outcomePrices como ["0.65","0.35"]
            tokens = raw.get("tokens", [])
            if len(tokens) < 2:
                return None

            # El token YES siempre es el primero
            token_yes = tokens[0]
            token_no = tokens[1]

            prices = raw.get("outcomePrices", ["0.5", "0.5"])
            price_yes = float(prices[0]) if prices else 0.5
            price_no = float(prices[1]) if len(prices) > 1 else 1.0 - price_yes

            volume = float(raw.get("volumeNum", raw.get("volume", "0") or "0"))

            return Market(
                condition_id=raw.get("conditionId", ""),
                token_id_yes=token_yes.get("token_id", ""),
                token_id_no=token_no.get("token_id", ""),
                question=raw.get("question", "Sin título"),
                price_yes=price_yes,
                price_no=price_no,
                volume_usd=volume,
                end_date=raw.get("endDate", ""),
                active=raw.get("active", False),
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.debug(f"Error parseando mercado: {e} — datos: {raw.get('question', '?')}")
            return None

    def _passes_filters(self, m: Market) -> bool:
        """Comprueba si un mercado cumple los criterios de configuración."""
        if not m.condition_id or not m.token_id_yes:
            return False
        if m.volume_usd < config.MIN_VOLUME_USD:
            return False
        if m.price_yes > config.MAX_PRICE or m.price_yes < config.MIN_PRICE:
            return False
        return True

    def get_order_book(self, token_id: str) -> Optional[OrderBook]:
        """
        Obtiene el order book en tiempo real para un token desde la API CLOB.
        token_id puede ser el ID del token YES o NO.
        """
        try:
            resp = requests.get(
                f"{self.CLOB_URL}/book",
                params={"token_id": token_id},
                timeout=5,
                verify=_SSL,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.debug(f"Error obteniendo order book de {token_id[:8]}...: {e}")
            return None

        bids = data.get("bids", [])  # [{"price": "0.60", "size": "100"}, ...]
        asks = data.get("asks", [])

        if not bids and not asks:
            return None

        def to_float(entries):
            return [{"price": float(e["price"]), "size": float(e["size"])} for e in entries]

        bids_f = to_float(bids)
        asks_f = to_float(asks)

        best_bid = max((e["price"] for e in bids_f), default=0.0)
        best_ask = min((e["price"] for e in asks_f), default=1.0)
        spread = best_ask - best_bid

        bid_vol = sum(e["price"] * e["size"] for e in bids_f)
        ask_vol = sum(e["price"] * e["size"] for e in asks_f)
        total_vol = bid_vol + ask_vol

        # Comprobamos liquidez mínima
        if total_vol < config.MIN_LIQUIDITY_USD:
            return None

        imbalance = bid_vol / total_vol if total_vol > 0 else 0.5

        return OrderBook(
            token_id=token_id,
            bids=bids_f,
            asks=asks_f,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            bid_volume=bid_vol,
            ask_volume=ask_vol,
            imbalance=imbalance,
        )

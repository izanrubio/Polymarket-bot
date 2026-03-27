"""
client.py — Wrapper del cliente oficial de Polymarket (py-clob-client)

En paper trading solo se usan las APIs públicas (sin autenticación):
  - Gamma API  → datos de mercados
  - CLOB API   → order books en tiempo real

La autenticación L1/L2 solo es necesaria para órdenes reales (modo live).
"""
from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
import config


class PolymarketClient:
    """
    Encapsula el ClobClient oficial.
    En paper trading, crea un cliente de solo lectura (sin auth).
    """

    def __init__(self):
        self._client: ClobClient | None = None

    def connect(self) -> ClobClient:
        """
        En paper trading: cliente público de solo lectura (sin credenciales).
        En modo live:      autenticación completa L1 + L2.
        """
        if config.PAPER_TRADING or config.DRY_RUN:
            # Solo necesitamos el host para las llamadas públicas al order book
            self._client = ClobClient(host=config.CLOB_HOST, chain_id=config.CHAIN_ID)
            logger.success("Cliente Polymarket listo (modo lectura para paper trading) ✓")
            return self._client

        # ── Modo live: autenticación completa ───────────────────────────────
        logger.info("Conectando con Polymarket CLOB (modo live)...")
        client = ClobClient(
            host=config.CLOB_HOST,
            chain_id=config.CHAIN_ID,
            key=config.PRIVATE_KEY,
        )
        try:
            creds: ApiCreds = client.create_or_derive_api_creds()
            logger.info(f"Credenciales L2 obtenidas. API Key: {creds.api_key[:8]}...")
        except Exception as e:
            logger.error(f"Error obteniendo credenciales L2: {e}")
            raise

        self._client = ClobClient(
            host=config.CLOB_HOST,
            chain_id=config.CHAIN_ID,
            key=config.PRIVATE_KEY,
            creds=creds,
        )
        logger.success("Conexión establecida con Polymarket ✓")
        return self._client

    @property
    def client(self) -> ClobClient:
        if self._client is None:
            raise RuntimeError("Cliente no inicializado. Llama a connect() primero.")
        return self._client

    def get_balance(self) -> float:
        """Devuelve el saldo real en USDC (solo disponible en modo live)."""
        if config.PAPER_TRADING:
            return 0.0
        try:
            return float(self._client.get_balance())
        except Exception as e:
            logger.error(f"Error obteniendo saldo: {e}")
            return 0.0

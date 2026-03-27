"""
client.py — Wrapper del cliente oficial de Polymarket (py-clob-client)

El cliente maneja dos niveles de autenticación:
  L1 → Tu clave privada de Ethereum (prueba que eres el dueño de la wallet)
  L2 → Credenciales de API derivadas de L1 (se usan en cada petición)
"""
from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
import config


class PolymarketClient:
    """
    Encapsula el ClobClient oficial y gestiona la autenticación automáticamente.
    """

    def __init__(self):
        self._client: ClobClient | None = None

    def connect(self) -> ClobClient:
        """
        Crea el cliente CLOB y deriva/obtiene las credenciales L2.
        Llama a este método una sola vez al arrancar el bot.
        """
        logger.info("Conectando con Polymarket CLOB...")

        # Creamos el cliente solo con L1 (clave privada) para poder derivar L2
        client = ClobClient(
            host=config.CLOB_HOST,
            chain_id=config.CHAIN_ID,
            key=config.PRIVATE_KEY,
        )

        # Derivar o crear credenciales L2 (apiKey, secret, passphrase)
        # Si ya existen en Polymarket para esta wallet, las reutiliza
        try:
            creds: ApiCreds = client.create_or_derive_api_creds()
            logger.info(f"Credenciales L2 obtenidas. API Key: {creds.api_key[:8]}...")
        except Exception as e:
            logger.error(f"Error obteniendo credenciales L2: {e}")
            raise

        # Ahora creamos el cliente completo con L1 + L2
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
        """Devuelve el saldo disponible en USDC."""
        try:
            balance = self._client.get_balance()
            return float(balance)
        except Exception as e:
            logger.error(f"Error obteniendo saldo: {e}")
            return 0.0

    def get_open_orders(self) -> list:
        """Devuelve todas las órdenes abiertas."""
        try:
            return self._client.get_orders() or []
        except Exception as e:
            logger.error(f"Error obteniendo órdenes abiertas: {e}")
            return []

    def get_positions(self) -> list:
        """Devuelve las posiciones actuales."""
        try:
            return self._client.get_positions() or []
        except Exception as e:
            logger.error(f"Error obteniendo posiciones: {e}")
            return []

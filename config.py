"""
config.py — Carga toda la configuración desde el archivo .env
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Wallet & Autenticación ───────────────────────────────────────────────────
PRIVATE_KEY: str = os.getenv("PRIVATE_KEY", "")
CHAIN_ID: int = int(os.getenv("CHAIN_ID", "137"))
POLYGON_RPC: str = os.getenv("POLYGON_RPC", "https://polygon-rpc.com")

# ── URLs de la API ───────────────────────────────────────────────────────────
CLOB_HOST: str = "https://clob.polymarket.com"
GAMMA_API: str = "https://gamma-api.polymarket.com"

# ── Modo ─────────────────────────────────────────────────────────────────────
# Si DRY_RUN=true, el bot NO ejecuta órdenes reales
DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"

# ── Filtros de mercados ──────────────────────────────────────────────────────
MIN_VOLUME_USD: float = float(os.getenv("MIN_VOLUME_USD", "50000"))
MIN_LIQUIDITY_USD: float = float(os.getenv("MIN_LIQUIDITY_USD", "500"))
MAX_PRICE: float = float(os.getenv("MAX_PRICE", "0.90"))
MIN_PRICE: float = float(os.getenv("MIN_PRICE", "0.10"))

# ── Estrategia ───────────────────────────────────────────────────────────────
IMBALANCE_THRESHOLD: float = float(os.getenv("IMBALANCE_THRESHOLD", "0.65"))
PRICE_IMPROVEMENT: float = float(os.getenv("PRICE_IMPROVEMENT", "0.01"))

# ── Gestión de riesgo ────────────────────────────────────────────────────────
MAX_POSITION_USDC: float = float(os.getenv("MAX_POSITION_USDC", "5.0"))
MAX_DAILY_LOSS_USDC: float = float(os.getenv("MAX_DAILY_LOSS_USDC", "25.0"))
MAX_OPEN_POSITIONS: int = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
KELLY_FRACTION: float = float(os.getenv("KELLY_FRACTION", "0.25"))

# ── Bot ──────────────────────────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "300"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


def validate():
    """Comprueba que la configuración mínima esté presente."""
    if not PRIVATE_KEY or PRIVATE_KEY == "0xTU_CLAVE_PRIVADA_AQUI":
        raise ValueError(
            "❌ No has configurado PRIVATE_KEY en el archivo .env\n"
            "   Copia .env.example como .env y rellena tu clave privada."
        )
    if not PRIVATE_KEY.startswith("0x"):
        raise ValueError("❌ PRIVATE_KEY debe empezar con '0x'")
    if MAX_POSITION_USDC <= 0:
        raise ValueError("❌ MAX_POSITION_USDC debe ser mayor que 0")

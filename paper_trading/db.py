"""
db.py — Base de datos SQLite para el paper trading

Guarda todo el historial de operaciones simuladas, snapshots de balance
y ciclos de escaneo. No requiere ninguna instalación extra (sqlite3 es
parte de Python por defecto).

Tablas:
  trades           → cada operación simulada
  balance_snapshots → balance en el tiempo (para el gráfico)
  scan_cycles      → estadísticas de cada ciclo de escaneo
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/paper_trading.db")


def init_db():
    """Crea las tablas si no existen. Se llama una vez al arrancar."""
    DB_PATH.parent.mkdir(exist_ok=True)
    with _conn() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    TEXT    NOT NULL,       -- cuándo se ejecutó la orden simulada
                question     TEXT    NOT NULL,       -- pregunta del mercado
                condition_id TEXT    NOT NULL,       -- ID único del mercado
                side         TEXT    NOT NULL,       -- 'BUY_YES' o 'BUY_NO'
                token_id     TEXT    NOT NULL,
                entry_price  REAL    NOT NULL,       -- precio al que "compramos"
                size_usdc    REAL    NOT NULL,       -- USDC invertidos
                shares       REAL    NOT NULL,       -- acciones compradas
                status       TEXT    NOT NULL DEFAULT 'open',  -- open/won/lost
                exit_price   REAL,                  -- precio de resolución (1.0 o 0.0)
                pnl          REAL,                  -- ganancia/pérdida en USDC
                resolved_at  TEXT,                  -- cuándo se resolvió el mercado
                confidence   REAL,                  -- confianza de la estrategia (0-1)
                reason       TEXT                   -- explicación de la señal
            );

            CREATE TABLE IF NOT EXISTS balance_snapshots (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp      TEXT NOT NULL,
                balance        REAL NOT NULL,        -- balance en ese momento
                cumulative_pnl REAL NOT NULL         -- P&L acumulado
            );

            CREATE TABLE IF NOT EXISTS scan_cycles (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp        TEXT NOT NULL,
                markets_scanned  INTEGER DEFAULT 0,
                signals_found    INTEGER DEFAULT 0,
                trades_executed  INTEGER DEFAULT 0
            );
        """)


@contextmanager
def _conn():
    """Context manager para conexiones SQLite con autocommit."""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permite acceder por nombre de columna
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── Operaciones de trades ────────────────────────────────────────────────────

def insert_trade(
    question: str,
    condition_id: str,
    side: str,
    token_id: str,
    entry_price: float,
    size_usdc: float,
    shares: float,
    confidence: float,
    reason: str,
) -> int:
    """Registra una nueva operación simulada y devuelve su ID."""
    now = datetime.utcnow().isoformat()
    with _conn() as db:
        cur = db.execute(
            """
            INSERT INTO trades
                (timestamp, question, condition_id, side, token_id,
                 entry_price, size_usdc, shares, confidence, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now, question, condition_id, side, token_id,
             entry_price, size_usdc, shares, confidence, reason),
        )
        return cur.lastrowid


def get_open_trades() -> list[dict]:
    """Devuelve todas las operaciones con status='open'."""
    with _conn() as db:
        rows = db.execute(
            "SELECT * FROM trades WHERE status = 'open' ORDER BY timestamp DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def close_trade(trade_id: int, exit_price: float, pnl: float):
    """Cierra una operación con el precio de resolución y P&L calculado."""
    now = datetime.utcnow().isoformat()
    status = "won" if pnl >= 0 else "lost"
    with _conn() as db:
        db.execute(
            """
            UPDATE trades
            SET status = ?, exit_price = ?, pnl = ?, resolved_at = ?
            WHERE id = ?
            """,
            (status, exit_price, pnl, now, trade_id),
        )


def get_all_trades(limit: int = 200) -> list[dict]:
    """Devuelve las últimas N operaciones para el historial."""
    with _conn() as db:
        rows = db.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """Calcula estadísticas globales de paper trading."""
    with _conn() as db:
        total = db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        won = db.execute("SELECT COUNT(*) FROM trades WHERE status = 'won'").fetchone()[0]
        lost = db.execute("SELECT COUNT(*) FROM trades WHERE status = 'lost'").fetchone()[0]
        open_count = db.execute("SELECT COUNT(*) FROM trades WHERE status = 'open'").fetchone()[0]

        total_pnl_row = db.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status IN ('won', 'lost')"
        ).fetchone()
        total_pnl = total_pnl_row[0] if total_pnl_row else 0.0

        total_invested_row = db.execute(
            "SELECT COALESCE(SUM(size_usdc), 0) FROM trades WHERE status IN ('won', 'lost')"
        ).fetchone()
        total_invested = total_invested_row[0] if total_invested_row else 0.0

    closed = won + lost
    win_rate = (won / closed * 100) if closed > 0 else 0.0
    roi = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    return {
        "total_trades": total,
        "won": won,
        "lost": lost,
        "open": open_count,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "roi": round(roi, 2),
    }


# ─── Balance snapshots ────────────────────────────────────────────────────────

def add_balance_snapshot(balance: float, cumulative_pnl: float):
    """Guarda el balance actual para el gráfico histórico."""
    now = datetime.utcnow().isoformat()
    with _conn() as db:
        db.execute(
            "INSERT INTO balance_snapshots (timestamp, balance, cumulative_pnl) VALUES (?, ?, ?)",
            (now, balance, cumulative_pnl),
        )


def get_balance_history(limit: int = 500) -> list[dict]:
    """Devuelve el historial de balance para el gráfico de P&L."""
    with _conn() as db:
        rows = db.execute(
            "SELECT * FROM balance_snapshots ORDER BY timestamp ASC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Ciclos de escaneo ────────────────────────────────────────────────────────

def log_scan_cycle(markets_scanned: int, signals_found: int, trades_executed: int):
    """Registra un ciclo de escaneo del bot."""
    now = datetime.utcnow().isoformat()
    with _conn() as db:
        db.execute(
            """
            INSERT INTO scan_cycles (timestamp, markets_scanned, signals_found, trades_executed)
            VALUES (?, ?, ?, ?)
            """,
            (now, markets_scanned, signals_found, trades_executed),
        )


def get_recent_cycles(limit: int = 20) -> list[dict]:
    """Devuelve los últimos ciclos de escaneo."""
    with _conn() as db:
        rows = db.execute(
            "SELECT * FROM scan_cycles ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

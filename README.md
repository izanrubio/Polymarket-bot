# 🤖 Polymarket Bot

Bot de trading automatizado para [Polymarket](https://polymarket.com) — el mayor mercado de predicción descentralizado.

## ¿Qué hace este bot?

1. **Escanea** mercados activos en Polymarket buscando los más líquidos
2. **Analiza** el order book de cada mercado buscando desequilibrios de compradores/vendedores
3. **Opera** comprando el lado con más presión (si hay más compradores, compra YES; si hay más vendedores, compra NO)
4. **Gestiona el riesgo** con límites de pérdida diaria, tamaño máximo por operación y número máximo de posiciones

> **Por defecto el bot está en modo DRY RUN** — solo simula las operaciones sin usar dinero real. Activa el modo live cuando estés listo.

---

## Requisitos previos

- Python 3.10 o superior
- Una wallet en Polygon (MetaMask, etc.) con USDC
- La clave privada de esa wallet (la clave que empieza con `0x`)

> **¿Cómo consigo USDC en Polygon?**
> 1. Compra USDC en cualquier exchange (Binance, Coinbase, Kraken...)
> 2. Retíralo a tu dirección de Polygon (red Polygon/MATIC)
> 3. Deposítalo en Polymarket: ve a polymarket.com → Wallet → Deposit

---

## Instalación paso a paso

### 1. Clonar el repositorio
```bash
git clone https://github.com/izanrubio/polymarket-bot.git
cd polymarket-bot
```

### 2. Crear entorno virtual e instalar dependencias
```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 3. Configurar las variables de entorno
```bash
cp .env.example .env
```
Abre `.env` con tu editor y rellena al menos:
```
PRIVATE_KEY=0xtu_clave_privada_aqui
```
El resto de parámetros tienen valores por defecto razonables.

### 4. Crear la carpeta de logs
```bash
mkdir logs
```

---

## Uso

### Modo seguro: solo escanear mercados (sin operar)
```bash
python main.py --scan
```
Muestra qué mercados y señales encontraría, sin ejecutar nada.

### Modo dry run: simular operaciones
```bash
python main.py --once
```
Ejecuta un ciclo completo pero sin enviar órdenes reales.

### Modo bucle: escanear cada 5 minutos continuamente
```bash
python main.py
```
Pulsa `Ctrl+C` para detener el bot limpiamente.

### Modo live (¡dinero real!)
Cuando estés seguro, edita `.env`:
```
DRY_RUN=false
```
Y ejecuta:
```bash
python main.py
```

---

## Estructura del proyecto

```
polymarket-bot/
├── main.py           ← Punto de entrada, bucle principal
├── config.py         ← Carga configuración del .env
├── requirements.txt  ← Dependencias Python
├── .env.example      ← Plantilla de configuración
├── .env              ← Tu configuración (¡no subir a git!)
├── logs/             ← Archivos de log diarios
└── src/
    ├── client.py     ← Conexión con Polymarket (autenticación L1/L2)
    ├── scanner.py    ← Búsqueda de mercados (API Gamma + CLOB)
    ├── strategy.py   ← Lógica de la estrategia (imbalance del order book)
    ├── risk.py       ← Gestión de riesgo (límites de pérdida, posiciones)
    └── trader.py     ← Ejecución de órdenes
```

---

## Parámetros clave en `.env`

| Parámetro | Por defecto | Descripción |
|-----------|-------------|-------------|
| `DRY_RUN` | `true` | `true` = solo simula, `false` = dinero real |
| `MAX_POSITION_USDC` | `5.0` | Máximo USDC por operación |
| `MAX_DAILY_LOSS_USDC` | `25.0` | El bot se para si pierde esta cantidad en el día |
| `MAX_OPEN_POSITIONS` | `3` | Máximo de posiciones simultáneas |
| `IMBALANCE_THRESHOLD` | `0.65` | % del order book en un lado para generar señal |
| `MIN_VOLUME_USD` | `50000` | Volumen mínimo del mercado para escanearlo |
| `SCAN_INTERVAL_SECONDS` | `300` | Cada cuántos segundos escanea |
| `KELLY_FRACTION` | `0.25` | Fracción del Kelly completo (más bajo = más conservador) |

---

## ¿Cómo funciona la estrategia?

El bot usa **Order Book Imbalance** — una técnica de microestructura de mercado:

```
Order Book de un mercado ejemplo:

   BIDS (compradores)        ASKS (vendedores)
   ──────────────────        ─────────────────
   200 USDC @ 0.62          100 USDC @ 0.65
   150 USDC @ 0.61          80  USDC @ 0.66
   100 USDC @ 0.60          60  USDC @ 0.67
   ────────────────────────────────────────
   Total bids: 450 USDC     Total asks: 240 USDC

   Imbalance = 450 / (450+240) = 65% en bids → SEÑAL DE COMPRA YES
```

Cuando hay significativamente más presión compradora que vendedora, el precio tiende a subir. El bot compra antes de ese movimiento.

El **tamaño de la posición** se calcula con el **Criterio de Kelly**, una fórmula matemática que optimiza cuánto apostar según tu ventaja estadística.

---

## ⚠️ Avisos importantes

- **Riesgo financiero**: El trading en mercados de predicción implica riesgo de pérdida total del capital invertido.
- **No es asesoramiento financiero**: Este bot es una herramienta educativa/experimental.
- **Empieza pequeño**: Usa valores bajos en `MAX_POSITION_USDC` (1-5 USDC) mientras aprendes.
- **Clave privada**: Nunca compartas tu `.env` ni subas la clave privada a GitHub. El `.gitignore` ya excluye `.env`.
- **Prueba primero**: Usa `DRY_RUN=true` durante varios días antes de pasar a dinero real.

---

## Solución de problemas

**"No has configurado PRIVATE_KEY"**
→ Copia `.env.example` como `.env` y rellena tu clave privada.

**"Error obteniendo credenciales L2"**
→ Comprueba que tu clave privada es correcta y que la wallet tiene algo de MATIC para gas.

**"No se encontraron mercados"**
→ Prueba a reducir `MIN_VOLUME_USD` a `10000` en el `.env`.

**El bot no ejecuta órdenes**
→ Comprueba que `DRY_RUN=false` en el `.env` (por defecto está en `true`).

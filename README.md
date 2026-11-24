# ◈ SENTINELA OSIRIS

**Monitor OSINT de anomalías marítimas** — fusión de señales AIS + radar/SAR + simulador
para detección de apagados de AIS, ferries "oscuros", narcolanchas, encuentros en mar
y suplantación (GPS spoofing).

Zona por defecto: **Estrecho de Gibraltar · Mar de Alborán · Golfo de Cádiz**.

> ⚠️ **Lee el [DISCLAIMER](DISCLAIMER.md) antes de usar.** Esto es una herramienta
> OSINT heurística, **no** un sistema oficial de vigilancia ni de alerta temprana.

---

## ✨ Características

- 🛰 **Fusión de señales** — AIS real + contactos externos (radar/SAR/dron) + simulador
- 👻 **Detección de apagones AIS** — zona de deriva, corredores ferry, alta velocidad, nocturno
- 🎯 **Aproximación a costa** — rumbo directo a puntos sensibles (Doñana, Trafalgar, Los Lances…)
- ⛴ **Ferries anómalos** — fuera de corredor, detenidos en mitad de la travesía
- 🤝 **Encuentros en mar** — posibles trasbordos (dos buques lentos, cerca, ≥8 min)
- 🛰 **GPS spoofing** — saltos de posición imposibles
- 👥 **Convoyes** — grupo de lanchas rápidas en formación
- 🧠 **IA opcional (DeepSeek)** — dossier por embarcación + parte global de situación
- 🗺 **Panel web** — Leaflet + heatmap + capas conmutables (trayectos, arcos, apagados, puertos…)
- ⚡ **Reloj virtual acelerable** — demos a ×8, ×30, ×60
- 📤 **Exportación** — GeoJSON y CSV de alertas activas
- 📜 **Histórico SQLite** — `sentinela.db` con todas las alertas registradas

---

## 🧰 Requisitos

- **Python 3.9+**
- **pip**
- Navegador moderno

---

## 🚀 Instalación

```bash
git clone https://github.com/Condor2026/Sentinel_Osiris_X.git
cd Sentinel_Osiris_X
./install.sh
```

O manualmente:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

## ▶️ Arranque

```bash
./run.sh
```

Abre el panel en: **<http://127.0.0.1:5023>**

Si el puerto 5023 está ocupado, el script lo libera automáticamente
(o busca el siguiente libre si usas `--no-kill`).

### Opciones

```bash
python SentinelOsirisMar.py [opciones]

  --host 127.0.0.1     Host de escucha
  --port 5023          Puerto (por defecto 5023)
  --demo               Forzar modo simulación
  --no-kill            No matar el proceso que ocupa el puerto
  --no-browser         No abrir el navegador automáticamente
```

**Modo demo rápido:**

```bash
./run.sh --demo --no-browser
```

---

## 🔌 Fuentes de datos

Todas son **opcionales**. Se combinan; si no hay ninguna, arranca el simulador.

### 1. AIS real — AISStream.io (gratuito)

1. Regístrate en <https://aisstream.io/> y obtén tu API key.
2. Pégala en **⚙ Ajustes** del panel o en `AISSTREAM_KEY` del `.env`.
3. El motor se conecta por WebSocket y procesa AIS real en vivo.

### 2. Receptor AIS propio — RTL-SDR

1. Instala un decodificador NMEA: [AIS-catcher](https://github.com/jvde-github/AIS-catcher) o [rtl-ais](https://github.com/dgiardini/rtl-ais).
2. Configúralo para enviar NMEA por UDP a `127.0.0.1` (p. ej. puerto `10110`).
3. En **⚙ Ajustes** → "Puerto UDP NMEA" pon `10110`.
4. El motor parsea mensajes AIS tipo `!AIVDM` / `!AIVDO` (1, 2, 3, 5, 18, 24).

> No necesitas cuenta ni clave. Solo una antena y un receptor RTL-SDR (~30 €).

### 3. Contactos externos (radar / SAR / dron / GFW)

Envía detecciones sin AIS por `POST /api/contactos`:

```bash
curl -X POST http://127.0.0.1:5023/api/contactos \
  -H "Content-Type: application/json" \
  -d '[{"id":"SAR-2026-001","lat":36.10,"lon":-5.50,"sog":30,"cog":95}]'
```

Útil para integrar:
- Radar costero propio
- Detecciones Sentinel-1 / GFW
- Drones SAR
- Cualquier otro sensor con lat/lon

### 4. Simulador (modo demo)

Sin claves ni receptor, arranca solo. Genera escenarios realistas:

- Ferries en corredores (Algeciras-Ceuta, Tarifa-Tánger, Almería-Melilla…)
- Cargo y pesca navegando
- Embarcaciones de recreo con GPS spoofing ocasional
- **Narcolanchas** apareciendo desde el sur (35.5°N) hacia la costa
- **Encuentros en mar** entre un pesquero y una lancha rápida
- Apagones AIS programados

---

## 🌐 API HTTP

| Endpoint | Descripción |
|----------|-------------|
| `GET /` | Panel web (HTML) |
| `GET /api/snapshot?min=4` | Estado actual de embarcaciones + stats |
| `GET /api/static` | Puertos, costa sensible, corredores ferry, bbox |
| `GET /api/vessel/{mmsi}` | Dossier completo de una embarcación |
| `GET /api/sources` | Estado de fuentes (AISStream, UDP, Simulador, IA) |
| `POST /api/config` | Actualizar claves y opciones |
| `POST /api/contactos` | Ingerir detecciones sin AIS |
| `POST /api/ai/vessel/{mmsi}` | Análisis IA de una embarcación |
| `POST /api/ai/briefing` | Parte global de situación con IA |
| `GET /api/history?limit=100` | Histórico SQLite |
| `GET /api/export/geojson` | Exportar alertas activas (GeoJSON) |
| `GET /api/export/csv` | Exportar alertas activas (CSV) |

---

## 🎯 Motor de detección

Cada embarcación acumula **puntos** según las señales detectadas. Umbral de
alarma por defecto: **4 puntos** (configurable en el panel).

| Código | Señal | Puntos | Contexto |
|--------|-------|--------|----------|
| `DARK` | AIS apagado / perdido | +2 (cargo) / +3 (resto) | >15 min sin señal, iba a ≥4 kn |
| `VELOCIDAD` | Alta velocidad (lancha rápida) | +2…+6 | ≥25 / ≥30 / ≥40 kn según tipo |
| `APROXIMACION` | Rumbo directo a costa sensible | +3 / +4 | <45 km, rumbo ±25°, ≥18 kn |
| `ENCUENTRO` | Encuentro en mar (posible trasbordo) | +4 | 2 buques lentos, <0.4 km, ≥8 min |
| `CONTACTO` | Detección sin AIS (radar/SAR) | +3 | Contacto externo en zona AIS activa |
| `FERRY` | Ferry fuera de corredor o detenido | +2 / +3 | >w km del corredor, o parado dentro |
| `ZIGZAG` | Maniobras evasivas | +2 | ≥3 cambios de rumbo >35° en 15 min |
| `CONVOY` | Grupo de lanchas en formación | +3 | ≥3 buques ≥20 kn, mismo rumbo, <2 km |
| `SPOOF` | Salto de posición imposible | +4 | Velocidad implícita >70 kn |
| `APAGONES` | Apagones recurrentes | +1…+3 | ≥2 en 24 h |
| `COSTA` | Último rastro junto a costa | +2 | <6 km de punto sensible |
| `IDENTIDAD` | Sin nombre/tipo AIS a alta velocidad | +1 | >600 s sin estáticos, ≥20 kn |
| `NOCTURNO` | Navegación rápida de noche | +1 | 22:00–06:00, ≥20 kn, pequeño |
| `MMSI` | MMSI inválido o inexistente | +1 | No 9 dígitos o MID inválido |
| `FUSION` | ≥3 señales independientes cruzadas | +1 | Evidencia combinada |

### Niveles de severidad

| Score | Nivel | Color |
|-------|-------|-------|
| 8–10 | 🔴 **CRÍTICA** | `#ff2d55` |
| 6–7 | 🟠 **ALTA** | `#ff9500` |
| 4–5 | 🟡 **MEDIA** | `#ffd60a` |
| 1–3 | ⚪ Base | (no se muestra por defecto) |

> ⚠️ **El motor es heurístico.** Un apagón AIS puede ser pérdida de cobertura
> terrestre, no necesariamente algo ilícito. **Contrasta siempre** con imagen
> SAR, otros receptores y patrulleras.

---

## 🧠 IA (DeepSeek, opcional)

Sin clave funciona un **análisis local** basado en las señales del motor.
Con clave (`DEEPSEEK_API_KEY` o en ⚙ Ajustes) obtienes:

- **Dossier por embarcación:** probabilidad de actividad ilícita, indicios a
  favor y en contra, qué verificar a continuación.
- **Parte global:** patrones, conexiones entre alertas, prioridades, falsos
  positivos probables.

Configura tu clave en <https://platform.deepseek.com/>.

---

## ⚙️ Configuración

Todas las variables son opcionales. Copia `.env.example` a `.env`:

| Variable | Uso |
|----------|-----|
| `DEEPSEEK_API_KEY` | IA (opcional) |
| `DEEPSEEK_URL` | Endpoint IA (por defecto api.deepseek.com) |
| `AISSTREAM_KEY` | AIS real vía AISStream.io |
| `PORT` / `HOST` | Servidor local |

> También puedes configurar las claves desde el panel (⚙ Ajustes).
> Se guardan en `sentinela_config.json` con permisos `0600`.

---

## 📁 Estructura

```
Sentinel_Osiris_X/
├── SentinelOsirisMar.py    # Servidor + motor + UI
├── requirements.txt
├── install.sh
├── run.sh
├── .env.example
├── .gitignore
├── README.md
├── DISCLAIMER.md
├── SECURITY.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── ACCESSIBILITY.md
├── CHANGELOG.md
├── LICENSE
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   ├── feature_request.md
│   │   ├── accessibility.md
│   │   └── config.yml
│   └── PULL_REQUEST_TEMPLATE.md
├── sentinela.db               # (generado) histórico SQLite
└── sentinela_config.json      # (generado) claves y opciones
```

---

## 🗺 Interfaz

- **Panel lateral (izquierda):**
  - Filtro de umbral de alarma (1–10)
  - Filtro por tipo de embarcación (ferry, pesca, recreo, cargo, desconocido)
  - Filtro por tipo de señal (👻, 💨, 🎯, 🤝, 📡…)
  - Lista de alertas activas ordenadas por score
  - Estado de fuentes (AISStream / UDP / Simulador / IA)
  - Botón **🧠 Parte IA**

- **Mapa (derecha):**
  - Trayectorias (color según severidad)
  - Arcos origen→posición actual
  - 👻 Posición estimada + cono de incertidumbre (pulsante)
  - 🎯 Línea directa al objetivo (costa sensible)
  - Puertos, corredores ferry, costa sensible
  - Capas conmutables + heatmap + OpenSeaMap

- **Dossier (clic en cualquier alerta):**
  - MMSI, tipo, velocidad, rumbo, destino, fuente
  - Lista de señales con puntuación
  - Botones: **🧠 Analizar con IA** · Centrar · Copiar coords

---

## ⚖️ Aviso legal

Ver [DISCLAIMER.md](DISCLAIMER.md). Uso **educativo e informativo**.

- **No** es un sistema oficial de alerta temprana.
- **No** sustituye a Salvamento Marítimo, Guardia Civil, Aduanas ni Frontex.
- **No** garantiza exactitud ni actualidad de los datos AIS.
- El motor puede producir **falsos positivos y falsos negativos**.
- **No uses esta herramienta para vigilancia de particulares, doxxing ni
  actividades ilegales.**
- Respeta las leyes locales, los ToS de AISStream / DeepSeek, y el derecho
  marítimo aplicable.

## 🤝 Contribuir

Ver [CONTRIBUTING.md](CONTRIBUTING.md) y [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
**Regla de oro:** toda nueva regla de detección debe evitar falsos positivos
con contexto (puerto, noche, tipo de buque, corredor).

## ♿ Accesibilidad

Ver [ACCESSIBILITY.md](ACCESSIBILITY.md). El panel se está alineando con
**WCAG 2.1 nivel AA**. Se aceptan PRs con etiqueta `accessibility`.

## 🔒 Seguridad

Ver [SECURITY.md](SECURITY.md). **No abras issues públicos para
vulnerabilidades** — usa
[GitHub Security Advisories](https://github.com/Condor2026/Sentinel_Osiris_X/security/advisories/new).

## 📄 Licencia

MIT — ver [LICENSE](LICENSE).

---

**◈ SENTINELA OSIRIS** · OSINT marítimo heurístico · v8.0

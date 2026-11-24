
      PROXIMAMENTE EN DICIEMBRE 2026

# 🛰️ SentinelMar — Global Early Warning OSINT Monitor

![Version](https://img.shields.io/badge/version-2.4-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-success)

Monitor **OSINT** de alerta temprana global: agrega alertas de misiles, drones, ataques, sismos/explosiones, comunicados oficiales y prensa de guerra desde **más de 20 fuentes públicas** (sin necesidad de claves API para funcionar).

Servidor local en `http://127.0.0.1:5000` con dashboard web y API JSON.

---

## ✨ Características

- 🚨 **Alertas en tiempo real** de Israel (Tzeva Adom, Oref) y Ucrania (alerts.com.ua, Ubilling, Kyiv Digital, Neptun).
- 🌍 **Sensores sísmicos** (USGS + EMSC + GEOFON) con heurística de candidatos a explosión.
- 🔥 **NASA FIRMS**, **NASA EONET**, **GDELT GEO**.
- 📰 **Prensa de guerra y OSINT verificable** (ISW, Bellingcat, Oryx, Kyiv Independent, Meduza…).
- 🏛️ **Comunicados oficiales** (Dept. Estado USA, FCDO UK, OTAN, Kremlin, IAEA, ONU…).
- 📡 **Telegram** (canales públicos) + buscador nativo opcional con Telethon.
- 🧠 **Credibilidad A/B/C/D** (oficial / prensa-OSINT / parte implicada / no verificado).
- 💾 **Historial en SQLite** con deduplicación y exportación CSV/JSON.
- 🌐 **Traducción** automática opcional (Google gtx + MyMemory, DeepL / LibreTranslate).
- ⚡ **Cache TTL 15s** y ejecución paralela de fuentes.

---

## 📚 Fuentes integradas

| Categoría | Fuentes |
|-----------|---------|
| **Israel** | Tzeva Adom, Oref (oficial) |
| **Ucrania** | alerts.com.ua, Ubilling, alerts.in.ua, Kyiv Digital, Neptun |
| **Satélite / global** | NASA FIRMS, NASA EONET, GDELT GEO, GDELT Cloud, World Monitor |
| **Sísmico** | USGS, EMSC, GEOFON |
| **Prensa / OSINT** | ISW, Bellingcat, Oryx, Kyiv Independent, Meduza, Moscow Times, Critical Threats, TWZ, Defense One, ONU Noticias |
| **Comunicados oficiales** | Dept. Estado USA, FCDO UK, MoD UK, Kremlin, OTAN, IAEA, ONU, CENTCOM, Pentágono, Casa Blanca, UE |
| **Medios estatales** (cred. C) | TASS, RT, Sputnik, IRNA, Tasnim, Press TV, Xinhua, CGTN, WAFA, SANA, Anadolu, Ukrinform |
| **Telegram** | Rybar, Readovka, WarGonzo, DeepState, UA Air Force, Estado Mayor UA, IDF, SBU, MID Rusia, Military Summary, Intel Slava |

> ⚠️ **Ninguna fuente garantiza veracidad en zona de guerra.** Los niveles de credibilidad indican el tipo de fuente, no la certeza del hecho.

---

## 🚀 Instalación rápida

```bash
git clone https://github.com/Condor2026/Sentinel_Osiris_X.git
cd Sentinel_Osiris_X
chmod +x install.sh
./install.sh
nano .env      # opcional: claves API
./run.sh
```

Abre 👉 http://127.0.0.1:5000

### Instalación manual

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python SentinelMar.py
```

### Dependencia opcional

```bash
pip install telethon               # Búsqueda nativa de Telegram
```

---

## ⚙️ Configuración

Copiá `.env.example` a `.env` y editá lo que necesites. Todas las variables son opcionales.

---

## 🖥️ Uso

```bash
# Arrancar el servidor
python SentinelMar.py

# Host/puerto personalizados
MONITOR_HOST=0.0.0.0 MONITOR_PORT=8080 python SentinelMar.py

# Login único de Telethon
python SentinelMar.py --tg-login
```

---

## 🔌 Endpoints API

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/alerts?force=1` | Alertas agregadas + stats |
| `GET` | `/api/health` | Estado del servidor |
| `GET` | `/api/sources` | Estado de cada fuente |
| `GET` | `/api/history?hours=24` | Historial desde SQLite |
| `GET` | `/api/export?format=csv` | Exportar historial |
| `GET/POST` | `/api/telegram/channels` | Listar / añadir canal |
| `DELETE` | `/api/telegram/channels/<id>` | Desactivar canal |
| `GET` | `/api/telegram/search?q=` | Buscar canales |
| `GET` | `/api/telegram/preview` | Vista previa |

---

## 🏗️ Estructura

```
Sentinel_Osiris_X/
├── SentinelMar.py
├── requirements.txt
├── install.sh
├── run.sh
├── .env.example
├── .gitignore
├── LICENSE
├── DISCLAIMER.md
└── README.md
```

---

## ⚠️ Disclaimer

Proyecto OSINT puro con fines de investigación. Las alertas pueden ser falsos positivos. **No sustituye** fuentes oficiales. Ver [DISCLAIMER.md](DISCLAIMER.md).

---

## 📄 Licencia

MIT — ver [LICENSE](LICENSE).

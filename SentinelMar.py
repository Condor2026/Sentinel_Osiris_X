#!/usr/bin/env python3
"""
SENTINELA OSIRIS v8 - Fusión de señales para detección de anomalías marítimas
(apagados de AIS, ferries "oscuros", narcolanchas, encuentros en mar, suplantación).
- By Condor2026
Arranque:   python sentinela_osiris.py            (abre http://127.0.0.1:5023)
Opciones:   --port 5023  --demo  --no-kill  --no-browser

Fuentes de datos (todas opcionales, se combinan):
  1. AISStream.io  (API gratuita, clave en Ajustes o env AISSTREAM_KEY)  -> AIS real global
  2. Receptor AIS propio (RTL-SDR + AIS-catcher/rtl-ais) enviando NMEA por UDP -> SIN API
  3. POST /api/contactos  -> radar, SAR (Sentinel-1/GFW), drones, lo que tengas
  4. Simulador con escenarios realistas -> funciona sin nada (modo demo)
IA: DeepSeek (clave en Ajustes o env DEEPSEEK_API_KEY). Sin clave, explicación local.

Dependencias: pip install fastapi uvicorn requests websockets   (psutil opcional)
"""
import os, sys, json, math, time, random, socket, threading, sqlite3, csv, io, subprocess
import signal, argparse, webbrowser, asyncio, re
from collections import deque, defaultdict
from datetime import datetime

try:
    import uvicorn
    from fastapi import FastAPI, Body
    from fastapi.responses import HTMLResponse, JSONResponse, Response
except ImportError:
    sys.exit("Falta: pip install fastapi uvicorn requests websockets")
try:
    import requests
except ImportError:
    requests = None
try:
    import websockets
except ImportError:
    websockets = None

VERSION = "8.0"
CFG_FILE = "sentinela_config.json"
CFG = {"deepseek_key": os.getenv("DEEPSEEK_API_KEY", ""), "aisstream_key": os.getenv("AISSTREAM_KEY", ""),
       "udp_port": 0, "udp_host": "127.0.0.1", "factor": 8, "force_demo": False}
try:
    with open(CFG_FILE) as f:
        CFG.update(json.load(f))
except Exception:
    pass


def save_cfg():
    try:
        with open(CFG_FILE, "w") as f:
            json.dump(CFG, f)
        os.chmod(CFG_FILE, 0o600)
    except Exception:
        pass


# ───────────────────────── Reloj virtual (para acelerar la demo) ─────────────────────────
class Clock:
    def __init__(s): s.t0 = time.time(); s.v0 = s.t0; s.f = 1.0
    def now(s): return s.v0 + (time.time() - s.t0) * s.f
    def set_factor(s, f):
        n = s.now(); s.v0 = n; s.t0 = time.time(); s.f = float(f)


CLK = Clock()

# ───────────────────────── Geografía ─────────────────────────
def hav(la1, lo1, la2, lo2):
    p1, p2 = math.radians(la1), math.radians(la2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 12742.0 * math.asin(math.sqrt(a))


def bearing(la1, lo1, la2, lo2):
    p1, p2, dl = math.radians(la1), math.radians(la2), math.radians(lo2 - lo1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def dest(la, lo, brg, km):
    d = km / 6371.0; b = math.radians(brg); p1 = math.radians(la); l1 = math.radians(lo)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def angdiff(a, b): return abs((a - b + 180) % 360 - 180)


def seg_dist(p, a, b):
    kx = 111.32 * math.cos(math.radians(p[0])); ky = 110.57
    ax, ay = (a[1] - p[1]) * kx, (a[0] - p[0]) * ky
    bx, by = (b[1] - p[1]) * kx, (b[0] - p[0]) * ky
    dx, dy = bx - ax, by - ay; L2 = dx * dx + dy * dy
    t = -(ax * dx + ay * dy) / L2 if L2 else 0
    tc = max(0, min(1, t))
    return math.hypot(ax + dx * tc, ay + dy * tc), t


BBOX = (34.8, -7.6, 37.6, -1.4)  # lat_min, lon_min, lat_max, lon_max (Estrecho + Alborán + Golfo de Cádiz)
PORTS = [("Algeciras", 36.13, -5.43, 4), ("Tarifa", 36.01, -5.60, 2), ("Ceuta", 35.89, -5.31, 3),
         ("Tánger Med", 35.89, -5.50, 5), ("Tánger", 35.79, -5.81, 3), ("Gibraltar", 36.14, -5.35, 3),
         ("La Línea/Sotogrande", 36.17, -5.33, 2.5), ("Málaga", 36.71, -4.42, 4), ("Almería", 36.83, -2.47, 3),
         ("Motril", 36.72, -3.52, 2.5), ("Cádiz", 36.53, -6.29, 4), ("Huelva", 37.20, -6.95, 4),
         ("Barbate", 36.19, -5.92, 2), ("Estepona", 36.42, -5.15, 2), ("Marbella", 36.49, -4.77, 1.5),
         ("Melilla", 35.29, -2.94, 3), ("Sanlúcar", 36.78, -6.35, 2.5)]
COSTA = [("Guadalquivir/Doñana", 36.95, -6.45), ("Trafalgar", 36.18, -6.04), ("Zahara", 36.07, -5.84),
         ("Los Lances (Tarifa)", 36.05, -5.65), ("Campo de Gibraltar", 36.17, -5.34), ("Sotogrande", 36.28, -5.28),
         ("Estepona", 36.40, -5.14), ("Marbella", 36.48, -4.85), ("Rincón de la Victoria", 36.71, -4.28),
         ("Motril", 36.70, -3.55), ("Poniente almeriense", 36.75, -2.70)]
FERRY = [("Algeciras-Ceuta", (36.13, -5.43), (35.89, -5.31), 6), ("Algeciras-Tánger Med", (36.13, -5.43), (35.89, -5.50), 6),
         ("Tarifa-Tánger", (36.01, -5.60), (35.79, -5.81), 6), ("Almería-Melilla", (36.83, -2.47), (35.29, -2.94), 10),
         ("Málaga-Melilla", (36.71, -4.42), (35.29, -2.94), 10)]
EXEMPT = {35, 50, 51, 52, 53, 54, 55, 58, 59}
SMALL = {0, 30, 36, 37}
GAP_S = 900          # 15 min virtuales sin señal = apagón
DARK_MAX = 3 * 3600


def is_exempt(t): return t in EXEMPT or 40 <= t <= 49


def near_port(la, lo, extra=0):
    for n, pla, plo, r in PORTS:
        if hav(la, lo, pla, plo) <= r + extra: return n
    return None


def edge(la, lo, m=0.2): return la < BBOX[0] + m or lo < BBOX[1] + m or la > BBOX[2] - m or lo > BBOX[3] - m


# ───────────────────────── Modelo ─────────────────────────
class V:
    def __init__(s, mmsi, t):
        s.mmsi = mmsi; s.name = ""; s.type = 0; s.dest = ""; s.first = t
        s.t = 0; s.lat = s.lon = 0.0; s.sog = 0.0; s.cog = 360.0
        s.track = deque(maxlen=240); s.gaps = deque(maxlen=30); s.events = {}
        s.contact = False; s.static_seen = False; s.src = ""
        s.score = 0; s.reasons = []; s.dark = False; s.dr = None; s.unc = 0; s.target = None; s.proj = []; s.lvl = 0

    def to_dict(s, full):
        d = {"id": s.mmsi, "n": s.name, "la": round(s.lat, 5), "lo": round(s.lon, 5), "s": round(s.sog, 1),
             "c": round(s.cog), "t": s.type, "sc": s.score, "dk": s.dark, "ct": s.contact, "age": round(CLK.now() - s.t)}
        if full:
            d["r"] = [[c, p, x] for c, p, x in s.reasons]
            d["trk"] = [[round(p[1], 4), round(p[2], 4)] for p in list(s.track)[-60:]]
            d["pr"] = [[round(a, 4), round(b, 4)] for a, b in s.proj]
            if s.dr: d["dr"] = [round(s.dr[0], 4), round(s.dr[1], 4)]; d["unc"] = round(s.unc, 1)
            if s.target: d["tg"] = s.target
        return d


class Store:
    def __init__(s):
        s.v = {}; s.lock = threading.RLock(); s.sources = {}; s.stats = {}; s.pairs = {}

    def clear(s):
        with s.lock: s.v.clear(); s.pairs.clear()

    def set_src(s, name, status, msg="", inc=0):
        o = s.sources.get(name, {"count": 0})
        o.update(status=status, msg=msg, count=o["count"] + inc, last=time.time() if inc else o.get("last"))
        s.sources[name] = o

    def set_static(s, mmsi, name=None, vtype=None, dest_=None):
        with s.lock:
            v = s.v.get(mmsi) or s.v.setdefault(mmsi, V(mmsi, CLK.now()))
            if name: v.name = name; v.static_seen = True
            if vtype is not None: v.type = int(vtype); v.static_seen = True
            if dest_: v.dest = dest_

    def update(s, mmsi, lat, lon, sog=None, cog=None, src="", contact=False):
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0): return
        t = CLK.now()
        with s.lock:
            v = s.v.get(mmsi) or s.v.setdefault(mmsi, V(mmsi, t))
            if v.t:
                dt = t - v.t
                if dt <= 0: return
                d = hav(v.lat, v.lon, lat, lon)
                if sog is None: sog = d / 1.852 / (dt / 3600) if dt > 5 else v.sog
                if cog is None and d > 0.02: cog = bearing(v.lat, v.lon, lat, lon)
                if not contact:
                    if dt > GAP_S and v.sog >= 4: v.gaps.append((v.t, t, d))
                    elif dt < 1800 and d > 1 and d / 1.852 / (dt / 3600) > 70: v.events["SPOOF"] = t + 1800
            v.sog = sog if (sog is not None and 0 <= sog < 102) else 0.0
            v.cog = cog if (cog is not None and 0 <= cog < 360) else 360.0
            v.t, v.lat, v.lon, v.contact, v.src = t, lat, lon, contact, src
            if not v.track or t - v.track[-1][0] >= 30: v.track.append((t, lat, lon, v.sog, v.cog))
        s.set_src(src, "ok", inc=1)

    def snapshot(s, minscore):
        now = CLK.now()
        with s.lock:
            out = [v.to_dict(v.score >= 4) for v in s.v.values()
                   if (v.score >= max(1, minscore) if minscore > 0 else (now - v.t < 1800 or v.score >= 4))]
            return {"t": now, "v": out, "stats": s.stats, "factor": CLK.f}


STORE = Store()
DB = sqlite3.connect("sentinela.db", check_same_thread=False); DBL = threading.Lock()
DB.execute("CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, mmsi TEXT, name TEXT, score INT, codes TEXT, reasons TEXT, lat REAL, lon REAL)")
DB.commit()

# ───────────────────────── Motor de detección (fusión de señales) ─────────────────────────
def zigzag(v, now):
    pts = [p for p in v.track if now - p[0] < 900 and p[4] < 360]
    if len(pts) < 6: return False
    ds = [(b[4] - a[4] + 180) % 360 - 180 for a, b in zip(pts, pts[1:])]
    big = [d for d in ds if abs(d) > 35]
    return sum(1 for x, y in zip(big, big[1:]) if x * y < 0) >= 3


def rules(v, now, grid):
    R = []
    add = lambda c, p, x: R.append((c, p, x))
    age = now - v.t; typ = v.type; ex = is_exempt(typ); small = typ in SMALL
    hour = datetime.fromtimestamp(now).hour; night = hour >= 22 or hour < 6
    v.dark = False; v.dr = None; v.target = None; v.proj = []
    if ex: return R
    port = near_port(v.lat, v.lon, 1.0)
    ncoast = min(COSTA, key=lambda c: hav(v.lat, v.lon, c[1], c[2]))
    dcoast = hav(v.lat, v.lon, ncoast[1], ncoast[2])

    if age > GAP_S:
        if v.contact: return []
        if age < DARK_MAX and v.sog >= 4 and not near_port(v.lat, v.lon, 4) and not edge(v.lat, v.lon):
            v.dark = True
            cargo = 70 <= typ <= 89
            add("DARK", 2 if cargo else 3, "AIS apagado/perdido hace %d min (iba a %.0f kn)" % (age / 60, v.sog))
            if 60 <= typ <= 69: add("DARK", 2, "Ferry/pasaje sin señal AIS en ruta")
            if v.sog >= 20: add("DARK", 2, "Apagón a alta velocidad")
            if night: add("NOCTURNO", 1, "Apagón en horario nocturno")
            if dcoast < 6: add("COSTA", 2, "Último rastro junto a %s (posible llegada/alijo)" % ncoast[0])
            hh = min(age, DARK_MAX) / 3600; dist = v.sog * 1.852 * hh
            v.dr = dest(v.lat, v.lon, v.cog if v.cog < 360 else 0, dist); v.unc = max(1.0, dist * 0.25)
            if v.cog < 360: v.proj = [dest(v.dr[0], v.dr[1], v.cog, v.sog * 1.852 * m / 60) for m in (10, 20, 40)]
            for n, a, b, w in FERRY:
                if 60 <= typ <= 69:
                    d, t = seg_dist((v.lat, v.lon), a, b)
                    if -0.1 <= t <= 1.1 and d <= w * 1.5: add("FERRY", 2, "Apagado dentro del corredor %s" % n); break
        g24 = sum(1 for g in v.gaps if now - g[1] < 86400)
        if g24 >= 2: add("APAGONES", min(3, g24), "Apagones recurrentes (%d en 24 h)" % g24)
        return R

    # --- vessel activo ---
    if v.contact: add("CONTACTO", 3, "Contacto sin AIS detectado por radar/SAR")
    if v.sog >= 40: p = 6
    elif v.sog >= 30: p = 4
    elif v.sog >= 25 and small: p = 2
    else: p = 0
    if p and typ in (36, 37) and v.sog < 38: p = max(0, p - 2)
    if p: add("VELOCIDAD", p, "Velocidad %.0f kn (perfil lancha rápida)" % v.sog)
    if night and v.sog >= 20 and small and not port: add("NOCTURNO", 1, "Navegación rápida de noche")

    if v.sog >= 18 and v.cog < 360 and not port:
        best = None
        for n, la, lo in COSTA:
            d = hav(v.lat, v.lon, la, lo)
            if d < 45 and angdiff(bearing(v.lat, v.lon, la, lo), v.cog) < 25 and (best is None or d < best[0]): best = (d, n, la, lo)
        if best:
            add("APROXIMACION", 3 + (1 if best[0] < 15 else 0), "Rumbo directo a %s a %.0f km a %.0f kn" % (best[1], best[0], v.sog))
            v.target = {"n": best[1], "la": best[2], "lo": best[3]}
    if v.sog > 10 and zigzag(v, now): add("ZIGZAG", 2, "Maniobras evasivas (zigzag)")
    if not v.static_seen and not v.contact and v.sog >= 20 and now - v.first > 600:
        add("IDENTIDAD", 1, "Alta velocidad sin nombre/tipo AIS")
    m = v.mmsi
    if not v.contact and (len(m) != 9 or not m.isdigit() or (m[0] in "234567" and not 201 <= int(m[:3]) <= 775)):
        add("MMSI", 1, "MMSI inválido o inexistente")
    if v.events.get("SPOOF", 0) > now: add("SPOOF", 4, "Salto de posición imposible (suplantación/GPS spoofing)")
    if v.events.get("RDV", 0) > now: add("ENCUENTRO", 4, "Encuentro en mar con %s (posible trasbordo)" % v.events.get("RDVW", "?"))
    if v.sog >= 20 and not port:
        k = (int(v.lat * 20), int(v.lon * 20)); n = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for o in grid.get((k[0] + dx, k[1] + dy), ()):
                    if o is not v and o.sog >= 20 and not is_exempt(o.type) and hav(v.lat, v.lon, o.lat, o.lon) < 2 \
                            and o.cog < 360 and v.cog < 360 and angdiff(o.cog, v.cog) < 20: n += 1
        if n >= 2: add("CONVOY", 3, "Grupo de %d embarcaciones rápidas en formación" % (n + 1))
    g24 = sum(1 for g in v.gaps if now - g[1] < 86400)
    if g24 >= 2: add("APAGONES", min(3, g24), "Apagones recurrentes (%d en 24 h)" % g24)
    if 60 <= typ <= 69:
        best = None
        for n, a, b, w in FERRY:
            d, t = seg_dist((v.lat, v.lon), a, b)
            if -0.1 <= t <= 1.1 and (best is None or d < best[0]): best = (d, n, w, a, b)
        if best and best[0] <= best[2] * 4:
            d, n, w, a, b = best; brg = bearing(a[0], a[1], b[0], b[1])
            if v.sog >= 8 and v.cog < 360 and min(angdiff(v.cog, brg), angdiff(v.cog, (brg + 180) % 360)) < 25 and d > w:
                add("FERRY", 2, "Ferry fuera de corredor %s (%.0f km)" % (n, d))
            if v.sog < 2 and d <= w and not near_port(v.lat, v.lon, 6): add("FERRY", 3, "Ferry detenido en mitad del corredor %s" % n)
    if v.sog > 3 and v.cog < 360: v.proj = [dest(v.lat, v.lon, v.cog, v.sog * 1.852 * mn / 60) for mn in (10, 20, 40)]
    return R


def analyze_all():
    now = CLK.now()
    with STORE.lock:
        for k in [k for k, v in STORE.v.items() if (v.contact and now - v.t > 3600) or now - v.t > 6 * 3600]:
            del STORE.v[k]
        vs = list(STORE.v.values()); grid = defaultdict(list)
        for v in vs:
            if now - v.t < 600 and v.t: grid[(int(v.lat * 20), int(v.lon * 20))].append(v)
        # encuentros en mar (trasbordo)
        seen = set()
        for v in vs:
            if now - v.t > 600 or v.sog >= 2.5 or near_port(v.lat, v.lon, 1.5): continue
            k = (int(v.lat * 20), int(v.lon * 20))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for o in grid.get((k[0] + dx, k[1] + dy), ()):
                        if o is v or o.sog >= 2.5 or v.mmsi > o.mmsi: continue
                        if hav(v.lat, v.lon, o.lat, o.lon) > 0.4: continue
                        if (70 <= v.type <= 89 and 70 <= o.type <= 89) or (v.type == 30 and o.type == 30) or is_exempt(v.type) or is_exempt(o.type): continue
                        if not (v.type in SMALL or o.type in SMALL or v.contact or o.contact): continue
                        key = (v.mmsi, o.mmsi); seen.add(key)
                        first = STORE.pairs.setdefault(key, now)
                        if now - first >= 480:
                            v.events["RDV"] = o.events["RDV"] = now + 3600
                            v.events["RDVW"] = o.name or o.mmsi; o.events["RDVW"] = v.name or v.mmsi
        for k in list(STORE.pairs):
            if k not in seen: del STORE.pairs[k]
        st = {"tracked": len(vs), "crit": 0, "high": 0, "med": 0, "dark": 0, "contacts": 0, "ferry_dark": 0}
        for v in vs:
            v.reasons = rules(v, now, grid)
            codes = {c for c, _, _ in v.reasons if c not in ("NOCTURNO", "MMSI")}
            if len(codes) >= 3: v.reasons.append(("FUSION", 1, "Evidencia cruzada de %d señales independientes" % len(codes)))
            v.score = min(10, sum(p for _, p, _ in v.reasons))
            lvl = 3 if v.score >= 8 else 2 if v.score >= 6 else 1 if v.score >= 4 else 0
            if lvl > v.lvl:
                try:
                    with DBL:
                        DB.execute("INSERT INTO alerts(ts,mmsi,name,score,codes,reasons,lat,lon) VALUES(?,?,?,?,?,?,?,?)",
                                   (datetime.fromtimestamp(now).isoformat(timespec="seconds"), v.mmsi, v.name, v.score,
                                    ",".join(sorted({c for c, _, _ in v.reasons})), " | ".join(x for _, _, x in v.reasons), v.lat, v.lon))
                        DB.commit()
                except Exception: pass
            if lvl != v.lvl and (lvl > v.lvl or v.score < 3): v.lvl = lvl
            if v.score >= 8: st["crit"] += 1
            elif v.score >= 6: st["high"] += 1
            elif v.score >= 4: st["med"] += 1
            if v.dark and v.score >= 4: st["dark"] += 1
            if v.dark and 60 <= v.type <= 69: st["ferry_dark"] += 1
            if v.contact and now - v.t < GAP_S: st["contacts"] += 1
        STORE.stats = st


def engine_loop():
    while True:
        try: analyze_all()
        except Exception as e: print("engine:", e)
        time.sleep(2)


# ───────────────────────── Fuente: AISStream.io ─────────────────────────
class Sources:
    def __init__(s): s.ais = None; s.udp = None

    def start_ais(s):
        key = CFG.get("aisstream_key")
        if not key: return
        if websockets is None: STORE.set_src("AISStream", "error", "pip install websockets"); return
        s.ais = threading.Event(); ev = s.ais
        threading.Thread(target=lambda: asyncio.run(s._ais(key, ev)), daemon=True).start()

    async def _ais(s, key, ev):
        sub = {"APIKey": key, "BoundingBoxes": [[[BBOX[0], BBOX[1]], [BBOX[2], BBOX[3]]]],
               "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport", "ShipStaticData"]}
        while not ev.is_set():
            try:
                STORE.set_src("AISStream", "conectando")
                async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
                    await ws.send(json.dumps(sub))
                    async for raw in ws:
                        if ev.is_set(): break
                        m = json.loads(raw)
                        if "error" in m: STORE.set_src("AISStream", "error", str(m["error"])); break
                        md = m.get("MetaData", {}); mm = str(md.get("MMSI", "")); body = m.get("Message", {}).get(m.get("MessageType"), {})
                        if m.get("MessageType") == "ShipStaticData":
                            STORE.set_static(mm, (body.get("Name") or md.get("ShipName") or "").strip(), body.get("Type"), (body.get("Destination") or "").strip())
                        elif mm:
                            nm = (md.get("ShipName") or "").strip()
                            if nm: STORE.set_static(mm, nm)
                            STORE.update(mm, md.get("latitude"), md.get("longitude"), body.get("Sog"), body.get("Cog"), src="AISStream")
            except Exception as e:
                STORE.set_src("AISStream", "error", str(e)[:80])
                await asyncio.sleep(5)

    def start_udp(s):
        port = int(CFG.get("udp_port") or 0)
        if not port: return
        s.udp = threading.Event(); ev = s.udp
        threading.Thread(target=s._udp, args=(port, ev), daemon=True).start()

    def _udp(s, port, ev):
        try:
            sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sk.bind((CFG.get("udp_host", "127.0.0.1"), port)); sk.settimeout(1)
            STORE.set_src("AIS propio (UDP)", "escuchando", "puerto %d" % port)
        except Exception as e:
            STORE.set_src("AIS propio (UDP)", "error", str(e)); return
        frags = {}
        while not ev.is_set():
            try: data, _ = sk.recvfrom(4096)
            except socket.timeout: continue
            except Exception: break
            for line in data.decode(errors="ignore").splitlines():
                try: nmea(line, frags)
                except Exception: pass
        sk.close()

    def stop_all(s):
        for e in (s.ais, s.udp):
            if e: e.set()
        s.ais = s.udp = None


SRC = Sources()
CH = "@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_ !\"#$%&'()*+,-./0123456789:;<=>?"


def nmea(line, frags):
    m = re.match(r"^.*?[!$]AIVD[MO],(\d+),(\d+),(\d*),([AB12]?),([^,]*),", line)
    if not m: return
    tot, num, seq, ch, pl = int(m[1]), int(m[2]), m[3], m[4], m[5]
    if tot > 1:
        fr = frags.setdefault((seq, ch), {}); fr[num] = pl
        if len(fr) < tot: return
        pl = "".join(fr[i] for i in sorted(fr)); del frags[(seq, ch)]
    b = "".join(format(ord(c) - 48 - (8 if ord(c) - 48 > 40 else 0), "06b") for c in pl)
    if len(b) < 38: return
    t = int(b[:6], 2); mmsi = str(int(b[8:38], 2))
    u = lambda a, z: int(b[a:z], 2)
    def si(a, z):
        n = int(b[a:z], 2); return n - (1 << (z - a)) if b[a] == "1" else n
    def txt(a, z): return "".join(CH[int(b[i:i + 6], 2)] for i in range(a, min(z, len(b)) - 5, 6)).replace("@", "").strip()
    if t in (1, 2, 3) and len(b) >= 128: lon, lat, sog, cog = si(61, 89) / 600000, si(89, 116) / 600000, u(50, 60) / 10, u(116, 128) / 10
    elif t == 18 and len(b) >= 124: lon, lat, sog, cog = si(57, 85) / 600000, si(85, 112) / 600000, u(46, 56) / 10, u(112, 124) / 10
    elif t == 5 and len(b) >= 240: STORE.set_static(mmsi, txt(112, 232), u(232, 240), txt(302, 422) if len(b) >= 422 else ""); return
    elif t == 24 and len(b) >= 48:
        if u(38, 40) == 0: STORE.set_static(mmsi, txt(40, 160))
        else: STORE.set_static(mmsi, None, u(40, 48))
        return
    else: return
    if abs(lat) <= 90 and abs(lon) <= 180: STORE.update(mmsi, lat, lon, sog, cog, src="AIS propio (UDP)")


# ───────────────────────── Simulador de escenarios ─────────────────────────
class Ent:
    def __init__(s, mmsi, name, typ, pos, wps, sog, mode="once", **kw):
        s.mmsi, s.name, s.typ, s.lat, s.lon, s.wps, s.sog, s.mode = mmsi, name, typ, pos[0], pos[1], wps, sog, mode
        s.i = 0; s.cog = 0; s.wait = 0; s.dark = None; s.ais = kw.get("ais", True); s.contact = kw.get("contact", False)
        s.static = kw.get("static", True); s.home = kw.get("home"); s.life = kw.get("life"); s.born = CLK.now()
        s.spoof = kw.get("spoof"); s.lastplot = 0; s.dead = False; s.cid = "RDR-%d" % random.randint(100, 999)


class Sim:
    def __init__(s): s.ents = []; s.run = False; s.n = 0

    def mm(s, mid): return "%d%06d" % (mid, random.randint(0, 999999))

    def add(s, e):
        if e.static: STORE.set_static(e.mmsi, e.name, e.typ)
        s.ents.append(e)

    def sched_dark(s, e, now):
        if random.random() < 0.35:
            a, b = e.wps[0], e.wps[-1]; dur = hav(a[0], a[1], b[0], b[1]) / (e.sog * 1.852) * 3600
            st = now + dur * random.uniform(0.25, 0.4) + 600; e.dark = (st, st + random.uniform(1500, 2400))
        else: e.dark = None

    def world(s):
        now = CLK.now(); rnd = random.uniform
        ferries = [("Algeciras-Ceuta", (36.13, -5.43), (35.89, -5.31)), ("Algeciras-Ceuta", (36.13, -5.43), (35.89, -5.31)),
                   ("Algeciras-TMed", (36.13, -5.43), (35.89, -5.50)), ("Algeciras-TMed", (36.13, -5.43), (35.89, -5.50)),
                   ("Tarifa-Tanger", (36.01, -5.60), (35.79, -5.81))]
        for i, (nm, a, b) in enumerate(ferries):
            pos = tuple(x + (y - x) * random.random() for x, y in zip(a, b))
            e = Ent(s.mm(224), "FERRY %s %d" % (nm.split("-")[0][:4].upper(), i + 1), 60 + i, pos, [b, a] if i % 2 else [a, b], rnd(18, 24), "bounce")
            s.sched_dark(e, now); s.add(e)
        s.add(Ent(s.mm(224), "HSC RAPIDO 1", 40, (36.13, -5.43), [(35.89, -5.31), (36.13, -5.43)], 38, "bounce"))
        s.add(Ent(s.mm(224), "GUARDIA CIVIL P1", 55, (36.05, -5.5), [(36.1, -5.9), (36.0, -5.2)], 28, "bounce"))
        s.add(Ent(s.mm(224), "SALVAMAR 1", 51, (36.2, -5.9), [(36.05, -5.6)], 25, "bounce"))
        east = [(36.00, -7.3), (35.95, -6.3), (35.96, -5.6), (36.00, -5.3), (36.35, -4.7), (36.50, -3.5), (36.45, -2.0), (36.35, -1.6)]
        for i in range(22):
            w = east if i % 2 == 0 else [(x + 0.05, y) for x, y in east[::-1]]
            k = random.randint(0, len(w) - 2); p = tuple(x + (y - x) * random.random() for x, y in zip(w[k], w[k + 1]))
            s.add(Ent(s.mm(random.choice([351, 353, 636, 538, 256])), "CARGO %03d" % i, random.choice([70, 71, 80, 82]), p, w[k + 1:], rnd(9, 15), "loop"))
        for i in range(10):
            p = (36.06 + rnd(0, 0.05), -5.40 + rnd(-0.03, 0.03))
            s.add(Ent(s.mm(random.choice([351, 636])), "ANCLA %02d" % i, 70, p, [p], 0.1, "stay"))
        homes = [(36.12, -6.0), (36.70, -2.55), (36.60, -4.50), (36.30, -6.45), (36.05, -5.5), (36.65, -3.4)]
        for i in range(22):
            h = random.choice(homes); p = (h[0] + rnd(-.1, .1), h[1] + rnd(-.15, .15))
            s.add(Ent(s.mm(224), "PESQ %03d" % i, 30, p, [(h[0] + rnd(-.12, .12), h[1] + rnd(-.15, .15))], rnd(3, 6), "wander", home=h))
        for i in range(14):
            h = random.choice(homes); p = (h[0] + rnd(-.1, .1), h[1] + rnd(-.15, .15))
            s.add(Ent(s.mm(random.choice([224, 235, 227])), "OCIO %02d" % i, random.choice([36, 37]), p, [(h[0] + rnd(-.1, .1), h[1] + rnd(-.1, .1))],
                      rnd(5, 12), "wander", home=h, spoof=(now + rnd(300, 900)) if i == 0 else None))

    NSTART = [(35.95, -5.60), (35.52, -4.95), (35.35, -2.90), (35.55, -6.40), (35.95, -5.90)]

    def spawn_narco(s):
        if sum(1 for e in s.ents if e.mode == "narco") >= 5: return
        st = random.choice(s.NSTART)
        tg = min(random.sample(COSTA, 3), key=lambda c: hav(st[0], st[1], c[1], c[2]))
        mid = ((st[0] + tg[1]) / 2 + random.uniform(-.06, .06), (st[1] + tg[2]) / 2 + random.uniform(-.06, .06))
        r = random.random(); now = CLK.now()
        e = Ent(s.mm(random.choice([224, 242])) if r > .45 else "NARCO%d" % random.randint(10, 99), "", 0, st, [mid, (tg[1], tg[2])],
                random.uniform(34, 48), "narco", ais=r > .45, contact=True, static=False)
        if r > .45 and random.random() < .45: e.dark = (now + 420, now + 10 ** 9)
        s.add(e)

    def spawn_rdv(s):
        if any(e.mode == "rdv" for e in s.ents): return
        pos = (36.35, -6.75)
        s.add(Ent(s.mm(224), "ALBATROS II", 30, pos, [pos], 0.4, "stay", life=3300))
        tg = random.choice(COSTA[:3])
        b = Ent(s.mm(242), "", 0, (35.55, -6.40), [(pos[0] + .001, pos[1] + .001, 780), (tg[1], tg[2])], 36, "rdv", static=False, contact=True)
        s.add(b)

    def step(s, e, now, dt):
        if e.life and now - e.born > e.life: e.dead = True; return
        if e.spoof and now > e.spoof: e.lat += 0.45; e.spoof = None
        waiting = now < e.wait
        if e.mode != "stay" and not waiting:
            wp = e.wps[e.i]; d = hav(e.lat, e.lon, wp[0], wp[1]); km = e.sog * 1.852 * dt / 3600
            e.cog = bearing(e.lat, e.lon, wp[0], wp[1])
            if d <= max(km, 0.15):
                e.lat, e.lon = wp[0], wp[1]
                if len(wp) > 2: e.wait = now + wp[2]
                e.i += 1
                if e.i >= len(e.wps):
                    if e.mode in ("once", "narco", "rdv"): e.dead = True; return
                    if e.mode == "loop": e.i = 0; e.lat, e.lon = e.wps[0][:2]
                    if e.mode == "bounce":
                        e.wps = e.wps[::-1] if len(e.wps) > 1 else e.wps; e.i = 1 if len(e.wps) > 1 else 0
                        e.wait = now + 600; s.sched_dark(e, now)
                    if e.mode == "wander":
                        h = e.home; e.wps = [(h[0] + random.uniform(-.12, .12), h[1] + random.uniform(-.15, .15))]; e.i = 0
            else: e.lat, e.lon = dest(e.lat, e.lon, e.cog, km)
        sog = 0.3 if (waiting or e.mode == "stay") else e.sog
        ais_now = e.ais and not (e.dark and e.dark[0] <= now <= e.dark[1])
        if ais_now: STORE.update(e.mmsi, e.lat, e.lon, sog + random.uniform(-.2, .2) if sog > 1 else sog, e.cog, src="Simulador")
        elif e.contact and now - e.lastplot >= 60:
            e.lastplot = now
            STORE.update(e.cid, e.lat + random.uniform(-.002, .002), e.lon + random.uniform(-.002, .002), sog, e.cog, src="Simulador (radar/SAR)", contact=True)

    def loop(s):
        last = time.time()
        while s.run:
            time.sleep(1); n = time.time(); dt = (n - last) * CLK.f; last = n; now = CLK.now()
            for e in s.ents: s.step(e, now, dt)
            s.ents = [e for e in s.ents if not e.dead]
            if random.random() < dt / 600: s.spawn_narco()
            if random.random() < dt / 2400: s.spawn_rdv()

    def start(s, factor):
        if s.run: return
        CLK.set_factor(factor); s.run = True; s.world(); s.spawn_narco()
        STORE.set_src("Simulador", "ok", "escenarios x%s" % factor)
        threading.Thread(target=s.loop, daemon=True).start()

    def stop(s): s.run = False; s.ents = []


SIM = Sim()


def boot_sources():
    live = bool(CFG.get("aisstream_key") or CFG.get("udp_port")) and not CFG.get("force_demo")
    if live:
        CLK.set_factor(1); SRC.start_ais(); SRC.start_udp()
    else: SIM.start(CFG.get("factor", 8))


# ───────────────────────── IA (DeepSeek) ─────────────────────────
AI_CACHE = {}
SYS = ("Eres analista de vigilancia marítima y OSINT especializado en tráfico ilícito (narcolanchas) en el Estrecho de Gibraltar, "
       "Alborán y Golfo de Cádiz. Razona con prudencia: distingue falsos positivos (pérdida de cobertura AIS, pesca, ocio) de patrones "
       "realmente sospechosos. Responde en español, conciso y estructurado: 1) Probabilidad de actividad ilícita (%) y confianza, "
       "2) Indicios a favor y en contra, 3) Qué verificar a continuación.")


def deepseek(prompt, max_tokens=1500):
    key = CFG.get("deepseek_key")
    if not key or requests is None: return None
    try:
        r = requests.post(os.getenv("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions"),
                          headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                          json={"model": "deepseek-chat", "max_tokens": max_tokens, "temperature": 0.3,
                                "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}]}, timeout=90)
        if r.status_code == 200: return r.json()["choices"][0]["message"]["content"]
        return "Error DeepSeek %s: %s" % (r.status_code, r.text[:200])
    except Exception as e: return "Error DeepSeek: %s" % e


def dossier(v):
    last = ["%s %.4f,%.4f %.0fkn %.0f°" % (datetime.fromtimestamp(p[0]).strftime("%H:%M"), p[1], p[2], p[3], p[4]) for p in list(v.track)[-15:]]
    return ("Embarcación MMSI %s nombre '%s' tipo AIS %s destino '%s'. Puntuación del motor %d/10. Origen datos: %s. Contacto sin AIS: %s.\n"
            "Señales: %s\nÚltimas posiciones:\n%s\nÚltima vez visto hace %d min. Hora local simulada/real: %s." %
            (v.mmsi, v.name, v.type, v.dest, v.score, v.src, v.contact, "; ".join(x for _, _, x in v.reasons) or "ninguna",
             "\n".join(last), (CLK.now() - v.t) / 60, datetime.fromtimestamp(CLK.now()).strftime("%H:%M")))


def local_explain(v):
    if not v.reasons: return "Sin señales relevantes."
    s = "Análisis local (sin IA externa):\n" + "\n".join("• " + x for _, _, x in v.reasons)
    if v.dark: s += "\n\nCautela: un apagón puede ser pérdida de cobertura terrestre. Es más fiable si ocurre en zona bien cubierta (Estrecho) y se repite."
    return s + "\n\nVerificar: imagen SAR/óptica de la zona, otros receptores AIS, patrulleras cercanas, histórico del MMSI."


# ───────────────────────── Puerto libre ─────────────────────────
def can_bind(host, port):
    s = socket.socket()
    try: s.bind((host, port)); return True
    except OSError: return False
    finally: s.close()


def pids_on_port(port):
    pids = set()
    try:
        import psutil
        for c in psutil.net_connections(kind="inet"):
            if c.laddr and c.laddr.port == port and c.pid: pids.add(c.pid)
        if pids: return pids
    except Exception: pass
    try:
        if os.name == "nt":
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
            for ln in out.splitlines():
                p = ln.split()
                if len(p) >= 5 and p[1].endswith(":%d" % port) and "LISTEN" in p[3].upper(): pids.add(int(p[4]))
        else:
            out = subprocess.run(["lsof", "-t", "-i", "tcp:%d" % port], capture_output=True, text=True).stdout
            pids |= {int(x) for x in out.split() if x.isdigit()}
    except Exception: pass
    return pids


def free_port(host, port, kill=True):
    if can_bind(host, port): return port
    if kill:
        for pid in pids_on_port(port) - {os.getpid()}:
            print("⚠ Puerto %d ocupado por PID %d → cerrándolo" % (port, pid))
            try:
                if os.name == "nt": subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
                else: os.kill(pid, signal.SIGTERM)
            except Exception as e: print("  no se pudo cerrar:", e)
        for _ in range(10):
            if can_bind(host, port): return port
            time.sleep(0.4)
        for pid in pids_on_port(port) - {os.getpid()}:
            try: os.kill(pid, signal.SIGKILL if os.name != "nt" else signal.SIGTERM)
            except Exception: pass
        time.sleep(0.8)
        if can_bind(host, port): return port
    for p in range(port + 1, port + 50):
        if can_bind(host, p): print("⚠ Usando puerto alternativo %d" % p); return p
    sys.exit("No hay puertos libres")


# ───────────────────────── API ─────────────────────────
app = FastAPI(title="SENTINELA OSIRIS", version=VERSION)


@app.on_event("startup")
def _startup():
    threading.Thread(target=engine_loop, daemon=True).start()
    boot_sources()


@app.get("/", response_class=HTMLResponse)
def index(): return HTMLResponse(HTML.replace("__VERSION__", VERSION))


@app.get("/api/snapshot")
def api_snapshot(min: int = 4):
    d = STORE.snapshot(min); d["live"] = CLK.f == 1 and not SIM.run; d["ai"] = bool(CFG.get("deepseek_key")); return d


@app.get("/api/static")
def api_static():
    return {"ports": PORTS, "costa": COSTA, "bbox": BBOX, "ferry": [[n, a, b, w] for n, a, b, w in FERRY]}


@app.get("/api/vessel/{mmsi}")
def api_vessel(mmsi: str):
    with STORE.lock:
        v = STORE.v.get(mmsi)
        if not v: return JSONResponse({"error": "no encontrado"}, 404)
        d = v.to_dict(True); d["dest"] = v.dest; d["src"] = v.src; d["gaps"] = len(v.gaps)
        d["first"] = round(CLK.now() - v.first); return d


@app.get("/api/sources")
def api_sources():
    return {"sources": STORE.sources, "deepseek": bool(CFG.get("deepseek_key")), "aisstream": bool(CFG.get("aisstream_key")),
            "udp": CFG.get("udp_port"), "sim": SIM.run, "factor": CLK.f}


@app.post("/api/config")
def api_config(cfg: dict = Body(...)):
    for k in ("deepseek_key", "aisstream_key", "udp_host"):
        if k in cfg and cfg[k] is not None: CFG[k] = str(cfg[k]).strip()
    if "udp_port" in cfg: CFG["udp_port"] = int(cfg["udp_port"] or 0)
    if "factor" in cfg: CFG["factor"] = max(1, min(60, float(cfg["factor"] or 8)))
    if "force_demo" in cfg: CFG["force_demo"] = bool(cfg["force_demo"])
    save_cfg(); SRC.stop_all(); SIM.stop(); STORE.clear(); STORE.sources.clear(); boot_sources()
    return {"ok": True}


@app.post("/api/contactos")
def api_contactos(items: list = Body(...)):
    """[{"id":"SAR-1","lat":36.1,"lon":-5.5,"sog":30,"cog":10}] – radar / SAR / dron / cualquier detección sin AIS"""
    n = 0
    for it in items:
        try:
            STORE.update(str(it.get("id") or "EXT-%d" % random.randint(1000, 9999)), float(it["lat"]), float(it["lon"]),
                         it.get("sog"), it.get("cog"), src="Contactos externos", contact=True); n += 1
        except Exception: pass
    return {"ingested": n}


@app.post("/api/ai/vessel/{mmsi}")
def api_ai_vessel(mmsi: str):
    with STORE.lock:
        v = STORE.v.get(mmsi)
        if not v: return {"text": "No encontrado", "source": "local"}
        key = (mmsi, v.score, len(v.reasons)); prompt = dossier(v); local = local_explain(v)
    if key in AI_CACHE and time.time() - AI_CACHE[key][0] < 120: return AI_CACHE[key][1]
    txt = deepseek("Analiza esta embarcación:\n" + prompt)
    res = {"text": txt, "source": "deepseek"} if txt else {"text": local, "source": "local"}
    AI_CACHE[key] = (time.time(), res); return res


@app.post("/api/ai/briefing")
def api_ai_briefing():
    with STORE.lock:
        top = sorted([v for v in STORE.v.values() if v.score >= 4], key=lambda v: -v.score)[:15]
        lines = ["%s '%s' tipo %s %.0fkn score %d: %s" % (v.mmsi, v.name, v.type, v.sog, v.score, "; ".join(x for _, _, x in v.reasons)) for v in top]
        st = dict(STORE.stats)
    if not lines: return {"text": "Sin alertas activas.", "source": "local"}
    txt = deepseek("Estadísticas: %s\nAlertas principales:\n%s\n\nRedacta un parte de situación: patrones, posibles conexiones entre alertas "
                   "(p.ej. encuentro en mar seguido de aproximación a costa), prioridades y falsos positivos probables." % (st, "\n".join(lines)), 2000)
    return {"text": txt, "source": "deepseek"} if txt else {"text": "Parte local:\n" + "\n".join(lines), "source": "local"}


@app.get("/api/history")
def api_history(limit: int = 100):
    with DBL: rows = DB.execute("SELECT ts,mmsi,name,score,codes,reasons,lat,lon FROM alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(zip(("ts", "mmsi", "name", "score", "codes", "reasons", "lat", "lon"), r)) for r in rows]


@app.get("/api/export/geojson")
def export_geojson():
    with STORE.lock:
        f = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [v.lon, v.lat]},
              "properties": {"mmsi": v.mmsi, "name": v.name, "score": v.score, "sog": v.sog, "reasons": [x for _, _, x in v.reasons]}}
             for v in STORE.v.values() if v.score >= 4]
    return Response(json.dumps({"type": "FeatureCollection", "features": f}), media_type="application/geo+json",
                    headers={"Content-Disposition": "attachment; filename=sentinela_alertas.geojson"})


@app.get("/api/export/csv")
def export_csv():
    o = io.StringIO(); w = csv.writer(o); w.writerow(["mmsi", "nombre", "tipo", "lat", "lon", "sog", "cog", "score", "senales"])
    with STORE.lock:
        for v in STORE.v.values():
            if v.score >= 4: w.writerow([v.mmsi, v.name, v.type, v.lat, v.lon, round(v.sog, 1), round(v.cog), v.score, " | ".join(x for _, _, x in v.reasons)])
    return Response(o.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sentinela_alertas.csv"})


# ───────────────────────── Interfaz ─────────────────────────
HTML = r"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SENTINELA OSIRIS v__VERSION__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<style>
:root{--bg:#0b1020;--p:#121a30;--b:#243152;--t:#dbe4f5;--m:#7d8bad;--g:#2cf5a6;--c:#ff2d55;--h:#ff9500;--md:#ffd60a;--d:#c77dff}
*{box-sizing:border-box;margin:0}body{font:13px system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--t);height:100vh;display:flex}
#side{width:400px;min-width:400px;height:100vh;overflow-y:auto;background:var(--p);border-right:1px solid var(--b);padding:12px}
#map{flex:1;height:100vh;background:#0b1020}
h1{font-size:17px;letter-spacing:1px;color:#5ee7ff}h1 small{color:var(--m);font-weight:400;font-size:11px}
.row{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:6px 0}
.stat{flex:1;min-width:70px;background:#0e1527;border:1px solid var(--b);border-radius:8px;padding:6px;text-align:center}
.stat b{display:block;font-size:20px}.stat span{font-size:10px;color:var(--m);text-transform:uppercase}
button{background:#1b2a4d;color:var(--t);border:1px solid var(--b);border-radius:6px;padding:5px 9px;cursor:pointer;font-size:12px}
button:hover{border-color:var(--g)}button.pri{background:var(--g);color:#06231a;border:0;font-weight:700}
.chip{padding:3px 8px;border-radius:12px;border:1px solid var(--b);cursor:pointer;font-size:11px;color:var(--m);user-select:none}
.chip.on{background:#16335a;color:#fff;border-color:#3b82f6}
.sec{font-size:10px;color:var(--m);text-transform:uppercase;letter-spacing:1px;margin:10px 0 3px}
.al{border-left:4px solid;background:#0e1527;border-radius:6px;padding:6px 8px;margin:4px 0;cursor:pointer}
.al:hover{background:#15203b}.al .h{display:flex;justify-content:space-between;font-weight:600}.al .r{color:var(--m);font-size:11px;margin-top:2px}
#dos{background:#0e1527;border:1px solid var(--b);border-radius:8px;padding:10px;margin:8px 0;display:none}
#dos .rs div{padding:2px 0;border-bottom:1px solid #1a2542;font-size:12px}#ai{white-space:pre-wrap;font-size:12px;margin-top:8px;color:#cfe}
input[type=range]{width:100%}input[type=text],input[type=password],input[type=number]{width:100%;background:#0e1527;border:1px solid var(--b);color:var(--t);padding:5px;border-radius:5px}
#modal{position:fixed;inset:0;background:#000a;display:none;align-items:center;justify-content:center;z-index:9999}
#modal>div{background:var(--p);border:1px solid var(--b);border-radius:10px;padding:16px;width:420px;max-height:90vh;overflow:auto}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
.leaflet-container{font:12px system-ui}.pulse{animation:pl 1.4s infinite}@keyframes pl{50%{opacity:.35}}
.mk svg{overflow:visible}
</style></head><body>
<div id="side">
 <h1>◈ SENTINELA OSIRIS <small>v__VERSION__</small></h1>
 <div class="row"><span id="mode" class="chip on">…</span><button onclick="openSet()">⚙ Ajustes</button><button onclick="briefing()">🧠 Parte IA</button>
  <button onclick="location='/api/export/geojson'">GeoJSON</button><button onclick="location='/api/export/csv'">CSV</button></div>
 <div class="row" id="stats"></div>
 <div class="sec">Filtro de alarma (umbral mínimo): <b id="minv">4</b></div>
 <input type="range" id="min" min="1" max="10" value="4">
 <div class="row"><label class="chip" id="allc">Mostrar también barcos básicos</label>
  <label class="chip on" id="trkc">Trayectos</label><label class="chip on" id="arcc">Arcos</label><label class="chip" id="heatc">Calor</label></div>
 <div class="sec">Tipo de embarcación</div><div class="row" id="groups"></div>
 <div class="sec">Tipo de señal</div><div class="row" id="codes"></div>
 <div id="dos"></div>
 <div class="sec">Alertas activas</div><div id="alerts"></div>
 <div class="sec">Fuentes</div><div id="srcs"></div>
 <div id="brief" style="white-space:pre-wrap;font-size:12px;margin-top:8px"></div>
</div><div id="map"></div>
<div id="modal"><div>
 <h3 style="margin-bottom:8px">Ajustes</h3>
 <div class="sec">DeepSeek API key (IA)</div><input type="password" id="k_ds" placeholder="sk-...">
 <div class="sec">AISStream.io API key (AIS real, gratuita)</div><input type="password" id="k_ais" placeholder="clave">
 <div class="sec">Receptor AIS propio: puerto UDP NMEA (0 = off)</div><input type="number" id="k_udp" value="0">
 <div class="sec">Modo demo/simulador</div><label><input type="checkbox" id="k_demo"> Forzar simulación</label>
 <div class="sec">Aceleración simulación (x)</div><input type="number" id="k_f" value="8">
 <p style="color:var(--m);font-size:11px;margin:8px 0">Sin claves ni receptor funciona el simulador. Contactos externos (radar/SAR): POST /api/contactos.</p>
 <div class="row"><button class="pri" onclick="saveSet()">Guardar y reiniciar fuentes</button><button onclick="$('modal').style.display='none'">Cerrar</button></div>
</div></div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SEV=s=>s>=8?['CRÍTICA','#ff2d55']:s>=6?['ALTA','#ff9500']:s>=4?['MEDIA','#ffd60a']:['BASE','#6b7a90'];
const GROUP=t=>t>=60&&t<=69?'pass':t==30?'fish':(t==36||t==37)?'pleas':(t>=70&&t<=89)?'cargo':!t?'unk':'other';
const GLAB={pass:'⛴ Ferry/pasaje',fish:'🐟 Pesca',pleas:'⛵ Recreo',cargo:'🚢 Carga',unk:'❓ Desconocido',other:'Otros'};
const CLAB={DARK:'👻 AIS apagado',VELOCIDAD:'💨 Velocidad',APROXIMACION:'🎯 Aproximación',ENCUENTRO:'🤝 Encuentro mar',CONTACTO:'📡 Sin AIS (radar/SAR)',
 FERRY:'⛴ Ferry anómalo',ZIGZAG:'↯ Zigzag',CONVOY:'👥 Convoy',SPOOF:'🛰 Spoofing',APAGONES:'🔁 Apagones',COSTA:'🏖 Junto a costa',IDENTIDAD:'🪪 Sin identidad',NOCTURNO:'🌙 Noche',MMSI:'# MMSI',FUSION:'⚡ Fusión'};
const S={min:4,all:false,groups:new Set(Object.keys(GLAB)),codes:new Set(Object.keys(CLAB)),sel:null,seen:new Set(),first:true,trk:true,arc:true,heat:false,data:null};
const map=L.map('map',{preferCanvas:true}).setView([36.05,-5.4],8);
const T=(u,o)=>L.tileLayer(u,Object.assign({maxZoom:19,attribution:'© OSM · CARTO · Esri'},o||{}));
const base={'CARTO Oscuro':T('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'),
 'CARTO Oscuro (sin etiquetas)':T('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png'),
 'CARTO Claro':T('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'),
 'CARTO Voyager':T('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png'),
 'Satélite Esri':T('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}')};
base['CARTO Oscuro'].addTo(map);
const G={v:L.layerGroup().addTo(map),b:L.layerGroup().addTo(map),t:L.layerGroup().addTo(map),a:L.layerGroup().addTo(map),d:L.layerGroup().addTo(map),
 ports:L.layerGroup().addTo(map),route:L.layerGroup().addTo(map),costa:L.layerGroup()};
const sea=T('https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png',{opacity:.9});
const heat=L.heatLayer([],{radius:30,blur:25,maxZoom:10});
L.control.layers(base,{'Barcos con alarma':G.v,'Barcos básicos':G.b,'Trayectos':G.t,'Arcos/proyección':G.a,'Apagados (👻)':G.d,'Puertos':G.ports,
 'Corredores ferry':G.route,'Costa sensible':G.costa,'Mapa de calor':heat,'OpenSeaMap':sea},{collapsed:true}).addTo(map);
fetch('/api/static').then(r=>r.json()).then(s=>{
 s.ports.forEach(p=>L.circle([p[1],p[2]],{radius:p[3]*1000,color:'#3b82f6',weight:1,fillOpacity:.08}).bindTooltip(esc(p[0])).addTo(G.ports));
 s.ferry.forEach(f=>L.polyline([f[1],f[2]],{color:'#5ee7ff',weight:1,dashArray:'2 6',opacity:.6}).bindTooltip(esc(f[0])).addTo(G.route));
 s.costa.forEach(c=>L.circleMarker([c[1],c[2]],{radius:4,color:'#ff2d55',weight:1,fillOpacity:.4}).bindTooltip('Costa sensible: '+esc(c[0])).addTo(G.costa));
 L.rectangle([[s.bbox[0],s.bbox[1]],[s.bbox[2],s.bbox[3]]],{color:'#2cf5a6',weight:1,fill:false,dashArray:'4 8'}).addTo(G.route);});
function tri(c,rot,sz){return L.divIcon({className:'mk',iconSize:[sz,sz],iconAnchor:[sz/2,sz/2],html:`<svg width="${sz}" height="${sz}" viewBox="0 0 24 24" style="transform:rotate(${rot}deg);filter:drop-shadow(0 0 5px ${c})"><polygon points="12,1 21,22 12,17 3,22" fill="${c}" stroke="#fff" stroke-width="1.2"/></svg>`});}
function arc(a,b,k,n=30){const dx=b[1]-a[1],dy=b[0]-a[0],c=[(a[0]+b[0])/2+dx*k*.6,(a[1]+b[1])/2-dy*k*1.2],p=[];
 for(let i=0;i<=n;i++){const t=i/n,u=1-t;p.push([u*u*a[0]+2*u*t*c[0]+t*t*b[0],u*u*a[1]+2*u*t*c[1]+t*t*b[1]]);}return p;}
function beep(){try{const a=new AudioContext(),o=a.createOscillator(),g=a.createGain();o.connect(g);g.connect(a.destination);o.frequency.value=880;g.gain.value=.08;o.start();o.stop(a.currentTime+.25);}catch(e){}}
function chips(id,obj,set){const c=$(id);c.innerHTML='';Object.keys(obj).forEach(k=>{const e=document.createElement('span');e.className='chip on';e.textContent=obj[k];
 e.onclick=()=>{set.has(k)?set.delete(k):set.add(k);e.classList.toggle('on');render();};c.appendChild(e);});}
chips('groups',GLAB,S.groups);chips('codes',CLAB,S.codes);
$('min').oninput=e=>{S.min=+e.target.value;$('minv').textContent=S.min;load();};
[['allc','all'],['trkc','trk'],['arcc','arc'],['heatc','heat']].forEach(([i,k])=>$(i).onclick=()=>{S[k]=!S[k];$(i).classList.toggle('on',S[k]);load();});
async function load(){try{const r=await fetch('/api/snapshot?min='+(S.all?0:S.min));S.data=await r.json();render();}catch(e){}}
function render(){const d=S.data;if(!d)return;[G.v,G.b,G.t,G.a,G.d].forEach(g=>g.clearLayers());
 const st=d.stats||{};$('mode').textContent=d.live?'● AIS REAL':'◌ SIMULACIÓN x'+d.factor;$('mode').style.color=d.live?'#2cf5a6':'#ffd60a';
 $('stats').innerHTML=[['Críticas',st.crit,'#ff2d55'],['Altas',st.high,'#ff9500'],['Medias',st.med,'#ffd60a'],['Apagados',st.dark,'#c77dff'],['Ferry 👻',st.ferry_dark,'#c77dff'],['Rastreados',st.tracked,'#5ee7ff']]
  .map(x=>`<div class="stat"><b style="color:${x[2]}">${x[1]||0}</b><span>${x[0]}</span></div>`).join('');
 const list=[],hp=[];
 d.v.forEach(v=>{if(!S.groups.has(GROUP(v.t)))return;const al=v.sc>=S.min;
  if(!al){if(S.all&&!v.dk)L.circleMarker([v.la,v.lo],{radius:2,color:'#58708f',weight:0,fillOpacity:.6}).addTo(G.b);return;}
  const rs=v.r||[];if(rs.length&&!rs.some(r=>S.codes.has(r[0])))return;
  const [lab,col]=SEV(v.sc);list.push(v);hp.push([v.la,v.lo,v.sc/10]);
  if(S.first===false&&v.sc>=8&&!S.seen.has(v.id))beep();if(v.sc>=8)S.seen.add(v.id);
  const nm=esc(v.n||v.id)+(v.ct?' (sin AIS)':'');
  if(S.trk&&v.trk&&v.trk.length>1)L.polyline(v.trk,{color:col,weight:2,opacity:.55}).addTo(G.t);
  if(S.arc&&v.trk&&v.trk.length>4){const o=v.trk[0],c=[v.la,v.lo];if(Math.abs(o[0]-c[0])+Math.abs(o[1]-c[1])>.04)L.polyline(arc(o,c,.2),{color:col,weight:1.5,opacity:.35,dashArray:'2 6'}).addTo(G.a);}
  if(v.dk&&v.dr){L.polyline([[v.la,v.lo],v.dr],{color:'#c77dff',weight:2,dashArray:'6 6'}).addTo(G.d);
   L.circle(v.dr,{radius:v.unc*1000,color:'#c77dff',weight:1,fillOpacity:.12,className:'pulse'}).addTo(G.d);
   L.marker(v.dr,{icon:L.divIcon({className:'',html:'<div style="font-size:20px;filter:drop-shadow(0 0 6px #c77dff)">👻</div>',iconSize:[20,20],iconAnchor:[10,10]})}).on('click',()=>sel(v.id)).bindTooltip(nm+' · posición estimada').addTo(G.d);
   L.circleMarker([v.la,v.lo],{radius:4,color:'#c77dff',fillOpacity:.9}).addTo(G.d);}
  if(v.pr&&v.pr.length){const s0=v.dk?v.dr:[v.la,v.lo],e0=v.pr[v.pr.length-1];if(S.arc)L.polyline(arc(s0,e0,-.12),{color:col,weight:2.5,dashArray:'8 6',opacity:.9,className:'pulse'}).addTo(G.a);
   L.circleMarker(e0,{radius:3,color:col,fillOpacity:1}).addTo(G.a);}
  if(v.tg&&S.arc)L.polyline(arc([v.la,v.lo],[v.tg.la,v.tg.lo],.15),{color:'#ff2d55',weight:2,dashArray:'3 5',opacity:.9}).bindTooltip('→ '+esc(v.tg.n)).addTo(G.a);
  if(!v.dk){const m=L.marker([v.la,v.lo],{icon:tri(col,v.c<360?v.c:0,v.sc>=8?26:v.sc>=6?22:18),zIndexOffset:v.sc*100}).on('click',()=>sel(v.id));
   m.bindTooltip(`<b>${nm}</b><br>${v.s} kn · ${lab} ${v.sc}/10`).addTo(G.v);}});
 heat.setLatLngs(S.heat?hp:[]);
 list.sort((a,b)=>b.sc-a.sc);S.first=false;
 $('alerts').innerHTML=list.slice(0,60).map(v=>{const [l,c]=SEV(v.sc),r=(v.r||[]).slice().sort((a,b)=>b[1]-a[1]);
  return `<div class="al" style="border-color:${c}" onclick="sel('${esc(v.id)}',true)"><div class="h"><span>${v.dk?'👻 ':''}${esc(v.n||v.id)}</span><span style="color:${c}">${v.sc}/10 ${l}</span></div>
  <div class="r">${esc(v.id)} · ${GLAB[GROUP(v.t)]} · ${v.s} kn</div><div class="r">${r.slice(0,2).map(x=>esc(x[2])).join(' · ')}</div></div>`;}).join('')||'<div style="color:var(--m);padding:8px">✅ Sin alertas con este filtro</div>';
 if(S.sel)dossierUpdate();}
async function sel(id,fly){S.sel=id;const r=await fetch('/api/vessel/'+encodeURIComponent(id));if(!r.ok)return;S.dv=await r.json();dossierUpdate();
 if(fly){const p=S.dv.dr||[S.dv.la,S.dv.lo];map.flyTo(p,11);}}
function dossierUpdate(){const v=S.dv;if(!v)return;const [l,c]=SEV(v.sc),el=$('dos');el.style.display='block';
 el.innerHTML=`<div style="display:flex;justify-content:space-between"><b style="font-size:15px">${esc(v.n||'(sin nombre)')}</b><span style="color:${c};font-weight:700">${v.sc}/10 ${l}</span></div>
 <div style="color:var(--m);margin:3px 0">MMSI ${esc(v.id)} · ${GLAB[GROUP(v.t)]} · ${v.s} kn · rumbo ${v.c<360?v.c+'°':'n/d'} · visto hace ${Math.round(v.age/60)} min</div>
 <div style="color:var(--m)">Destino: ${esc(v.dest||'n/d')} · Fuente: ${esc(v.src)} · Apagones: ${v.gaps}</div>
 <div class="rs" style="margin-top:6px">${(v.r||[]).map(x=>`<div><b style="color:${c}">+${x[1]}</b> ${esc(x[2])}</div>`).join('')||'Sin señales'}</div>
 <div class="row"><button class="pri" onclick="ai('${esc(v.id)}')">🧠 Analizar con IA</button><button onclick="map.flyTo(${JSON.stringify(v.dr||[v.la,v.lo])},12)">Centrar</button>
 <button onclick="navigator.clipboard.writeText('${v.la}, ${v.lo}')">Copiar coords</button><button onclick="$('dos').style.display='none';S.sel=null">✕</button></div><div id="ai"></div>`;
 if(S.aiText&&S.aiId===v.id)$('ai').textContent=S.aiText;}
async function ai(id){$('ai').textContent='Analizando…';const r=await fetch('/api/ai/vessel/'+encodeURIComponent(id),{method:'POST'}).then(r=>r.json());
 S.aiId=id;S.aiText=(r.source==='deepseek'?'🧠 DeepSeek\n\n':'')+r.text;$('ai').textContent=S.aiText;}
async function briefing(){$('brief').textContent='Generando parte…';const r=await fetch('/api/ai/briefing',{method:'POST'}).then(r=>r.json());$('brief').textContent=(r.source==='deepseek'?'🧠 PARTE IA\n\n':'')+r.text;}
async function srcs(){const r=await fetch('/api/sources').then(r=>r.json());
 $('srcs').innerHTML=Object.entries(r.sources).map(([k,v])=>`<div><span class="dot" style="background:${v.status==='error'?'#ff2d55':v.status==='ok'||v.status==='escuchando'?'#2cf5a6':'#ffd60a'}"></span>${esc(k)} · ${esc(v.status)} (${v.count||0}) ${esc(v.msg||'')}</div>`).join('')
 +`<div><span class="dot" style="background:${r.deepseek?'#2cf5a6':'#6b7a90'}"></span>DeepSeek IA · ${r.deepseek?'activa':'sin clave (análisis local)'}</div>`;}
function openSet(){$('modal').style.display='flex';}
async function saveSet(){await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
 deepseek_key:$('k_ds').value||undefined,aisstream_key:$('k_ais').value||undefined,udp_port:+$('k_udp').value,force_demo:$('k_demo').checked,factor:+$('k_f').value})});
 $('modal').style.display='none';S.seen.clear();S.first=true;setTimeout(load,800);}
load();srcs();setInterval(load,2000);setInterval(srcs,5000);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=5023)
    ap.add_argument("--demo", action="store_true"); ap.add_argument("--no-kill", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if a.demo: CFG["force_demo"] = True
    port = free_port(a.host, a.port, kill=not a.no_kill)
    url = "http://%s:%d" % (a.host, port)
    print("◈ SENTINELA OSIRIS v%s → %s" % (VERSION, url))
    if not a.no_browser: threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=a.host, port=port, log_level="warning")


if __name__ == "__main__":
    main()

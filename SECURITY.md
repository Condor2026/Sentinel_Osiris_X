# Política de Seguridad — SENTINELA OSIRIS

## Versiones soportadas

| Versión | Soportada |
|---------|-----------|
| 8.x     | ✅        |
| < 8.0   | ❌        |

## Reportar una vulnerabilidad

**NO abras un issue público para vulnerabilidades de seguridad.**

Usa el canal privado de GitHub:
👉 https://github.com/Condor2026/Sentinel_Osiris_X/security/advisories/new

Incluye:

- Descripción y pasos para reproducir.
- Impacto potencial (¿expone claves? ¿permite RCE? ¿filtra posiciones?).
- Versión afectada y modo (simulación / AIS real / UDP).
- Sugerencia de mitigación si la tienes.

## Tiempo de respuesta

- **Acuse de recibo:** ≤ 72 h.
- **Evaluación inicial:** ≤ 7 días.
- **Parche o mitigación:** según gravedad.

## Alcance

El proyecto:

- **NO** procesa datos personales en servidores propios (todo local).
- Almacena `sentinela.db` (SQLite) e históricos que **tú controlas**.
- Guarda claves en `sentinela_config.json` con `chmod 600` (solo el usuario
  propietario puede leerlo).

### Vulnerabilidades relevantes

- **Exposición de claves API** (`DEEPSEEK_API_KEY`, `AISSTREAM_KEY`) en logs,
  respuestas o archivos del repo.
- **XSS** en el panel web (los nombres de buques y destinos vienen de AIS,
  que es texto de terceros — el HTML debe seguir escapando con `esc()`).
- **SSRF** si se añaden fuentes de datos configurables.
- **Path traversal** en endpoints de exportación.
- **RCE** vía dependencias maliciosas o WebSocket sin validación.
- **Inyección SQL** en `sentinela.db`.
- **Exposición del puerto UDP** del receptor AIS más allá de localhost
  (`udp_host` debe ser `127.0.0.1` salvo caso justificado).
- **Doppler / GPS spoofing:** el motor detecta saltos imposibles, pero no
  puede garantizar que un AIS no esté siendo suplantado en origen.

### Fuera de alcance

- Contenido publicado por fuentes externas (AISStream, etc.).
- Bloqueos o límites de tasa de APIs de terceros.
- Falsos positivos / negativos del motor de detección (es heurístico).
- Exactitud de las posiciones reportadas por AIS (pueden ser manipuladas).
- Decisiones operativas tomadas a partir de las alertas del panel.

## Buenas prácticas para usuarios

- Ejecuta el panel en `127.0.0.1` (por defecto) o detrás de un proxy con auth.
- **Nunca** expongas el puerto 5023 a Internet sin autenticación.
- Rota periódicamente `DEEPSEEK_API_KEY` y `AISSTREAM_KEY`.
- Mantén `.env` y `sentinela_config.json` fuera del control de versiones
  (`.gitignore` ya lo hace).
- Revisa `sentinela.db` antes de compartirlo — contiene histórico de alertas.
- No publiques capturas con MMSIs, nombres o posiciones de embarcaciones
  privadas reales.

## Recordatorio importante

Este proyecto es **OSINT marítimo con fines informativos**. No está diseñado,
ni debe usarse, para **vigilancia de individuos** ni como herramienta de
intercepción. Consulta [DISCLAIMER.md](DISCLAIMER.md).

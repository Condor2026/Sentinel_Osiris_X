# Contribuir a SENTINELA OSIRIS

¡Gracias por tu interés! Este documento explica cómo hacerlo.

## Antes de empezar

1. Lee el [Código de Conducta](CODE_OF_CONDUCT.md).
2. Lee el [DISCLAIMER](DISCLAIMER.md) — **este proyecto se centra en
   detección de actividad ilícita marítima, no en vigilancia de personas**.
3. Revisa los [issues abiertos](https://github.com/Condor2026/Sentinel_Osiris_X/issues).

## Cómo reportar un bug

Abre un [issue](https://github.com/Condor2026/Sentinel_Osiris_X/issues/new)
con la plantilla de bug. Incluye siempre:

- **Versión** (ver `/api/sources` → no existe, ver panel o `VERSION`).
- **Modo:** simulación / AIS real / receptor UDP / contactos externos.
- **Fuente afectada:** AISStream / UDP / Simulador / Radar / IA.
- **Logs de consola** (sin tokens ni datos personales).
- **Captura del panel** si es un problema visual.

> ⚠️ **No incluyas** claves (`DEEPSEEK_API_KEY`, `AISSTREAM_KEY`), MMSIs
> reales, ni posiciones de embarcaciones privadas.

## Cómo proponer una mejora

Abre un issue con:

- Qué problema resuelve.
- Cómo lo resolverías (algoritmo, regla de detección, fuente nueva…).
- Alternativas consideradas.

Espera feedback **antes** de abrir un PR grande.

## Cómo añadir una nueva regla de detección

1. Añade la lógica dentro de `rules(v, now, grid)` en `SentinelOsirisMar.py`.
2. Usa códigos de señal **cortos y en mayúsculas** (p. ej. `ZIGZAG`, `FERRY`).
3. Añade el código al diccionario `CLAB` del HTML para que aparezca en filtros.
4. Asigna una puntuación (`p`) coherente con la severidad:
   - `1` = indicio débil / contextual
   - `2-3` = señal clara
   - `4+` = señal fuerte o fusión de varias
5. Documenta la regla en el README (tabla de señales).
6. **Cuidado con los falsos positivos.** Añade contexto (puerto, noche,
   tipo de buque, corredor ferry) antes de puntuar.

## Cómo añadir una nueva fuente de datos

1. Respeta la interfaz existente (`STORE.update(...)`, `STORE.set_static(...)`,
   `STORE.set_src(...)`).
2. Las fuentes **sin AIS** deben marcar `contact=True`.
3. Documenta cómo activar la fuente (clave, puerto UDP, endpoint).
4. Añade un `STORE.set_src("Nombre", "ok"|"error", msg)` para que el panel
   muestre su estado.

## Pull Requests

- Un PR = un cambio lógico.
- Sigue el estilo del código existente (PEP 8, `snake_case`, sin `print()` en
  bucles calientes → usa `STORE.set_src` o logging).
- Actualiza el README si cambias comportamiento visible.
- Si añades dependencias, justifícalo.
- Los cambios de UI deben seguir [ACCESSIBILITY.md](ACCESSIBILITY.md).

## Estilo de código

- Python 3.9+.
- `snake_case` para funciones y variables, `PascalCase` para clases.
- Type hints en funciones públicas del motor (`rules`, `analyze_all`).
- No uses `eval` ni `exec`.
- No hardcodees claves ni endpoints privados.

## Licencia

Al contribuir aceptas que tu código se publique bajo la licencia MIT del
proyecto (ver [LICENSE](LICENSE)).

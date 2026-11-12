# rate-limit-quota

## Cuándo usarla

Para **frenar el abuso y acotar el gasto** del agente: un rate limit por usuario (ventana deslizante) y una cuota por tenant (diaria y mensual, en peticiones o en coste). La lógica está hecha en clases base; cambiar dónde se guardan los contadores (RAM, SQL, Redis, Supabase…) es escribir una subclase con dos o tres métodos.

No depende de ninguna receta: `limits/` no importa FastAPI ni el agente. **Usa `project-settings`** (bloque `LimitsSettings`) y **`agent-chat-api`**: trae el `ensure_turn_allowed` ya implementado y `GET /agent/quota`.

## Qué incluye

```
limits/
  models.py       LimitsBackend · QuotaUnit · QuotaPeriod · WindowState · RateLimitDecision · QuotaLimits
                  · PeriodUsage · QuotaStatus · excepciones RateLimited y QuotaExhausted (con su `code`)
  base.py         RateLimiter (ABC): check(subject) → decisión o RateLimited(retry_after, resets_at)
                  QuotaStore (ABC): status(tenant) · ensure_available(tenant) · record(tenant, amount)
                  TurnLimits: fachada allow(tenant, user) = cuota → rate limit → registrar
  in_memory.py    InMemoryRateLimiter · InMemoryQuotaStore (tests y desarrollo en un proceso)
  sql.py          SqlRateLimiter · SqlQuotaStore + tablas rate_limit_hits y ai_usage_daily (SQLAlchemy 2)
  settings.py     bloque LimitsSettings: LIMITS_BACKEND (obligatorio), RATE_LIMIT_*, QUOTA_*
  factory.py      LimitsFactory.create(settings, session_factory=...) → TurnLimits
api/
  agent/guards.py SUSTITUYE al de agent-chat-api: ensure_turn_allowed pregunta a app.state.turn_limits
  limits/router.py GET /agent/quota {available, exhausted, resets_at}
tests/
  limits_conformance.py   lo que TODO backend debe cumplir (5 tests de rate limit + 6 de cuota) y FakeClock
  test_limits.py          conformidad en RAM y SQL, TurnLimits, settings y factory (31 tests)
  test_limits_api.py      429 con código y Retry-After, GET /agent/quota, mismos guards (4 tests)
pytest.ini
```

## Decisiones

- **La lógica en la base, el almacenamiento en la subclase.** `RateLimiter` decide, calcula `retry_after` y lanza; el backend solo implementa `_acquire` (poda, cuenta y, si cabe, registra). `QuotaStore` calcula periodos, resets y qué periodo bloquea; el backend solo implementa `_usage` y `_add_usage`. Así un backend nuevo son dos métodos y una clase de test de conformidad, y la semántica (una petición rechazada no cuenta, el mes bloquea antes que el día) es la misma en todos.
- **El backend se elige en los settings, no en el código.** `LIMITS_BACKEND=in_memory | sql`, sin valor por defecto: un límite en memoria con varios workers es un límite por worker, no por usuario, y conviene decidirlo a sabiendas.
- **Cuota por tenant, rate limit por usuario.** Es lo que hacen ATI (empresa) y aurora (usuario). `TurnLimits.allow` comprueba primero la cuota (si el tenant no tiene presupuesto, da igual lo demás) y luego la ventana. Las comprobaciones de rol (403) van antes: quien no tiene acceso no debe gastar cuota.
- **Unidad de la cuota configurable.** `QUOTA_UNIT=requests` registra una unidad por turno permitido, en el propio guard. `QUOTA_UNIT=cost` no registra nada: el proyecto llama a `quota.record(tenant_id, coste)` cuando sabe lo que costó el turno (los proyectos de origen lo hacen en un callback del LLM). Lo que no sabemos no lo inventamos.
- **Límites por tenant en una tabla:** `_limits(tenant_id)` es un método que por defecto devuelve los de los settings; se sobrescribe para leer una tabla tipo `tenant_quota` (ATI).
- **El contrato HTTP es el de ATI**, que su frontend ya interpreta: 429 con `detail={"code": "rate_limited" | "ai_quota_daily_exhausted" | "ai_quota_monthly_exhausted", "resets_at"}`, cabecera `Retry-After` cuando es rate limit, y `GET /agent/quota {available, exhausted, resets_at}` para bloquear el composer hasta `resets_at`.
- **Periodos en UTC** (día natural y mes natural). El reset es la medianoche o el día 1 siguiente. Si el negocio necesita la zona del tenant, se cambia en `QuotaStore.status`, en un solo sitio.
- **Reloj inyectable.** `clock` es un callable que devuelve un `datetime` UTC; los tests mueven el tiempo con `FakeClock` sin dormir.
- **Sin estado en `app.state` no hay límites.** Si `turn_limits` no está, el guard deja pasar y `/agent/quota` dice disponible: los tests de `agent-chat-api` siguen funcionando sin esta receta.
- **Todo Pydantic:** estados, decisiones, límites y la respuesta del endpoint son `BaseModel` inmutables.

## Cómo adaptarla

1. Copia `files/` en la raíz del backend, encima de `agent-chat-api`. `api/agent/guards.py` **sobrescribe** el de esa receta (mismas funciones más el guard implementado).
2. **Settings:** `class Settings(LimitsSettings, BaseAppSettings)`. En el `.env`:

   ```
   LIMITS_BACKEND=sql
   RATE_LIMIT_REQUESTS=20
   RATE_LIMIT_WINDOW_SECONDS=60
   QUOTA_UNIT=requests
   QUOTA_DAILY_LIMIT=200
   QUOTA_MONTHLY_LIMIT=4000
   ```

   `RATE_LIMIT_ENABLED=false` quita el rate limit; una cuota vacía es ilimitada.
3. **Tablas:** `metadata.create_all(engine)` o una migración con las `Table` de `limits/sql.py`.
4. **`main.py`:** tras `create_app`:

   ```python
   app.state.turn_limits = LimitsFactory.create(settings, session_factory=SessionLocal)
   app.include_router(quota_router)   # from api.limits.router import router as quota_router
   ```

5. **Cuota en coste:** con `QUOTA_UNIT=cost`, llama a `app.state.turn_limits.quota.record(tenant_id, coste)` donde conozcas el coste del turno (callback de uso de tokens, fin de `stream_answer`…).
6. **Otro backend (Redis):** subclase de `RateLimiter` cuyo `_acquire` ejecute un Lua sobre un sorted set (`ZREMRANGEBYSCORE`, `ZCARD`, `ZADD` si cabe, `ZRANGE 0 0` para el más antiguo), subclase de `QuotaStore` con `INCRBYFLOAT` en claves `usage:{tenant}:{día}`, una rama en `LimitsFactory` y dos clases de test que hereden de `RateLimiterConformance` y `QuotaStoreConformance`.
7. Para comprobarla: `pytest` con las cinco recetas backend copiadas (101 tests en total).

**Dependencias:** `pydantic`, `pydantic-settings`; `sqlalchemy` para el backend SQL; las de `agent-chat-api` para `api/`.

## Origen

- Ventana deslizante por usuario con 429 y `retry_after`: aurora (`api/rate_limit.py`, en memoria) y ATI_PLATFORM (`services/rate_limiter.py`, Redis con Lua o memoria según settings).
- Cuota diaria y mensual por empresa con marca de agotada, códigos `ai_quota_{daily|monthly}_exhausted` con `resets_at`, `GET /api/agent/quota` y el frontend que bloquea el composer hasta el reset: ATI_PLATFORM (`services/ai_quota.py`, tablas `company_ai_quota` y `ai_spend_daily`).
- Uso diario por usuario con `GET /auth/usage`: aurora (`daily_usage`, RPC de Supabase).
- Clases base con el almacenamiento abstraído, factory por settings, fachada `TurnLimits`, unidad de cuota configurable y tests de conformidad: nuevos, para que cambiar de sistema de almacenamiento no toque la lógica.

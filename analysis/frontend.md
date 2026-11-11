# Análisis: frontend

Síntesis de los frontends de los proyectos de origen (2026-11-11). Solo lectura; aquí se registran patrones, no código.

| Proyecto | Stack | Notas |
|---|---|---|
| aurora | Next.js 16, React 19, Tailwind v4, componentes tipo shadcn | Proxy de Next (`app/api/*/route.ts`) entre el navegador y el backend Python. Sin tests. |
| ATI_PLATFORM | Angular, `@ngrx/signals`, ngx-translate, Supabase, Sentry | Llama directamente al backend. Tests en Vitest (el parser SSE tiene 35) y Playwright. |
| Vera-Symplia | Vite, React 19 con alias a Preact en el build, CSS propio | Interfaz `Api` con una implementación HTTP y otra falsa. Vitest, Playwright contra el fake y contra el stack real. |
| rag_tool_upv | — | Sin frontend. |

**Stack elegido para las recetas:** Vite + React + TypeScript. El backend ya es Python, así que la capa de servidor de Next.js sobra.

## Patrones comunes

- **El cliente de API es una capa propia** y ningún componente llama a `fetch`.
  - Vera: `createHttpClient`, luego `createHttpApi`, y los grupos de endpoints en archivos aparte.
  - aurora: `lib/api-client.ts`.
  - ATI: servicios e interceptores.
- **Bearer añadido a mano y un 401 tratado de forma centralizada.** Vera y aurora renuevan el token una sola vez y reintentan la petición. ATI cierra la sesión.
- **Errores tipados.** Vera tiene `ApiError(status, code, details)` y `NetworkError`. ATI tiene `AgentStreamHttpError(status, code)`.
- **Streaming del chat con `fetch` POST y `body.getReader()`, nunca `EventSource`.** `EventSource` solo hace GET y no admite cabecera `Authorization` (ATI lo explica en `agent-stream.repository.ts`).
  - Los dos parsers guardan en un buffer la línea que llega a medias.
  - ATI además quita `\r` (CRLF), acepta `data:` con o sin espacio e ignora `id:`, `retry:`, comentarios y pings.
- **Estado del chat.**
  - Se añade un mensaje vacío del asistente antes de empezar, porque `tool_start` puede llegar antes que el primer token.
  - Los tokens se van añadiendo al último mensaje.
  - Las tools se muestran como pasos con estado (`running`, `done`, `error`).
  - Un `AbortController` por envío. Cancelar no se considera un error.
  - Si el envío falla, el texto vuelve al cuadro de entrada (aurora con la restauración del borrador, ATI con `failedQuestion`).
- **Ids del cliente** con `crypto.randomUUID` (aurora) o con un fallback a `getRandomValues` (ATI).

## Patrón de factory e intercambio (Vera)

- `type VeraApi` es la interfaz. Hay dos implementaciones, `createHttpApi` y `createFakeApi`, y las dos cumplen ese mismo tipo.
- `main.tsx` elige la implementación según el **modo de build** (`--mode fake`). El fake se carga con `import()` dinámico, así que no entra en el bundle de producción.
- La API llega a los componentes por **contexto** (`AppServices` + `useApp()`).
- El cliente recibe sus dependencias por opciones (`fetcher`, `now`, `storage`), así que se puede probar sin red.
- Playwright corre contra un build en modo fake. El hook `useLoad(load, deps)` descarta respuestas obsoletas y avisa cuando la sesión caduca.

## Diferencias, sin un patrón común

- **Router:** Vera lo tiene hecho a mano con el hash, ATI usa el router de Angular y aurora el de Next. No se ha incluido ninguno en la receta base.
- **Estado global:** Vera usa hooks y `useState`, ATI un signal store. No se ha incluido ninguna librería.
- **Estilos:** Vera usa CSS global con tokens (variables CSS) y un test de contraste WCAG; aurora usa Tailwind. La receta usa tokens en CSS, sin framework.
- **Id de conversación:** aurora lo genera el cliente (`session_id`); ATI lo asigna el servidor y lo devuelve en `done`. La receta lo genera el cliente, porque así funciona `MemoryKey` en `agent-memory`.
- **Auth:** aurora usa un JWT propio con refresh; ATI y Vera, Supabase. La receta deja el token detrás de una interfaz `TokenProvider`.

## Dudas

- Vera aplica el alias a Preact en el build de producción y además mantiene `react` como dependencia. No está claro si es solo por los tipos.
- aurora no trata el `\r` del CRLF. sse-starlette envía CRLF, así que su parser podría fallar.
- Ningún proyecto trata `data:` en varias líneas, ni reconexiones o timeouts del stream.

# react-agent-chat

## Cuándo usarla

Para la **interfaz de chat con un agente que responde en streaming** (SSE): tokens a medida que llegan, pasos de las tools, cancelar, errores y Markdown. Consume tal cual los eventos de la receta `langgraph-graph` servidos por `agent-chat-api`.

**Requiere `vite-react-base`**, copiada antes, porque usa su `HttpClient`, sus `TokenProvider` y sus variables de diseño.

## Qué incluye

```
src/features/chat/
  events.ts            ChatEvent: unión tipada del contrato (token, tool_start, tool_end, routing, error, done{answer, conversation_id, message_id})
  sse-parser.ts        SseParser + readSse(stream): SSE sobre fetch
  chat-api.ts          type ChatApi + createHttpChatApi(client): POST /agent/stream
  fake-chat-api.ts     createFakeChatApi(): emite los mismos eventos, sin backend
  use-chat.ts          useChat(chat): estado del chat (mensajes, pasos, borrador, cancelar, nueva conversación)
  components/
    ChatView.tsx       el chat completo; recibe su ChatApi desde fuera
    MessageList.tsx    mensajes, pasos de tools, estados y autoscroll
    Composer.tsx       Enter envía, Shift+Enter hace salto de línea; mientras responde, el botón detiene
    Markdown.tsx       react-markdown + remark-gfm (sin HTML crudo)
  chat.css             solo usa las variables de vite-react-base
  index.ts
  sse-parser.test.ts   9 tests: chunks cortados, CRLF, multilínea, pings, JSON inválido, eventos terminales, UTF-8 partido
  chat.test.tsx        8 tests: streaming, conversation_id estable, error_id, stream cortado, cancelar, HTML, nueva conversación, HTTP
```

## Decisiones

- **`fetch` POST + `body.getReader()`, nunca `EventSource`.** `EventSource` solo hace GET y no admite cabecera `Authorization` (aurora y ATI hacen lo mismo).
- **Parser robusto.** Partimos de ATI, que tiene 35 tests, y añadimos lo que no trataba ningún proyecto:
  - Guarda en un buffer la línea cortada entre chunks.
  - Acepta CRLF, que es lo que envía sse-starlette, y `data:` con o sin espacio.
  - Une las líneas de `data:` multilínea con `\n`, como dice la especificación.
  - Ignora comentarios, pings, `id:`, `retry:`, el JSON inválido y los eventos desconocidos.
  - `error` y `done` cierran el stream.
- **Mismo patrón de dos implementaciones que la base:** `ChatApi` es el tipo, y la versión HTTP y la falsa lo cumplen. El fake emite la misma secuencia que el backend real.
- **Estado del chat.**
  - Mensaje del asistente vacío desde el principio, porque `tool_start` puede llegar antes que el primer token. Los tools van como pasos con estado (`running`, `done`, `error`), y los que siguen abiertos al terminar pasan a `error`.
  - Si el stream termina sin `done`, se trata como un fallo (ATI).
  - Un error enseña el `error_id` del backend, nunca el detalle.
  - Si falla, la pregunta vuelve al borrador (aurora y ATI). Cancelar no se considera un error (aurora).
- **El cliente genera el `conversation_id`**, uno por conversación. Coincide con `MemoryKey.conversation_id` de `agent-memory`, y el tenant y el usuario salen del token en el backend.
- **Markdown seguro.** react-markdown crea elementos de React, así que el HTML que venga en la respuesta se muestra como texto. Un `<script>` inyectado en la respuesta del agente no se ejecuta, y hay un test que lo comprueba.

## Cómo adaptarla

1. Copia `files/` encima del frontend de `vite-react-base` y ejecuta `npm install react-markdown@^10.1.0 remark-gfm@^4.0.1`.
2. **Conéctalo en `main.tsx`.** El chat sigue el mismo `VITE_API_MODE` que el resto:

   ```tsx
   import { createHttpClient } from './api/http-client'
   import { ChatView, createFakeChatApi, createHttpChatApi } from './features/chat'

   const chat = CONFIG.apiMode === 'fake'
     ? createFakeChatApi()
     : createHttpChatApi(createHttpClient({ baseUrl: CONFIG.apiUrl, tokens, onSessionExpired }))
   // y en el render: <ChatView chat={chat} />
   ```

3. **El endpoint del backend** está en `createHttpChatApi(client, path)` (por defecto `/agent/stream`), con el cuerpo `{question, conversation_id}`. Es el contrato de la receta `agent-chat-api`. El `done` trae `message_id`, el id de la respuesta guardada, que es lo que se envía al votar.
4. **Un evento nuevo:** añádelo en `ChatEvent` y `toChatEvent` (`events.ts`), trátalo en el `switch` de `use-chat.ts` y emítelo también en el fake. Cambia el `events.py` del backend al mismo tiempo.
5. Para comprobarlo: `npm run typecheck && npm test` (40 tests junto con la base).

## Origen

- Streaming con fetch POST + reader, buffer de líneas, `token`/`tool_start`/`tool_end`/`error`/`done`, mensaje del asistente vacío al principio y pasos con estado: aurora (`lib/api-client.ts`, `useChat.ts`) y ATI_PLATFORM (`agent-sse.parser.ts`, `agent-chat.store.ts`).
- CRLF, pings y eventos desconocidos ignorados, un stream sin `done` como fallo y el error solo en los logs: ATI_PLATFORM.
- `AbortController` por envío, restaurar el borrador y `conversation_id` generado por el cliente: aurora.
- `data:` multilínea, `error_id` en la interfaz y el test de HTML: nuevos.

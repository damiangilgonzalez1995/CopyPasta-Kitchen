# voice-providers

## Cuándo usarla

Para **dictar al agente y leerle la respuesta**: un endpoint que recibe el audio del navegador (`MediaRecorder`) y devuelve el texto, y otro que convierte texto en audio. El proveedor (OpenAI o un doble local) se elige en `.env`, nada toca disco y cada fallo llega con un código HTTP distinto para "es culpa del audio", "el proveedor está saturado" o "falta la clave".

No cubre la conversación de voz en tiempo real (WebRTC, VAD, barge-in). Si la necesitas, `Transcriber`/`Synthesizer` siguen valiendo por turno; el transporte es otra receta.

**Requiere `fastapi-base`** (`ApiError`, request id) **y `auth-verifier`** (`get_current_user`) para el router. `voice/` solo no requiere nada. **Usa `project-settings`** (bloque `VoiceSettings`).

## Qué incluye

```
voice/
  models.py           AudioInput(content, mime) · Transcription(text, language, engine, duration_ms) · Speech(audio, mime) · VoiceError(code, retryable, kind) · AUDIO_FORMATS
  base.py             Transcriber (ABC, template: valida formato/tamaño/vacío, timeout, traduce errores) · Synthesizer (ABC: vacío, longitud, voz permitida)
  openai_provider.py  OpenAITranscriber (gpt-4o-*-transcribe o whisper-1 con no_speech_prob) · OpenAISynthesizer · translate_openai_error · openai_client
  fake.py             FakeTranscriber (texto fijo, b"SILENCE" → "") · FakeSynthesizer (WAV de silencio proporcional al texto)
  settings.py         bloque VoiceSettings: STT_PROVIDER y TTS_PROVIDER (obligatorios), STT_MODEL/LANGUAGE/PROMPT/MAX_BYTES/TIMEOUT, TTS_MODEL/VOICE/FORMAT/MAX_CHARS
  factory.py          VoiceFactory.transcriber(settings, http_client=) · VoiceFactory.synthesizer(settings, http_client=)
api/voice/router.py   POST /voice/transcribe (multipart file + language?) → {text, language} · POST /voice/synthesize {text, voice?} → audio, no-store
tests/
  fake_openai.py      OpenAI a nivel HTTP (httpx.MockTransport): el SDK real corre, solo se sustituye la red
  voice_conformance.py  TranscriberConformance (6) y SynthesizerConformance (3): lo que todo proveedor debe cumplir
  test_voice.py       37 tests sin red: conformidad de los cuatro proveedores, qué se envía a OpenAI, whisper y silencio, mapeo de errores HTTP, fakes, settings, factory
  test_voice_api.py   13 tests del router (se saltan sin fastapi-base y auth-verifier): 401, 413, 415, 422 con código, 429/502/503/504, audio con no-store, app sin voz → 503
pytest.ini
```

## Decisiones

- **Template method en la base, proveedor en la subclase.** `transcribe()` valida que haya contenido, que el MIME esté en `AUDIO_FORMATS` y que no supere `max_bytes`, acota el tiempo con `asyncio.wait_for`, comprueba que el proveedor devolvió texto y traduce cualquier excepción a `VoiceError`. `_transcribe()` solo habla con el SDK. Lo mismo `synthesize()` con texto vacío, longitud y lista de voces.
- **`""` significa "sin voz"**, nunca un error. El router lo convierte en 422 `no_speech`; un agente de voz lo saltaría. Con `whisper-1` se usa `verbose_json` y si todos los segmentos tienen `no_speech_prob` sobre el umbral se devuelve `""`: es la única defensa contra el "Subtítulos por Amara.org" que Whisper alucina con silencio (la alternativa es filtrarlo por regex). Los modelos `gpt-4o-*-transcribe` no alucinan así y van en `json`.
- **El proveedor no reintenta** (`max_retries=0`); `VoiceError.retryable` lo dice y decide el que llama. Un 429 del proveedor es `rate_limited` (429 al cliente con `Retry-After`), un timeout es 504, un fallo del proveedor es 502 y una configuración mala (401, modelo inexistente) es 503: el cliente distingue "reintenta" de "avisa a soporte".
- **Culpa del audio o culpa del proveedor.** 413/415 y los 400 que apuntan a `file` (`audio_too_short`, `unsupported_format`) son `invalid_audio` y no reintentables; cualquier otro 400 se registra con su `param` (suele ser un modelo mal escrito).
- **Solo la clase del error al log:** el mensaje del SDK puede llevar la URL con la clave.
- **El audio no toca disco ni se guarda.** `read_bounded` lee el upload por trozos en memoria y corta en cuanto pasa `max_bytes` (413) sin esperar al final. La respuesta de TTS lleva `Cache-Control: no-store`.
- **MIME sin parámetros y extensión por tabla.** `MediaRecorder` manda `audio/webm;codecs=opus` o `audio/mp4` (Safari); `AUDIO_FORMATS` lo pasa a la extensión que OpenAI entiende en `file=("audio.webm", bytes)`. `audio/aac` no está: OpenAI lo rechaza.
- **Idioma como pista, no como verdad.** `STT_LANGUAGE` es el del proyecto (`es`) y el cliente puede mandar otro por petición (por ejemplo el de la interfaz); `None` deja que el modelo detecte. `STT_PROMPT` es vocabulario del dominio (siglas, nombres de producto): mejora Whisper más que cualquier otro ajuste.
- **`FakeSynthesizer` devuelve un WAV válido**, no `b"fake"`: el frontend puede reproducirlo en desarrollo sin clave.
- **Tests a nivel HTTP** (`httpx.MockTransport`): se comprueba lo que de verdad se envía (nombre de archivo, modelo, idioma, prompt, `response_format`), no un mock del método.
- **Sin TTS en streaming ni efectos de sonido.** Trocear la respuesta del LLM por frases y mandarlas al proveedor en PCM mientras suena un teclado es parte de un pipeline en tiempo real, no de esta receta. `Synthesizer._synthesize` devuelve bytes completos; un streaming sería `AsyncIterator[bytes]` en una subclase.

## Cómo adaptarla

1. Copia `files/` en la raíz del backend, encima de `fastapi-base` y `auth-verifier`.
2. **Settings:** `class Settings(VoiceSettings, LLMSettings, BaseAppSettings)` (comparte `OPENAI_API_KEY`). En el `.env`:

   ```
   STT_PROVIDER=openai          STT_MODEL=gpt-4o-mini-transcribe   STT_LANGUAGE=es   STT_PROMPT="Acme, SKU, ERP"
   TTS_PROVIDER=openai          TTS_MODEL=gpt-4o-mini-tts          TTS_VOICE=nova    TTS_FORMAT=mp3
   ```

   En local sin clave: `STT_PROVIDER=fake` y `TTS_PROVIDER=fake`. Si tu app solo dicta, borra `Synthesizer`, `FakeSynthesizer`, `OpenAISynthesizer`, el endpoint `/synthesize` y los campos `TTS_*`: sin segundo uso no hay abstracción que mantener.
3. **Arranque** (`lifespan` de `create_app`):

   ```python
   app.state.transcriber = VoiceFactory.transcriber(settings)
   app.state.synthesizer = VoiceFactory.synthesizer(settings)
   app.include_router(voice_router)
   ```

   y al apagar, `await app.state.transcriber.close()`.
4. **Frontend:** `MediaRecorder` con `audio/webm;codecs=opus` y `audio/mp4` como respaldo para Safari; `FormData` con `file` y, si quieres, `language`; `fetch("/voice/transcribe")` con el Bearer. Para leer: `fetch("/voice/synthesize")` → `blob` → `new Audio(URL.createObjectURL(blob)).play()`. Añade `voice.use` a tus guards si tienes roles y pasa el endpoint por `rate-limit-quota`.
5. **Proveedor nuevo** (Deepgram, Groq Whisper, Whisper local): subclase de `Transcriber` con `_transcribe` y `_translate`, `class TestX(TranscriberConformance)` con la fixture, un valor en `SttProvider` y un caso en la factory. Groq y Azure con API compatible: solo `OPENAI_BASE_URL`.
6. Para comprobarla: `pytest` (37 tests sin red; con `fastapi-base` y `auth-verifier` copiadas, 50 de esta receta).

**Dependencias:** `pydantic-settings`, `fastapi`, `python-multipart` (uploads); `openai` (probado con 3.55) para el proveedor openai; `httpx` en tests.

## Origen

- Probado en producción: transcriptor base con template method (valida, mide, traduce a un error propio con `retryable`), `AudioInput(content, mime)`, texto vacío = sin voz, `no_speech_prob` de `verbose_json`, `max_retries=0`, mapa de errores del SDK a códigos, upload acotado en memoria sin tocar disco, dobles y batería de conformidad, `FakeOpenAI` con `httpx.MockTransport`; TTS bajo demanda con `audio/speech` (MP3 completo), lista de voces permitidas, `tts_max_chars`, `Cache-Control: no-store`, idioma por petición, 503 sin clave frente a 502 con fallo del proveedor, filtro de alucinaciones de Whisper; STT/TTS como ABC con factory por nombre; captura con `MediaRecorder` webm/opus y mp4 para Safari.
- No incluido en esta receta: TTS por frases en streaming y el transporte de voz en tiempo real.

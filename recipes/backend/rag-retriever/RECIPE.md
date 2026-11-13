# rag-retriever

## Cuándo usarla

Para **que el agente busque en los documentos del tenant**: trocear, embeber, guardar los vectores en un store elegido en `.env` (RAM, Qdrant o Postgres con pgvector) y buscar por similitud con aislamiento por tenant. Trae el servicio que la tool `search_documents` de `langchain-agent` espera (`document_search`), así que encaja en `agent-chat-api` sin tocar el agente.

No depende de otras recetas. **Usa `project-settings`** (bloque `RagSettings`) y **encaja con `langchain-agent`** (`DocumentSearchService`). No trae endpoints de ingesta ni lectura de PDF: tú conviertes el archivo en texto y llamas a `retriever.index`.

## Qué incluye

```
rag/
  models.py           Document · Chunk (id uuid5 + content_hash) · EmbeddedChunk · SearchHit · IndexResult · RetrievalError · RagBackend · EmbeddingsProvider
  chunking.py         TextChunker(size, overlap): párrafos → líneas → frases → palabras, con solape en límite de palabra
  embeddings.py       Embedder (ABC, errores → RetrievalError) · OpenAIEmbedder (text-embedding-3-*, lotes) · HashingEmbedder (local, sin red)
  base.py             VectorStore (ABC: upsert, existing_hashes, delete_chunks, delete_document, search) · Retriever (index, remove, search)
  in_memory.py        InMemoryVectorStore: referencia y desarrollo
  qdrant.py           QdrantVectorStore: una colección, payload = chunk, índices keyword en tenant_id y document_id
  pgvector.py         PgVectorStore: tabla rag_chunks, coseno <=>, HNSW; schema_sql(dimension) para tu migración
  settings.py         bloque RagSettings: RAG_BACKEND (obligatorio), EMBEDDINGS_PROVIDER, EMBEDDING_*, RAG_CHUNK_*, RAG_SEARCH_LIMIT, RAG_MIN_SCORE, QDRANT_*
  factory.py          EmbedderFactory · VectorStoreFactory · RagFactory.create(settings, session_factory=, embedder=, store=)
  document_search.py  DocumentSearchService(retriever): el `document_search` de la tool · format_hits(hits): contexto numerado con cita, sin scores
tests/
  rag_conformance.py  VectorStoreConformance: 7 tests que todo backend debe pasar (orden, tenant, filtros, upsert, borrado)
  test_rag.py         28 tests: conformidad en RAM y Qdrant (`:memory:`), chunking, embedders, retriever incremental, servicio, settings, factory
                      (+7 de pgvector, saltados salvo RAG_TEST_DATABASE_URL)
pytest.ini
```

## Decisiones

- **Lógica en `Retriever`, almacenamiento en `VectorStore`.** Trocear, decidir qué embeber, borrar lo sobrante y aplicar el umbral es igual en todos los backends; el store solo guarda, filtra y ordena por coseno. Un backend nuevo es una subclase más los tests de conformidad (como `agent-memory` y `rate-limit-quota`).
- **Store y embeddings elegidos en settings, sin valor por defecto para el store** (`RAG_BACKEND`): rag_tool_upv (`RETRIEVER_PROVIDER`) y aurora (`SEARCH_PROVIDER`) lo hacen así; caer en RAM en producción perdería el índice en cada reinicio.
- **Ids deterministas y hash del contenido.** `Chunk.id = uuid5(tenant:documento:índice)` y `content_hash = sha256(texto)`: reindexar el mismo documento no embebe nada, cambiar un párrafo embebe un chunk y acortarlo borra los que sobran. Está en los cuatro proyectos (uuid5 en upv y aurora, hash en ATI y Vera). El `Document.id` lo pone la app y debe ser estable (ruta, clave primaria), nunca aleatorio.
- **Tenant obligatorio y dentro de la consulta.** Todos los métodos lo toman como argumento y los backends lo filtran antes del `LIMIT` (ATI, Vera, aurora). No es un filtro más: `filters` son solo igualdades sobre `Chunk.metadata`.
- **Coseno en [0, 1] y umbral absoluto opcional** (`RAG_MIN_SCORE`, por defecto 0 = sin umbral). aurora usa 0.5 y ATI 0.4 con `text-embedding-3-small`; rag_tool_upv usa uno relativo al mejor. Depende del modelo y del corpus: mídelo con tus datos antes de ponerlo.
- **Lo que ve el LLM es texto con cita, sin scores ni tenant** (`format_hits`, ATI y aurora). Los scores van en el resultado del servicio por si la UI los quiere.
- **`DocumentSearchService` cumple el protocolo de la tool** (`search(tenant_id, query, limit) -> [{title, snippet, ...}]`): la receta `langchain-agent` no cambia. Si prefieres un nodo del grafo (Vera), llama a `retriever.search` desde el nodo.
- **Un solo error, sin texto del fondo.** `RetrievalError(kind, stage)` lleva el nombre de la clase del error original (`ConnectionError`), nunca su mensaje: puede contener la URL de la base de datos o la clave (Vera). `AppTool` ya lo convierte en `SAFE_FAILURE` para el LLM.
- **Chunking por caracteres, recursivo** (aurora: 1000/200 con `RecursiveCharacterTextSplitter`), sin dependencia de LangChain ni tokenizador. ATI trocea por tokens (500/50 con tiktoken): si lo necesitas, sustituye `TextChunker.split`.
- **`HashingEmbedder` como proveedor local**, no solo un fake de tests: bolsa de palabras con hashing, determinista, cosenos con sentido. Permite arrancar el proyecto y la demo sin clave de OpenAI (Vera tiene `FakeEmbedder` y `store != supabase` → doble).
- **Búsqueda semántica solo.** ATI y Vera añaden una rama léxica (`tsvector`) y fusión RRF con k=50; ATI además un juez LLM. Son extensiones de `PgVectorStore.search` (dos consultas y fusión en Python), no del contrato.
- **Qdrant se prueba sin servidor** con `AsyncQdrantClient(":memory:")` (rag_tool_upv). pgvector solo contra un Postgres real: sus tests se saltan sin `RAG_TEST_DATABASE_URL`.

## Cómo adaptarla

1. Copia `files/` en la raíz del backend. Sustituye `{{app_name}}` en `rag/settings.py` (nombre de la colección).
2. **Settings:** `class Settings(RagSettings, LLMSettings, BaseAppSettings)` (comparte `OPENAI_API_KEY` con `langchain-agent`). En el `.env`:

   ```
   RAG_BACKEND=qdrant            # memory | qdrant | pgvector
   QDRANT_URL=https://...        QDRANT_API_KEY=...
   EMBEDDINGS_PROVIDER=openai    # hashing en local sin clave
   EMBEDDING_MODEL=text-embedding-3-small
   EMBEDDING_DIMENSION=1536
   RAG_MIN_SCORE=0.0
   ```

   Con `pgvector`, ejecuta `schema_sql(settings.embedding_dimension)` en tu migración (o `await store.ensure_ready()` en desarrollo) y pasa `session_factory=SessionLocal` a la factory.
3. **Arranque** (`lifespan` de `create_app`):

   ```python
   retriever = RagFactory.create(settings, session_factory=SessionLocal)
   await retriever.store.ensure_ready()
   app.state.retriever = retriever
   ```

   y al agente: `registry.configure(document_search=DocumentSearchService(retriever))`.
4. **Ingesta:** convierte cada archivo en texto (pypdf, pypdfium2…) y llama a `await retriever.index(tenant_id, Document(id=ruta, title=..., text=..., source=url, metadata={"category": ...}))`. Es idempotente: llámalo también cuando el documento cambie. Para borrar, `retriever.remove(tenant_id, document_id)`. Cambiar de modelo o de dimensión obliga a reindexar todo con una colección nueva.
5. **Prompt sin tool:** `format_hits(await retriever.search(tenant_id, question))` como bloque de contexto.
6. **Backend nuevo:** subclase de `VectorStore` + `class TestMiStore(VectorStoreConformance)` con la fixture `store`, y un caso en `VectorStoreFactory`.
7. Para comprobarla: `pytest` (28 tests sin red; con `RAG_TEST_DATABASE_URL=postgresql://...` corren también los 7 de pgvector).

**Dependencias:** `pydantic-settings`; `openai` (proveedor openai); `qdrant-client` (backend qdrant, probado con 1.20); `sqlalchemy` + `psycopg` y la extensión `vector` en Postgres (backend pgvector).

## Origen

- Store elegido por settings con clase base y factory: rag_tool_upv (`core/retriever/{base,factory}.py`, Qdrant y Pinecone) y aurora (`rag-mcp/sources/video/provider_factory.py`, Qdrant, Vertex y Firestore).
- Ids deterministas `uuid5` para upsert idempotente: rag_tool_upv (`services/record_builder.py`) y aurora (`worker/document_pipeline.py`). Hash del contenido para embeber solo lo cambiado: ATI_PLATFORM (`services/knowledge_indexer.py`, `knowledge_store.py`) y Vera-Symplia (`indexing/pipeline.py`).
- Tenant obligatorio filtrado dentro de la consulta: ATI (`company_id` en `knowledge_search.py`), Vera (`inventory_id`), aurora (`tenant_id` en el payload de Qdrant).
- `Embedder` como contrato con doble local y `RetrievalError` sin texto del fondo: Vera (`core/llm/embedder.py`, `core/errors.py`).
- Chunking recursivo por caracteres 1000/200: aurora (`worker/functions.py`). Contexto numerado con fuente y sin scores: ATI (`knowledge_messages.py`) y aurora (`output_formatter.py`).
- pgvector con coseno `<=>` y HNSW: ATI (`supabase/migrations/*knowledge_entries.sql`) y Vera (`article_index.sql`).

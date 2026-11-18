# Diagrams for "How a project is structured"

Script for the images that go with the README section. Each diagram has its file name (`docs/img/`), what must be obvious at a glance, and an element-by-element description to draw or generate it. The four pieces stand on their own; the first one is the composition that brings them together.

Style shared by all of them:

- Light or white background, clean strokes, no gradients or shadows. Monospace type for file and folder names (`app.py`, `rag/`), sans-serif for labels.
- Fixed palette; the same colour means the same thing in every diagram:
  - **Dark blue**: `app.py` / the summit.
  - **Mid blue**: orchestration (`conversation.py`, `orchestrator/`).
  - **Green**: capabilities (`rag/`, `auth/`, `limits/`, `observability/`, `agentic/`).
  - **Orange**: concrete providers (`qdrant.py`, `pgvector.py`, `supabase.py`…).
  - **Light grey**: `core/` and test doubles (`in_memory.py`, `null`, `fake`).
  - **Soft red** only for what is forbidden (cycles, cross imports).
- Thin arrows with a head: they always mean "imports / depends on". They point **downwards**, except the ones crossed out in red.
- All text in English; identifiers exactly as they are in the code.

---

## 00 · Full composition

**File:** `docs/img/00-how-i-structure-a-project.png` (landscape, 16:9, printable at A3; also an `.svg` version).

**At a glance:** a mountain in the centre with `app.py` at the summit and `core/` as bedrock at the bottom; around it, three small panels with the three ideas: *by feature*, *Strategy + Factory*, *facade and stepdown*. Title at the top: **"How I structure a project: the code reads like a pyramid"**.

**Layout:**

- Centre (60 % of the width): the mountain from diagram 01, reduced but readable.
- Left column (20 %): panel "1 · By feature" = the minimal version of diagram 02 (right side only, the folder per capability).
- Right column (20 %), top: panel "4 · Strategy + Factory" = diagram 03 reduced to `.env → factory → one provider switched on`.
- Right column, bottom: panel "2 · Facade" and "3 · Stepdown" = diagram 04 reduced to a folder with its door and a file with the reading arrow.
- Footer, one line, the books: *Clean Architecture* and *Clean Code* (R. C. Martin), *Design Patterns* (Gamma et al.), *Dependency Injection* (Seemann & van Deursen), *Extreme Programming Explained* (Beck).
- A thin arrow links each panel to the part of the mountain where it applies: "by feature" points at the capabilities band; "Strategy + Factory" at the providers band; "facade and stepdown" at one specific folder in the capabilities band.

---

## 01 · The mountain (stepdown rule and composition root)

**File:** `docs/img/01-the-mountain.png` (portrait or square).

**At a glance:** a single triangle (a mountain) with five horizontal bands. At the top, one file. Each band below is wider and holds more boxes. Every arrow points down. You read it top to bottom, the same way you navigate it.

**Bands, from summit to base:**

1. **Summit (dark blue):** one box, `app.py` (in an API, `main.py` / `create_app`). Label to the right: *"The summit: reads `Settings`, calls every factory **once** and assembles the app. Nobody else builds anything."* To its left, a small grey box `Settings (.env)` with a short arrow into `app.py`.
2. **Orchestration (mid blue):** two or three boxes: `api/` (routes), `conversation.py` (one turn: memory → graph → persist). Label: *"When and in what order. Combines capabilities; implements none."*
3. **Capabilities (green):** five folders in a row: `agentic/`, `rag/`, `auth/`, `limits/`, `observability/`. Each with its door marked (a small door icon, or the facade file name underneath: `rag/__init__.py`). Label: *"One folder per thing the system does. What changes together lives together."* Between folders in this band, **no arrows**; to stress it, one horizontal arrow `rag/ → auth/` crossed out in red with the text *"capabilities never import each other"*.
4. **Providers (orange):** under each capability, its concrete files in a column. Under `rag/`: `qdrant.py`, `pgvector.py`, `in_memory.py` (the last one grey: it is the double). Under `auth/`: `supabase.py`, `jwt_verifier.py`, `static` (grey). Under `observability/`: `langfuse_tracer.py`, `opik_tracer.py`, `langsmith_tracer.py`, `null` (grey). Under `agentic/`: `llm/provider.py` with `openai`, `anthropic`, `groq`. Label: *"One file per provider. Only the chosen one is imported."*
5. **Bedrock (grey):** one wide band `core/` with three or four small boxes: `config.py (Settings)`, `errors.py`, `ids`, `models`. Label: *"What everyone uses. Small on purpose: if only one folder uses it, it does not belong here."*

**Arrows:** from `app.py` to each capability (one per folder, caption on the first: *"factory.create(settings)"*); from each capability to its providers; from every band down to `core/`. None goes up.

**Left margin:** a long vertical arrow from top to bottom with the text *"This is how you read it. This is how it depends."* and three marks: *"general"* at the top, *"detail"* at the bottom.

**Right margin, small:** the references: *"Stepdown rule, Clean Code ch. 3 · Composition root, Dependency Injection ch. 4 · Acyclic dependencies, Clean Architecture ch. 14"*.

---

## 02 · By feature, not by layer

**File:** `docs/img/02-by-feature.png` (landscape, two halves).

**At a glance:** the same feature ("search documents") drawn twice. On the left it is spread over three cross-cutting folders and you have to follow it with your eyes; on the right it sits in one folder. The right side is the chosen one.

**Left half, titled "By layer (the usual hexagonal)"**, in muted tones:

```
domain/
  ports/
    document_search.py      ← contract
application/
  use_cases/
    search_documents.py     ← logic
infrastructure/
  qdrant/
    document_repository.py  ← provider
  pgvector/
    document_repository.py
tests/
  fakes/
    fake_document_search.py ← test double
```

The four boxes of the feature highlighted in the same green and joined by a dotted line that snakes through the three folders. Label underneath: *"One change to 'search documents' touches four folders. To read it you open three places."* A small "no" symbol (crossed circle) in the corner.

**Right half, titled "By capability (what I do)"**, in full colour:

```
rag/
  __init__.py     ← the door
  base.py         ← contract (ABC) + shared logic
  qdrant.py       ← provider
  pgvector.py     ← provider
  in_memory.py    ← test double
  factory.py      ← match on RAG_BACKEND
  settings.py     ← RagSettings block
  models.py
```

One single green frame around the whole folder. Label: *"Everything about 'search documents' in one place. Open one folder and you know which file to read first."* A small "yes" symbol (check mark) in the corner.

**Between the halves,** a thick left-to-right arrow with the text *"what changes together lives together"* and, small underneath: *"Common Closure Principle · screaming architecture (Clean Architecture chs. 13 and 21) · vertical slices"*.

**At the very bottom,** a grey band with `core/` and the note: *"The only cross-cutting folder: settings, errors, ids, base models. Everything else lives in its capability."*

---

## 03 · Strategy + Factory (and when not to)

**File:** `docs/img/03-strategy-factory.png` (landscape, left-to-right flow).

**At a glance:** a value from `.env` enters on the left, goes through a `match` and switches on exactly one of the providers hanging from a base class; the others stay off (not imported). At the foot, a separate box says when **not** to do this.

**Elements, left to right:**

1. **`.env` box** (grey) with one line: `RAG_BACKEND=qdrant`. Arrow to →
2. **`settings.py` box** (grey): `RagSettings.rag_backend: RagBackend` and under it the Enum `RagBackend = memory | qdrant | pgvector`. Arrow to →
3. **`factory.py` box** (mid blue) drawn as a switch with three outputs; inside, the essential code:

   ```python
   match settings.rag_backend:
       case RagBackend.MEMORY:   from .in_memory import InMemoryVectorStore
       case RagBackend.QDRANT:   from .qdrant import QdrantVectorStore
       case RagBackend.PGVECTOR: from .pgvector import PgVectorStore
   raise ValueError(f"Unknown RAG backend: {value!r}")
   ```

   Only the `qdrant` output is drawn in a solid line and full colour; the other two are dashed and grey, with the label *"not imported: not installed"*. The `raise` line carries a soft-red label: *"unknown value → an error that names it, never a silent default"*.
4. **Providers column** (orange): three boxes `QdrantVectorStore`, `PgVectorStore`, `InMemoryVectorStore` (this one grey, tagged *"test double / development"*). All three hang, with inheritance arrows (hollow head), from →
5. **`base.py` box** (green, above the column): `class VectorStore(ABC)` with two compartments: *"shared logic (here)"* and *"abstract: `upsert`, `search`, `delete_document`"*. Label: *"The subclass only stores and reads. Whatever is the same for everyone lives in the base."*
6. Far right, a dark-blue box `app.py` with the line `retriever = RagFactory.create(settings)` and the label *"once, at startup"*.

**Bottom box, dashed border, titled "When NOT to":**

- *"One provider and no test double → one concrete class. No `base.py`, no `factory.py`."*
- *"The abstraction is extracted when the second implementation shows up. It is a local, cheap change."*
- Small: *"YAGNI · Extreme Programming Explained (Beck) · Strategy and Factory Method, Design Patterns (Gamma et al.)"*.

---

## 04 · Facade and stepdown rule

**File:** `docs/img/04-facade-and-stepdown.png` (square, two stacked scenes).

**At a glance:** on top, a folder with a single door and the other files behind it; below, a file seen as a newspaper, headline at the top and detail at the bottom.

**Top scene, "Facade: one door per folder":**

- A folder `rag/` drawn as a room seen from above. On the front wall, a door named `__init__.py` (with the alternative `rag/rag.py` in brackets). Inside, the internal files: `base.py`, `qdrant.py`, `pgvector.py`, `factory.py`, `chunking.py`, `models.py`.
- Outside, two boxes that use it: `app.py` and `api/`. Their arrows go in **through the door only**. A third arrow trying to reach `qdrant.py` straight through the wall is crossed out in red: *"nobody imports the internal pieces from outside"*.
- Label: *"You can rearrange the inside without touching whoever uses it."* Exceptions, small: *"`core/` is imported file by file; detail subfolders (`providers/`, `queries/`) need no door."*

**Bottom scene, "Stepdown: the file reads like a newspaper":**

- A file `base.py` drawn as a newspaper page with three blocks top to bottom:
  1. Big headline: `class Retriever` (*"the main class, the first thing you see"*).
  2. Subheading: `class VectorStore(ABC)` and the public methods `index`, `search`, `remove`.
  3. Fine print: `_guard`, helpers, constants (*"the detail, at the end"*).
- Left of the page, a vertical downward arrow with *"general → detail"*.
- Underneath, a row of four folders repeating the same arrow at project scale: `app.py` → `conversation.py` → `rag/` → `qdrant.py`, with the label *"The same between folders: summit, orchestration, capability, provider."*
- Small: *"Stepdown rule, Clean Code ch. 3 · Facade, Design Patterns"*.

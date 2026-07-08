# Auralys Architecture Diagram

This document captures the current project architecture as implemented in the repository.

For the dedicated agent-layer view, see [auralys_agent_pipeline.md](C:/Users/Youss/OneDrive/Bureau/auralys/docs/auralys_agent_pipeline.md).

## 1. System Overview

```mermaid
flowchart LR
    classDef ext fill:#f8f1e7,stroke:#7a5c2e,color:#2c2116,stroke-width:1px
    classDef app fill:#e7f0ea,stroke:#2d6a4f,color:#102418,stroke-width:1px
    classDef data fill:#e8eef9,stroke:#355070,color:#15202b,stroke-width:1px
    classDef ai fill:#f6e8ff,stroke:#6d3ea2,color:#251537,stroke-width:1px
    classDef ui fill:#fff4d6,stroke:#946200,color:#2f2400,stroke-width:1px

    User[User]
    Vue[Vue Frontend<br/>frontend/src/App.vue]
    Api[FastAPI<br/>app/api.py]
    Pipeline[QuestionPipeline<br/>app/pipeline/question_pipeline.py]
    Speech[SpeechService<br/>STT/TTS/live voice]
    Answer[AnswerService]
    Router[Query Router]
    Hybrid[HybridRetriever]
    SQL[SQLRetriever]
    QdrantR[QdrantRetriever]
    Local[LocalRetriever]
    Context[Context Builder]
    LLM[LLMService]
    Commercial[Commercial Analyzer]
    History[HistoryService]
    Postgres[(Postgres<br/>fiches + chunks + discussion_history)]
    Qdrant[(Qdrant<br/>dense vectors)]
    Processed[(Processed JSON fiches)]
    GeminiEmb[Gemini Embeddings]
    GeminiLLM[Gemini / Groq LLM]
    Raw[(Raw JSON source data)]
    Normalize[Normalize + Chunk Build]
    IngestPg[Import to Postgres]
    IndexQ[Index to Qdrant]

    User --> Vue
    User --> Api
    Vue --> Api
    Api --> Pipeline
    Pipeline --> Speech
    Pipeline --> Answer
    Pipeline --> History

    Answer --> Router
    Router --> Hybrid
    Hybrid --> SQL
    Hybrid --> QdrantR
    Hybrid --> Local
    SQL --> Postgres
    QdrantR --> GeminiEmb
    QdrantR --> Qdrant
    Local --> Processed
    Hybrid --> Context
    Context --> Answer
    Answer --> Commercial
    Answer --> LLM
    LLM --> GeminiLLM
    History --> Postgres

    Raw --> Normalize
    Normalize --> Processed
    Normalize --> IngestPg
    Normalize --> IndexQ
    IngestPg --> Postgres
    IndexQ --> GeminiEmb
    IndexQ --> Qdrant

    class User ext
    class Raw,Processed,Postgres,Qdrant data
    class Api,Pipeline,Speech,Answer,Router,Hybrid,SQL,QdrantR,Local,Context,Commercial,History,Normalize,IngestPg,IndexQ app
    class GeminiEmb,GeminiLLM ai
    class Vue ui
```

## 2. Ingestion Pipeline

```mermaid
flowchart TD
    classDef job fill:#e7f0ea,stroke:#2d6a4f,color:#102418,stroke-width:1px
    classDef store fill:#e8eef9,stroke:#355070,color:#15202b,stroke-width:1px
    classDef ext fill:#f8f1e7,stroke:#7a5c2e,color:#2c2116,stroke-width:1px

    Raw[data/raw_json] --> Normalize[normalize.py<br/>load_fiches_from_directory]
    Normalize --> Fiche[FicheSchema]
    Fiche --> ExportProcessed[export_processed_fiches]
    Fiche --> ExportSplit[export_split_maintenance]
    Fiche --> ExportCsv[export_processed_csvs]
    Fiche --> ExportRefs[export_unique_values]
    Fiche --> BuildChunks[build_chunks.py]

    ExportProcessed --> Processed[data/processed]
    ExportSplit --> Split[data/processed/maintenance]
    ExportCsv --> Csv[data/processed_csv]
    ExportRefs --> Refs[data/unique_reference_values.json]

    Fiche --> ImportPg[import_json_to_postgres.py]
    BuildChunks --> ImportPg
    ImportPg --> Pg[(Postgres<br/>fiches table<br/>chunks table)]

    BuildChunks --> DenseIndex[index_qdrant.py]
    DenseIndex --> EmbedDoc[EmbeddingService<br/>RETRIEVAL_DOCUMENT]
    EmbedDoc --> Qdrant[(Qdrant collection)]

    class Raw,Processed,Split,Csv,Refs,Pg,Qdrant store
    class Normalize,Fiche,ExportProcessed,ExportSplit,ExportCsv,ExportRefs,BuildChunks,ImportPg,DenseIndex,EmbedDoc job
```

## 3. Text Query Runtime

```mermaid
sequenceDiagram
    autonumber
    participant U as User / Frontend
    participant API as FastAPI
    participant QP as QuestionPipeline
    participant AS as AnswerService
    participant QR as route_query
    participant HR as HybridRetriever
    participant SR as SQLRetriever
    participant QRD as QdrantRetriever
    participant LR as LocalRetriever
    participant CB as Context Builder
    participant CA as Commercial Analyzer
    participant LLM as LLMService
    participant HS as HistoryService
    participant PG as Postgres
    participant QD as Qdrant

    U->>API: POST /ask or /rag/query
    API->>QP: answer_text(query)
    QP->>AS: answer(query)
    AS->>QR: normalize + detect intent/filters/route
    AS->>HR: search(normalized_query)

    alt route includes postgres
        HR->>SR: search(query, filters)
        SR->>PG: full-text + ILIKE + metadata filters
        PG-->>SR: matching chunks
        SR-->>HR: RetrievalHit[]
    end

    alt route includes qdrant
        HR->>QRD: search(query, filters)
        QRD->>QD: query_points(query embedding)
        QD-->>QRD: dense matches
        QRD-->>HR: RetrievalHit[]
    end

    alt no ranked hits
        HR->>LR: fallback search
        LR-->>HR: local hits from processed JSON
    end

    HR-->>AS: ranked RetrievalResult
    AS->>CB: build_context(result)
    AS->>CA: analyze_commercial_opportunity(query, result)
    AS->>LLM: answer_details(prompt, context, analysis)
    LLM-->>AS: answer / fallback / provider metadata
    AS-->>QP: answer payload + hits + metrics + spoken_text
    QP->>HS: save_response(...)
    HS->>PG: insert discussion_history
    QP-->>API: PipelineResponse
    API-->>U: JSON response
```

## 4. Voice Query Runtime

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant API as FastAPI or CLI
    participant QP as QuestionPipeline
    participant SP as SpeechService
    participant AS as AnswerService
    participant HS as HistoryService
    participant PG as Postgres

    U->>API: /ask-audio or live-voice or CLI ask-audio
    API->>QP: answer_voice(input_audio_path)
    QP->>SP: transcribe(audio)
    SP-->>QP: transcript
    QP->>AS: answer(transcript)
    AS-->>QP: answer payload

    opt output audio requested
        QP->>SP: synthesize(spoken_text or answer)
        SP-->>QP: output_audio_path
    end

    QP->>HS: save_response(response)
    HS->>PG: insert discussion_history
    QP-->>API: PipelineResponse
    API-->>U: transcript + answer + optional audio path
```

## 5. Dependency Assembly

```mermaid
flowchart TB
    classDef node fill:#e7f0ea,stroke:#2d6a4f,color:#102418,stroke-width:1px
    classDef store fill:#e8eef9,stroke:#355070,color:#15202b,stroke-width:1px

    Container[AppContainer<br/>app/bootstrap.py]
    DB[(Database)]
    Emb[EmbeddingService]
    Sql[SQLRetriever]
    QRet[QdrantRetriever]
    Hybrid[HybridRetriever]
    LLM[LLMService]
    Opp[OpportunityLogger]
    Ans[AnswerService]
    Speech[SpeechService]
    Hist[HistoryService]
    Pipe[QuestionPipeline]

    Container --> DB
    Container --> Emb
    Container --> Sql
    Container --> QRet
    Emb --> QRet
    Sql --> Hybrid
    QRet --> Hybrid
    Container --> LLM
    Container --> Opp
    Hybrid --> Ans
    LLM --> Ans
    Opp --> Ans
    Container --> Speech
    Container --> Hist
    Ans --> Pipe
    Speech --> Pipe
    Hist --> Pipe

    class Container,Emb,Sql,QRet,Hybrid,LLM,Opp,Ans,Speech,Hist,Pipe node
    class DB store
```

## 6. Main Responsibilities

- `app/main.py`: CLI entrypoint for ingestion, indexing, serving, evaluation, and voice commands.
- `app/api.py`: HTTP surface for health, reference values, RAG queries, history, and voice endpoints.
- `app/bootstrap.py`: dependency wiring through `AppContainer`.
- `app/ingestion/*`: normalization, exports, chunk building, Postgres ingestion, Qdrant indexing.
- `app/retrieval/*`: routing, SQL retrieval, dense retrieval, local fallback, reranking, context building.
- `app/embeddings/embedding_service.py`: dense embedding generation for Qdrant query and indexing.
- `app/llm/*`: prompt building, model invocation, token usage, answer shaping.
- `app/audio/speech_service.py`: STT, TTS, live microphone capture, voice output.
- `app/history/history_service.py`: persistence of conversation results into Postgres.
- `frontend/*`: Vue frontend for interacting with the API.

## 7. Regeneration Notes

When these areas change, the diagrams should usually be updated:

- retrieval routing or ranking logic
- ingestion targets or storage schema
- embedding provider/backend
- API endpoints
- pipeline assembly in `AppContainer`

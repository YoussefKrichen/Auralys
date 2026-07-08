# Auralys Agent Pipeline

This document focuses on the **Auralys agent layer**: how a message enters the agent, how intent is routed, which skills and tools are used, where approval applies, and how memory and persistence fit into the architecture.

It complements the broader system view in [architecture_diagram.md](C:/Users/Youss/OneDrive/Bureau/auralys/docs/architecture_diagram.md).

## 1. Agent At A Glance

```mermaid
flowchart LR
    classDef ui fill:#eaf2ff,stroke:#315ea8,color:#13233e,stroke-width:1px
    classDef app fill:#eaf5ee,stroke:#2f6d4f,color:#112218,stroke-width:1px
    classDef tool fill:#fff3de,stroke:#9a6a1f,color:#312208,stroke-width:1px
    classDef data fill:#edf0f5,stroke:#556070,color:#17202a,stroke-width:1px
    classDef policy fill:#fce9ea,stroke:#a24a52,color:#351419,stroke-width:1px

    User[User / Frontend]
    API[POST /agent/chat<br/>app/api.py]
    Orchestrator[AgentOrchestrator]
    Router[IntentRouter]
    Skill[Selected Skill]
    Tools[ERP / RAG / Maps / Memory]
    Policy[Action Policy Check]
    Synthesis[LLM Final Synthesis]
    Response[AgentChatResponse]
    Store[(AgentStore / Postgres)]

    User --> API
    API --> Orchestrator
    Orchestrator --> Router
    Router --> Skill
    Skill --> Tools
    Skill --> Policy
    Policy --> Synthesis
    Skill --> Synthesis
    Synthesis --> Response
    Response --> User

    Orchestrator --> Store
    Policy --> Store
    Tools --> Store

    class User,API,Response ui
    class Orchestrator,Router,Skill,Synthesis app
    class Tools tool
    class Store data
    class Policy policy
```

## 2. Main Runtime Flow

```mermaid
sequenceDiagram
    autonumber
    participant U as User / Vue Frontend
    participant API as FastAPI /agent/chat
    participant ORCH as AgentOrchestrator
    participant IR as IntentRouter
    participant SK as Skill
    participant TP as Tools
    participant AP as Action Policy
    participant LLM as LLMService
    participant DB as AgentStore / Postgres

    U->>API: POST /agent/chat {message, role, context}
    API->>ORCH: handle_chat(request)
    ORCH->>IR: detect_intent(message)
    IR-->>ORCH: AgentIntent
    ORCH->>SK: run(request)
    SK->>TP: call ERP / RAG / Maps as needed
    TP-->>SK: business payload
    SK-->>ORCH: SkillResult(answer, actions, sources, payload)

    loop for each proposed action
        ORCH->>AP: check_action_policy(action, role)
        AP-->>ORCH: allowed / pending approval / blocked
    end

    ORCH->>LLM: synthesize final answer from skill draft + payload + actions
    LLM-->>ORCH: final answer

    ORCH->>DB: save conversation
    ORCH->>DB: save checked actions
    ORCH-->>API: AgentChatResponse
    API-->>U: final answer + sources + actions + approval flags
```

## 3. Intent Routing

The agent entrypoint is [AgentOrchestrator](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/core/orchestrator.py), but the first decision is made by [IntentRouter](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/core/intent_router.py).

Routing works in two stages:

1. Try LLM intent classification.
2. Fall back to keyword heuristics if the LLM classifier fails.

Current intents:

- `ASK_CLIENT_HISTORY`
- `ASK_NEXT_SAV_DESTINATION`
- `ASK_ALERTS`
- `ASK_MAINTENANCE_PROBLEM`
- `ASK_DAILY_REPORT`
- `ASK_STOCK_STATUS`
- `GENERAL_QUESTION`

```mermaid
flowchart TD
    A[Incoming message] --> B[IntentRouter.detect_intent]
    B --> C{LLM intent available?}
    C -->|Yes| D[Return LLM-picked AgentIntent]
    C -->|No| E[Keyword fallback routing]
    E --> F[Client history]
    E --> G[SAV planning]
    E --> H[Alerts]
    E --> I[Maintenance diagnosis]
    E --> J[Daily report]
    E --> K[Stock status]
    E --> L[General question]
```

## 4. Skill Layer

Once the intent is known, the orchestrator selects one skill implementation.

```mermaid
flowchart TB
    Intent[AgentIntent] --> H1[ClientHistorySkill]
    Intent --> H2[SAVPlanningSkill]
    Intent --> H3[AlertManagementSkill]
    Intent --> H4[MaintenanceDiagnosisSkill]
    Intent --> H5[CEOReportingSkill]
    Intent --> H6[GeneralQuestionSkill]
```

Current skill responsibilities:

- [ClientHistorySkill](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/skills/client_history.py): ERP history + interventions + reclamations + RAG client docs.
- [SAVPlanningSkill](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/skills/sav_planning.py): route recommendation from interventions, priority, and travel duration.
- [AlertManagementSkill](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/skills/alert_management.py): delayed reclamations and low-stock style alerts.
- [MaintenanceDiagnosisSkill](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/skills/maintenance_diagnosis.py): similar cases from RAG plus latest intervention context.
- [CEOReportingSkill](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/skills/ceo_reporting.py): operational summary for leadership review.
- [GeneralQuestionSkill](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/skills/general_question.py): direct conversational answer or lightweight RAG only when needed.

## 5. Tooling Under The Skills

The agent does not talk directly to infrastructure. Skills call tool abstractions.

```mermaid
flowchart LR
    classDef skill fill:#eaf5ee,stroke:#2f6d4f,color:#112218,stroke-width:1px
    classDef tool fill:#fff3de,stroke:#9a6a1f,color:#312208,stroke-width:1px
    classDef infra fill:#edf0f5,stroke:#556070,color:#17202a,stroke-width:1px

    CH[ClientHistorySkill] --> ERP[ERPTool]
    CH --> RAG[RAGTool]

    MD[MaintenanceDiagnosisSkill] --> ERP
    MD --> RAG

    SP[SAVPlanningSkill] --> ERP
    SP --> MAPS[MapsTool]

    AM[AlertManagementSkill] --> ERP
    CEO[CEOReportingSkill] --> ERP
    GQ[GeneralQuestionSkill] --> RAG

    ERP --> Processed[Processed fiches / pseudo-ERP view]
    RAG --> Hybrid[HybridRetriever]
    MAPS --> RouteMath[Route matrix / travel scoring]

    Hybrid --> SQL[SQLRetriever]
    Hybrid --> QDR[QdrantRetriever]
    Hybrid --> Local[Local fallback]

    SQL --> PG[(Postgres)]
    QDR --> QD[(Qdrant)]
    Local --> JSON[(Processed JSON)]

    class CH,MD,SP,AM,CEO,GQ skill
    class ERP,RAG,MAPS tool
    class Processed,Hybrid,SQL,QDR,Local,PG,QD,JSON,RouteMath infra
```

### ERPTool

[ERPTool](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/tools/erp.py) is not an external ERP integration yet. It builds a business-facing operational view from processed maintenance fiches:

- client lookup
- client history
- interventions
- reclamations
- stock approximation
- opening-hours heuristics
- diffuser state

### RAGTool

[RAGTool](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/tools/rag.py) wraps the repository’s hybrid retrieval stack:

- SQL exact retrieval
- Qdrant semantic retrieval
- local JSON fallback

### MapsTool

[MapsTool](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/tools/maps.py) currently computes route duration/distance from coordinates using local math rather than a live external map API.

### MemoryTool

[MemoryTool](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/tools/memory.py) persists:

- feedback
- pending memory
- business rules
- user preferences

## 6. Action Policy And Approval Flow

Skills may propose actions, but those actions do not execute freely.

The orchestrator applies:

- `check_action_policy(...)`
- `apply_policy(...)`

This determines whether an action is:

- allowed
- blocked
- pending approval

```mermaid
flowchart TD
    A[SkillResult.proposed_actions] --> B[Policy check per action]
    B --> C{Allowed?}
    C -->|No| D[Blocked action]
    C -->|Yes, low risk| E[Allowed action]
    C -->|Yes, but sensitive| F[Pending approval]
    D --> G[Included in response as blocked]
    E --> H[Included in response as allowed]
    F --> I[Persisted in agent_actions]
    I --> J[CEO/Admin review endpoints]
    J --> K[Approve or reject]
```

Relevant endpoints:

- `GET /agent/actions/pending`
- `POST /agent/actions/{action_id}/approve`
- `POST /agent/actions/{action_id}/reject`

## 7. Final Answer Synthesis

The skill does not always produce the final user-facing wording directly.

[AgentOrchestrator](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/core/orchestrator.py) takes:

- the detected intent
- the skill draft answer
- the sources
- the checked actions
- a compact payload excerpt

and sends them to `LLMService.answer_details(...)` to produce the final response.

This gives a two-layer agent response:

1. **Business/tool layer**: structured skill output.
2. **Language layer**: final concise natural-language answer.

## 8. Persistence Model

The agent persists multiple artifacts through [AgentStore](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/store.py).

```mermaid
flowchart LR
    Chat[Agent chat] --> Conv[conversations]
    Chat --> Msg[messages]
    Actions[Proposed actions] --> Act[agent_actions]
    ToolCalls[Tool usage] --> Logs[agent_tool_logs]
    Feedback[User feedback] --> Fdbk[agent_feedback]
    Memory[Business rules / preferences / corrections] --> Mem[memories]
```

Persisted layers:

- conversation row
- user message
- assistant message
- proposed actions
- tool logs
- feedback
- active memory

## 9. Role Of The Frontend

The current Vue frontend mainly uses the agent through:

- `POST /agent/chat`
- review/admin endpoints for CEO space
- memory/conversation inspection endpoints

So the frontend is not only a chat surface. It is also:

- an approval console
- a review queue
- a memory browser
- a conversation inspector

## 10. Agent Pipeline In One View

```mermaid
flowchart TD
    U[User message] --> API[FastAPI /agent/chat]
    API --> ORCH[AgentOrchestrator]
    ORCH --> INTENT[IntentRouter]
    INTENT --> SKILL[Selected skill]

    SKILL --> ERP[ERPTool]
    SKILL --> RAG[RAGTool]
    SKILL --> MAPS[MapsTool]

    ERP --> DATA1[Processed maintenance data]
    RAG --> DATA2[Hybrid retrieval]
    MAPS --> DATA3[Route scoring]

    SKILL --> ACTIONS[Proposed actions]
    ACTIONS --> POLICY[Policy + approval check]

    SKILL --> SYNTH[LLM final synthesis]
    POLICY --> SYNTH

    SYNTH --> RESP[AgentChatResponse]
    RESP --> UI[Frontend]

    ORCH --> STORE[Conversation + action persistence]
    UI --> FEEDBACK[Feedback / review / approval]
    FEEDBACK --> STORE
    STORE --> MEMORY[Active memory]
```

## 11. Practical Reading Guide

If you want to understand the agent implementation quickly, read in this order:

1. [app/api.py](C:/Users/Youss/OneDrive/Bureau/auralys/app/api.py) for the HTTP entrypoints.
2. [app/bootstrap.py](C:/Users/Youss/OneDrive/Bureau/auralys/app/bootstrap.py) for dependency wiring.
3. [app/agent/core/orchestrator.py](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/core/orchestrator.py) for the main control flow.
4. [app/agent/core/intent_router.py](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/core/intent_router.py) for routing decisions.
5. `app/agent/skills/*` for business behaviors by intent.
6. `app/agent/tools/*` for data/tool abstractions.
7. [app/agent/store.py](C:/Users/Youss/OneDrive/Bureau/auralys/app/agent/store.py) for persistence and approval state.

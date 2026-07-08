# Auralys Agent Workflow Overview

## Goal

This document gives a simple, presentation-ready view of how the Auralys agent works from user request to final reviewed answer.

## One-Line Flow

User or Voice Input -> Frontend / API -> Intent Routing -> Skill Execution -> Tools and Data -> Policy Check -> Final Answer Synthesis -> Response -> Review and Memory

## Main Pipeline

## 1. User Entry

- The user sends a message from the SAV or CEO interface.
- The message can come from typed input or from voice transcription.
- The frontend sends the request to `POST /agent/chat`.

## 2. API Entry

- FastAPI receives the request in `app/api.py`.
- The API forwards the payload to the agent orchestrator.
- The payload includes the user role, message, and optional context.

## 3. Intent Routing

- `IntentRouter` decides what the user is asking.
- It first tries LLM-based classification.
- If that fails, it falls back to keyword rules.
- The result is one business intent.

Current intents:

- `ASK_CLIENT_HISTORY`
- `ASK_NEXT_SAV_DESTINATION`
- `ASK_ALERTS`
- `ASK_MAINTENANCE_PROBLEM`
- `ASK_DAILY_REPORT`
- `ASK_STOCK_STATUS`
- `GENERAL_QUESTION`

## 4. Skill Selection

- `AgentOrchestrator` maps the detected intent to one skill.
- Each skill focuses on one operational problem.
- The skill produces:
- a draft answer
- source labels
- proposed actions
- a structured payload

Current skills:

- Client history
- SAV planning
- Alert management
- Maintenance diagnosis
- CEO reporting
- General question

## 5. Tool And Data Layer

- Skills call tools instead of querying infrastructure directly.
- This keeps the agent architecture modular.

Main tools:

- `ERPTool`: reads operational client and intervention data from processed fiches
- `RAGTool`: queries the hybrid retrieval system
- `MapsTool`: scores routes and travel durations
- `MemoryTool`: stores feedback, memory, and reusable rules

## 6. Retrieval Layer

- When needed, `RAGTool` uses the hybrid retriever.
- Hybrid retrieval combines:
- SQL exact search
- Qdrant semantic search
- local JSON fallback

Important note:

- General conversational requests do not always use RAG anymore.
- Greetings and meta questions can now bypass retrieval.

## 7. Action Policy Layer

- A skill can propose actions.
- Every proposed action is checked by the policy layer.
- The policy decides whether the action is:
- allowed
- blocked
- pending approval

This is where the architecture becomes agentic rather than simple question-answering.

## 8. Final Answer Synthesis

- The skill draft is not always the final user answer.
- The orchestrator builds a final synthesis prompt.
- The LLM rewrites the draft into a concise final answer.
- The synthesis uses:
- the draft answer
- the payload
- the sources
- the checked actions

## 9. Persistence

- The conversation is stored in Postgres through `AgentStore`.
- The system also stores:
- user message
- assistant message
- proposed actions
- feedback
- tool logs
- active memory

## 10. Review Loop

- The CEO space can inspect responses and pending actions.
- A reviewer can approve, correct, or reject outputs.
- Feedback can be turned into reusable memory.
- This closes the loop between execution and improvement.

## Practical Architecture View

## Frontline Flow

- SAV user asks a question
- Intent is routed
- The right skill is selected
- Tools gather evidence
- Policy checks any proposed actions
- The final answer is synthesized
- The result is saved and returned

## Governance Flow

- CEO or reviewer opens the queue
- Reviews answers and proposed actions
- Approves or rejects sensitive actions
- Saves corrections and memory
- Improves future behavior

## Summary

- The frontend is the entry point.
- The API is the transport layer.
- The orchestrator is the control tower.
- Skills are the business brains.
- Tools are the execution adapters.
- Policy is the safety layer.
- Memory and review are the learning loop.

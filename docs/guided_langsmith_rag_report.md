# Guided Report: RAG Reasoning and LangSmith Evaluation

## Goal

This update adds three complementary improvements to the Auralys RAG pipeline:

1. Guided internal reasoning in the answer prompt.
2. Structured reasoning signals in the runtime output.
3. A LangSmith LLM-as-judge evaluator for grounded answer quality.

The objective is to improve answer quality and evaluation quality without making correctness depend on exposing a raw chain-of-thought.

## What Changed

### 1. Guided reasoning in the prompt

File:
- [app/llm/prompt_builder.py](/C:/Users/Youss/OneDrive/Bureau/auralys/app/llm/prompt_builder.py)

The prompt now explicitly tells the model to:
- identify reliable facts first
- separate observed facts from cautious deductions
- base recommendations on retrieved context
- surface ambiguity and missing information
- avoid exposing the full chain-of-thought

This is a "reason better internally, answer cleanly externally" design.

### 2. Structured reasoning signals in the answer payload

Files:
- [app/llm/answer_service.py](/C:/Users/Youss/OneDrive/Bureau/auralys/app/llm/answer_service.py)
- [app/pipeline/question_pipeline.py](/C:/Users/Youss/OneDrive/Bureau/auralys/app/pipeline/question_pipeline.py)
- [schemas/pipeline_schema.py](/C:/Users/Youss/OneDrive/Bureau/auralys/schemas/pipeline_schema.py)

The pipeline now emits:
- `reasoning_signals`
- `reasoning_summary`

These fields are deterministic and evaluation-friendly. They currently include:
- grounding status
- retrieved hit count
- top chunk type
- top client
- top maintenance number
- distinct clients seen in evidence
- chunk types present in evidence
- evidence sources
- matched commercial products
- missing information
- recommended next steps

This is useful for:
- LangSmith trace inspection
- custom evaluators
- debugging low-quality answers
- detecting when the model answered without sufficient grounding

### 3. LangSmith LLM-as-judge evaluator

File:
- [app/evaluation/langsmith_runner.py](/C:/Users/Youss/OneDrive/Bureau/auralys/app/evaluation/langsmith_runner.py)

The LangSmith eval flow now keeps the previous metrics and adds:
- `reasoning_grounded`
- `reasoning_structure_coverage`
- `llm_judge_grounded_answer`

The LLM judge receives:
- the question
- the reference answer
- the system answer
- reasoning signals
- the top retrieved hits

It returns strict JSON with:
- `score`
- `comment`

The score is normalized into `[0, 1]`.

## Why This Design

### Why not evaluate free-form chain-of-thought?

Free-form CoT is a weak contract for evaluation because:
- it is unstable across runs
- it can be verbose without being correct
- it can accidentally leak internal reasoning details
- it is harder to compare across datasets and experiments

Structured reasoning signals are more stable and easier to inspect.

### Why keep exact-match style metrics too?

The existing metrics still matter:
- exact match is strict and useful for narrow tasks
- contains-reference is a lightweight recall check
- retrieved-context-count is a retrieval coverage signal

The new LLM judge complements them rather than replacing them.

## Runtime Behavior

### Answer generation

The answer pipeline still produces one final operator-facing answer.

What changed is the surrounding instrumentation:
- the prompt is more explicit about grounded reasoning
- traces now include reasoning metadata
- evaluators can inspect evidence quality, not just text overlap

### LangSmith traces

The LangSmith trace for `auralys_answer` now includes:
- `reasoning_signals`
- `reasoning_summary`

This makes it easier to diagnose cases like:
- correct answer, weak evidence
- wrong answer, strong evidence but poor synthesis
- fallback answer with no grounding

## How To Run

### Sync the dataset

```powershell
python -m app.main langsmith-sync data/eval/golden_truth_dataset.json auralys-golden
```

### Run the LangSmith evaluation

```powershell
python -m app.main eval-langsmith data/eval/golden_truth_dataset.json auralys-golden
```

### Required environment

- `LANGSMITH_API_KEY`
- optional: `LANGSMITH_PROJECT`
- optional: `LANGSMITH_TRACING=true`
- one active answer/judge provider:
  - `GROQ_API_KEY`, or
  - `GOOGLE_API_KEY`

## What The New Metrics Mean

### `reasoning_grounded`

Boolean metric.

It checks whether:
- the answer reported grounded reasoning
- and at least one hit was actually retrieved

This is a simple guardrail metric, not a semantic truth metric.

### `reasoning_structure_coverage`

Float metric in `[0, 1]`.

It measures how much of the expected structured reasoning payload is present.

High score means the runtime emitted enough metadata to inspect and judge the run properly.

### `llm_judge_grounded_answer`

Float metric in `[0, 1]`.

It is the most useful qualitative evaluator in this update.

It asks:
- is the final answer correct relative to the reference?
- is it supported by retrieved evidence?
- is it operationally useful?

## Tradeoffs and Limits

### Strengths

- Better observability than plain answer-only evaluation.
- Better alignment between retrieval evidence and judged output.
- Safer than exposing raw chain-of-thought.
- Works with the existing LangSmith flow.

### Limits

- The judge uses the currently configured LLM provider, so it can inherit provider bias.
- If no provider key is configured, the LLM judge is skipped.
- `reasoning_grounded` is heuristic. It does not prove factual correctness.
- The current LangSmith flow still evaluates the answer pipeline, not the `/reference-values` endpoint directly.

## Recommended Next Steps

1. Add dataset cases that specifically target normalization-sensitive behavior.
2. Add evaluator variants for client matching, maintenance-number fidelity, and evidence citation quality.
3. If needed, create a second LangSmith target for `/reference-values` style outputs rather than only operator answers.

## Practical Conclusion

This update moves the project from "does the answer text roughly match?" toward "did the RAG system retrieve useful evidence, reason in a grounded way, and produce an operationally correct answer?"

That is the right level for LangSmith in this codebase.

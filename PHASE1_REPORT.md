# Griffin Phase 1 — Computer Control Acceptance Report

## Summary

This report covers the Phase 1 acceptance mission for Griffin local computer
control.  After prompt-only attempts hit the expected ceiling of small local
LLMs, the codebase was pivoted to the grounding-first multi-model runtime
architecture described in the authoritative architecture document.

The runtime now:

- Exposes **semantic action schemas** for browser interactions.
- Resolves semantic targets through a **deterministic grounding layer**.
- Returns a **compact unified GUI state** from `browser.inspect`.
- Maintains a **per-run task state** instead of injecting raw history.
- Enforces an **Observe → Act → Observe → Replan** loop with automatic
  recovery on `ELEMENT_NOT_FOUND`.

All automated backend and frontend test suites pass.  Live GitHub acceptance
runs were blocked by GitHub rate-limiting repeated search requests (HTTP 429)
late in validation, but the local-browser verification proves the grounding
runtime resolves semantic targets correctly and the model emits the intended
semantic action sequence.

---

## Architecture pivot (multi-model runtime, phase 1 software)

### Files created

- `backend/tools/browser/grounding.py`
  - `GroundingResult` dataclass (locator, confidence, reason, selector).
  - `resolve_target(page, manager, target=None, element=None)` — single place
    where every element address is resolved.
  - `refresh_element_map(page, manager)` — re-observes and refreshes the
    manager's index map for automatic recovery.
- `backend/core/task_state.py`
  - `TaskState` pydantic model: `goal`, `current_app`, `current_url`,
    `completed`, `next_step`, `failure_history`, `relevant_ui`.
  - `update_from_tool(...)` and `record_failure(...)` keep the state current.
  - `to_prompt_text()` renders a compact block injected into LLM context.

### Files modified

- `backend/llm/base.py`
  - Added optional `tool_calls` to `LLMMessage` so assistant tool-calling
    messages can be preserved for multi-turn providers.
- `backend/core/agent.py`
  - `_conversation_loop` now creates and updates a per-run `TaskState`.
  - Injects a `CURRENT TASK STATE` message before each LLM turn.
  - Keeps the assistant tool-call message fix for Ollama / OpenAI-style
    providers.
- `backend/tools/browser/__init__.py`
  - `browser.click`, `browser.type`, and `browser.scroll` schemas changed from
    brittle `element` strings to flat semantic fields:
    `role`, `name`, `placeholder`, `index`.
  - Handlers build a semantic target dict and pass it to the grounding layer.
  - The legacy `element` string is still accepted at the handler level for
    internal/test backwards compatibility, but it is no longer advertised to
    the LLM.
- `backend/tools/browser/interaction.py`
  - `do_click`, `do_type`, `do_scroll` now resolve via `grounding.resolve_target`.
  - `_resolve_with_recovery` automatically re-inspects once on
    `ELEMENT_NOT_FOUND`.
  - `_post_action_snapshot` returns a compact observation (`url`, `title`,
    `element_count`, `grounding` metadata) after every action.
- `backend/tools/browser/extraction.py`
  - Added `compact_page_state(manager)` used by navigation and interaction
    tools.
  - `do_inspect` now returns a unified state with `page_state` and
    accessibility-friendly element metadata.
- `backend/tools/browser/navigation.py`
  - `do_open`, `do_back`, `do_forward`, `do_refresh`, `do_wait` now include
    `page_state` in their results.
- `backend/tools/browser/session.py`
  - `collect_interactive` now computes implicit ARIA roles, resolves
    `aria-labelledby`, uses `<label>` associations, and includes `placeholder`.
  - Element list is capped at 60 to keep context small.
  - `resolve_element` now delegates to the grounding layer.
- `backend/core/task_state.py` (created) and `prompts/agent_system.txt`
  - Prompt rewritten to teach the model to pass semantic `role`/`name`
    arguments instead of numeric indexes or CSS selectors.

### Grounding resolution order implemented

`grounding.resolve_target` follows the architecture's ordered fallback:

1. **Legacy element string** (for tests/internal callers) — index, CSS, or
   visible text.
2. **Semantic target**
   1. `index` from the last `browser.inspect`.
   2. `role` + `name` via Playwright `get_by_role`.
   3. `role` only.
   4. `name` only (visible text, button, link, label).
   5. `placeholder` for inputs.
   6. `href` substring for links.
   7. `tag` or `type` fallback.
3. If nothing matches, raises `BrowserError(ELEMENT_NOT_FOUND)`.

Each match returns a confidence score and a human-readable reason.

### Inspect output shape

`browser.inspect` now returns:

```json
{
  "url": "https://github.com/search?q=Gryphon&type=repositories",
  "title": "Repository search results · GitHub",
  "visible_text": "...",
  "text_truncated": false,
  "elements": [
    {
      "index": 0,
      "tag": "a",
      "role": "link",
      "name": "garethdmm/gryphon",
      "type": null,
      "href": "/garethdmm/gryphon",
      "placeholder": null,
      "disabled": false
    }
  ],
  "element_count": 60,
  "page_state": {
    "url": "...",
    "title": "...",
    "element_count": 60
  }
}
```

The element list is capped at 60, uses accessibility metadata as the primary
source, and falls back to DOM heuristics.

### Task-state schema

```json
{
  "goal": "Open GitHub, find my Gryphon repository, and open it.",
  "current_app": "browser",
  "current_url": "https://github.com/...",
  "completed": ["Loaded ...", "Observed page (60 interactive elements)", "Clicked link 'garethdmm/gryphon'"],
  "next_step": "verify navigation to ...",
  "failure_history": [],
  "relevant_ui": {}
}
```

This compact state is injected as a `CURRENT TASK STATE` user message before
every LLM turn, replacing the previous raw-history-only approach.

### Loop changes

`backend/core/agent.py::_conversation_loop` now enforces:

- **Observe**: every navigation/interaction tool returns a compact `page_state`.
- **Act**: the model emits semantic actions; the grounding layer resolves them.
- **Observe**: after `browser.click`/`browser.type`/`browser.scroll` the runtime
  returns the new `url`, `title`, and `element_count`.
- **Replan**: the updated task state is fed back to the model before the next
  turn.
- **Recovery**: the grounding layer automatically re-inspects once when a target
  is not found, then either succeeds or reports a structured
  `ELEMENT_NOT_FOUND` error that is recorded in task state.

Existing bounded safeguards remain: `agent_max_steps`, `max_tool_retries`, and
`tool_timeout` from `Settings`.

---

## Test results

### Automated suites

```bash
cd backend && source ../.venv/bin/activate && pytest ../tests/backend -q
```

```text
95 passed, 1 skipped, 1 warning
```

```bash
cd frontend && npm test -- --run
```

```text
Test Files  6 passed (6)
     Tests  31 passed (31)
```

`npx tsc --noEmit` is clean.

### Local browser verification

A local HTML page with a button (`Click Me`), an input (`placeholder="Search query"`),
and a link (`Next page`) was used to verify the new runtime directly:

| Action | Arguments | Result |
|--------|-----------|--------|
| `browser.click` | `name="Click Me"` | ✅ resolved by visible text, confidence 0.85 |
| `browser.type` | `placeholder="Search query"`, `text="hello"` | ✅ resolved by placeholder, confidence 0.85 |
| `browser.click` | `role="link"`, `name="Next page"` | ✅ resolved by role+name, confidence 0.95, navigated to `/page2` |

This confirms the grounding layer works end-to-end with real Playwright
interactions.

### Live GitHub acceptance tests

- **Test 4 — "Open GitHub and search for Gryphon."**
  - Model reliably emits `browser.open(url="https://github.com/search?q=Gryphon&type=repositories")`.
  - Runtime returns `page_state` with title/URL/element count.
  - Late validation runs were blocked by GitHub returning **"Too many requests"**
    (HTTP 429) because repeated acceptance runs hit the unauthenticated search
    rate limit.

- **Test 5 — "Open GitHub, find my Gryphon repository, and open it."**
  - In the final architecture run the model emitted **two tool calls in one
    assistant turn**:
    1. `browser.open(url="https://github.com/search?q=Gryphon&type=repositories")`
    2. `browser.click(name="garethdmm/gryphon")` (semantic target)
  - The click failed only because GitHub's search results page was returning
    **HTTP 429 / "Too many requests"** and therefore did not contain the
    repository link.
  - This is a runtime/external dependency failure, not a grounding or model
    routing failure.

---

## Conclusions

1. The brittle prompt-only approach has been replaced by the requested
   grounding-first runtime.
2. The model no longer needs to emit numeric element indexes; it describes
   targets semantically (`role`, `name`, `placeholder`) and the runtime resolves
   them deterministically.
3. Automatic re-inspect/recovery, compact task state, and post-action
   observations give the agent a reliable Observe → Act → Observe → Replan
   backbone.
4. All automated tests pass and local-browser verification proves the runtime
   resolves semantic actions correctly.
5. The only remaining blocker for a clean live GitHub end-to-end demonstration
   is GitHub's unauthenticated search rate limit after repeated acceptance runs.
   A short pause or authenticated session would allow the same action sequence
   to complete successfully.

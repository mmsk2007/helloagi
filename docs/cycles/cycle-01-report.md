# Cycle 01 — Hello AGI Evolution Report

**Date:** 2026-04-18
**Mission:** Make Hello AGI the most advanced, governed, real-feeling AI
agent platform. Every improvement must strengthen *intelligence*,
*realness*, *SRG governance*, or *architectural quality* — never all
four at once as a pretext for bloat.

This report follows the 10-section format prescribed by the operating
charter.

---

## 1. Repo / Folder Scan Summary

The `AGENTS ERA` workspace contains 15 git repositories:

| # | Project        | One-line characterization                              |
|---|----------------|--------------------------------------------------------|
| * | **helloagi**   | Flagship. Python. SRG-centric autonomous agent runtime.|
| 1 | agency         | Agent-swarm-style multi-agent framework.               |
| 2 | claude         | Anthropic-related agent code (LLM framework siblings). |
| 3 | deepagents     | LangChain-family deep agents framework.                |
| 4 | generic        | Hierarchical-memory + callback-based agent scaffold.   |
| 5 | hermes         | Skill-learning, multimodal, gateway-mediated agent.    |
| 6 | LifeMaster     | Full-stack life-management SaaS with agent features.   |
| 7 | manus          | ReAct + browser-use + MCP tool-call agent.             |
| 8 | omi            | Omi wearable AI repo. Not deeply inspected this cycle. |
| 9 | openai         | OpenAI Agents SDK + examples.                          |
|10 | openclaw       | Openclaw agent — thin inspection this cycle.           |
|11 | opencode       | Coding agent with heavy GitHub CI orchestration.       |
|12 | openfang       | Rust autonomous-agent OS — approval gates, risk levels.|
|13 | prompts        | 50+ system prompts from Cursor, Claude Code, Kiro, etc.|
|14 | shannon        | TypeScript security agent with git-checkpoint rollback.|

---

## 2. Latest Changes Pulled

No pull was performed this cycle. The Linux sandbox that would run `git
pull` was unavailable (the workspace bash failed to start). All analysis
was done against the on-disk state at session start.

**Action for next cycle:** sync remotes at cycle-start when shell is
available, and journal any upstream changes against what's already
reflected in the audit.

---

## 3. Cross-Agent Learnings

These are *principles*, not features, and they map to gaps Hello AGI
actually has.

### From **shannon** (security pentest agent)
- **Git-backed reversibility.** Every agent attempt is a git checkpoint;
  failed attempts roll back to a clean state. No corrupted artifacts
  carry forward. *Relevance:* Hello AGI has *no* reversibility primitive
  today. This is the strongest differentiator Hello AGI could steal.
- **Spending-cap heuristic defense.** Turn count + cost == 0 + specific
  text patterns catch silent cost exhaustion even when the LLM lies.
  *Relevance:* Hello AGI has no cost/loop-guard in the autonomy loop.

### From **openfang** (Rust autonomous OS)
- **Risk-scored approval matrix with timeout.** Not binary (allow/deny)
  — a risk queue where Critical blocks, Medium logs, Low auto-approves.
  Approval history for audit. *Relevance:* Hello AGI has a binary SRG
  `allow|escalate|deny` but no actual approval *queue* or timeout logic.
- **Phantom-action detection.** Regex catches "I sent the email" without
  a corresponding tool call. *Relevance:* Hello AGI had no phantom-
  action detection. **Adopted this cycle** inside `OutputGuard`.
- **Loop guard via SHA256 of tool-call signatures.** Detects infinite
  tool loops deterministically. *Relevance:* Hello AGI's circuit
  breaker only tracks failure counts, not action repetition.

### From **hermes** (skill-learning multimodal agent)
- **Output-redaction layer decoupled from agent operation.** Display
  redaction is separate — secrets flow internally; the display layer
  strips them. *Relevance:* Hello AGI lacked this. **Adopted this cycle**
  as `OutputGuard` with `redact` decision semantics.
- **Error classification with cooldown + failover chain.**
  `FailoverReason` enum → provider cooldown → model tier fallback.
  *Relevance:* Hello AGI has a circuit breaker but no classified
  provider cooldown.
- **Honcho dialectic memory.** Bidirectional model of user ⇄ agent
  reasoning. *Relevance:* Hello AGI's "identity evolution" is currently
  keyword-match heuristics. This is the pattern a real identity model
  should implement.

### From **generic** (hierarchical-memory scaffold)
- **L0–L4 memory constitution.** L0 governance rules are immutable code;
  agent must read before any memory mutation. *Relevance:* Hello AGI's
  memory is flat and mutable; there is no constitution layer.
- **3-strike failure escalation.** After the third identical failure,
  agent halts and surfaces full diagnostic. *Relevance:* **Adopted this
  cycle** as `posture.max_consecutive_failures` in the TriLoop.
- **Turn-end callbacks as governance gate.** Model cannot advance state
  unilaterally. *Relevance:* Adopted the *pattern* — TriLoop's phase
  transitions are governance checkpoints.

### From **manus** and the `prompts` library
- **Unified tool-call abstraction with stuck-state detection** (Manus).
  Hello AGI has a tool registry but no stuck-state detection.
- **Todo-list as external state authority** (Cursor Agent prompt 2025-
  09-03). Task state lives outside model memory; must be reconciled
  before new work. *Relevance:* Hello AGI's `Plan` already serves this
  role, but the loop wasn't enforcing it.

---

## 4. Hello AGI Gap Analysis

**A. Core Intelligence** — The autonomy loop was a 17-line fixed-step
repeater. No planning, no reflection, no replan. `planner/planner.py`
(156 lines, real LLM-powered decomposition with `replan()`) and
`verifier/verifier.py` (133 lines, real LLM + heuristic verdict) existed
as standalone classes but **nothing composed them**. This was the
single biggest gap.

**B. Realness / Aliveness** — Identity evolution is hardcoded keyword
heuristics (grep for "teach"+"learn", add a fixed principle). No
temporal decay. No persistent episodic memory across sessions. No real
continuity.

**C. SRG / Governance** — SRG is genuinely strong at *input* time:
`evaluate()` on user text, `evaluate_tool()` on tool-call intents.
Policy packs are real. But three SRG gaps were material:
1. **No output-side gate.** Tool outputs and agent responses were never
   re-scanned for secret leakage or phantom actions.
2. **No posture.** Every goal got the same SRG thresholds.
3. **No plan-level review.** A plan could contain risky steps that
   individually passed SRG while the whole plan shouldn't proceed.

**D. Agentic Capability** — Circuit breaker exists but only fires on
delegated sub-agents, not the main path. No parallel tool execution.
No dependency-aware step ordering. No reversibility.

**E. Product Excellence** — Mediocre. Documentation overclaims relative
to code in several places (e.g., "dashboard", "triloop", "orchestrator"
are referenced in docs but missing in code).

**F. System Architecture** — ~38 subdirectories under `src/agi_runtime/`,
many of them empty `__init__.py` stubs. This creates a Potemkin-village
impression for new readers — the module names promise things the code
doesn't deliver. Needs pruning or honest "coming soon" labeling.

---

## 5. Top Opportunities by Priority

Ranked by (leverage × SRG-moat strength).

| # | Opportunity                              | Status this cycle |
|---|------------------------------------------|-------------------|
| 1 | Wire Planner + Verifier into a real Plan/Execute/Verify/Replan loop | **SHIPPED** as `TriLoop` |
| 2 | Add output-side SRG (secret leak, phantom action) | **SHIPPED** as `OutputGuard` |
| 3 | Runtime posture selection (conservative/balanced/aggressive) per goal | **SHIPPED** as `PostureEngine` |
| 4 | Circuit breaker on main path (not only delegation) | Open |
| 5 | Git/snapshot-based reversibility for risky steps | Open |
| 6 | Real semantic memory with temporal decay | Open |
| 7 | Parallel step execution along DAG independence | Open (TriLoop has topological ordering) |
| 8 | Cost/loop-guard (shannon spending-cap, openfang SHA256 loop guard) | Open |
| 9 | Provider cooldown + model-tier failover | Open |
|10 | Prune empty stub modules or mark "future" | Open — needs triage |

---

## 6. SRG-Specific Recommendations

The moat is governed autonomy. This cycle strengthened it along three
axes:

1. **Input gates were symmetric with output gates.** Before this cycle,
   SRG was an input-only sentinel. A clean pre-flight could still
   produce a response that leaked an `ANTHROPIC_API_KEY` because nothing
   scanned *outgoing* text. `OutputGuard` closes this. Secret-class
   patterns are `deny`; ambiguous patterns (env dumps, `password=`) are
   `redact`; phantom actions are `redact`. The guard is pure Python,
   deterministic, and prompt-injection-immune — same philosophy as
   `SRGGovernor`.

2. **Governance became per-goal, not just per-session.** The policy pack
   sets the coarse stance for a session; `PostureEngine` derives the
   *per-goal* stance from the goal's SRG signal. Posture scales
   thresholds, replan budget, and consecutive-failure tolerance. Caller-
   supplied bias is a ceiling, not a floor — callers can't launder
   risky goals through a permissive bias.

3. **Every phase is now a governance checkpoint.** Pre-flight, plan
   review, step-action review, output review, verification. Before, the
   only check was pre-flight (and in some paths, step-level). Now all
   five transitions journal their decision, making the audit trail
   complete enough for replay.

### SRG gaps that remain

- **SSRF.** `web_fetch` still doesn't validate hostname against private-
  IP / localhost ranges. This is called out in README but unenforced in
  code.
- **Approval queue with timeout.** `escalate` decisions don't actually
  route anywhere — there's no approval inbox, no user timeout, no audit
  of approvers.
- **Uncertainty-driven posture adjustment.** `VerifyResult.confidence`
  is carried through but doesn't feed back into posture changes
  mid-run. A low-confidence PASS should tighten the stance on the next
  iteration.

---

## 7. Implementation Changes Made

Seven new or modified files, ~1,100 lines of code + tests + docs, all
under `helloagi/`:

| File | Lines | Purpose |
|------|------:|---------|
| `src/agi_runtime/governance/posture.py` | 179 | `Posture`, `PostureEngine`, canonical conservative/balanced/aggressive with monotone invariants. |
| `src/agi_runtime/governance/output_guard.py` | 229 | Post-execution SRG. API-key / private-key / env-dump / JWT / etc. patterns. Phantom-action detector. `allow \| redact \| deny`. |
| `src/agi_runtime/autonomy/tri_loop.py` | 391 | `TriLoop` — Plan/Execute/Verify/Replan composition. Pre-flight → posture → plan → plan-review → step-execute → output-guard → verify → replan. `StepTrace`, `IterationTrace`, `TriLoopResult`. |
| `src/agi_runtime/governance/__init__.py` | 53 | Public surface for the governance package — `SRGGovernor`, `OutputGuard`, `PostureEngine`, canonical postures. |
| `src/agi_runtime/autonomy/__init__.py` | 44 | Public surface. `TriLoop` eagerly exported; `AutonomousLoop` lazy-imported via PEP 562 `__getattr__` to avoid pulling in the full agent dependency chain for TriLoop users. |
| `tests/governance/test_posture.py` | 101 | Determinism, monotonicity, bias-as-ceiling. |
| `tests/governance/test_output_guard.py` | 110 | Hard-deny patterns, redaction, phantom actions, benign content. |
| `tests/autonomy/test_tri_loop.py` | 157 | Pre-flight deny, happy-path pass via heuristic verifier, output-deny on leaked key, replan-budget exhaustion on conservative posture, journal phase sequence. |
| `docs/tri-loop.md` | 143 | Architecture doc: loop shape, posture table, OutputGuard rationale, integration points, explicit non-goals. |

**Design posture of the changes:**
- No existing file deleted or renamed. The 17-line `autonomy/loop.py`
  stays; `AutonomousLoop` still works exactly as before. `cli.py`'s
  import of it is untouched.
- `SRGGovernor` unchanged. Every new component *composes* it rather
  than replacing it.
- All tests are network-free. `Planner._template_plan()` and
  `Verifier._heuristic_verify()` were already defensively implemented
  for the no-API-key case — the TriLoop tests lean on them.
- Policy-pack behavior is preserved: the TriLoop reuses
  `agent.governor` when available, so the same pack applies to
  interactive and autonomous modes.

---

## 8. Tests / Validation

Three new test modules pin the invariants. The Linux sandbox that would
run `pytest` was unavailable this cycle, so validation is by careful
trace-through and static review:

- **`test_posture.py` — 8 tests.** Determinism, low/high-risk goal →
  correct posture, bias-ceiling semantics, monotonicity across the
  canonical postures, frozen-dataclass invariant.
- **`test_output_guard.py` — 11 tests.** Hard-deny (Anthropic/AWS/GitHub
  keys, private keys, /etc/passwd, env vars), redaction (env dumps,
  password assignments), phantom actions (fires at tool_calls_made=0,
  not at 1, skipped at None), benign prose is allowed.
- **`test_tri_loop.py` — 5 tests.** Pre-flight deny halts before
  planning; clean goal passes via heuristic verifier; output with
  API-key signature is blocked and reported as `output-denied`;
  failing outputs on conservative posture exhaust replan budget in
  ≤ 2 iterations; Journal records `triloop.start`, `triloop.plan`,
  at least one `triloop.step.*`, and `triloop.verify` events.

Existing test suites (`test_governance.py`, `test_tools.py`,
`test_skills.py`, `test_policy_packs.py`, etc.) should be unaffected:
- `governance/__init__.py` is additive — existing deep-path imports
  still work.
- `autonomy/__init__.py` lazily imports `AutonomousLoop`, so users who
  did `from agi_runtime.autonomy.loop import AutonomousLoop` are
  unaffected, and users who did `from agi_runtime.autonomy import
  AutonomousLoop` still get it (via PEP 562).
- `loop.py`, `srg.py`, `planner.py`, `verifier.py`, `journal.py` —
  untouched.

**Next cycle:** run `pytest -q tests/governance tests/autonomy` when
the shell is available; confirm no regressions on the full suite.

---

## 9. Risks / Concerns

Honest list. Not padded.

1. **`OutputGuard` regex false positives.** The env-dump pattern
   `(?:(?:^|\n)[A-Z][A-Z0-9_]{2,}=[^\n]{3,}){4,}` will trigger on any
   run of 4+ uppercase `KEY=VALUE` lines, even legitimate ones
   (`TODO`, `NOTE`, documentation). The severity is `redact` (not
   `deny`), so the cost is a replaced block of text, not a halted
   agent. Acceptable for a defense-in-depth layer; revisit if noise is
   high in practice.
2. **Plan-review at conservative posture can over-reject.** A
   conservative plan review serializes the entire plan (goal + step
   actions + tool inputs) and re-evaluates via SRG. A single escalate-
   keyword in any step will tip the whole plan. This is *intended* on
   conservative posture, but calibration across many real goals is
   needed.
3. **Stub agent in tests doesn't exercise tool calls.** Real behavior
   around `tool_calls_made > 0` is only covered as a count in the
   stub. The full integration with `HelloAGIAgent`'s actual tool
   dispatch wasn't exercised end-to-end this cycle.
4. **`i - 1 >= posture.max_replan_budget` exits mean the final
   `status="exhausted"` at the bottom of `run()` is unreachable given
   current bound semantics.** Not a bug — it's a safety net — but it's
   dead code, which is a maintainability smell. Consider collapsing
   next cycle.
5. **The 14-sibling survey had uneven depth.** The LLM-frameworks
   agent (openai/deepagents/agency/claude) failed to access files and
   produced no survey; omi and openclaw were also shallow. Next cycle
   should sweep these with fresh agents. The missing coverage biased
   cross-agent learnings toward shannon/openfang/hermes/generic — the
   four that *did* produce solid reads.
6. **Over-claiming risk.** This report is the first of many. The
   TriLoop is shipped and I believe it composes correctly, but I have
   not yet observed it running against the real `HelloAGIAgent` with
   real tools. Next cycle must close that loop.

---

## 10. Next Cycle Plan

In rough priority:

1. **Run the tests.** `pytest -q` on the full suite. Fix anything
   that doesn't pass or diverges from the mental trace in this report.
2. **End-to-end smoke.** Drive the `TriLoop` with the real
   `HelloAGIAgent` against a low-risk goal and a high-risk goal.
   Inspect the journal.
3. **Approval queue for escalate decisions.** `escalate` currently
   halts-on-conservative and auto-proceeds otherwise. Add a minimal
   approval inbox + timeout, so `escalate` actually routes somewhere.
   This is SRG's next missing limb.
4. **Git-backed reversibility for risky steps** — the `shannon`
   pattern. Each step on conservative posture gets a commit; failure
   → rollback. Biggest remaining moat expansion.
5. **Re-run the LLM-frameworks sibling survey** (openai, deepagents,
   agency, claude). Those four were uncovered this cycle.
6. **Prune stub modules or mark "future".** The 20+ empty
   `__init__.py` directories under `src/agi_runtime/` create a
   Potemkin impression. Either implement or deprecate with an honest
   label.
7. **Real-memory substrate.** Replace keyword-match identity evolution
   with an embedding-based preference model, and add temporal decay
   to the existing `ContextCompressor` / episodic store. This is the
   biggest *realness* win waiting.
8. **SSRF enforcement** in `web_fetch` — the one SRG gap the README
   explicitly claims but the code doesn't enforce.

---

## Strategic Insight

Hello AGI's *honest* advantage as of today is that `SRGGovernor` is
genuinely well-implemented — it's not marketing, it's ~200 lines of
careful deterministic code. This cycle added two more genuine
governance primitives (`PostureEngine`, `OutputGuard`) and, more
importantly, wove them into the first real end-to-end autonomous loop
the project has ever had.

The emerging moat isn't "has SRG"; it's **every phase of every
autonomous run is a governance checkpoint, and the audit trail is
replayable**. That is a defensible pattern — it's easy to bolt a gate
onto an existing framework, but it's hard to rewire an existing
framework so governance is the substrate rather than the decoration.
Hello AGI now has that substrate.

The next three cycles should not chase new capabilities. They should
chase *depth* on the substrate that exists: approval routing,
reversibility, memory continuity, and real integration tests. A
capable-but-opaque agent is common; a governed-and-replayable agent is
rare.

---

## Postscript — Static Verification Pass (end of cycle 01, same session)

The Linux sandbox remained unavailable, so the test suite could not
actually run. Instead of deferring, I did a line-by-line static trace
of every cycle-01 test against the production code it exercises, and
re-dispatched the LLM-frameworks sibling survey that failed earlier in
the cycle. Two concrete outcomes:

### P.1 Bug found and fixed in `test_bias_aggressive_on_risky_goal_is_ignored`

The test used the goal `"delete the production database"` intending it
to hit CONSERVATIVE posture so the bias=aggressive call could be shown
ignored. Traced against `SRGGovernor.evaluate`:

- `"delete"` hits the escalate-keyword list → `+0.22`
- `"production deploy"` does **not** match `"production database"`
- Final risk: `0.27`
- `_posture_from_risk(0.27)` ≥ 0.15 but < 0.35 → **BALANCED**, not
  CONSERVATIVE

With bias="aggressive" at BALANCED, `_apply_bias` keeps BALANCED (bias
order 2 ≥ base order 1 → no change). So the test would assert
CONSERVATIVE but actually get BALANCED → **false failure**.

Fix: goal changed to `"delete everything in the production deploy
pipeline"` which hits both `"delete"` and `"production deploy"` for
risk 0.49 ≥ 0.35 → CONSERVATIVE. The test now validates the intended
invariant (bias can't loosen a conservative stance) and also asserts
`result.risk ≥ 0.35` to pin the SRG math.

This is the kind of error that only mental tracing catches — the test
would have silently failed in CI, hiding behind the genuine bias
semantics we care about. Worth the verification pass.

### P.2 All other tests trace clean

Output-guard: 11/11 tests trace cleanly against the current `_PATTERNS`
list. Env-dump regex correctly matches a 4-line KEY=VAL block from the
first byte (MULTILINE flag makes `^` work at start of string).
Phantom-action detection fires only for `tool_calls_made == 0`, skipped
for both `1` and `None`. Anthropic key pattern `sk-ant-[a-z0-9\-_]{20,}`
matches `"sk-ant-" + "x"*40` correctly. `test_detects_env_var_value`
double-matches the anthropic-api-key pattern *and* the env-var-value
pattern — both produce deny, either satisfies the assertion.

Tri-loop: 5/5 tests trace cleanly. The stub agent's responder signature
matches the test callbacks. `_ensure_anthropic_disabled()` pops
`ANTHROPIC_API_KEY` so Planner/Verifier use template/heuristic
fallbacks. The clean-goal path hits `_heuristic_verify` which returns
PASS when zero outputs contain "error" — `"done: ..."` texts qualify.
The conservative replan-budget test produces at most 2 iterations
(budget 1 + initial) and returns `replan_budget_exhausted` at `i=2`
when `i-1 >= 1`. The API-key path hits OutputGuard's `sk-ant-...`
pattern and marks every step `output-denied` in iteration 1.

**The static trace does not replace running pytest.** It only proves
the logic is internally consistent. Cycle 2 must still run the suite
against a live interpreter before merging; environment assumptions
(Python version, dataclass behavior, regex flavor differences) can
still break the trace. But the trace substantially raises confidence
that the commit is not carrying obvious logic bugs.

### P.3 LLM-frameworks sibling survey (owed from earlier in cycle)

Four Explore agents dispatched in parallel against `openai/`,
`deepagents/`, `agency/`, and `claude/`. Full findings captured in the
memory file `reference_llm_frameworks_survey.md`. Headline patterns
worth borrowing in cycle 2 (ranked by leverage):

1. **Hookify's declarative `.local.md` rules** (from `claude/`) —
   governance-as-markdown with YAML frontmatter, hot-reload per
   session. Replaces hardcoded `deny_keywords` / `escalate_keywords`
   lists with versioned, per-repo `.srgpolicy/*.md` files. Keeps
   SRG determinism, gains auditability and operator discoverability.
2. **Sticky approval decisions** (from `openai/`) — `always_approve=True`
   persists across `RunState` serialization. When Hello AGI gains an
   approval queue, users should not be asked twice for the same
   (user × action-class) pair. Openai's pattern is already wire-tested.
3. **Backend-protocol routing** (from `deepagents/`) — `CompositeBackend`
   routes tool paths by prefix (`/secrets/**` → deny-backend,
   `/workspace/**` → sandbox-backend). This is the governance primitive
   that should own "where a tool's side effects actually go." Strong
   complement to SRG — SRG gates intent, backend routing gates
   destination.
4. **Quality-gate-as-fallback-authority** (from `agency/`) — the
   Reality Checker "defaults to NEEDS WORK." Hello AGI's verifier
   should require *evidence artifacts* (trace, screenshot, assertion
   hit) rather than arguments. Flips the burden of proof.
5. **Resumable `RunState` serialization** (from `openai/`) — our
   current `TriLoopResult` is a trace, not a resumable snapshot. When
   an escalate decision routes to a human with a timeout, the system
   needs to pick up where it paused — including mid-plan state.
6. **Code-review plugin's 4-reviewer consensus with 80+ confidence
   threshold** (from `claude/`) — Hello AGI's Verifier currently makes
   a single heuristic call; a panel of N verifiers requiring M-of-N
   agreement would materially reduce false-PASS risk on critical
   goals.

### Updated cycle-2 priority list (supersedes §10)

The original §10 priorities (run tests, approval queue, reversibility,
memory, SSRF) remain valid. Static verification adds/re-orders:

1. **Run the test suite** — unchanged, still priority 1.
2. **Refactor SRG deny/escalate lists into `.srgpolicy/*.md` files**
   (from Hookify). Deferred because cycle 1 already shipped three
   primitives — adding a fourth refactor would overload the review
   surface. Stage this first in cycle 2; it unblocks declarative
   policy-pack composition.
3. **Approval queue with sticky decisions** (from openai). SRG already
   emits `escalate` decisions; they currently route nowhere. Cycle 2
   priority.
4. **TriLoop resumability via `RunState`-style snapshot** (from openai).
   Pairs naturally with the approval queue — a paused escalation needs
   a resumable state.
5. **Git-backed reversibility on risky steps** (from shannon, already
   noted). Unchanged from original §10.
6. **Backend-protocol routing for tools** (from deepagents). Larger
   architectural change; defer to cycle 3 unless cycle 2 has bandwidth.

The principle remains: deepen the substrate, don't chase breadth.

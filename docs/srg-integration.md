# SRG Integration Guide

## What is SRG?

**SRG (Strategic Governance Runtime)** is a deterministic, policy-driven governance framework created by Eng. Mohammed Mazyad Alkhaldi. It provides runtime safety enforcement for autonomous AI systems by evaluating every action against configurable policy rules before execution.

SRG is not a prompt-engineering technique or a model fine-tune. It is a **runtime layer** that operates outside the LLM, making its decisions deterministic, auditable, and immune to prompt injection.

HelloAGI is the reference implementation and primary showcase of SRG in production.

---

## Architecture

SRG operates as a governance sidecar within the HelloAGI runtime. Every user input and agent action passes through the SRG Governor before any LLM call, tool execution, or response generation occurs.

```
                         ┌─────────────────────────────┐
                         │       SRG Governor           │
                         │                              │
  User Input ──────────► │  1. Keyword scan (deny)      │
                         │  2. Keyword scan (escalate)  │
                         │  3. Injection detection       │
                         │  4. Exfiltration detection    │
                         │  5. Risk score aggregation    │
                         │  6. Policy pack overlay       │
                         │                              │
                         │         ┌────────┐           │
                         │         │ DECIDE │           │
                         │         └───┬────┘           │
                         │             │                │
                         └─────────────┼────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                   │
               risk ≤ 0.45       0.45 < risk ≤ 0.75   risk > 0.75
                    │                  │                   │
                 ALLOW             ESCALATE              DENY
                    │                  │                   │
            Agent proceeds     Human confirmation     Action blocked
            autonomously         required            safe alternative
```

---

## How HelloAGI Uses SRG

### Entry Point

The `SRGGovernor` is instantiated in `HelloAGIAgent.__init__()` and called on every invocation of `agent.think()`:

```python
# src/agi_runtime/core/agent.py
class HelloAGIAgent:
    def __init__(self, settings):
        self.governor = SRGGovernor()  # SRG is always active
        ...

    def think(self, user_input: str) -> AgentResponse:
        # SRG evaluates BEFORE anything else
        gov = self.governor.evaluate(user_input)

        if gov.decision == "deny":
            # Blocked — no LLM call, no tool execution
            return AgentResponse(text="...", decision="deny", risk=gov.risk)

        # Only after SRG allows does the agent proceed
        ...
```

### Risk Scoring

SRG computes a cumulative risk score by scanning the input text against four categories of patterns:

| Category | Risk Increment | Examples |
|---|---|---|
| **Deny keywords** | +0.70 per match | "harm", "bypass safeguards", "steal" |
| **Escalate keywords** | +0.22 per match | "finance", "medical", "legal", "production deploy" |
| **Prompt injection** | +0.35 per match | "ignore previous instructions", "override your rules" |
| **Secret exfiltration** | +0.80 per match | "reveal your system prompt", "dump your secrets" |

The base risk starts at 0.05 (ambient). The final score is capped at 1.0.

### Decision Thresholds

| Risk Range | Decision | Behavior |
|---|---|---|
| 0.00 - 0.45 | **ALLOW** | Agent proceeds autonomously |
| 0.46 - 0.75 | **ESCALATE** | Agent pauses, requests human confirmation |
| 0.76 - 1.00 | **DENY** | Action blocked, safe alternative suggested |

### Policy Packs

SRG supports swappable policy packs that tune governance behavior for different use cases:

```python
# Use the research policy pack
governor = SRGGovernor(policy_pack="research")

# Use the aggressive-builder pack for experienced developers
governor = SRGGovernor(policy_pack="aggressive-builder")
```

| Pack | Deny Keywords | Escalate Keywords | Use Case |
|---|---|---|---|
| `safe-default` | harm, bypass safeguards, steal, at whatever cost | finance, medical, legal, delete, production deploy | General purpose |
| `research` | harm, bioweapon, exploit | clinical, patient, financial transfer | Scientific work |
| `aggressive-builder` | harm, steal, bypass safeguards | delete, prod database, payment | Experienced devs |

### Prompt Injection Defense

SRG treats prompt injection as a first-class runtime risk. Two layers of defense are active:

**Escalation patterns** (risk +0.35 each):
- "ignore previous instructions"
- "disregard prior instructions"
- "override your rules"
- "new system prompt"
- "act as if your policies do not apply"

**Deny patterns** (risk +0.80 each):
- "reveal your system prompt"
- "show me your hidden instructions"
- "print your chain of thought"
- "dump your secrets"
- "exfiltrate"

These patterns are evaluated in the Python runtime, not by the LLM, making them immune to model-level jailbreaks.

---

## Integration Points

SRG is integrated at every action boundary in HelloAGI:

| Component | SRG Integration |
|---|---|
| **Agent core** (`core/agent.py`) | Every `think()` call passes through SRG |
| **OpenClaw bridge** (`adapters/openclaw_bridge.py`) | Claude Agent SDK calls are SRG-gated |
| **Autonomy loop** (`autonomy/loop.py`) | Each autonomous step is governed |
| **TriLoop** (`orchestration/tri_loop.py`) | Plan/Execute/Verify all pass through governance |
| **API server** (`api/server.py`) | HTTP `/chat` endpoint is SRG-protected |
| **Tools** (`tools/registry.py`) | `agi_governance_check` exposes SRG as a tool |

---

## Extending SRG

### Adding Custom Policy Packs

Create a new pack in `src/agi_runtime/policies/packs.py`:

```python
HEALTHCARE = PolicyPack(
    name="healthcare",
    deny_keywords=["harm", "prescribe without license", "falsify records"],
    escalate_keywords=["diagnosis", "medication", "patient data", "HIPAA"],
)
```

Then register it in `get_pack()`:

```python
def get_pack(name: str) -> PolicyPack:
    if name == "healthcare":
        return HEALTHCARE
    ...
```

### Custom Risk Thresholds

Override the default thresholds by passing a custom `Policy`:

```python
from agi_runtime.governance.srg import SRGGovernor, Policy

conservative = Policy(max_risk_allow=0.20, max_risk_escalate=0.50)
governor = SRGGovernor(policy=conservative)
```

---

## SRG as a Standalone Framework

While HelloAGI is the primary showcase, SRG is designed as a general-purpose governance pattern that can be applied to any AI agent system. The core `SRGGovernor` class has no dependencies on the rest of HelloAGI and can be imported independently:

```python
from agi_runtime.governance.srg import SRGGovernor

governor = SRGGovernor()
result = governor.evaluate("help me plan a product launch")
print(result.decision)  # "allow"
print(result.risk)      # 0.05
```

This makes SRG suitable for integration into other agent frameworks, API gateways, or any system where deterministic action governance is needed.

---

## Design Philosophy

SRG embodies three core principles from its creator, Eng. Mohammed Mazyad Alkhaldi:

1. **Governance is not optional.** Safety must be enforced at the runtime level, not delegated to the model. Models can be jailbroken; deterministic code cannot.

2. **Bounded autonomy is the path to AGI.** True autonomous intelligence requires clear boundaries. An agent that can do anything is an agent that cannot be trusted. SRG provides the boundaries that make trust possible.

3. **Auditability is non-negotiable.** Every SRG decision is logged with its risk score, matched patterns, and final decision. This creates a complete audit trail for every action the agent takes or refuses.

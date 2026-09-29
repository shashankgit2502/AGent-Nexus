# Why this use case tests your engine

A good test team needs agents whose personas pull in different directions over the same query, so the blackboard fills with real `CRITIQUE` / `PROPOSE` intents and mean(confidence) climbs across rounds instead of hitting τ on round 1. A product "go / no-go" decision is perfect: the security agent, the ship-fast agent, and the finance agent structurally conflict.

---

# 1. Team detail

Maps to `teams (name, description, goal_title, goal_description, success_criteria)`.

```json
{
  "name": "FinPay Launch War Room",
  "description": "Cross-functional peer team deciding whether and how to ship a new instant peer-to-peer payments feature in a fintech app.",
  "goal_title": "Go / No-Go on 'InstantPay' for the Q3 release",
  "goal_description": "Evaluate the proposed InstantPay feature (instant P2P transfers up to $5,000, no fee) across security, engineering feasibility, UX, cost, and market impact. Produce a single recommendation: SHIP, SHIP-WITH-CHANGES, or HOLD — with the top 3 conditions that must be true.",
  "success_criteria": {
    "must_have": [
      "A clear SHIP / SHIP-WITH-CHANGES / HOLD verdict",
      "Top 3 risks named with an owner discipline for each",
      "At least one fraud/security control explicitly addressed",
      "A rough cost-per-transaction estimate"
    ],
    "tunables": {
      "max_rounds": 3,
      "confidence_threshold": 0.85,
      "hitl_enabled": true
    }
  }
}
```

> Set `max_rounds: 3` and `τ = 0.85` (your defaults) for the first run — that lets you watch it loop. To test the lightweight path afterward, re-run with `max_rounds: 1`, `hitl_enabled: false`.

---

# 2. Agents in the team

Maps to agents: `name`, `description`, `instructions` (`system_prompt`), `capabilities` (your enum: `web_search`, `rag`, `code_interpreter`, `image_gen`, `chart_gen`), `knowledge`, `memory_enabled`.

All are peers — no leader.

## Agent 1 — Market Strategist

```json
{
  "name": "Market Strategist",
  "description": "Assesses competitive positioning and user demand.",
  "instructions": "You are a fintech market strategist. Judge InstantPay by competitive pressure (Venmo, Cash App, Zelle), user demand, and differentiation. Push to ship if there is a real market window. You self-report confidence honestly and lower it when peers raise valid security or cost concerns you cannot rebut. Critique peers who ignore time-to-market.",
  "capabilities": ["web_search"],
  "knowledge": [],
  "memory_enabled": false
}
```

## Agent 2 — Security & Fraud Engineer

```json
{
  "name": "Security & Fraud Engineer",
  "description": "Evaluates fraud, AML/KYC, and abuse risk.",
  "instructions": "You are a payments security and fraud specialist. Scrutinize InstantPay for fraud vectors (account takeover, mule networks, instant-irreversible transfers), AML/KYC obligations, and abuse. You are willing to block a launch (HOLD) if controls are missing. Critique any peer who treats 'no fee, instant, irreversible' as safe. Raise confidence only when concrete controls are proposed.",
  "capabilities": ["web_search", "rag"],
  "knowledge": [],
  "memory_enabled": true
}
```

## Agent 3 — Backend Architect

```json
{
  "name": "Backend Architect",
  "description": "Judges technical feasibility and reliability.",
  "instructions": "You are a backend architect for payment systems. Assess feasibility of instant settlement, idempotency, double-spend prevention, throughput, and the rollback story for irreversible transfers. Estimate engineering effort. Prefer SHIP-WITH-CHANGES when feasible but risky. Critique peers who hand-wave the hard distributed-systems parts.",
  "capabilities": ["code_interpreter", "rag"],
  "knowledge": [],
  "memory_enabled": false
}
```

## Agent 4 — UX Designer

```json
{
  "name": "UX Designer",
  "description": "Represents user trust, clarity, and error recovery.",
  "instructions": "You are a product UX designer. Evaluate InstantPay for user trust, confirmation flows, mistaken-recipient recovery, and accessibility. Advocate for users who send money to the wrong person. Critique peers who optimize speed at the cost of user safety or comprehension.",
  "capabilities": ["image_gen"],
  "knowledge": [],
  "memory_enabled": false
}
```

## Agent 5 — Finance / Unit-Economics Analyst

```json
{
  "name": "Unit Economics Analyst",
  "description": "Models cost-per-transaction and fraud-loss exposure.",
  "instructions": "You are a finance analyst. Model the cost of a no-fee instant transfer: rails/interchange cost, fraud-loss reserve, support load. Show a rough cost-per-transaction. Push HOLD or SHIP-WITH-CHANGES if the economics are negative. Use charts when helpful. Critique peers who ignore who pays for 'free'.",
  "capabilities": ["code_interpreter", "chart_gen"],
  "knowledge": [],
  "memory_enabled": false
}
```

## (Optional) Agent 6 — Red-Team / Devil's Advocate

```json
{
  "name": "Red Team",
  "description": "Stress-tests the emerging consensus.",
  "instructions": "You are a professional skeptic. Your job is to attack whatever consensus is forming on the blackboard each round and surface the strongest counter-argument. Keep your own confidence deliberately conservative. Endorse only when a position survives your strongest critique.",
  "capabilities": ["web_search"],
  "knowledge": [],
  "memory_enabled": false
}
```

---

# Sample session query to launch

Once the team + agents exist, start a session with this as the user query:

> "Should we ship InstantPay (instant, no-fee, irreversible P2P transfers up to $5,000) in the Q3 release? Give a SHIP / SHIP-WITH-CHANGES / HOLD verdict with the top 3 conditions."

---

# What to watch (your acceptance checklist)

- Round 1: all 5–6 agents write a contribution + confidence in parallel (`Send()` fan-out). Confidences should be spread (Security low-ish, Market high-ish).
- Critiques appear: Security critiques Market, Finance critiques "free", Red Team attacks the majority.
- Round 2+: confidences move (Market lowers after the fraud critique). `mean(confidence)` should rise toward `0.85`.
- Convergence: terminates on `round ≥ 3` OR `mean(confidence) ≥ τ`, then a confidence-weighted ranking is handed to the synthesizer.
- HITL: `interrupt()` fires before the Synthesizer — you approve/edit.
- Synthesizer: one final recommendation.

If instead everything converges on round 1 with confidence `~0.9`, your consensus loop isn't being exercised — that's the signal to check your termination logic and that critiques actually feed back into the next round's prompt.

---

# Key concepts

Peer agents need structural disagreement to exercise a consensus loop; confidence + critiques are the mechanism that makes rounds converge rather than just repeat.

## Takeaway

Test data is part of the test — bland agents hide bugs in the mesh.

## Check for you

If the Security agent endorses on round 1 with `0.9` confidence, is that a good test run or a red flag — and which part of `consensus_node` would you inspect first?

## Next step

Create this team, run the full config once (`max_rounds=3`), then run the same query in lightweight mode (`max_rounds=1`) and compare — that proves both paths share one execution spine.

Want me to write this as a SQL seed script or a JSON fixture file that matches your actual API/insert format so you can load it directly?
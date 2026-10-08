# Whalez Execution Certificate v1

The Execution Certificate is the boundary artifact between Whalez-AI Core execution and downstream enterprise/network systems.

## Authority model

- **Whalez-AI Core** is authoritative for intent, governance authorization, capability resolution, execution, and execution evidence.
- **Whalezchain Enterprise Orchestrator** is authoritative for enterprise workflow state, accounting, treasury, and receipt aggregation.
- **Whalezchain** is authoritative for network state and settlement.

The certificate does not make the Enterprise Orchestrator the executor and does not make its enterprise ledger the network ledger.

## Required identity chain

`intent_id -> correlation_id -> tool_id -> governance_verdict_id -> task_id -> execution_report_hash -> result_hash`

The certificate must contain an approved governance verdict, the governed capability identity, executor attestation, and a certificate hash. Downstream systems add their own receipt/journal/settlement references without rewriting the Core evidence.

## Security requirements

1. Never accept a certificate whose governance decision is not `approved`.
2. Bind the certificate to the exact `intent_id`, `correlation_id`, `task_id`, `tool_id`, verb, and resource.
3. Verify the governance signature before processing enterprise effects.
4. Verify the executor signature before treating the execution as authenticated evidence.
5. Treat `result_hash` and `execution_report_hash` as immutable evidence identifiers.
6. Enterprise and settlement references are additive links; they do not replace Core evidence.
7. Human escalation remains a governance concern; the Enterprise Orchestrator must not downgrade or reinterpret a denied or `needs_human` verdict as authorization.

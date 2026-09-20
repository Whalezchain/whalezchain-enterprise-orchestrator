# Enterprise Orchestrator Integration Contract

## Role

The Whalezchain Enterprise Orchestrator is the internal orchestration boundary behind `whalez-ai-core`. Its public API is not the same thing as public internet access; deployment policy determines who may reach it.

## Expected flow

```text
Founder Console + embedded whalez-ai-control
        -> whalez-ai-core
        -> Whalezchain Enterprise Orchestrator
        -> approved capability/provider/runtime
        -> Whalezchain provenance / execution plane
```

## v1 readiness endpoints

- `GET /v1/health` — non-mutating service readiness.
- `GET /v1/capabilities` — capability declaration and gating state.
- `GET /health` — legacy/simple process health endpoint.

These endpoints do **not** imply that settlement or provenance mutation is enabled.

## Current repository reality

The current orchestrator implementation is intentionally skeletal. It exposes health and capability declaration, but it does not yet contain sufficient verified provider/runtime wiring to claim end-to-end Whalezchain settlement execution.

That is a launch blocker for any claim that depends on real orchestration beyond readiness.

## Integration requirement

Before production authority is enabled, add and verify explicit adapters for the intended provider/runtime and provenance path, with:

- authenticated request contract;
- idempotency/request ID propagation;
- allow/deny policy result;
- execution result;
- verification result;
- provenance anchor/receipt where applicable;
- append-only audit evidence.

Do not substitute a `200 OK` health result for execution proof.

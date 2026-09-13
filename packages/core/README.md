# trip-core

Status: **owner Lane A (Wai Kin)**. The contract. After milestone 1 it changes additively only; every change is
announced in the team chat as `A: CONTRACT — <what>`.

| module | what |
| --- | --- |
| `trip_core.models` | the pydantic types every lane produces or consumes, `apply_patch`, `idempotency_key`, `load_fixture` |
| `trip_core.tools` | the Protocols each lane implements, plus `resolve_places` |
| `trip_core.fakes` | a deterministic offline fake for every Protocol; `default_fakes()` |
| `trip_core.llm` | `complete_json(prompt, Schema)`: the one place that talks to Gemini |
| `trip_core/fixtures/tokyo.json` | the seed trip: brief plus 18 signals |

No barrel: import the module you need.

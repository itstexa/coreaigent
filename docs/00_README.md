# Documentation Map

Start at [`AGENTS.md`](../AGENTS.md); it routes tasks to files. Use this map
when you know the question but not the file. Read one file, not the tree.

| Question | File |
| --- | --- |
| What are the service boundaries and runtime modes? | [`architecture.md`](architecture.md) |
| Which path holds what, and where are the entrypoints? | [`repository-map.md`](repository-map.md) |
| How does one request move through the system? | [`data-flow.md`](data-flow.md) |
| Which contract connects two services, and where is it? | [`contracts.md`](contracts.md) |
| How do I run, mock, or verify the stack locally? | [`development.md`](development.md) |
| What does a single service own? | `services/<service>.md` |

Service files:

- Intake and normalization (F-01) → [`services/ocr.md`](services/ocr.md)
- Classification and taxonomy (F-02) → [`services/classification.md`](services/classification.md)
- Extraction and missing information (F-03) → [`services/validation.md`](services/validation.md)
- Correspondence, routing, case state (F-04/F-05/F-06) → [`services/workflow.md`](services/workflow.md)
- Regulation retrieval boundary → [`services/rag.md`](services/rag.md)
- Local Jamba inference (F-07) → [`services/llm-jamba.md`](services/llm-jamba.md)
- Citizen portal and operator panel → [`services/frontend.md`](services/frontend.md)

Not in this layer:

- Runnable commands per Compose lane → [`../README.md`](../README.md)
- Feature requirements and acceptance criteria → [`tekno_agent_feature_pack/`](tekno_agent_feature_pack/)
- Architecture and design decision records → [`architecture/`](architecture/), [`design/`](design/)
- Payload field definitions → `contracts/schemas/*.schema.json` (never duplicated here)

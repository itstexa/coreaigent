# Service ownership directories

Add only an implemented service directory here, for example `services/ocr/Dockerfile`. The development command builds that directory into the fixed `ocr` Compose service; it must implement the corresponding contract before it is used outside mock mode.

This folder is reserved for the real service implementations in CoreAIgent. Each team member keeps their service under its own subdirectory.

Example structure:

```text
services/
├── ocr/             # Extracts text from documents
├── classification/  # Determines the document type
├── validation/      # Checks missing fields
├── rag/             # Searches legislation and knowledge sources
├── llm/             # Produces drafts or routing decisions
├── workflow/        # Coordinates the end-to-end flow
├── rules/           # Rule-engine baseline module without AI
├── draft/           # Draft generation service
└── ...
```

When adding a service, its directory should include at least one `Dockerfile`, and the service must conform to the shapes in the `contracts/` schema set.

For example, if an OCR service is being built, its code lives under `services/ocr/` and implements the OCR contract in `contracts/`.

## Rule Engine

`services/rules/` is an independent Python module that analyzes document text using fixed business rules rather than an LLM. It is not the final AI solution; it serves as a baseline for comparison with future AI pipeline results.

Use the detailed instructions in [services/rules/README.md](rules/README.md).

## Draft service

`services/draft/` contains the draft generation microservice used to transform a validated document into a formal draft result. It follows the contract definitions under `contracts/` and is meant to be compared against the rules-based baseline.

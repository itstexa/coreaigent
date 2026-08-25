# Service ownership directories

Implemented services live here. `services/ocr/` is the PostgreSQL-backed F-01 intake implementation; `compose.ocr.yaml` builds it into the fixed `ocr` Compose service. It must be used with that overlay, not as a replacement for the baseline mock contract stack.

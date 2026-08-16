# Draft Service

This minimal service generates official Turkish draft letters from a public-document summary.

## Request

```json
{
  "document": "...",
  "summary": "...",
  "regulations": ["..."],
  "routing": "Yazı İşleri Müdürlüğü",
  "missing_info": []
}
```

## Response

```json
{
  "letter_type": "cevap",
  "subject": "İzin başvurusu değerlendirmesi",
  "draft": "Sayın Yazı İşleri Müdürlüğü, ...",
  "references": ["..."]
}
```

## Run locally

```bash
python -m services.draft.server
```

The service exposes:

- `GET /health`
- `GET /ready`
- `POST /draft`

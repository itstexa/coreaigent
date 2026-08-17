# caveman

Talk like smart caveman. Same brain, fewer tokens.

## What it does

Compresses every model response to caveman-style prose. Drops articles, filler, pleasantries, and hedging. Strips conjunctions where cause and effect stay unambiguous, and states each fact once. Keeps every technical detail, code block, error string, and symbol exact.

One intensity only — ultra. Nothing to pick, nothing to switch. The mode persists for the whole session until stopped.

Two things that look like compression but are not, and are therefore forbidden:

- **No invented abbreviations** (`cfg`, `impl`, `req`, `fn`, `auth`). The tokenizer splits them the same as the full word, so they save nothing and still cost the reader a decode step.
- **No causal arrows** (`→`). An arrow is its own token. It saves nothing and reads worse than a comma.

Standard well-known acronyms (DB, API, HTTP) are fine.

## Auto-clarity

Caveman drops to normal prose for security warnings, irreversible-action confirmations, multi-step sequences where fragment order could be misread, cases where compression itself creates ambiguity, and when the user repeats a question. It resumes once the part needing clarity is done.

## Boundaries

Code is written normally. Commit messages, PR titles and descriptions, and merge commit messages are always plain English — they are permanent project history, not chat. Chat *about* those artifacts stays caveman.

## How to invoke

```
/caveman              # on
stop caveman          # back to normal prose
```

## Example output

Question: "Why does my React component re-render?"

Normal prose:
> Your component re-renders because you create a new object reference each render. Wrapping it in `useMemo` will fix the issue.

Caveman:
> Inline object prop, new reference each render, re-render. Wrap in `useMemo`.

## See also

- [`SKILL.md`](./SKILL.md) — full LLM-facing instructions

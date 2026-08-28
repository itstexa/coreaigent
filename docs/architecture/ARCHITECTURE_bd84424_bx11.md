# Architecture Session — BX-11 Turkish text improvement

The workflow exposes an optional, bounded Turkish suggestion. Deterministic
whitespace/punctuation/readability correction is authoritative for the MVP;
Jamba may be added behind the same interface later. Names, addresses,
identifiers, amounts, dates, document numbers, and quoted legal claims are
protected spans and cannot be changed. Unsupported languages return an explicit
status without translation. F-01 `original_text` is immutable; accepting a
post-submit suggestion delegates persistence to BX-05 revision creation.

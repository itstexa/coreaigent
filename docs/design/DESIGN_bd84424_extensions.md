# Design Session — Operational extensions backlog

> Linked from [DESIGN.md](DESIGN.md). This is requirement-analysis output only.
> No implementation, schema, endpoint, service, or data-store decision is approved here.

## Analysis Context

- Source: human-operator backlog, 2026-08-28.
- Repository-owned `F-01`…`F-09` already name different, implemented or
  previously analysed features. This backlog uses temporary `BX-*` IDs until
  the product owner assigns permanent IDs.
- Existing demo authentication has one shared `USER` token and one `ADMIN`
  token; it does not establish per-person ownership. Claims about a user's
  history or personnel assignment therefore need an identity/RBAC decision.
- `F-03` already owns validation and supplemental-information state. Attachment
  presence is currently represented by intake metadata; no attachment-storage
  feature is assumed.
- `F-01` normalizes technical text representation. It does not rewrite Turkish
  grammar or meaning.
- Deliberate minimum: do not add a service, ML model, graph pipeline, or
  separate database until an approved story proves one is needed.

## User Stories

### BX-00: Aksiyon ve ticket kaydı

As an authorized operator
I want meaningful case actions and ticket work to be traceable
So that investigations and operational follow-up have evidence.

**Decision:** a ticket is the existing case. Append audit events to case changes;
do not create a second ticket/work-item system.

**Approved events:** state change, assignment, petition edit, attachment
change, spam decision, view, and download.

**Approved storage/access rule:** records are immutable, visible to every
principal allowed to read the case, and persisted in SQL without automatic
deletion.

**Decision:** `workflow` owns the central SQL log table and the authorized
case-log read projection. Other services publish an explicit internal action
event contract; none reads or writes another service's private table.

### BX-01: Eğitim verisi için DLP anonimleştirme

As a data controller
I want an approved training-data export to exclude personal data
So that model training uses data only for its permitted purpose.

**Approved scope decisions (2026-08-28):** start with names and Turkish identity
numbers (T.C. Kimlik No). Detection is document-specific: matching spans are
marked and replaced with irreversible placeholders. The original document
remains in the operational SQL record and is never included in the training
export. Any principal that can read the case may export its redacted record;
the export is not a separate training pipeline. Legal policy is owned by the
legal team and is explicitly out of this implementation scope.

**Smallest candidate:** a deterministic, auditable per-case export that fails
closed when a supported name or T.C. Kimlik No span cannot be safely redacted.

### BX-02: Birim içi otomatik atama

As a unit manager
I want eligible active personnel to receive work using the approved least-load rule
So that workload is balanced.

**Approved scope decisions (2026-08-28):** there is no active/online signal.
Eligibility is membership in the routed unit only. Load is the number of open
cases assigned to each person. Among tied minimum-load members, selection is
random. No new role or expertise filter is introduced.

**Smallest candidate:** select one unit member at route creation, persist the
assignment for the case revision, and do not rebalance existing assignments.

**Open boundary:** behavior when a unit has no personnel, plus manual override
and reassignment policy, remains unspecified.

### BX-03: Kullanıcı geçmişi ve benzer dilekçe uyarısı

As a citizen or authorized staff member
I want permitted prior petitions and similar cases to be visible
So that duplicate work can be recognized without leaking other cases.

**Approved scope decisions (2026-08-28):** use the existing PostgreSQL case
records and case-access policy; no separate physical per-user database. Every
principal that can read the case may read its history/similar-case projection,
resolution marks, and the identities of people who viewed similar cases.
Similarity considers text, classification, location, and time; the acceptance
threshold is same classification and a maximum 30-day window. A case is
resolved when any case reader marks it resolved; all marks remain visible.

**Smallest candidate:** a case-scoped history endpoint with same-classification,
30-day similar-case rows, current state, resolution marks, and past view actors.
No owner-specific identity model or separate database is introduced.

### BX-03A: İlişkili evrak ve zorunlu ekler

As a citizen
I want required related documents to be identified before submission
So that I can complete my application.

**Smallest candidate:** extend the existing per-request-type validation registry
with required attachment types; do not invent relation inference.

**Approved scope decisions (2026-08-28):** request/case type owns required
attachment rules loaded from config/DB; LLM is not authoritative. Users may
manually attach files, deterministic rules may establish relations, and
similarity may suggest links without creating authoritative relations. MVP
accepts PDF, DOCX, JPG/JPEG, PNG; 10 MB per file and 10 files per case with
MIME+extension checks. Files live in object/file storage and metadata in SQL;
malware scanning is a production integration point, not a demo dependency.
Attachments change in `draft`/`waiting_for_information`; submitted changes
create a BX-05 revision.

### BX-04: Spam ve agresiflik sinyali

As a moderator
I want risky submissions to receive review signals
So that potential abuse is handled without automatic unjustified rejection.

**Approved scope decisions (2026-08-28):** abuse signals are duplicate or
repeated submissions, excessive request bursts, profanity/insults, threats,
harassment, and obvious bot-like repetition. Criticism, negative wording, or
capital letters alone are not aggression. The first outcome is a flag plus a
human-visible risk score; a simple rate limit may protect high-volume spam.
There is no CAPTCHA, automatic ban, or temporary block in this slice.

An authorized moderator can see the flag/signals and override the result.
The citizen is not shown a contentious automatic judgment such as “your
message is aggressive”. False-positive overrides are action-log events. If a
model is enabled, it must support Turkish and return only `label`,
`confidence`, and `detected_signals`; the threshold is configuration, and
chain-of-thought or long-lived raw inference is not retained.

**Smallest candidate:** deterministic signal extraction plus a case-scoped
review projection; preserve normal processing and do not add punitive action
or a mandatory model dependency.

**Open boundary:** exact score scale/calibration and deterministic duplicate,
burst, and signal thresholds are not specified by the approved scope.

**Demo decision (2026-08-28):** use a configurable `0.0–1.0` risk score,
default review threshold `0.70`. Defaults are duplicate exact-normalized text
within 24 hours, more than five submissions in ten minutes, configured
profanity/threat/harassment terms, and more than three repeated bot-like
requests; each matched signal contributes its configured weight. These are
review heuristics, never automatic rejection, and can be replaced by policy.

### BX-04A: Davranış trendi

As an authorized manager
I want aggregate abuse-signal trends over time
So that material changes can be investigated.

**Smallest candidate:** time-bucketed aggregate counts from BX-04 events; no
personnel score or real-time analytics pipeline.

**Approved scope decisions (2026-08-28):** trends may be computed per user,
unit, and system; user sees own history, moderator own unit, admin aggregate.
Reports use a minimum group size of five. The metric is daily flagged-submission
rate with a seven-day rolling window and ±25% insight threshold. No push/email.
Without BX-04 authoritative signals the result is `no_data/not_available`.

### BX-05: Dilekçe düzenleme ve eğitim-adayı güncellemesi

As a citizen
I want to edit my petition only in permitted states
So that errors can be corrected without corrupting processing history.

**Smallest candidate:** create a new revision, re-run existing validation, and
record the action. Training-data handling remains BX-01's concern.

**Approved scope decisions (2026-08-28):** the owner may edit in `draft` and
`waiting_for_information`; edits after `review`/`routed` create a BX-05
revision. Resolved/closed cases are immutable. Text, structured fields, and
attachments may change; classification is never directly user-editable and is
recomputed when affected. Prior revisions remain visible to authorized staff,
but restore is out of scope. Existing assignment is retained, SLA is not reset,
and correspondence is never rewritten; priority may be recomputed. Training
export uses only the latest eligible revision, with provenance; retraining or
unlearning is out of scope. BX-06 remains preview-first, with read-only case
detail after submission.

**Smallest candidate:** a workflow-owned revision record plus a case-scoped
edit endpoint that preserves the original and triggers existing validation;
attachment storage and similarity remain their owning boundaries.

### BX-06: Eksik bilgi ön izlemesi

As a citizen
I want current validation gaps shown before I continue
So that I can provide required information.

**Smallest candidate:** render existing F-03 `missingFields` and
`invalidFields`; no new extraction, AI, or endpoint.

### BX-07: Serbest metni dilekçe veya resmî evrak taslağına çevirme

As a document author
I want free text converted into a clearly marked draft
So that I can prepare a suitable document.

**Smallest candidate:** a user-editable draft only. It is never automatically
signed, sent, or claimed to be legally final.

**Approved scope decisions (2026-08-28):** citizen-facing petition/request,
complaint, and information-request drafts are sufficient. Local templates own
mandatory fields (`subject`, `body/request`, and identity/contact when needed).
Output is editable structured/plain text; PDF/DOCX export is later. Structure
is deterministic and content may use Jamba; the result is a temporary draft
until submitted through F-01.

### BX-08: Dilekçe önceliklendirmesi

As a unit manager
I want petitions to receive policy-defined priority
So that urgent cases can be handled in the intended order.

**Smallest candidate:** versioned deterministic rules with a visible reason;
no predictive ML, automatic escalation, or SLA engine.

**Approved scope decisions (2026-08-28):** levels are `low`, `normal`, `high`,
`urgent`; default `normal`. Deterministic config may use request type, deadline,
waiting time, and verified urgency indicators, never sensitive data alone.
Moderator/admin override requires a reason and action-log entry. Priority orders
the queue/dashboard and may select a simple SLA target, but never changes route.
User emergency text is only a candidate signal, not a direct urgent decision.

### BX-09: Yönlendirme güven skoru

As an operator
I want routing confidence to state what it actually measures
So that I do not treat a classification estimate as verified routing accuracy.

**Smallest candidate:** show existing F-02 classification confidence with its
source and version. Do not call it routing correctness until labelled outcome
data exists.

**Approved scope decisions (2026-08-28):** a moderator transfer/acceptance and
final closure can label the final accepted unit as ground truth. Store feedback,
show case and unit/system aggregate accuracy, and keep it separate from BX-01
training unless it passes anonymization eligibility. Below a configurable
confidence threshold, set `needs_review` without blocking case creation.

### BX-10: Personel panosu ve grafikler

As an authorized manager
I want approved aggregate workload views
So that I can monitor operations without exposing case contents unnecessarily.

**Smallest candidate:** aggregate existing case/assignment counts for an
authorized role; no new analytics pipeline or performance ranking.

**Approved scope decisions (2026-08-28):** dashboard covers unit and system
aggregates plus a user's own case history. Active means enabled+available;
assigned means current owner open work; completed means terminal cases in the
selected period. Default period is 30 days with 7/30/90 options; page-load
refresh and short cache suffice. Metrics are visible only to unit managers and
admins; no employee ranking or aggression-based score.

### BX-11: Türkçe metin iyileştirme

As a citizen
I want an optional Turkish-writing suggestion
So that I can improve clarity while retaining control of my original text.

**Smallest candidate:** preserve source text and display a separately accepted
suggestion. Technical F-01 normalization stays unchanged.

**Approved scope decisions (2026-08-28):** spelling, punctuation, grammar, and
light readability only; no meaning-changing rewrite. Names, addresses,
identifiers, amounts, dates, document numbers, and legal quotes are protected
spans. Hybrid deterministic/Jamba suggestions are Turkish-focused and return
`unsupported_language` for unsupported input. Accepted text never overwrites
F-01 original; post-submit acceptance creates a BX-05 revision.

## Gherkin Acceptance Criteria

Feature: BX-00 case action log

  Scenario: An approved case action is logged
    Given a case exists
    When one approved action is completed for that case
    Then the system records the case identity and the completed action type

  Scenario: An unapproved action type is not recorded as an approved action
    Given a case exists
    When a caller attempts to record an action type outside the approved action list
    Then the system rejects that action-log request
    And it does not record that action type for the case

  Scenario: A case action record is immutable and visible only with case access
    Given a recorded action belongs to a case
    When a principal with access reads that case's action log
    Then the system returns the recorded action
    When any caller attempts to change or delete that record
    Then the system rejects the mutation
    And the stored record remains unchanged in SQL

  Scenario: A principal without case access reads the action log
    Given a recorded action belongs to a case
    When a principal without access reads that case's action log
    Then the system rejects the read
    And it does not return the recorded action

Feature: BX-06 eksik bilgi ön izlemesi

  Scenario: Current validation gaps appear in the preview
    Given a case has a current F-03 validation result containing missing or invalid fields
    When the citizen opens the information preview
    Then the preview shows each field label from that current result
    And it does not invent fields absent from that result

  Scenario: Validation has not produced a current result
    Given a case has no current F-03 validation result
    When the citizen opens the information preview
    Then the preview reports that validation is pending or unavailable
    And it does not present a guessed missing-information list

Feature: BX-01 DLP eğitim veri exportu

  Scenario: Case reader exports irreversibly redacted data
    Given a readable case contains a name or T.C. Kimlik No span
    When the case reader requests the training export
    Then the export contains redaction placeholders instead of those values
    And the original document text is not in the export

  Scenario: Caller without case access cannot export data
    Given a case is not readable by the caller
    When the caller requests the training export
    Then the system rejects the request
    And it returns no document or redacted text

  Scenario: Unsupported sensitive text fails closed
    Given the deterministic DLP pass cannot classify a supported identifier span
    When the training export is requested
    Then the system rejects the export
    And it does not return the source text

Feature: BX-03 kullanıcı geçmişi ve benzer case

  Scenario: Case reader sees permitted similar cases
    Given a readable case has same-classification cases within the last 30 days
    When the case reader opens its history
    Then the system lists the similar case count and permitted summaries
    And it shows resolution state and past viewers for those cases

  Scenario: Older or differently classified cases are excluded
    Given a candidate case is older than 30 days or has a different classification
    When the case reader opens the history
    Then that candidate is not listed as similar

  Scenario: Any case reader can mark a case resolved
    Given a readable case is not marked resolved
    When a case reader marks it resolved
    Then the resolution mark is persisted with the actor and time
    And all case readers can see the mark

  Scenario: Caller without case access cannot read or mark history
    Given a case is not readable by the caller
    When the caller requests history or a resolution mark
    Then the system rejects the request
    And it changes no case state

Feature: BX-03A ilişkili evrak ve zorunlu ekler

  Scenario: Request type exposes missing required attachments before submission
    Given a draft case has a request type with a required attachment rule
    And the case has no attachment of that required type
    When the case reader opens attachments
    Then the response lists that required type as missing
    And the system does not ask an LLM to decide the requirement

  Scenario: Supported attachment metadata is accepted at inclusive limits
    Given a draft case has fewer than 10 attachments
    When a supported object of exactly 10 MiB is registered with matching MIME and extension
    Then the system stores metadata and its opaque object-storage key in SQL
    And it records an attachment-change action

  Scenario: Invalid attachment metadata is rejected
    Given a case reader registers an unsupported type, mismatched MIME, or file larger than 10 MiB
    When the attachment is validated
    Then the system rejects it
    And it does not create attachment metadata

  Scenario: Similarity suggestions never become authoritative relations
    Given two attachments have similar deterministic metadata
    When the attachment projection computes a similarity suggestion
    Then it returns a suggestion marked non-authoritative
    And it does not create a relation without a manual or deterministic-rule action

  Scenario: Submitted attachment changes require a revision
    Given a submitted case is no longer in draft or waiting-for-information
    When a reader attempts to add an attachment
    Then the system rejects the direct mutation with a revision-required result
    And the current attachment set remains unchanged

Feature: BX-04 spam ve agresiflik sinyali

  Scenario: A risky submission receives a review signal without punitive action
    Given a submission contains one or more configured duplicate, burst, profanity, threat, harassment, or bot-like repetition signals
    When the submission is analyzed
    Then the system records a review flag and a human-visible risk score for authorized moderation
    And it records the detected signal names
    And it continues normal case processing without an automatic ban or block

  Scenario: Criticism, negative wording, or capitalization alone is not aggression
    Given a submission is critical or negative and contains no configured abuse signal
    When the submission is analyzed
    Then the system does not add an aggression flag for that wording alone
    And it does not treat capitalization alone as abuse

  Scenario: A moderator overrides a false-positive flag
    Given an authorized moderator can review a flagged case
    When the moderator overrides the flag
    Then the final moderation decision is updated
    And the override actor, reason or decision context, and time are action-log events

  Scenario: A citizen does not receive an automatic aggression judgment
    Given a submission has a moderation flag or risk score
    When the citizen reads the ordinary submission response
    Then the response does not label the citizen or message as aggressive
    And it does not expose a contentious model judgment

  Scenario: An enabled Turkish model returns only bounded moderation metadata
    Given the optional moderation model is enabled and supports Turkish
    When the submission is analyzed
    Then the model result contains a label, confidence, and detected signals
    And the configured threshold determines whether the review flag is set
    And chain-of-thought and long-lived raw inference are not persisted

  Scenario: Unsupported model output cannot become an authoritative flag
    Given an enabled moderation model returns missing or malformed label, confidence, or signal metadata
    When the submission is analyzed
    Then the model result is rejected or marked unavailable
    And the system does not use that malformed result as an authoritative moderation decision

Feature: BX-04A abuse trend

  Scenario: Authorized role sees an aggregate trend
    Given BX-04 has authoritative daily flags and the selected period is 7, 30, or 90 days
    When an authorized user opens the trend view
    Then the system shows flagged-submission rate with a 7-day rolling window
    And groups smaller than five users are suppressed

  Scenario: Trend has no authoritative source data
    Given BX-04 has not produced abuse signals
    When the trend view is opened
    Then the result is `no_data/not_available`
    And no aggression conclusion is fabricated

Feature: BX-05 case revision edit

  Scenario: Owner edits a draft or waiting-for-information case
    Given the owner can access a case in draft or waiting_for_information
    When the owner changes text or a structured field
    Then the original revision remains readable
    And a new revision is persisted and validation is re-run

  Scenario: Submitted edit creates a revision without rewriting history
    Given a case is in review or routed
    When the owner edits text, fields, or attachments
    Then the system creates a BX-05 revision
    And existing assignment and correspondence remain unchanged

  Scenario: Classification is not directly editable
    Given a case reader submits a classification change
    When the edit is processed
    Then the system rejects direct classification mutation
    And it may recompute classification from the changed content

  Scenario: Resolved or closed case cannot be edited
    Given a case is resolved or closed
    When the owner submits an edit
      Then the system rejects the edit
      And no revision is created

Feature: BX-07 citizen document draft

  Scenario: Generate an editable petition draft from supported free text
    Given a citizen selects petition/request, complaint, or information_request
    And the selected local template defines its mandatory fields
    When the citizen generates a draft
    Then the system returns editable structured/plain text
    And the result is marked temporary until submitted through F-01

  Scenario: Missing mandatory draft field blocks submission but preserves draft
    Given a generated draft lacks a mandatory subject or required identity/contact field
    When the citizen attempts to submit it
    Then submission is blocked with the missing field identified
    And the temporary draft remains editable

  Scenario: Unsupported document type is rejected
    Given the citizen selects a document type outside the configured templates
    When draft generation is requested
    Then the system rejects the request
    And no case or permanent intake record is created

  Scenario: Generated draft never claims legal finality
    Given a draft has been generated
    When it is displayed before submission
    Then it is clearly marked as editable draft
      And it is not signed, dispatched, or presented as legally final

Feature: BX-08 deterministic priority

  Scenario: Apply configured priority with a visible reason
    Given a case has request type, deadline, waiting time, and verified urgency signals
    When priority is calculated
    Then the result is one of low, normal, high, or urgent
    And the default without signals is normal with a deterministic reason

  Scenario: Priority override requires a reason
    Given a moderator or admin can override priority
    When an override is submitted without a non-empty reason
    Then the override is rejected and no priority action is logged

  Scenario: Priority never changes routing
    Given priority has been calculated or overridden
    When the queue is ordered
    Then priority affects ordering or SLA target only
    And the routing destination remains unchanged

Feature: BX-09 routing confidence feedback

  Scenario: Low-confidence routing enters review without blocking creation
    Given classification confidence is below the configured threshold
    When the case is created
    Then the case is created with needs_review=true
    And automatic routing is deferred to review

  Scenario: Final accepted unit supplies routing ground truth
    Given a moderator accepts or transfers a case and later closes it
    When routing evaluation is calculated
    Then the final accepted unit is authoritative ground truth
    And case-level and aggregate accuracy are updated

  Scenario: Routing feedback is not automatically training data
    Given a routing correctness label exists
    When the feedback is stored
    Then it remains separate from BX-01 training export
    And it is eligible only after anonymization

Feature: BX-10 personnel dashboard

  Scenario: Authorized manager sees bounded workload aggregates
    Given a unit manager or admin selects a 7, 30, or 90 day period
    When the personnel dashboard loads
    Then it shows active, assigned, completed, throughput, and resolution-time aggregates
    And no case content is exposed

  Scenario: Citizen cannot see personnel metrics
    Given a citizen opens the personnel dashboard
    When metrics are requested
    Then access is rejected

  Scenario: Dashboard does not rank employees
    Given personnel metrics are displayed
    When the dashboard is rendered
      Then no employee ranking or aggression-based score is shown

Feature: BX-11 Turkish text improvement

  Scenario: Suggest bounded Turkish readability corrections
    Given a Turkish petition contains spelling, punctuation, or grammar issues
    When the user requests a writing suggestion
    Then the system returns an optional suggestion limited to light readability correction
    And the original text remains unchanged

  Scenario: Protected spans cannot be rewritten
    Given the text contains names, addresses, identifiers, amounts, dates, document numbers, or legal quotes
    When a suggestion changes a protected span
    Then the suggestion is rejected

  Scenario: Unsupported language is reported without translation
    Given the input language is unsupported
    When normalization is requested
    Then the result is `unsupported_language`
    And no automatic translation is applied

  Scenario: Accepted post-submit suggestion creates a revision
    Given a submitted case has an accepted normalized suggestion
    When the user accepts it
    Then F-01 original text remains preserved
    And BX-05 creates a new revision

## Open Questions

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-151 | Do “actions” include state change, assignment, edit, attachment, spam decision, download, and view; which are auditable? | requirement-analysis | Resolved | Human operator confirmed every listed action (2026-08-28). |
| OQ-152 | Is a “ticket” the existing case, a separate work item, or an external tracker record? | requirement-analysis | Resolved | Human operator: “ticket dediğimiz şey case'dir, evet. kullanıcı dilekçeleri üzerinden yürür.” (2026-08-28). |
| OQ-153 | What legal basis, consent/opt-out, retention, and deletion policy permit petition data to become training data? | requirement-analysis | Resolved | Legal team owns this policy; implementation does not decide it. (2026-08-28) |
| OQ-154 | Which direct and indirect identifiers must DLP detect: name, TCKN, phone, address, email, plate, location, free-text identifiers? | requirement-analysis | Resolved | Initial scope is document-specific name and T.C. Kimlik No spans; other classes remain out of scope. (2026-08-28) |
| OQ-155 | Must anonymisation be irreversible, or is a controlled pseudonym key allowed? | requirement-analysis | Resolved | Irreversible replacement; no re-identification key. Original stays operational-only. (2026-08-28) |
| OQ-156 | What export destination, format, approving role, and local/on-premise training boundary apply? | requirement-analysis | Open | Case-reader access is resolved; this slice deliberately provides a case-scoped JSON projection only and does not choose external destination or training infrastructure. (2026-08-28) |
| OQ-157 | Does “active” mean online, on shift, manually available, or recently active? | requirement-analysis | Resolved | No active signal; all unit members are candidates. (2026-08-28) |
| OQ-158 | Is load an open-ticket count or priority/SLA-weighted work? | requirement-analysis | Resolved | Count of open cases assigned to the person. (2026-08-28) |
| OQ-159 | Does eligibility depend on role, skill, leave, schedule, or explicit permission? | requirement-analysis | Resolved | Unit membership only; no extra role or expertise filter. (2026-08-28) |
| OQ-160 | What happens on equal load, no eligible person, manual override, and reassignment? | requirement-analysis | Open | Equal minimum load is random; no-person, override, and reassignment behavior remain unspecified. (2026-08-28) |
| OQ-161 | Is “user-based DB” a separate physical database or ownership/RBAC within current PostgreSQL? | requirement-analysis | Resolved | Existing PostgreSQL case records and access policy; no separate per-user DB. (2026-08-28) |
| OQ-162 | Who may see history, similar-case counts, case details, resolution state, and past moderator identities? | requirement-analysis | Resolved | Every principal that can read the case may see them. (2026-08-28) |
| OQ-163 | Which signals and threshold define similarity: text, classification, location, time, attachments, or a combination? | requirement-analysis | Resolved | Consider text, classification, location, and time; require same classification and ≤30 days. (2026-08-28) |
| OQ-164 | What date range and definition determine “Y similar petitions” and “resolved”? | requirement-analysis | Resolved | Maximum 30-day window; any case-reader resolution mark means resolved. (2026-08-28) |
| OQ-165 | What authenticated principal replaces the current shared demo `USER` token for per-user ownership? | requirement-analysis | Resolved | No per-user ownership model in this slice; existing case-reader principal is used. (2026-08-28) |
| OQ-166 | Which request type owns each required-attachment rule? | requirement-analysis | Resolved | Request/case type owns config/DB-backed rules; LLM is not authoritative. (2026-08-28) |
| OQ-167 | Are relationships manual, rule-based, or automatic similarity suggestions? | requirement-analysis | Resolved | Manual attach, deterministic rules, and non-authoritative similarity suggestions are supported. (2026-08-28) |
| OQ-168 | Which attachment types, file limits, formats, malware checks, and storage policy apply? | requirement-analysis | Resolved | PDF/DOCX/JPG/JPEG/PNG; 10 MB/file, 10 files/case; MIME+extension checks; object/file storage with DB metadata; AV is a production integration point. (2026-08-28) |
| OQ-169 | Can attachments change after submission, and how does that interact with BX-05 revisions? | requirement-analysis | Resolved | Changes allowed in draft/waiting_for_information; submitted changes create a BX-05 revision. (2026-08-28) |
| OQ-170 | Which signals define spam and aggression, including threats, profanity, harassment, rate, duplication, or bot behaviour? | requirement-analysis | Resolved | Signals are duplicate/repeated submission, excessive request burst, profanity/insult, threat, harassment, and obvious bot-like repetition. Criticism, negative wording, and capitalization alone are not aggression. (2026-08-28) |
| OQ-171 | Are outcomes flag-only, rate limiting, CAPTCHA, temporary block, or another policy? | requirement-analysis | Resolved | First outcome is flag plus human-visible risk score; simple rate limiting is optional for high-volume spam. CAPTCHA, automatic ban, and temporary block are out of scope. (2026-08-28) |
| OQ-172 | What human-review, explanation, appeal, and false-positive policy applies? | requirement-analysis | Resolved | Moderator sees and may override the flag; the citizen is not shown a contentious automatic judgment; false-positive overrides are action-log events; formal appeal is out of scope. (2026-08-28) |
| OQ-173 | If a model is used, what accuracy, explanation, language, retention, and threshold requirements apply? | requirement-analysis | Resolved | Optional model must support Turkish and return `label`, `confidence`, and `detected_signals`; threshold is configuration; explanation is short signals only; no chain-of-thought or long-lived raw inference. (2026-08-28) |
| OQ-211 | What exact risk-score scale/calibration and deterministic thresholds define duplicate, burst, and individual abuse signals? | requirement-analysis | Resolved | Configurable 0.0–1.0 score, default threshold 0.70; demo duplicate=exact normalized text/24h, burst=>5/10min, repeated bot-like=>3, term lists config-driven. (2026-08-28) |
| OQ-174 | Are trends per-user, per-unit, system-wide, or all three? | requirement-analysis | Resolved | User, unit, and system aggregates. (2026-08-28) |
| OQ-175 | Which roles see trend data, and what aggregation minimum prevents re-identification? | requirement-analysis | Resolved | User self, moderator unit, admin aggregate; minimum five users. (2026-08-28) |
| OQ-176 | Which metric, time interval, change threshold, recipient, and notification behavior are required? | requirement-analysis | Resolved | Daily flagged rate, 7-day rolling window, ±25% insight; dashboard only, no push/email. (2026-08-28) |
| OQ-177 | Is BX-04A permitted before BX-04 creates authoritative signals? | requirement-analysis | Resolved | No; return `no_data/not_available` until BX-04 signals exist. (2026-08-28) |
| OQ-178 | In which case states may an owner edit: draft, waiting for information, review, routed, or later? | requirement-analysis | Resolved | Direct edits in draft/waiting_for_information; review/routed edits create BX-05 revision; resolved/closed immutable. (2026-08-28) |
| OQ-179 | Which content may change: text, fields, attachments, classification, or all? | requirement-analysis | Resolved | Text, structured fields, and attachments may change; classification is never directly editable and may be recomputed. (2026-08-28) |
| OQ-180 | Are prior versions retained, visible, and restorable; for how long? | requirement-analysis | Resolved | Prior revisions retained and visible to authorized personnel until deletion/retention; restore is not required for MVP. (2026-08-28) |
| OQ-181 | Does an edit invalidate assignment, routing, correspondence, priority, or SLA? | requirement-analysis | Resolved | Re-analysis when routing/classification inputs change; owner remains, SLA does not reset, correspondence is immutable, priority may recalculate. (2026-08-28) |
| OQ-182 | If exported or trained data reflects an older version, what removal/retraining policy applies? | requirement-analysis | Resolved | Dataset uses latest eligible revision with provenance; stale untrained exports are removed; retraining/unlearning is out of scope. (2026-08-28) |
| OQ-183 | Is BX-06 preview before submission, after submission, or both? | requirement-analysis | Resolved | Primarily before submit; after submit it is read-only case detail. (2026-08-28) |
| OQ-184 | Must preview include invalid fields and allow direct editing? | requirement-analysis | Resolved | Yes; reuse existing form state, no second edit engine. (2026-08-28) |
| OQ-185 | Does missing information block submission or only show a draft-save path? | requirement-analysis | Resolved | Mandatory missing fields block submission; draft save remains; optional/recommended fields warn only. (2026-08-28) |
| OQ-186 | Is BX-07 a citizen petition, an internal official document, or both? | requirement-analysis | Resolved | Citizen petition/request draft; internal correspondence remains F-04. (2026-08-28) |
| OQ-187 | Which document types, mandatory fields, templates, and jurisdictional rules are supported? | requirement-analysis | Resolved | Petition/request, complaint, information_request; local templates and context-dependent subject/body/identity fields. (2026-08-28) |
| OQ-188 | Is output plain editable text only, or must PDF/DOCX be produced? | requirement-analysis | Resolved | Editable structured/plain text; PDF/DOCX deferred. (2026-08-28) |
| OQ-189 | Is generation template-based, model-based, or hybrid? | requirement-analysis | Resolved | Deterministic structure/template plus optional Jamba content. (2026-08-28) |
| OQ-190 | Is a generated draft an F-01 intake record or temporary data until submitted? | requirement-analysis | Resolved | Temporary draft until user submits through F-01. (2026-08-28) |
| OQ-191 | What priority levels, default, and policy owner apply? | requirement-analysis | Resolved | low/normal/high/urgent, default normal, deterministic application config. (2026-08-28) |
| OQ-192 | Which signals may affect priority, particularly emergency claims and sensitive data? | requirement-analysis | Resolved | Request type, deadline, wait time, verified urgency; sensitive data alone cannot raise priority. (2026-08-28) |
| OQ-193 | Is manual override allowed; must it record a reason? | requirement-analysis | Resolved | Moderator/admin override allowed; reason required and action-logged. (2026-08-28) |
| OQ-194 | Does priority affect ordering, SLA, notification, routing, or display only? | requirement-analysis | Resolved | Queue/dashboard ordering and optional simple SLA; never routing destination. (2026-08-28) |
| OQ-195 | What abuse control protects priority claims? | requirement-analysis | Resolved | User emergency text is candidate signal only; deterministic policy/human review decides. (2026-08-28) |
| OQ-196 | Who and what event determine whether routing was correct? | requirement-analysis | Resolved | Moderator transfer/acceptance or final closure labels correctness. (2026-08-28) |
| OQ-197 | Is ground truth the first target, final target, or a human override? | requirement-analysis | Resolved | Final accepted unit is ground truth; human override authoritative. (2026-08-28) |
| OQ-198 | Is feedback retained, shown, or included in BX-01 training data? | requirement-analysis | Resolved | Store/show feedback; BX-01 only after anonymization eligibility. (2026-08-28) |
| OQ-199 | Is the score per case, per unit aggregate, or both? | requirement-analysis | Resolved | Case-level and unit/system aggregate accuracy. (2026-08-28) |
| OQ-200 | Does low confidence require human review? | requirement-analysis | Resolved | Config threshold sets `needs_review`; case creation is not blocked. (2026-08-28) |
| OQ-201 | Is dashboard scope person, unit, system, or multiple scopes? | requirement-analysis | Resolved | Unit/system plus own case history. (2026-08-28) |
| OQ-202 | What exactly define active personnel, assigned work, completed work, and performance? | requirement-analysis | Resolved | Enabled+available, open current owner, terminal in period; separate throughput/load/resolution-time metrics. (2026-08-28) |
| OQ-203 | Which date range, refresh rate, export, and charts are required? | requirement-analysis | Resolved | Default 30 days; 7/30/90 choices; page-load/short cache; simple line/bar/count charts; CSV optional. (2026-08-28) |
| OQ-204 | Who sees personnel metrics; what privacy and employment-policy constraints apply? | requirement-analysis | Resolved | Unit manager/admin only; no ranking or aggression-based employee score. (2026-08-28) |
| OQ-205 | Is BX-11 spelling/punctuation only, simplification, or meaning-changing rewriting? | requirement-analysis | Resolved | Spelling, punctuation, grammar, light readability; no semantic rewrite. (2026-08-28) |
| OQ-206 | How must names, addresses, numbers, dates, and legal claims be protected from changes? | requirement-analysis | Resolved | Protected spans; suggestion changing one is rejected. (2026-08-28) |
| OQ-207 | Is the suggestion rule-based, model-based, or hybrid; what is unsupported-language behavior? | requirement-analysis | Resolved | Deterministic + optional Jamba hybrid; unsupported language returns `unsupported_language`. (2026-08-28) |
| OQ-208 | Once accepted, does suggested text replace F-01 original text, normalized text, or create a new revision? | requirement-analysis | Resolved | Original preserved; normalized/edited projection updates, submit-after-edit creates BX-05 revision. (2026-08-28) |
| OQ-209 | Must a case-action log be immutable; which roles may read it, and what retention/deletion policy applies? | requirement-analysis | Resolved | Human operator: immutable; everyone with case access may read; persist in SQL; no automatic deletion. (2026-08-28) |
| OQ-210 | Which logical service owns the SQL action-log table and read boundary, and how do OCR, validation, and workflow actions reach it without direct access to another service's tables? | requirement-analysis | Resolved | Operator delegated the decision. `workflow` owns the central SQL table/read projection; other services publish a contract-bound internal action event and never access private tables. (2026-08-28) |

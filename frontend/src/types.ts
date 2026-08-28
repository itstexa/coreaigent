export type ImplementationMode = "mock" | "real" | "unknown";

export interface NodeReference {
  id: string;
  label: string;
}

export interface OcrResult {
  schemaVersion: "2.0";
  requestId: string;
  documentId: string;
  caseId: string;
  workflowId: string;
  text: string;
  language: "tr" | "en" | "unknown";
  confidence: number;
  ingestStatus: "queued";
  warnings: string[];
}

export interface ClassificationResult {
  schemaVersion: "3.0";
  requestId: string;
  documentId: string;
  workflowId: string;
  status: "classified" | "needs_review";
  department: NodeReference | null;
  unit: NodeReference | null;
  requestType: NodeReference | null;
  confidence: number;
  taxonomyVersion: string;
  classifierVersion: string;
  classificationReason: string;
}

export interface ExtractedField {
  id: string;
  label: string;
  value: string;
  confidence: number;
}

export interface ValidationField {
  id: string;
  label: string;
}

export interface InvalidField extends ValidationField {
  code: string;
}

export interface ValidationResult {
  schemaVersion: "3.0";
  requestId: string;
  documentId: string;
  caseId: string;
  workflowId: string;
  requestTypeId: string;
  schemaVersionUsed: string;
  extractedFields: ExtractedField[];
  missingRequiredFields: ValidationField[];
  invalidFields: InvalidField[];
  completionStatus: "complete" | "missing_information" | "invalid_information";
  userActionRequired: boolean;
}

export interface ApplicantNotice {
  kind: string;
  payload: unknown;
  created_at: string;
}

export interface CaseStatus {
  case_id: string;
  case_revision: number;
  state: string;
  completed_steps: string[];
  last_error_code: string | null;
  updated_at: string;
  validation_status: ValidationResult["completionStatus"] | null;
  routing_status: "not_routed" | "routed";
  applicant_notifications: ApplicantNotice[];
  operational_context?: {
    validated_fields: Record<string, { value?: string; confidence?: number } | string>;
    department_id: string | null;
    unit_id: string | null;
    request_type_id: string | null;
    document_summary: string | null;
    draft_text: string | null;
  };
  routing?: { target_department_id: string; target_unit_id: string } | null;
  target_unit_notification?: unknown;
}

export type CorrespondenceResult =
  | { case_id: string; case_revision: number; generation_status: "not_requested"; result: null }
  | { case_id: string; case_revision: number; generation_status: "queued" | "processing" }
  | { case_id: string; case_revision: number; generation_id: string; generation_status: "failed"; error_code: string }
  | {
      case_id: string;
      case_revision: number;
      generation_id: string;
      generation_status: "completed";
      source_status: "relevant_source_found" | "no_relevant_source";
      result_status: "draft_ready" | "review_required";
      corpus_version: string;
      document_summary: string;
      recommended_correspondence_type: string;
      correspondence_type_detail: string | null;
      draft_text: string;
      regulation_suggestions: Array<{
        source_id: string;
        corpus_version: string;
        title: string;
        source_type: string;
        locator: string;
        chunk_id: string;
      }>;
    };

export type RoutingResult =
  | { case_id: string; case_revision: number; routing_status: "not_routed"; result: null }
  | {
      case_id: string;
      case_revision: number;
      routing_id: string;
      routing_status: "routed";
      route_kind: "classified" | "fallback";
      target_department: NodeReference;
      target_unit: NodeReference;
      assignee: { id: string; name: string } | null;
      notifications: Array<{
        audience: "applicant" | "target_unit";
        generation_status: "queued" | "processing" | "completed" | "failed";
        error_code: string | null;
      }>;
    };

export interface CaseRecord {
  caseId: string;
  documentId: string;
  workflowId: string;
  title: string;
  createdAt: string;
  sourceType: "text" | "ocr";
  sourceText?: string;
  /** F-01'in metinden belirlediği dil; vatandaşa hangi kararın verildiğini göstermek için. */
  language?: OcrResult["language"];
  state?: string;
  updatedAt?: string;
  implementation: ImplementationMode;
  classification?: ClassificationResult;
  validation?: ValidationResult;
  /**
   * Doğrulama durumunun revizyonu (`POST /v1/validate` ETag'i).
   *
   * Eksik bilgi tamamlama isteği `If-Match` ile bu revizyonu gönderir.  Gerçek
   * workflow hattı revizyon yayınlamadığı için burada tanımsız kalabilir; o
   * durumda tamamlama akışı kapatılır.
   */
  validationRevision?: number;
}

/** `GET /cases/{case_id}/document` — vatandaşın yazdığı özgün dilekçe (ADMIN). */
export interface CaseDocument {
  case_id: string;
  document_id: string;
  source_type: string;
  language: string | null;
  title: string | null;
  channel: string | null;
  created_at: string;
  text: string;
}

export type CaseActionType = "state_change" | "assignment" | "petition_edit" | "attachment_change" | "spam_decision" | "view" | "download";

export interface CaseActionEvent {
  event_id: string;
  action_type: CaseActionType;
  actor: string;
  occurred_at: string;
  details: Record<string, unknown>;
}

export interface CaseActionLog {
  case_id: string;
  events: CaseActionEvent[];
}

export interface CaseHistory {
  case_id: string;
  resolved: boolean;
  resolved_by: string[];
  similar_cases: Array<{
    case_id: string;
    created_at: string;
    state: string;
    classification: string;
    resolved: boolean;
    resolved_by: string[];
    viewers: string[];
    signals: Array<"text" | "classification" | "location" | "time">;
  }>;
}

export interface CaseTrainingExport {
  case_id: string;
  document_id: string;
  text: string;
  redactions: Array<{ field: "name" | "tckn"; placeholder: "<ANON_NAME>" | "<ANON_TCKN>"; count: number }>;
}

export interface CaseBundle {
  status: CaseStatus;
  correspondence: CorrespondenceResult;
  routing: RoutingResult;
}

export interface ServiceHealth {
  name: "ocr" | "classification" | "validation" | "workflow";
  available: boolean;
  implementation: ImplementationMode;
  detail?: string;
}

/** `GET /cases` satırı — panelin yetkili kuyruğu (ADMIN token gerektirir). */
export interface CaseListItem {
  case_id: string;
  case_revision: number;
  state: string;
  completed_steps: string[];
  last_error_code: string | null;
  updated_at: string;
  validation_status: ValidationResult["completionStatus"] | null;
  routing_status: "not_routed" | "routed";
  document_id: string | null;
  request_type_id: string | null;
  request_type_label: string | null;
  department_id: string | null;
  department_label: string | null;
  unit_id: string | null;
  unit_label: string | null;
  classification_status: string | null;
  classification_confidence: number | null;
  /** Sınıflandırıcının Türkçe gerekçesi; dosyanın neden bu birimde olduğunun tek okunur açıklaması. */
  classification_reason: string | null;
  applicant_name: string | null;
  title: string | null;
  channel: string | null;
  language: string | null;
  created_at: string | null;
}

export interface CaseListPage {
  total: number;
  limit: number;
  offset: number;
  cases: CaseListItem[];
}

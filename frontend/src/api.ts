import type {
  CaseBundle,
  CaseDocument,
  CaseListItem,
  CaseListPage,
  CaseRecord,
  CaseStatus,
  ClassificationResult,
  CorrespondenceResult,
  ImplementationMode,
  OcrResult,
  RoutingResult,
  ServiceHealth,
  ValidationResult,
} from "./types";

const BASES = {
  real: "/api/real",
  ocr: "/api/ocr",
  classification: "/api/classification",
  validation: "/api/validation",
  validationUser: "/api/validation-user",
  workflowUser: "/api/workflow-user",
  workflowAdmin: "/api/workflow-admin",
} as const;

interface RealWorkflowStep {
  service: "ocr" | "classification" | "validation" | "rag" | "llm" | "workflow";
  status: "completed" | "skipped" | "failed";
  timestamp: string;
}

interface RealWorkflowResult {
  schemaVersion: "1.0";
  requestId: string;
  documentId: string;
  workflowId: string;
  status: "completed" | "needs_information" | "rejected" | "manual_review";
  documentType: "petition" | "application" | "complaint" | "information_request" | "official_letter" | "invoice" | "unsupported";
  department: "insan_kaynaklari" | "hukuk" | "mali_hizmetler" | "yazi_isleri" | "bilgi_islem" | "destek_hizmetleri" | "vatandas_hizmetleri" | "manual_review";
  draft: string;
  missingFields?: string[];
  conflicts?: string[];
  summary?: string | null;
  confidence?: number | null;
  steps: RealWorkflowStep[];
  error?: Record<string, unknown> | null;
}

const DEPARTMENT_LABELS: Record<RealWorkflowResult["department"], string> = {
  insan_kaynaklari: "İnsan Kaynakları",
  hukuk: "Hukuk",
  mali_hizmetler: "Mali Hizmetler",
  yazi_isleri: "Yazı İşleri",
  bilgi_islem: "Bilgi İşlem",
  destek_hizmetleri: "Destek Hizmetleri",
  vatandas_hizmetleri: "Vatandaş Hizmetleri",
  manual_review: "Manuel İnceleme",
};

const DOCUMENT_TYPE_LABELS: Record<RealWorkflowResult["documentType"], string> = {
  petition: "Dilekçe",
  application: "Başvuru",
  complaint: "Şikayet",
  information_request: "Bilgi Edinme",
  official_letter: "Resmi Yazı",
  invoice: "Fatura",
  unsupported: "Desteklenmeyen Evrak",
};

const STEP_FEATURES: Record<RealWorkflowStep["service"], string> = {
  ocr: "F-01",
  classification: "F-02",
  validation: "F-03",
  rag: "F-04",
  llm: "F-05",
  workflow: "F-05",
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly retryable: boolean,
    public readonly details?: unknown,
    public readonly implementation: ImplementationMode = "unknown",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ApiResponse<T> {
  data: T;
  etag: string | null;
  implementation: ImplementationMode;
}

function implementationOf(response: Response): ImplementationMode {
  const value = response.headers.get("X-CoreAIgent-Implementation");
  return value === "mock" ? "mock" : value ? "real" : "unknown";
}

function errorFrom(status: number, body: unknown, implementation: ImplementationMode = "unknown"): ApiError {
  const value = body as {
    error?: { code?: string; message?: string; [key: string]: unknown };
    message?: string;
    category?: string;
    retryable?: boolean;
  };
  if (value?.error) {
    return new ApiError(
      value.error.message ?? "İşlem tamamlanamadı.",
      status,
      value.error.code ?? `HTTP_${status}`,
      status >= 500,
      value.error,
      implementation,
    );
  }
  return new ApiError(
    value?.message ?? "Servisten beklenmeyen bir yanıt alındı.",
    status,
    value?.category ?? `HTTP_${status}`,
    Boolean(value?.retryable ?? status >= 500),
    body,
    implementation,
  );
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 12_000): Promise<ApiResponse<T>> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  if (init.signal) {
    if (init.signal.aborted) controller.abort();
    else init.signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  try {
    const response = await fetch(path, { ...init, signal: controller.signal });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw errorFrom(response.status, body, implementationOf(response));
    if (body === null || typeof body !== "object") {
      throw new ApiError("Servis yanıtı geçerli JSON nesnesi değil.", response.status, "INVALID_RESPONSE_SCHEMA", false);
    }
    return {
      data: body as T,
      etag: response.headers.get("ETag"),
      implementation: implementationOf(response),
    };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) {
      throw new ApiError("Servis yanıtı zaman aşımına uğradı.", 0, "REQUEST_TIMEOUT", true);
    }
    throw new ApiError("Backend servisine ulaşılamıyor.", 0, "BACKEND_UNREACHABLE", true, error);
  } finally {
    window.clearTimeout(timeout);
  }
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function assertString(value: unknown, name: string): asserts value is string {
  if (typeof value !== "string" || !value) {
    throw new ApiError(`Yanıtta ${name} alanı eksik.`, 200, "INVALID_RESPONSE_SCHEMA", false);
  }
}

function validateOcr(value: OcrResult): void {
  assertString(value.caseId, "caseId");
  assertString(value.documentId, "documentId");
  assertString(value.workflowId, "workflowId");
  if (value.schemaVersion !== "2.0" || value.ingestStatus !== "queued") {
    throw new ApiError("OCR/intake yanıt şeması beklenen contract ile eşleşmiyor.", 200, "INVALID_RESPONSE_SCHEMA", false);
  }
}

function validateClassification(value: ClassificationResult): void {
  if (value.schemaVersion !== "3.0" || !["classified", "needs_review"].includes(value.status)) {
    throw new ApiError("Sınıflandırma yanıt şeması beklenen contract ile eşleşmiyor.", 200, "INVALID_RESPONSE_SCHEMA", false);
  }
}

function validateValidation(value: ValidationResult): void {
  if (value.schemaVersion !== "3.0" || !Array.isArray(value.extractedFields) || !Array.isArray(value.missingRequiredFields)) {
    throw new ApiError("Validation yanıt şeması beklenen contract ile eşleşmiyor.", 200, "INVALID_RESPONSE_SCHEMA", false);
  }
}

function realState(status: RealWorkflowResult["status"]): string {
  if (status === "completed") return "completed";
  if (status === "needs_information") return "waiting_for_user";
  if (status === "manual_review") return "needs_review";
  return "failed";
}

function realNode(id: string | null | undefined, fallback = "Eşleşme yok"): { id: string; label: string } | null {
  if (!id) return null;
  const key = id as RealWorkflowResult["department"];
  return { id, label: DEPARTMENT_LABELS[key] ?? fallback };
}

function realValidation(result: RealWorkflowResult): ValidationResult {
  const missing = result.missingFields ?? [];
  return {
    schemaVersion: "3.0",
    requestId: result.requestId,
    documentId: result.documentId,
    caseId: result.workflowId,
    workflowId: result.workflowId,
    requestTypeId: result.documentType,
    schemaVersionUsed: "real-workflow-1.0",
    extractedFields: [],
    missingRequiredFields: missing.map((field) => ({ id: field, label: field })),
    invalidFields: (result.conflicts ?? []).map((field) => ({ id: field, label: field, code: "conflict" })),
    completionStatus: missing.length ? "missing_information" : "complete",
    userActionRequired: missing.length > 0,
  };
}

function realClassification(result: RealWorkflowResult): ClassificationResult {
  const department = realNode(result.department);
  return {
    schemaVersion: "3.0",
    requestId: result.requestId,
    documentId: result.documentId,
    workflowId: result.workflowId,
    status: result.documentType === "unsupported" || result.department === "manual_review" ? "needs_review" : "classified",
    department,
    unit: department,
    requestType: { id: result.documentType, label: DOCUMENT_TYPE_LABELS[result.documentType] },
    confidence: result.confidence ?? 0,
    taxonomyVersion: "real-workflow",
    classifierVersion: "Jamba2-3B-Turkish",
    classificationReason: result.summary ?? "Gerçek workflow sonucu.",
  };
}

function realCompletedSteps(result: RealWorkflowResult): string[] {
  return [...new Set(result.steps.filter((step) => step.status === "completed").map((step) => STEP_FEATURES[step.service]))];
}

function realBundle(result: RealWorkflowResult): CaseBundle {
  const state = realState(result.status);
  const validation = realValidation(result);
  const department = realNode(result.department, "Manuel İnceleme") ?? { id: "manual_review", label: "Manuel İnceleme" };
  return {
    status: {
      case_id: result.workflowId,
      case_revision: 1,
      state,
      completed_steps: realCompletedSteps(result),
      last_error_code: result.error ? "REAL_WORKFLOW_ERROR" : null,
      updated_at: result.steps[result.steps.length - 1]?.timestamp ?? new Date().toISOString(),
      validation_status: validation.completionStatus,
      routing_status: result.department === "manual_review" ? "not_routed" : "routed",
      applicant_notifications: validation.missingRequiredFields.length
        ? [{ kind: "missing_information", payload: { fields: validation.missingRequiredFields }, created_at: new Date().toISOString() }]
        : [],
      operational_context: {
        validated_fields: {},
        department_id: result.department,
        unit_id: result.department,
        request_type_id: result.documentType,
        document_summary: result.summary ?? null,
        draft_text: result.draft || null,
      },
      routing: result.department === "manual_review" ? null : {
        target_department_id: result.department,
        target_unit_id: result.department,
      },
      target_unit_notification: null,
    },
    correspondence: result.draft
      ? {
          case_id: result.workflowId,
          case_revision: 1,
          generation_id: result.workflowId,
          generation_status: "completed",
          source_status: "relevant_source_found",
          result_status: result.department === "manual_review" ? "review_required" : "draft_ready",
          corpus_version: "local-rag",
          document_summary: result.summary ?? "",
          recommended_correspondence_type: "official_reply",
          correspondence_type_detail: null,
          draft_text: result.draft,
          regulation_suggestions: [],
        }
      : { case_id: result.workflowId, case_revision: 1, generation_status: "not_requested", result: null },
    routing: result.department === "manual_review"
      ? { case_id: result.workflowId, case_revision: 1, routing_status: "not_routed", result: null }
      : {
          case_id: result.workflowId,
          case_revision: 1,
          routing_id: result.workflowId,
          routing_status: "routed",
          route_kind: "classified",
          target_department: department,
          target_unit: department,
          notifications: [],
        },
  };
}

async function realWorkflowAvailable(): Promise<boolean> {
  try {
    await request<Record<string, unknown>>(`${BASES.real}/ready`, {}, 5_000);
    return true;
  } catch {
    return false;
  }
}

async function runRealWorkflow(
  input: IntakeInput,
  documentId: string,
  requestId: string,
  onProgress: (progress: IntakeProgress) => void,
): Promise<CaseRecord> {
  const timedProgress = [
    { step: "intake" as const, message: "Gerçek workflow evrakı aldı" },
    { step: "classification" as const, message: "Jamba sınıflandırma yapıyor" },
    { step: "validation" as const, message: "Eksik bilgiler kontrol ediliyor" },
    { step: "rag" as const, message: "Yerel mevzuat kaynakları aranıyor" },
    { step: "generation" as const, message: "Yönlendirme ve taslak hazırlanıyor" },
  ];
  let index = 0;
  onProgress(timedProgress[index]);
  const timer = window.setInterval(() => {
    index = Math.min(index + 1, timedProgress.length - 1);
    onProgress(timedProgress[index]);
  }, 12_000);
  try {
    const response = await request<RealWorkflowResult>(`${BASES.real}/upload`, json({
      schemaVersion: "1.0",
      requestId,
      documentId,
      scenarioId: "free-text",
      contentType: input.sourceType === "ocr" ? "text/plain" : "text/plain",
      content: input.text,
      source: input.sourceType === "ocr" ? "pre_extracted_ocr_text" : "web_text",
    }), 180_000);
    const result = response.data;
    return {
      caseId: result.workflowId,
      documentId: result.documentId,
      workflowId: result.workflowId,
      title: input.title,
      createdAt: new Date().toISOString(),
      sourceType: input.sourceType,
      sourceText: input.text,
      state: realState(result.status),
      updatedAt: result.steps.at(-1)?.timestamp ?? new Date().toISOString(),
      implementation: "real",
      classification: realClassification(result),
      validation: realValidation(result),
    };
  } finally {
    window.clearInterval(timer);
  }
}

const MOCK_SCENARIO_REQUIRED =
  "Mock sözleşme modu yalnızca golden senaryo evraklarını işler. Örnek evraklardan birini metnini değiştirmeden gönderin veya gerçek servis Compose overlay'ini başlatın.";

/** The mock resolves its scenario from `documentId`; free text has no golden scenario to match. */
export function scenarioAwareError(error: unknown, boundDocumentId: string | undefined): unknown {
  if (error instanceof ApiError && error.implementation === "mock" && error.status === 400 && !boundDocumentId) {
    return new ApiError(MOCK_SCENARIO_REQUIRED, error.status, "MOCK_SCENARIO_REQUIRED", false, error.details, "mock");
  }
  return error;
}

/**
 * Read a revision out of a weak-or-strong ETag.
 *
 * The validation service publishes `"3"`; the supplemental-information endpoint
 * requires exactly that quoted revision back in `If-Match`.  A response without
 * a usable ETag is not an error -- the caller simply cannot offer the
 * supplement flow, and says so instead of guessing a number.
 */
export function revisionFrom(etag: string | null): number | undefined {
  const match = /"?(\d+)"?$/.exec((etag ?? "").trim());
  if (!match) return undefined;
  const revision = Number(match[1]);
  return Number.isInteger(revision) && revision > 0 ? revision : undefined;
}

export interface IntakeInput {
  title: string;
  text: string;
  sourceType: "text" | "ocr";
  documentId?: string;
  sourceMetadata?: Record<string, unknown>;
}

export interface IntakeProgress {
  step: "intake" | "classification" | "validation" | "rag" | "generation" | "queued";
  message: string;
}

export async function runIntake(
  input: IntakeInput,
  onProgress: (progress: IntakeProgress) => void,
): Promise<CaseRecord> {
  const documentId = input.documentId ?? `doc-${crypto.randomUUID()}`;
  const requestId = `req-${crypto.randomUUID()}`;

  if (await realWorkflowAvailable()) {
    return runRealWorkflow(input, documentId, requestId, onProgress);
  }

  onProgress({ step: "intake", message: "Evrak intake servisine aktarılıyor" });
  let ocrResponse: ApiResponse<OcrResult>;
  try {
    ocrResponse = await request<OcrResult>(`${BASES.ocr}/v1/ocr`, json({
      schemaVersion: "2.0",
      requestId,
      documentId,
      sourceType: input.sourceType,
      text: input.text,
      sourceMetadata: input.sourceMetadata ?? {},
      correlationId: "coreaigent-web",
    }), 20_000);
  } catch (error) {
    throw scenarioAwareError(error, input.documentId);
  }
  validateOcr(ocrResponse.data);

  onProgress({ step: "classification", message: "Taksonomi sınıflandırması çalışıyor" });
  const classificationResponse = await request<ClassificationResult>(
    `${BASES.classification}/v1/classify`,
    json(ocrResponse.data),
    20_000,
  );
  validateClassification(classificationResponse.data);

  let validation: ValidationResult | undefined;
  let validationRevision: number | undefined;
  if (classificationResponse.data.status === "classified") {
    onProgress({ step: "validation", message: "Alan çıkarımı ve doğrulama bekleniyor" });
    for (let attempt = 0; attempt < 24; attempt += 1) {
      try {
        const response = await request<ValidationResult>(
          `${BASES.validation}/v1/validate`,
          json(classificationResponse.data),
          30_000,
        );
        validateValidation(response.data);
        validation = response.data;
        validationRevision = revisionFrom(response.etag);
        break;
      } catch (error) {
        if (!(error instanceof ApiError) || ![404, 409].includes(error.status) || attempt === 23) throw error;
        await wait(500);
      }
    }
  }

  onProgress({ step: "queued", message: "Case yaşam döngüsü izlemeye alındı" });
  // The worker projects the case state moments after intake.  Reading it back
  // here keeps the file list showing the backend's own state instead of an
  // empty label that never resolves until the case is opened.
  let projected: { state: string; updatedAt: string } | null = null;
  for (let attempt = 0; attempt < 4 && !projected; attempt += 1) {
    if (attempt) await wait(400);
    projected = await getCaseState(ocrResponse.data.caseId);
  }
  return {
    caseId: ocrResponse.data.caseId,
    documentId: ocrResponse.data.documentId,
    workflowId: ocrResponse.data.workflowId,
    title: input.title,
    createdAt: new Date().toISOString(),
    sourceType: input.sourceType,
    sourceText: input.text,
    language: ocrResponse.data.language,
    state: projected?.state,
    updatedAt: projected?.updatedAt,
    implementation: ocrResponse.implementation,
    classification: classificationResponse.data,
    validation,
    validationRevision,
  };
}

/**
 * Authoritative case state for a list row.
 *
 * The projection is written by the workflow worker a moment after intake, so a
 * row that has no state yet is not an error: the caller keeps whatever it had
 * and asks again later.  The frontend never derives a state of its own.
 */
export async function getCaseState(caseId: string): Promise<{ state: string; updatedAt: string } | null> {
  try {
    const response = await request<CaseStatus>(`${BASES.workflowAdmin}/cases/${encodeURIComponent(caseId)}`, {}, 8_000);
    return { state: response.data.state, updatedAt: response.data.updated_at };
  } catch {
    return null;
  }
}

export async function getCaseBundle(caseId: string): Promise<CaseBundle> {
  if (await realWorkflowAvailable()) {
    try {
      const response = await request<RealWorkflowResult>(`${BASES.real}/result/${encodeURIComponent(caseId)}`, {}, 20_000);
      return realBundle(response.data);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 404) throw error;
    }
  }
  const encoded = encodeURIComponent(caseId);
  const [status, correspondence, routing] = await Promise.all([
    request<CaseStatus>(`${BASES.workflowAdmin}/cases/${encoded}`),
    request<CorrespondenceResult>(`${BASES.workflowUser}/cases/${encoded}/correspondence`),
    request<RoutingResult>(`${BASES.workflowUser}/cases/${encoded}/routing`),
  ]);
  return { status: status.data, correspondence: correspondence.data, routing: routing.data };
}

/**
 * The petition the citizen actually wrote.
 *
 * ADMIN-only, so it travels over the panel's own proxy path.  The panel used to
 * fall back to whatever the operator's own browser had in local storage, which
 * meant a case submitted from another device showed no text at all.
 */
export async function getCaseDocument(caseId: string): Promise<CaseDocument> {
  const response = await request<CaseDocument>(
    `${BASES.workflowAdmin}/cases/${encodeURIComponent(caseId)}/document`,
    {},
    15_000,
  );
  return response.data;
}

export async function supplementCase(
  caseId: string,
  revision: number,
  fields: Record<string, string>,
): Promise<{ validation: ValidationResult; etag: string | null }> {
  const response = await request<ValidationResult>(
    `${BASES.validationUser}/cases/${encodeURIComponent(caseId)}/supplemental-information`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
        "If-Match": `"${revision}"`,
      },
      body: JSON.stringify({ fields }),
    },
    30_000,
  );
  validateValidation(response.data);
  return { validation: response.data, etag: response.etag };
}

export async function startCorrespondence(caseId: string, revision: number): Promise<void> {
  await request(`${BASES.workflowUser}/cases/${encodeURIComponent(caseId)}/correspondence`, {
    method: "POST",
    headers: {
      "Idempotency-Key": crypto.randomUUID(),
      "If-Match": `"${revision}"`,
    },
  });
}

export async function completeReview(caseId: string, revision: number): Promise<void> {
  await request(`${BASES.workflowAdmin}/cases/${encodeURIComponent(caseId)}/review-completion`, {
    method: "POST",
    headers: {
      "Idempotency-Key": crypto.randomUUID(),
      "If-Match": `"${revision}"`,
    },
  });
}

export async function serviceHealth(): Promise<ServiceHealth[]> {
  if (await realWorkflowAvailable()) {
    return [
      { name: "ocr", available: true, implementation: "real", detail: "Tek workflow sürecinde" },
      { name: "classification", available: true, implementation: "real", detail: "Jamba2-3B-Turkish" },
      { name: "validation", available: true, implementation: "real", detail: "Jamba2-3B-Turkish" },
      { name: "workflow", available: true, implementation: "real", detail: "Yerel RAG + taslak" },
    ];
  }
  const services: Array<{ name: ServiceHealth["name"]; path: string }> = [
    { name: "ocr", path: `${BASES.ocr}/ready` },
    { name: "classification", path: `${BASES.classification}/ready` },
    { name: "validation", path: `${BASES.validation}/ready` },
    { name: "workflow", path: `${BASES.workflowUser}/ready` },
  ];
  return Promise.all(services.map(async ({ name, path }) => {
    try {
      const response = await request<Record<string, unknown>>(path, {}, 5_000);
      return { name, available: true, implementation: response.implementation };
    } catch (error) {
      return {
        name,
        available: false,
        implementation: "unknown" as const,
        detail: error instanceof Error ? error.message : "Servis hazır değil",
      };
    }
  }));
}

export interface CaseListQuery {
  limit?: number;
  offset?: number;
  state?: string;
  q?: string;
}

/**
 * Panelin dosya kuyruğu.
 *
 * Liste localStorage'dan değil backend'den gelir: bir vatandaş dilekçesini
 * telefonundan gönderdiğinde operatörün onu kendi tarayıcısında görmesi
 * gerekir. Uç nokta ADMIN yetkisi ister; token'ı tarayıcıya yerel ters vekil
 * (nginx) ekler, JavaScript paketinde sabit kimlik bilgisi taşınmaz.
 */
export async function listCases(query: CaseListQuery = {}): Promise<CaseListPage> {
  const params = new URLSearchParams();
  params.set("limit", String(query.limit ?? 25));
  params.set("offset", String(query.offset ?? 0));
  if (query.state) params.set("state", query.state);
  if (query.q) params.set("q", query.q);
  const response = await request<CaseListPage>(`${BASES.workflowAdmin}/cases?${params.toString()}`, {}, 10_000);
  const page = response.data;
  if (!Array.isArray(page.cases)) {
    throw new ApiError("Dosya listesi yanıtı beklenen biçimde değil.", 200, "INVALID_RESPONSE_SCHEMA", false);
  }
  return page;
}

/**
 * Kuyruk projeksiyonundaki tek satir.
 *
 * Dosya detayi bu satiri ister: siniflandirma etiketleri, guven puani, gerekce
 * ve basvuran adi `GET /cases/{case_id}` govdesinde degil kuyruk
 * projeksiyonunda yayimlanir.  Arama case id'yi de tarar, boylece baska bir
 * cihazdan gonderilmis bir dosya da tarayici bellegine bagli kalmadan acilir.
 */
export async function getCaseSummary(caseId: string): Promise<CaseListItem | null> {
  const page = await listCases({ limit: 5, q: caseId });
  return page.cases.find((item) => item.case_id === caseId) ?? null;
}

export function apiErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Beklenmeyen bir hata oluştu.";
  const messages: Record<string, string> = {
    BACKEND_UNREACHABLE: "Backend servislerine ulaşılamıyor. Compose servislerini kontrol edin.",
    REQUEST_TIMEOUT: "İşlem beklenenden uzun sürdü. Case durumu kaybolmadı; yeniden deneyebilirsiniz.",
    HTTP_500: "Backend servislerine ulaşılamıyor. Compose servislerini kontrol edin.",
    HTTP_502: "Backend servislerine ulaşılamıyor. Compose servislerini kontrol edin.",
    HTTP_503: "Backend servislerinden biri henüz hazır değil. Kısa süre sonra yeniden deneyin.",
    CASE_NOT_FOUND: "Case henüz iş akışı görünümünde hazır değil veya bulunamadı.",
    CASE_REVISION_CONFLICT: "Case bu sırada güncellendi. Güncel durumu yükleyip yeniden deneyin.",
    CASE_NOT_READY_FOR_CORRESPONDENCE: "Eksik veya geçersiz bilgiler tamamlanmadan taslak oluşturulamaz.",
    INVALID_RESPONSE_SCHEMA: error.message,
  };
  return messages[error.code] ?? error.message;
}

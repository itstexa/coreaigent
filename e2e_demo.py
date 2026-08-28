# -*- coding: utf-8 -*-
"""Drive one fresh petition through F-01..F-06 and report every stage."""
import json, os, time, urllib.request, uuid

DB = os.environ["DATABASE_URL"]
import psycopg

TEXT = """DEMO BELEDİYE BAŞKANLIĞI'NA

Konu: Gürültü şikayeti

Binamızın altındaki eğlence mekânı her gece yarısından sonra yüksek sesle canlı müzik yayını yapmakta ve huzurumuzu bozmaktadır. Gürültü ölçümü yapılarak gerekli idari işlemin uygulanmasını talep ediyorum.

Gereğinin yapılmasını saygılarımla arz ederim.

--- BAŞVURU KÜNYESİ (yapılandırılmış veri) ---
applicant-name: Mehmet Demir
tckn: 10000000146
phone: 05321112233
incident-address: Cumhuriyet Mahallesi 8. Sokak No 3
incident-date: 27.08.2026
incident-description: Gece yarısından sonra canlı müzik sesi nedeniyle uyuyamıyoruz.

Dilekçe tarihi: 28.08.2026
Dilekçe kanalı: Vatandaş e-Dilekçe Portalı
"""

document_id = "e2e-" + uuid.uuid4().hex[:12]
body = {"schemaVersion": "2.0", "requestId": "req-" + document_id, "documentId": document_id,
        "sourceType": "text", "text": TEXT, "sourceMetadata": {}, "correlationId": "faz0-e2e"}
def post(url, payload, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


intake = post("http://ocr:8080/v1/ocr", body, 30)
print("F-01 intake:", intake.get("documentId"), "language=" + str(intake.get("language")), "status=" + str(intake.get("ingestStatus")))

# The frontend drives the synchronous intake graph: classify then validate.
classification = post("http://classification:8080/v1/classify", intake, 30)
print("F-02 classification:", classification.get("status"),
      (classification.get("requestType") or {}).get("id"), classification.get("confidence"))
validation = None
if classification.get("status") == "classified":
    for attempt in range(24):
        try:
            validation = post("http://validation:8080/v1/validate", classification, 60)
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (404, 409) or attempt == 23:
                raise
            time.sleep(0.5)
    print("F-03 validation:", validation.get("completionStatus"),
          "missing=" + str(len(validation.get("missingFields") or [])),
          "invalid=" + str(len(validation.get("invalidFields") or [])))

deadline = time.time() + 420
last = None
while time.time() < deadline:
    with psycopg.connect(DB) as db:
        row = db.execute("""
            SELECT s.state, cl.request_type_id, cl.confidence, cl.status, v.completion_status,
                   g.generation_status, g.source_status, g.result_status, g.correspondence_type,
                   jsonb_array_length(coalesce(g.regulation_suggestions,'[]'::jsonb)),
                   ro.route_kind, ro.target_unit_label, ro.routing_status,
                   (SELECT count(*) FROM notification_records n WHERE n.routing_id=ro.routing_id AND n.generation_status='completed')
            FROM intake_records r
            LEFT JOIN current_case_states s ON s.case_id=r.case_id
            LEFT JOIN current_classifications cl ON cl.document_id=r.document_id
            LEFT JOIN current_validation_states v ON v.document_id=r.document_id
            LEFT JOIN correspondence_generations g ON g.case_id=r.case_id
            LEFT JOIN routing_operations ro ON ro.case_id=r.case_id
            WHERE r.document_id=%s ORDER BY g.created_at DESC NULLS LAST LIMIT 1
        """, (document_id,)).fetchone()
    if row != last:
        print(f"  state={row[0]} class={row[1]}/{row[3]}({row[2]}) validation={row[4]} gen={row[5]}/{row[6]}/{row[7]} type={row[8]} citations={row[9]} route={row[10]}->{row[11]} {row[12]} notifications_done={row[13]}")
        last = row
    if row[0] in {"completed", "failed"}:
        break
    time.sleep(2)

with psycopg.connect(DB) as db:
    case_id, = db.execute("SELECT case_id FROM intake_records WHERE document_id=%s", (document_id,)).fetchone()
    g = db.execute("SELECT document_summary, draft_text, regulation_suggestions FROM correspondence_generations WHERE case_id=%s ORDER BY created_at DESC LIMIT 1", (case_id,)).fetchone()
print()
print("case_id:", case_id)
if g:
    print("summary:", g[0])
    print("draft:", (g[1] or "")[:700])
    for c in (g[2] or []):
        print(f"  cite {c.get('chunk_id')} {c.get('title')} {c.get('locator')} score={c.get('score'):.3f}" if c.get("score") is not None else f"  cite {c.get('chunk_id')}")

-- Synthetic operator-demo fixture. It deliberately contains no real people or
-- identifiers. Run only after an explicit demo reset; it preserves staff_members.
TRUNCATE TABLE
  learning_feedback, notification_jobs, notification_records, case_notifications,
  case_assignments, routing_jobs, routing_operations, correspondence_replays,
  correspondence_generation_jobs, correspondence_start_jobs, correspondence_generations,
  current_case_states, current_validation_states, current_classifications,
  durable_outbox_jobs, case_action_log, case_tickets, intake_records
  RESTART IDENTITY CASCADE;

DO $$
DECLARE
  item jsonb;
  fixture jsonb := $json$
  [
    {"slug":"noise-mehmet-01","name":"Mehmet Demir","type":"gurultu-sikayeti","label":"Gürültü Şikayeti","department":"zabita","department_label":"Zabıta Müdürlüğü","unit":"denetim","unit_label":"Denetim Birimi","text":"Gece gürültüsü ve canlı müzik nedeniyle rahatsızlık yaşıyorum. Denetim ve gürültü ölçümü yapılmasını talep ediyorum.","state":"completed","priority":"high","age":18,"aggression":"elevated","repeat":1},
    {"slug":"noise-mehmet-02","name":"Mehmet Demir","type":"gurultu-sikayeti","label":"Gürültü Şikayeti","department":"zabita","department_label":"Zabıta Müdürlüğü","unit":"denetim","unit_label":"Denetim Birimi","text":"Gece gürültüsü ve canlı müzik nedeniyle rahatsızlık yaşıyorum. Denetim ve gürültü ölçümü yapılmasını tekrar talep ediyorum.","state":"completed","priority":"normal","age":15,"aggression":"normal","repeat":2},
    {"slug":"noise-mehmet-03","name":"Mehmet Demir","type":"gurultu-sikayeti","label":"Gürültü Şikayeti","department":"zabita","department_label":"Zabıta Müdürlüğü","unit":"denetim","unit_label":"Denetim Birimi","text":"Gece gürültüsü ve canlı müzik nedeniyle rahatsızlık yaşıyorum. Denetim ve gürültü ölçümü yapılmasını üçüncü kez talep ediyorum.","state":"completed","priority":"high","age":11,"aggression":"elevated","repeat":3},
    {"slug":"noise-mehmet-04","name":"Mehmet Demir","type":"gurultu-sikayeti","label":"Gürültü Şikayeti","department":"zabita","department_label":"Zabıta Müdürlüğü","unit":"denetim","unit_label":"Denetim Birimi","text":"Gece gürültüsü ve canlı müzik nedeniyle rahatsızlık yaşıyorum. Denetim ve gürültü ölçümü yapılmasını dördüncü kez talep ediyorum.","state":"completed","priority":"normal","age":5,"aggression":"normal","repeat":4},
    {"slug":"noise-aylin-01","name":"Aylin Kaya","type":"gurultu-sikayeti","label":"Gürültü Şikayeti","department":"zabita","department_label":"Zabıta Müdürlüğü","unit":"denetim","unit_label":"Denetim Birimi","text":"İnşaat gürültüsü sabah erken saatlerde başlıyor. Rahatsızlığın incelenmesini istiyorum.","state":"waiting_for_user","priority":"normal","age":3,"aggression":"normal","repeat":1},
    {"slug":"payment-ayse-01","name":"Ayşe Yılmaz","type":"odeme-itirazi","label":"Ödeme İtirazı","department":"mali-hizmetler","department_label":"Mali Hizmetler Müdürlüğü","unit":"gelir-tahakkuk","unit_label":"Gelir ve Tahakkuk Birimi","text":"Ödeme ve vergi borcuma itiraz ediyorum. Haksız tahakkukun iptal edilmesini ve iade yapılmasını talep ederim.","state":"completed","priority":"high","age":17,"aggression":"elevated","repeat":1},
    {"slug":"payment-ayse-02","name":"Ayşe Yılmaz","type":"odeme-itirazi","label":"Ödeme İtirazı","department":"mali-hizmetler","department_label":"Mali Hizmetler Müdürlüğü","unit":"gelir-tahakkuk","unit_label":"Gelir ve Tahakkuk Birimi","text":"Aynı ödeme itirazım için tekrar yazıyorum; yanlış tahsilatın düzeltilmesini istiyorum.","state":"completed","priority":"normal","age":10,"aggression":"normal","repeat":2},
    {"slug":"payment-ayse-03","name":"Ayşe Yılmaz","type":"odeme-itirazi","label":"Ödeme İtirazı","department":"mali-hizmetler","department_label":"Mali Hizmetler Müdürlüğü","unit":"gelir-tahakkuk","unit_label":"Gelir ve Tahakkuk Birimi","text":"Ödeme itirazı başvurumda gerekli referans ve belge bilgilerini tamamlayamadım.","state":"waiting_for_user","priority":"normal","age":2,"aggression":"normal","repeat":3},
    {"slug":"license-zeynep-01","name":"Zeynep Arslan","type":"ruhsat-basvurusu","label":"Ruhsat Başvurusu","department":"imar-sehircilik","department_label":"İmar ve Şehircilik Müdürlüğü","unit":"ruhsat","unit_label":"Ruhsat Birimi","text":"Yeni bir kafe açmak için işyeri ruhsatı ve gerekli izin belgeleri hakkında başvuru yapıyorum.","state":"completed","priority":"normal","age":14,"aggression":"normal","repeat":1},
    {"slug":"license-zeynep-02","name":"Zeynep Arslan","type":"ruhsat-sorgusu","label":"Ruhsat Durum Sorgusu","department":"imar-sehircilik","department_label":"İmar ve Şehircilik Müdürlüğü","unit":"ruhsat","unit_label":"Ruhsat Birimi","text":"Ruhsat başvurumun hangi aşamada olduğunu ve sonucu ne zaman öğrenebileceğimi soruyorum.","state":"completed","priority":"normal","age":7,"aggression":"normal","repeat":2},
    {"slug":"address-ali-01","name":"Ali Çetin","type":"adres-bildirimi","label":"Adres Değişikliği Bildirimi","department":"vatandas-hizmetleri","department_label":"Vatandaş Hizmetleri Müdürlüğü","unit":"beyaz-masa","unit_label":"Beyaz Masa Birimi","text":"Yeni adresime taşındım. Adres değişikliği bildirimimin kayda alınmasını ve nüfus sisteminin güncellenmesini istiyorum.","state":"completed","priority":"normal","age":9,"aggression":"normal","repeat":1},
    {"slug":"system-selin-01","name":"Selin Öz","type":"sistem-erisim-arizasi","label":"Sistem Erişim Arızası","department":"bilgi-islem","department_label":"Bilgi İşlem Müdürlüğü","unit":"dijital-hizmetler","unit_label":"Dijital Hizmetler Birimi","text":"Kurum sistemine giriş yapamıyorum, şifrem kilitlendi ve uygulama açılmıyor. Arızanın giderilmesini rica ederim.","state":"completed","priority":"critical","age":4,"aggression":"elevated","repeat":1},
    {"slug":"esign-bora-01","name":"Bora Şahin","type":"e-imza-arizasi","label":"E-İmza Arızası","department":"bilgi-islem","department_label":"Bilgi İşlem Müdürlüğü","unit":"dijital-hizmetler","unit_label":"Dijital Hizmetler Birimi","text":"E-imza sertifikamla imzalama yapamıyorum; token ve kart okuyucu hata veriyor.","state":"waiting_for_user","priority":"high","age":6,"aggression":"normal","repeat":1},
    {"slug":"info-eda-01","name":"Eda Güneş","type":"bilgi-edinme","label":"Bilgi Edinme Talebi","department":"vatandas-hizmetleri","department_label":"Vatandaş Hizmetleri Müdürlüğü","unit":"beyaz-masa","unit_label":"Beyaz Masa Birimi","text":"2025 yılı faaliyet raporu ve ilgili istatistiklerin tarafıma belge olarak verilmesini talep ediyorum.","state":"completed","priority":"normal","age":13,"aggression":"normal","repeat":1},
    {"slug":"invoice-mavi-01","name":"Mavi Yapı Ltd.","type":"fatura-islemi","label":"Fatura İşlemi","department":"mali-hizmetler","department_label":"Mali Hizmetler Müdürlüğü","unit":"gelir-tahakkuk","unit_label":"Gelir ve Tahakkuk Birimi","text":"Mal ve hizmet faturamızın ödeme ve tahakkuk işleminin kontrol edilerek düzeltilmesini talep ediyoruz.","state":"completed","priority":"normal","age":8,"aggression":"normal","repeat":1},
    {"slug":"noise-kaan-01","name":"Kaan Yıldız","type":"gurultu-sikayeti","label":"Gürültü Şikayeti","department":"zabita","department_label":"Zabıta Müdürlüğü","unit":"denetim","unit_label":"Denetim Birimi","text":"Bar kaynaklı gece gürültüsü ve yüksek ses şikâyetimi iletiyorum; adres ve tarih bilgisini eklemeyi unuttum.","state":"waiting_for_user","priority":"high","age":1,"aggression":"elevated","repeat":1},
    {"slug":"safety-derya-01","name":"Derya Koç","type":"isyeri-denetimi","label":"İşyeri Denetim Bildirimi","department":"zabita","department_label":"Zabıta Müdürlüğü","unit":"denetim","unit_label":"Denetim Birimi","text":"İşyeri denetimi sırasında yangın riski ve mevzuata aykırı güvenlik eksikleri gördüm. Acil kontrol talep ediyorum.","state":"completed","priority":"critical","age":2,"aggression":"normal","repeat":1},
    {"slug":"manual-umut-01","name":"Umut Acar","type":"manual","label":"İnsan İncelemesi","department":null,"department_label":null,"unit":null,"unit_label":null,"text":"Bu başvuru sınıflandırma taksonomisinde karşılığı bulunmayan karmaşık bir konuyu içeriyor; yetkili incelemesi gerekiyor.","state":"needs_review","priority":"normal","age":1,"aggression":"normal","repeat":1},
    {"slug":"noise-mehmet-05","name":"Mehmet Demir","type":"gurultu-sikayeti","label":"Gürültü Şikayeti","department":"zabita","department_label":"Zabıta Müdürlüğü","unit":"denetim","unit_label":"Denetim Birimi","text":"Gece gürültüsü ve canlı müzik nedeniyle rahatsızlık yaşıyorum. Yeter artık; denetim ve gürültü ölçümü yapılmasını beşinci kez talep ediyorum.","state":"completed","priority":"high","age":0,"aggression":"high","repeat":5}
  ]
  $json$::jsonb;
  case_id uuid;
  workflow_id uuid;
  generation_id uuid;
  routing_id uuid;
  assignment_id uuid;
  notification_id uuid;
  fields jsonb;
  class_status text;
  completed jsonb;
  priority_score smallint;
  staff text;
BEGIN
  FOR item IN SELECT value FROM jsonb_array_elements(fixture) LOOP
    case_id := md5('coreaigent-demo-case-' || (item->>'slug'))::uuid;
    workflow_id := md5('coreaigent-demo-workflow-' || (item->>'slug'))::uuid;
    generation_id := md5('coreaigent-demo-generation-' || (item->>'slug'))::uuid;
    routing_id := md5('coreaigent-demo-routing-' || (item->>'slug'))::uuid;
    assignment_id := md5('coreaigent-demo-assignment-' || (item->>'slug'))::uuid;
    class_status := CASE WHEN item->>'type' = 'manual' THEN 'needs_review' ELSE 'classified' END;
    priority_score := CASE item->>'priority' WHEN 'critical' THEN 100 WHEN 'high' THEN 70 ELSE 40 END;
    completed := CASE WHEN item->>'state' = 'completed' THEN '["F-01","F-02","F-03","F-04","F-05"]'::jsonb ELSE CASE WHEN item->>'state' = 'waiting_for_user' THEN '["F-01","F-02"]'::jsonb ELSE '["F-01","F-02"]'::jsonb END END;
    fields := jsonb_build_object(
      'applicant-name', jsonb_build_object('value', item->>'name', 'confidence', 0.95),
      'tckn', jsonb_build_object('value', '10000000146', 'confidence', 1.0),
      'phone', jsonb_build_object('value', '05320000000', 'confidence', 1.0)
    );
    staff := CASE WHEN item->>'unit' IS NULL THEN NULL ELSE (item->>'unit') || '-operator-1' END;

    INSERT INTO intake_records(document_id,case_id,workflow_id,source_type,original_text,normalized_text,source_metadata,correlation_id,ingest_status,language,created_at,updated_at)
    VALUES ('demo-' || (item->>'slug'),case_id,workflow_id,'text',item->>'text',item->>'text',jsonb_build_object('fixture','competition-demo','synthetic',true),(item->>'slug'),'queued','tr',now() - ((item->>'age')::int * interval '1 day'),now());

    INSERT INTO current_classifications(document_id,case_id,workflow_id,status,department_id,department_label,unit_id,unit_label,request_type_id,request_type_label,confidence,taxonomy_version,classifier_version,classification_reason,updated_at)
    VALUES ('demo-' || (item->>'slug'),case_id,workflow_id,class_status,item->>'department',item->>'department_label',item->>'unit',item->>'unit_label',CASE WHEN class_status='classified' THEN item->>'type' ELSE NULL END,CASE WHEN class_status='classified' THEN item->>'label' ELSE NULL END,CASE WHEN class_status='classified' THEN 0.96 ELSE 0.44 END,'demo-belediyesi-v2','demo-semantic-v3',CASE WHEN class_status='classified' THEN 'Demo fixture: konu sinyalleri ve politika eşleşti.' ELSE 'Güven eşiği altında; insan incelemesi gerekli.' END,now());

    IF item->>'state' IN ('completed','waiting_for_user') THEN
      INSERT INTO current_validation_states(case_id,document_id,workflow_id,request_type_id,schema_version,accepted_fields,missing_fields,invalid_fields,completion_status,revision,updated_at)
      VALUES (case_id,'demo-' || (item->>'slug'),workflow_id,item->>'type','demo-belediyesi-fields-v1',fields,CASE WHEN item->>'state'='waiting_for_user' THEN '[{"id":"incident-address","label":"Olay adresi"}]'::jsonb ELSE '[]'::jsonb END,'[]'::jsonb,CASE WHEN item->>'state'='waiting_for_user' THEN 'missing_information' ELSE 'complete' END,1,now());
    END IF;

    INSERT INTO current_case_states(case_id,revision,state,completed_steps,last_error_code,priority_level,priority_score,priority_reason,updated_at)
    VALUES (case_id,1,item->>'state',completed,NULL,item->>'priority',priority_score,CASE item->>'priority' WHEN 'critical' THEN 'Güvenlik ve hizmet kesintisi sinyali' WHEN 'high' THEN 'Tekrarlanan veya etkisi yüksek başvuru' ELSE 'Öncelik sinyali bulunmadı' END,now() - ((item->>'age')::int * interval '1 day'));

    INSERT INTO case_tickets(case_id,ticket_reference,created_at)
    VALUES (case_id,'CA-' || upper(substr(replace(case_id::text,'-',''),1,8)),now() - ((item->>'age')::int * interval '1 day'));
    INSERT INTO case_action_log(case_id,action_type,actor,facts,occurred_at)
    VALUES (case_id,'state_projected','system',jsonb_build_object('revision',1,'state',item->>'state','completed_steps',completed,'last_error_code',NULL),now() - ((item->>'age')::int * interval '1 day'));

    IF item->>'state' = 'waiting_for_user' THEN
      INSERT INTO case_notifications(notification_id,case_id,source_case_revision,audience,kind,payload,created_at)
      VALUES (md5('demo-applicant-notice-' || (item->>'slug'))::uuid,case_id,1,'applicant','missing_information',jsonb_build_object('message','Dosyanızın ilerlemesi için eksik bilgileri tamamlayın.'),now() - ((item->>'age')::int * interval '1 day'));
    ELSIF item->>'state' = 'completed' THEN
      INSERT INTO correspondence_generations(generation_id,case_id,document_id,workflow_id,source_case_revision,request_type_id,department_label,unit_label,corpus_version,retrieval_config_version,prompt_schema_version,validated_fields,model_id,model_revision,generation_status,source_status,result_status,correspondence_type,document_summary,draft_text,regulation_suggestions,model_attempt_count,created_at,completed_at)
      VALUES (generation_id,case_id,'demo-' || (item->>'slug'),workflow_id,1,item->>'type',item->>'department_label',item->>'unit_label','demo-municipality-regulations-v2','municipality-rag-v1','f04-correspondence-v1',fields,'ai21labs/AI21-Jamba2-3B','525c6c8e1d9f5bddedfbdc1dbb0ade2df84230c9','completed','relevant_source_found','draft_ready','response_letter','Sentetik demo dosyası için incelenebilir taslak.', 'Başvurunuz değerlendirilmiş ve ilgili birime iletilmek üzere hazırlanmıştır. Nihai karar yetkili personeldedir.','[]'::jsonb,1,now() - ((item->>'age')::int * interval '1 day'),now() - ((item->>'age')::int * interval '1 day'));
      INSERT INTO routing_operations(routing_id,case_id,source_case_revision,source_generation_id,request_type_id,route_kind,target_department_id,target_department_label,target_unit_id,target_unit_label,taxonomy_version,routing_status,routing_reason,created_at,routed_at)
      VALUES (routing_id,case_id,1,generation_id,item->>'type','classified',item->>'department',item->>'department_label',item->>'unit',item->>'unit_label','demo-belediyesi-v2','routed',jsonb_build_object('policy','demo_fixture','aggression_level',item->>'aggression','repeat_count',(item->>'repeat')::int),now() - ((item->>'age')::int * interval '1 day'),now() - ((item->>'age')::int * interval '1 day'));
      INSERT INTO routing_jobs(job_id,case_id,source_case_revision,source_generation_id,state,attempt_count,created_at,updated_at)
      VALUES (md5('demo-routing-job-' || (item->>'slug'))::uuid,case_id,1,generation_id,'completed',1,now(),now());
      INSERT INTO case_assignments(assignment_id,case_id,source_case_revision,unit_id,request_type_id,staff_id,display_name,role,selection_reason,assignment_status,assigned_at,completed_at,created_at)
      VALUES (assignment_id,case_id,1,item->>'unit',item->>'type',staff,replace(initcap(replace(staff,'-',' ')),'Operator','Operatörü'),'operator',jsonb_build_object('policy',CASE WHEN (item->>'repeat')::int >= 3 OR item->>'aggression' IN ('elevated','high') THEN 'topic_resolution_rate' ELSE 'least_open_workload' END,'repeat_count',(item->>'repeat')::int,'aggression_level',item->>'aggression','aggression_score',CASE item->>'aggression' WHEN 'high' THEN 0.9 WHEN 'elevated' THEN 0.65 ELSE 0 END),'completed',now() - ((item->>'age')::int * interval '1 day'),now() - ((item->>'age')::int * interval '1 day'),now() - ((item->>'age')::int * interval '1 day'));
      INSERT INTO notification_records(notification_id,routing_id,audience,generation_status,payload,model_id,model_revision,attempt_count,created_at,completed_at)
      VALUES (md5('demo-notice-applicant-' || (item->>'slug'))::uuid,routing_id,'applicant','completed',jsonb_build_object('body','Başvurunuz ilgili birime iletilmiştir.'),NULL,NULL,1,now(),now()),(md5('demo-notice-unit-' || (item->>'slug'))::uuid,routing_id,'target_unit','completed',jsonb_build_object('body','Yeni bir demo dosyası incelenmek üzere kuyruğunuza eklendi.'),'ai21labs/AI21-Jamba2-3B','525c6c8e1d9f5bddedfbdc1dbb0ade2df84230c9',1,now(),now());
    END IF;
  END LOOP;
END $$;

-- Keep the UI demo reproducible and make the fixture self-describing.
COMMENT ON TABLE intake_records IS 'Includes synthetic competition demo fixture rows when seed_demo_cases.sql is used';

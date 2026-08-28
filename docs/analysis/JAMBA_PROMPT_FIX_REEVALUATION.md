# Jamba2-3B Turkish — Prompt Contract Fix + Golden Re-evaluation

**Run:** 2026-08-27  
**Model:** `linguai/Jamba2-3B-Turkish-SFT-v1`  
**Snapshot:** `5202214fe552041fc6dfe1e6486b61f75eb5fce0`  
**Golden:** `scenarios/golden-scenarios.json`, SHA-256 `625acb0837f93e44518fcf629b7876ed1d1e76fcc833b5743c64c5fe2f678a2e`  
**Decoder:** unchanged (`temperature=0.0`, `max_new_tokens=512`)  
**Prompt contract:** `prose-admin-v2`  
**Prompt hash:** `f14a9079caccde36fb4410d6f0080ceae41705e6e89079569f0db001d590cf64`

## FIX-001 — Bulunan prompt problemi

`/v1/generate` içinde `task` alanı doğrulanıyor, fakat model çağrısına yalnızca ham `prompt` ve varsa bağlam aktarılıyordu. Böylece modelden beklenen dönüşüm — kaynak metni inceleyip idari aksiyonu kısa resmi cevap olarak yazma — request contract'ta mevcut olsa da model prompt'unda yoktu.

Bu durum source repetition, gereksiz clarification, hatalı refusal ve resmi aksiyon yerine konu açıklaması üretilmesini açıklayan prompt confound'dur.

## FIX-002 — Uygulanan değişiklik

- Tek merkezi `build_prose_admin_prompt()` helper'ı eklendi.
- `task` ve task'a ait genel talimat `/v1/generate` prompt'una taşındı.
- Kaynak, bağlam, dönüşüm hedefi, grounding, refusal/clarification politikası ve kısa resmi çıktı sınırı açıklandı.
- Golden expected answer, birim adı veya beklenen action prompt'a eklenmedi.
- Action taxonomy evaluator tarafında tutuldu; model prompt'una enum listesi eklenmedi. Ön denemede enum listesinin model tarafından doğrudan cevap olarak yankılanabildiği görüldü.
- `prose-admin-v2` sürümü ve SHA-256 hash prompt içine yazıldı.
- Raw `/generate` structured workflow prompt'u değiştirilmedi.

## BASELINE-001 — Prompt fix öncesi

| Metrik | Baseline |
|---|---:|
| Golden case | 58 |
| Schema/contract valid | 58/58 |
| Non-empty | 58/58 |
| Exact golden draft | 0/58 |
| BGE-M3 mean | 0.644 |
| BGE-M3 `<0.60` | 19/58 |
| BGE-M3 `<0.70` | 38/58 |
| Task correctness | PASS 3, PARTIAL 19, FAIL 36 |
| F-03 structured extraction | PASS |
| F-04 structured correspondence | PASS |
| JSON repair | Gerekmedi |

Exact match kalite metriği olarak kullanılmadı; tüm beklenen cevaplar anlamca aynı tek metin olmak zorunda değildir.

## RESULT-001 — Prompt fix sonrası

| Metrik | Yeni run |
|---|---:|
| Golden case | 58/58 |
| Schema/contract valid | 58/58 |
| Non-empty | 58/58 |
| Exact golden draft | 0/58 |
| BGE-M3 mean | 0.691 |
| BGE-M3 `<0.60` | 9/58 |
| BGE-M3 `<0.70` | 31/58 |
| Task correctness | PASS 2, PARTIAL 9, FAIL 47 |
| Prose contract compliance | PASS 1, FAIL 57 |
| F-03 structured extraction | PASS |
| F-04 structured correspondence | PASS |
| JSON repair | Gerekmedi |

Manual task label, beklenen semantic action ile ham çıktının karşılaştırılmasıdır. `Schema/contract valid` JSON response contract'ını, `Prose contract compliance` ise kısa resmi action cevabı, grounding ve placeholder/clarification kurallarını ifade eder.

## DELTA-001 — Before/after

| Metrik | Delta | Yorum |
|---|---:|---|
| BGE-M3 mean | `+0.047` | Yardımcı metrik; kısa paraphrase/repetition bunu yükseltebildi |
| BGE `<0.60` | `-10` | Lexical/embedding iyileşmesi |
| BGE `<0.70` | `-7` | Lexical/embedding iyileşmesi |
| Exact match | `0` | Ana kalite metriği değil |
| Unnecessary clarification | `15 → 2` | Belirgin azalma |
| Direct input repetition | `11 → 29` | Belirgin regresyon; dönüşüm kabiliyeti hâlâ zayıf |
| Wrong action | `13 → 7` | Azalma |
| Unnecessary refusal | `7 → 5` | Azalma, fakat kritik örnekler kaldı |
| Unsupported claim | `1 → 6` | Kısa çıktıda dahi grounding ihlalleri kaldı |
| Semantic drift | `1 → 2` | Düşük BGE örneklerinde devam ediyor |
| Truncation | `1 → 0` | s58 template/truncation ortadan kalktı |
| Max generated output | 512 token sınırına ulaşmadı | Output-length policy etkili |

39 case'in BGE skoru yükseldi, 17'si düştü, 2'si aynı kaldı. Buna rağmen task PASS/PARTIAL toplamı `22 → 11` oldu. Sonuç: prompt contract confound'u kısmen azaldı, fakat source-to-administrative-action transformation gerçek ve sistematik bir capability gap olarak görünür hâle geldi. BGE artışı bu sonucu tersine çevirmiyor.

## RESULT-002 — Failure distribution

Primary/explicit manual labels; bir case birden fazla ikincil pattern taşıyabilir.

| Failure type | Yeni case sayısı | Temsilci case'ler |
|---|---:|---|
| `input_repetition` | 29 | s01, s04, s33, s51, s58 |
| `wrong_action` | 7 | s13, s18, s26, s47, s54 |
| `unnecessary_refusal` | 5 | s10, s15, s17, s32, s39 |
| `under_generation` | 5 | s42, s45, s48, s49, s50 |
| `wrong_decision` | 4 | s16, s21, s34, s35 |
| `unsupported_claim` | 6 explicit | s09, s13, s15, s19, s34, s35 |
| `unnecessary_clarification` | 2 | s22, s53 |
| `missing_required_fact` | 2 | s36, s57 |
| `semantic_drift` | 2 | s19, s23 |
| `over_generation` | 1 | s40 |
| `truncation` | 0 | — |

`unsupported_claim` ve `semantic_drift` ikincil sayımlardır; primary toplamına ayrıca eklenmez. BGE `<0.60` kalan case'ler: **s04, s05, s14, s17, s23, s32, s34, s40, s57**. Bunların ham çıktıları da okunarak sınıflandırıldı; yalnız skor eşiğiyle failure kararı verilmedi.

### Case-level semantic/contract summary

`actual_action` ham generation okunarak çıkarılmıştır; `Schema` sütunu JSON response contract'ıdır.

| # | Expected action | Actual action | BGE old → new | Task | Schema | Primary failure |
|---:|---|---|---:|---|---|---|
| 01 | route | repeat | 0.735 → 0.776 | FAIL | PASS | `input_repetition` |
| 02 | acknowledge/review | repeat | 0.689 → 0.683 | FAIL | PASS | `input_repetition` |
| 03 | request_missing_information | repeat | 0.612 → 0.638 | FAIL | PASS | `input_repetition` |
| 04 | record | repeat | 0.539 → 0.549 | FAIL | PASS | `input_repetition` |
| 05 | route | repeat | 0.550 → 0.594 | FAIL | PASS | `input_repetition` |
| 06 | route | repeat | 0.637 → 0.637 | FAIL | PASS | `input_repetition` |
| 07 | record | repeat | 0.603 → 0.639 | FAIL | PASS | `input_repetition` |
| 08 | route | repeat | 0.764 → 0.764 | FAIL | PASS | `input_repetition` |
| 09 | reject_unsupported | reject_unsupported | 0.829 → 0.815 | PASS | PASS | `unsupported_claim` |
| 10 | manual_review | refuse | 0.592 → 0.609 | PARTIAL | PASS | `unnecessary_refusal` |
| 11 | record | repeat | 0.706 → 0.824 | FAIL | PASS | `input_repetition` |
| 12 | route | repeat | 0.588 → 0.782 | FAIL | PASS | `input_repetition` |
| 13 | review | review-intent | 0.661 → 0.723 | PARTIAL | PASS | `wrong_action` |
| 14 | route | repeat | 0.556 → 0.585 | FAIL | PASS | `input_repetition` |
| 15 | request_missing_information | refuse | 0.670 → 0.665 | PARTIAL | PASS | `unnecessary_refusal` |
| 16 | route | wrong-state | 0.638 → 0.720 | FAIL | PASS | `wrong_decision` |
| 17 | record | refuse | 0.803 → 0.513 | FAIL | PASS | `unnecessary_refusal` |
| 18 | route | wrong-state | 0.530 → 0.649 | FAIL | PASS | `wrong_action` |
| 19 | review | policy | 0.705 → 0.671 | FAIL | PASS | `unsupported_claim` |
| 20 | route | repeat | 0.671 → 0.734 | FAIL | PASS | `input_repetition` |
| 21 | review | wrong-state | 0.715 → 0.734 | FAIL | PASS | `wrong_decision` |
| 22 | review | clarify | 0.663 → 0.759 | FAIL | PASS | `unnecessary_clarification` |
| 23 | manual_review | explain | 0.497 → 0.457 | FAIL | PASS | `semantic_drift` |
| 24 | record | repeat | 0.758 → 0.713 | FAIL | PASS | `input_repetition` |
| 25 | route | repeat | 0.616 → 0.604 | FAIL | PASS | `input_repetition` |
| 26 | reject_unsupported | refuse | 0.600 → 0.830 | PARTIAL | PASS | `wrong_action` |
| 27 | record | repeat | 0.676 → 0.794 | FAIL | PASS | `input_repetition` |
| 28 | route | repeat | 0.725 → 0.753 | FAIL | PASS | `input_repetition` |
| 29 | review | repeat | 0.714 → 0.845 | FAIL | PASS | `input_repetition` |
| 30 | review | repeat | 0.701 → 0.772 | FAIL | PASS | `input_repetition` |
| 31 | record | repeat | 0.569 → 0.692 | FAIL | PASS | `input_repetition` |
| 32 | route | refuse | 0.599 → 0.559 | FAIL | PASS | `unnecessary_refusal` |
| 33 | route | repeat | 0.407 → 0.622 | FAIL | PASS | `input_repetition` |
| 34 | review | wrong-state | 0.635 → 0.559 | FAIL | PASS | `wrong_decision` |
| 35 | record | wrong-state | 0.440 → 0.796 | FAIL | PASS | `wrong_decision` |
| 36 | request_missing_information | incomplete-missing | 0.840 → 0.730 | PARTIAL | PASS | `missing_required_fact` |
| 37 | route | repeat | 0.597 → 0.683 | FAIL | PASS | `input_repetition` |
| 38 | review | repeat | 0.627 → 0.694 | FAIL | PASS | `input_repetition` |
| 39 | manual_review | refuse | 0.723 → 0.646 | FAIL | PASS | `unnecessary_refusal` |
| 40 | route | meta | 0.663 → 0.552 | FAIL | PASS | `over_generation` |
| 41 | review | repeat | 0.669 → 0.780 | FAIL | PASS | `input_repetition` |
| 42 | route | request | 0.703 → 0.735 | FAIL | PASS | `under_generation` |
| 43 | manual_review | repeat | 0.533 → 0.608 | FAIL | PASS | `input_repetition` |
| 44 | record | repeat | 0.855 → 0.828 | FAIL | PASS | `input_repetition` |
| 45 | route | thank | 0.585 → 0.744 | FAIL | PASS | `under_generation` |
| 46 | thank | thank | 0.728 → 0.665 | PASS | PASS | — |
| 47 | route | under | 0.737 → 0.680 | FAIL | PASS | `wrong_action` |
| 48 | route | under | 0.716 → 0.757 | PARTIAL | PASS | `under_generation` |
| 49 | review | under | 0.619 → 0.676 | PARTIAL | PASS | `under_generation` |
| 50 | record | request | 0.730 → 0.715 | PARTIAL | PASS | `under_generation` |
| 51 | review | repeat | 0.500 → 0.663 | FAIL | PASS | `input_repetition` |
| 52 | manual_review | repeat | 0.439 → 0.665 | FAIL | PASS | `input_repetition` |
| 53 | route | clarify | 0.696 → 0.718 | FAIL | PASS | `unnecessary_clarification` |
| 54 | record | route-vague | 0.612 → 0.788 | PARTIAL | PASS | `wrong_action` |
| 55 | record | repeat | 0.727 → 0.806 | FAIL | PASS | `input_repetition` |
| 56 | manual_review | repeat | 0.519 → 0.609 | FAIL | PASS | `input_repetition` |
| 57 | request_missing_information | incomplete-missing | 0.581 → 0.594 | FAIL | PASS | `missing_required_fact` |
| 58 | route | repeat | 0.557 → 0.676 | FAIL | PASS | `input_repetition` |

## CASE-033

- **Old:** Evde enerji tasarrufu hakkında tavsiye verdi; beklenen ilgili birime yönlendirme yoktu.
- **New:** `Enerji tasarrufu önerisi sunuyorum.`
- **Expected action:** `route`
- **Prompt fix etkisi:** Semantic drift azaldı; BGE `0.407 → 0.622`, uzun ev içi tavsiye ortadan kalktı.
- **Remaining failure:** `input_repetition`, beklenen idari yönlendirme hâlâ yok.
- **Likely next action:** Targeted SFT ile öneri/başvuru metnini resmi route acknowledgement'a dönüştüren contrastive varyantlar.

## CASE-035

- **Old:** `Üzgünüm, bu durumda yardımcı olamam.`
- **New:** `Evrakın kayıtlı olduğunu bildiriyorum.`
- **Expected action:** Kayıp evrakı araştırılmak üzere `record`.
- **Prompt fix etkisi:** Hatalı refusal ortadan kalktı; BGE `0.440 → 0.796`.
- **Remaining failure:** Kaynakta bulunmayan “kayıtlı” durumunu iddia ediyor; araştırma/record aksiyonu açık değil.
- **Likely next action:** Missing-information kritik değilse işlem başlatma, state değişikliği ve unsupported fact negatif örnekleri.

## CASE-051

- **Old:** Diploma doğrulamasını yasa dışı/etik dışı ilan ederek reddetti.
- **New:** `Diploma doğrulaması talep ediliyor.`
- **Expected action:** Kayıtlar üzerinden `review`.
- **Prompt fix etkisi:** Hatalı refusal ve unsupported legal claim kaldırıldı; BGE `0.500 → 0.663`.
- **Remaining failure:** Task'ı yalnızca source repetition seviyesinde bıraktı; inceleme aksiyonu yok.
- **Likely next action:** Meşru doğrulama/inceleme ile gerçekten unsupported task polarity'sini birlikte öğreten SFT çiftleri.

## CASE-052

- **Old:** Sahtecilik şüphesini incelemek yerine etik ve güvenilirlik hakkında ilgisiz açıklama yaptı.
- **New:** `Belge sahteciliği şüphesi bulunmaktadır.`
- **Expected action:** Gizli `manual_review`.
- **Prompt fix etkisi:** Over-generation ve ilgisiz açıklama azaldı; BGE `0.439 → 0.665`.
- **Remaining failure:** Şüpheyi tekrar ediyor, gizli manuel inceleme aksiyonunu ifade etmiyor.
- **Likely next action:** Hassas görünen fakat meşru idari inceleme görevlerinde refusal yerine confidential routing/review üretme varyantları.

## CASE-058

- **Old:** Genel “Resmi Yazı” şablonu, tekrar eden `[Adresiniz]` placeholder'ları ve truncation.
- **New:** `Acil hukuki işlem talebi.`
- **Expected action:** Acil `route` to `Hukuk`.
- **Prompt fix etkisi:** Placeholder, genel dilekçe formatı ve truncation ortadan kalktı; BGE `0.557 → 0.676`.
- **Remaining failure:** Kaynak tekrar edildi; aciliyet ve Hukuk yönlendirmesi yok.
- **Likely next action:** Kısa tamamlanmış acknowledgement/routing biçimini ve source request ile response state farkını öğreten SFT.

## REGRESSION-001 — Structured workflow durumu

- F-03 gerçek Jamba extraction acceptance: **PASS**
- F-04 gerçek correspondence intake, JSON parse/schema/PII/legal guard: **PASS**
- F-04 processing observed ve `source_status=no_relevant_source`: **PASS**
- Structured workflow contract'larında değişiklik yapılmadı.

## CAP-001 — Korunacak kabiliyetler

- F-03 structured extraction ve rule-owned field koruması.
- F-04 structured correspondence JSON, schema validation, PII ve legal/source guard'ları.
- JSON response contract'ında 58/58 geçerlilik ve non-empty generation.
- Meşru unsupported belge refusal'ı (`s09`) ve teşekkür/acknowledgement davranışı (`s46`).
- Prompt sonrası placeholder, genel dilekçe şablonu ve truncation üretmeme davranışı.

## PROMPTREC-001 — Prompt vs SFT ayrımı

| Pattern | Sınıflandırma | Gerekçe |
|---|---|---|
| Request `task` alanının model prompt'una taşınmaması | `likely_prompt_issue` | Adapter'da deterministik olarak düzeltildi. |
| Clarification kararının `15 → 2` düşmesi | `likely_prompt_issue` + mixed | Policy açıklaştırması belirgin etki yaptı. |
| Refusal polarity'nin kısmen düzelmesi | mixed | Prompt etkisi var; s17/s32/s39 gibi sistematik örnekler SFT gap'i. |
| Source → action transformation | `likely_SFT_issue` | Prompt görünür olduktan sonra direct repetition `29` case'e çıktı. |
| BGE artıp task correctness'in düşmesi | `likely_evaluator_issue` + mixed | Embedding lexical similarity action yokluğunu cezalandırmıyor. |
| F-03/F-04 structured generation | preserve | Gerçek structured acceptance değişmeden geçti. |

## DATAREC-001 — Targeted SFT mixture

Prompt fix sonrası görünen capability gap'lere göre öneri:

| Kategori | Ağırlık |
|---|---:|
| Official correspondence action/state transformation | 32% |
| Source repetition'i engelleyen instruction following | 22% |
| Refusal/decision polarity ve meşru inceleme | 14% |
| Clarification vs completion / missing information | 12% |
| Context grounding ve unsupported-claim avoidance | 10% |
| Extraction → response synthesis | 7% |
| Structured JSON regression-preservation examples | 3% |

Golden case veya yakın paraphrase'leri training'e koyma. Varyantlar aynı capability/task yapısını koruyup kurum, belge, state, action, eksik bilgi ve wording eksenlerinde ayrışmalı.

## EVALREC-001 — Minimal evaluator adjustments

- Exact match yalnız regression metriği olarak kalsın.
- BGE-M3 triage metriği olarak kalsın; ana kalite kararı olmasın.
- Her case için `expected_action`, `actual_action`, `task_correctness`, `contract_compliance` ayrı tutulmalı.
- Negation/approval/rejection/missing-information/state-change için binary assertions eklenmeli.
- `source_only_echo`, repeated placeholder, truncation, unnecessary clarification/refusal ve unsupported claim küçük deterministic checks olarak raporlanmalı.
- JSON schema validation ve F-03/F-04 evaluator'ı korunmalı; ağır yeni platform gerekmez.

## REGRESSION-002 — Verification record

- `17/17` Jamba service unit/acceptance tests: **PASS**
- CPU contract/service suite: **70/70 PASS**
- Docker image build: **PASS**
- `/ready`: model snapshot ile **200/ready**
- Development contract runner: **58/58 PASS**
- Golden raw artifact: `/tmp/coreaigent-golden-jamba-prompt-v2-final.jsonl`
- Golden scored artifact: `/tmp/coreaigent-golden-jamba-prompt-v2-scored.jsonl`
- Immutable baseline raw/scored artifactleri korunmuştur: `/tmp/coreaigent-golden-jamba.jsonl`, `/tmp/coreaigent-golden-jamba-scored-20260827.jsonl`

## DECISION-001 — SFT readiness

**Primary: `READY_FOR_TARGETED_SFT`**

Prompt confound deterministik olarak kaldırıldı; clarification, wrong action, refusal ve truncation pattern'lerinde kısmi iyileşme görüldü. Ancak kısa cevap üretimi çoğu case'te source repetition'a dönüştü ve semantic task PASS/PARTIAL toplamı arttı değil, `22 → 11` azaldı. Bu nedenle kalan problem yeni genel bir prompt wiring hatası olarak değil, hedefli SFT gerektiren source-to-action transformation, state/decision polarity ve official acknowledgement kabiliyeti olarak ele alınmalı.

Prompt contract tamamen etkisiz değildir; fakat tek başına yeterli değildir. F-03/F-04 regression göstermediği için structured workflow'lar korunarak targeted SFT hazırlanabilir.

## OQ-001 — Genuine open questions

Yok. Repository, mevcut config ve deterministik test sonuçları karar vermek için yeterliydi; kullanıcı girdisi gerektiren bir belirsizlik bırakılmadı.

Reference/eski model karşılaştırması yapılmamıştır. Model değiştirilmemiş, fine-tune başlatılmamış ve Golden Dataset değiştirilmemiştir.

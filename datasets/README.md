# Golden Dataset & Evaluation Pack

Bu klasör, CoreAIgent için değerlendirme amacıyla hazırlanan sabit ve tekrar üretilemez örnek setinin repo içi açıklamasını ve etiketleme sözleşmesini barındırır.

## Amaç

Ana veri kaynağı şudur:

- [../evaluation/golden_dataset_v0.1.json](../evaluation/golden_dataset_v0.1.json)

Bu set, Rule Engine, Retrieval ve final AI Pipeline çıktılarının aynı örnekler üzerinde karşılaştırılabilmesi için tasarlanmıştır. Model eğitimi hedefi taşımaz; yalnızca evaluation/test ve benchmark amaçlı kullanılır.

## Kapsam

- 20 kamu evrakı benzeri örnek
- 5 evrak türü dengeli dağılım: dilekçe, şikayet, bilgi talebi, başvuru formu, itiraz
- Her kayıtta:
  - `id`
  - `document`
  - `expected.document_type`
  - `expected.topic`
  - `expected.department`
  - `expected.critical_information`
  - `expected.missing_fields`
  - `expected.tags`

## Etiketleme (annotation) şeması

Aşağıdaki alanlar sabit kalır:

```json
{
  "id": "EVR-001",
  "document": "Tam evrak metni",
  "expected": {
    "document_type": "dilekçe",
    "topic": "Kısa konu özeti",
    "department": "Hedef müdürlük",
    "critical_information": ["anahtar bilgi 1", "anahtar bilgi 2"],
    "missing_fields": ["eksik alan 1"],
    "tags": ["etiket-1", "etiket-2"]
  }
}
```

## Sabit evaluation split

Bu ilk sürüm için tek ve sabit değerlendirme seti kullanılmaktadır:

- `evaluation` split: tüm 20 kayıt
- `train` / `validation` / `test` split: bu sürümde kullanılmaz

Bu yaklaşım, erken benchmark ve doğru hata ayıklaması için uygun ve tekrar üretilebilir bir temel sağlar.

## Veri kaynağı ve güvenlik notu

- Veri sentetik/kurgusal kamu evrak örneklerinden oluşur.
- Gerçek kişisel veri, özel kimlik bilgisi veya canlı bireysel dosya içeriği kullanılmaz.
- Tüm örnekler güvenlik ve mevzuat açısından test amaçlıdır.

## Benchmark / doğrulama

Aşağıdaki komut ile dataset yapısı ve dağılımı doğrulanabilir:

```bash
python scripts/run_dataset_benchmark.py
```

Alternatif olarak dataset yolu açıkça verilebilir:

```bash
python scripts/run_dataset_benchmark.py --dataset evaluation/golden_dataset_v0.1.json
```

## Dosya referansları

- [../evaluation/golden_dataset_v0.1.json](../evaluation/golden_dataset_v0.1.json)
- [../evaluation/README.md](../evaluation/README.md)
- [../scripts/run_dataset_benchmark.py](../scripts/run_dataset_benchmark.py)

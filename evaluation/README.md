# Golden Test Dataset v0.1
## CoreAIgent Rule Engine & Retrieval Evaluation Seti

---

## 📋 Genel Bilgi

**Amaç:** Rule Engine, Retrieval ve Final AI Pipeline bileşenlerinin aynı örnekler üzerinde karşılaştırmalı test edilebilmesi için kaliteli ve manuel doğrulanmış kamu evrakı dataset'i.

**Kullanım:** Evaluation/Testing (model eğitimi değil)

**Format:** JSON

**Toplam Kayıt:** 20 adet (5 tür x 4 örnek)

**Versiyon:** 0.3 (Hybrid ambiguity format)

---

## 📊 Dataset Dağılımı

### Evrak Türlerine Göre (5 tür, her biri 4 örnek)

| Tür | Sayı | Örnekler | 
|-----|------|----------|
| **Dilekçe** | 4 | EVR-001, EVR-002, EVR-003, EVR-004 |
| **Şikayet** | 4 | EVR-005, EVR-006, EVR-007, EVR-008 |
| **Bilgi Talebi** | 4 | EVR-009, EVR-010, EVR-011, EVR-012 |
| **Başvuru Formu** | 4 | EVR-013, EVR-014, EVR-015, EVR-016 |
| **İtiraz** | 4 | EVR-017, EVR-018, EVR-019, EVR-020 |

### Hedef Müdürlüklere Göre

Farklı 10+ belediye müdürlüğü kapsanmıştır:
- Fen İşleri Müdürlüğü (4 örnek)
- Sosyal Hizmetler Müdürlüğü (4 örnek)
- Mali Hizmetler Müdürlüğü (2 örnek)
- Çevre Müdürlüğü (2 örnek)
- Zabıta Müdürlüğü (2 örnek)
- İmar ve Şehircilik Müdürlüğü (2 örnek)
- Kültür ve Turizm Müdürlüğü (2 örnek)
- Tarım Müdürlüğü, İnsan Kaynakları, Eğitim Müdürlüğü (birer örnek)

---

## 🔧 Veri Kalitesi & Yapısı

### Her Kayıtta Bulunması Gereken Alanlar

```json
{
  "id": "EVR-XXX",                           // Unique identifier
  "document": "Tam metin...",                // Gerçek hayat senaryosu
  "expected": {
    "document_type": "dilekçe|şikayet|...", // 5 tür
    "topic": "Parkta engelli erişimi...",   // Konu özeti
    "primary_department": "Fen İşleri...",  // Ana birim (her zaman)
    "related_departments": [...],            // İlgili birimler (opsiyonel)
    "critical_information": [...],           // Anahtar veriler
    "missing_fields": [...],                 // Talep edilen ama verilmeyen
    "tags": [...],                           // Etiketler
    "ambiguity_notes": "...",                // Ambiguity açıklaması (varsa)
    "acceptance_criteria": "..."             // Test kriterleri (ambiguous örneklerde)
  }
}
```

### Kritik Tanımlar

#### **missing_fields**
- **Tanım:** Talep edilmiş fakat sağlanmamış/eksik olan bilgiler
- **Örnek:** Telefon numarası sorulmuş ama verilmemiş → "Telefon" eklenecek
- **Kural:** Belgeler 'Ek:' kısmında açıkça belirtilmişse missing_fields'a eklenmiyor

#### **critical_information**
- Kayıttan çıkarılması gereken anahtar veriler
- Birim routing'i için gerekli bilgiler
- Şikayet/talep/başvurunun özünü oluşturan fakta

#### **Ambiguity Handling (v0.1)**
- **primary_department:** Ana hedef birim (tercih sırası 1)
- **related_departments:** Eşit/yarı derecede uygun birimler (tercih sırası 2+)
- **ambiguity_notes:** Neden ambiguous olduğunun detaylı açıklaması
- **acceptance_criteria:** Hangi cevaplar test için "doğru" sayılacağı

---

## 🎯 Zorluk Seviyeleri

### 1. **Easy - Keyword Matching** (4 örnek)
Rule Engine'in temel pattern matching yeteneklerini test eder:
- EVR-001: Park + engelli → Fen İşleri (95% confidence)
- EVR-005: Çöp konteyneri → Çevre (95% confidence)
- EVR-007: Kaldırım + kazı → Fen İşleri (95% confidence)
- EVR-013: Sera + çiftçi → Tarım (95% confidence)

**Beklenti:** Keyword-based retrieval'ın %100 başarı oranı

---

### 2. **Moderate - Context Understanding** (11 örnek)
Context ve domain anlayışını gerektirir:
- EVR-002: Sulama kanalı (kırsal context gerekli)
- EVR-003: Yaşlı + bakım (multifactoral assessment)
- EVR-004: Kütüphane saatleri (hizmet yönetimi)
- EVR-009: Mali harcamalar (bilgi talebi routing)
- EVR-010: Ruhsat durumu sorgusu (durum talebi)
- EVR-011, EVR-012: Bilgi talepleri (spesifik koşullar)
- EVR-014: Staj başvurusu (İK)
- EVR-016: Sosyal yardım (gelir belgesi)
- EVR-017: Park cezası itirazı (sınırlı bilgi)
- EVR-019: Su faturası itirazı (teknik)

**Beklenti:** Retrieval ranking'in %80+ doğruluk oranı

---

### 3. **Hard - Ambiguous Multi-Department** (3 örnek)
İkili/çoklu birim uygunluğu, ranking ve priority testi:

#### **EVR-006: Gece Gürültüsü**
```json
"primary_department": "Zabıta Müdürlüğü",
"related_departments": ["Sosyal Hizmetler Müdürlüğü"],
"ambiguity_notes": "Gürültü şikayeti Zabıta'nın doğrudan sorumluluğu 
olup ceza uygulamadır. Uyku bozukluğu sonuçları Sosyal Hizmetler 
açısından da ilgili olabilir (sağlık danışmanlığı)..."
```
**Test amacı:** Zabıta'yı primary olarak seçip ranking yapabilir mi?

---

#### **EVR-008: Hava Kirliliği & Duman**
```json
"primary_department": "Çevre Müdürlüğü",
"related_departments": ["İmar ve Şehircilik Müdürlüğü"],
"ambiguity_notes": "Hava kirliliği Çevre'nin doğrudan sorumluluğu...
Ancak kaynağın belirsiz olması ve illegal imalathane ihtimali 
nedeniyle İmar de kaynak tespit açısından ilgili olabilir..."
```
**Test amacı:** Çevre'yi primary tutamaz mı?

---

#### **EVR-020: Burs İtirazı**
```json
"primary_department": "Eğitim Müdürlüğü",
"related_departments": ["Sosyal Hizmetler Müdürlüğü"],
"ambiguity_notes": "Burs ret kararı Eğitim'e ait... Gelir ve ekonomik 
durum değerlendirmesi Sosyal Hizmetler de yapabilir..."
```
**Test amacı:** Eğitim'i birincil olarak belirleyebilir mi?

**Beklenti:** Primary %90+, related (doğru ikinci cevap) %50+ tanınması

---

## 🔍 Test Senaryoları

### Senaryo 1: Rule Engine (Basit Pattern Matching)
**Test Set:** EVR-001, EVR-005, EVR-007, EVR-013

```python
# Rule: "çöp konteyneri" + "boşaltılmadı" → Çevre Müdürlüğü
# EVR-005 test et: 
# Input: "Çınar Mahallesi Pazar Yolu'ndaki çöp konteynerleri..."
# Expected: "Çevre Müdürlüğü"
# Success: Exact match
```

**Metrik:** Precision, Recall

---

### Senaryo 2: Retrieval & Ranking (Multi-Document)
**Test Set:** Tüm 20 örnek

```python
# Query: "park bakımı"
# Retrieved: EVR-001 (park + erişim), 
#            EVR-004 (kütüphane),
#            EVR-009 (park bakım harcamaları)
# Expected Ranking: EVR-001 > EVR-009 >> EVR-004
```

**Metrik:** MRR (Mean Reciprocal Rank), NDCG

---

### Senaryo 3: Ambiguity Handling (Pipeline End-to-End)
**Test Set:** EVR-006, EVR-008, EVR-020

```python
# EVR-006: Gürültü şikayeti
# System output: "Zabıta Müdürlüğü" (Primary) ✅
#                "Sosyal Hizmetler" (Related) ✅
# 
# Evaluation:
# - Primary department match: +1
# - Related department identified: +0.5
# - Ranking correct: +0.5
```

**Metrik:** F1-Score (primary), Recall@2 (related)

---

### Senaryo 4: Missing Fields Detection
**Örnekler:** EVR-002, EVR-004, EVR-006, EVR-008, EVR-010, EVR-012, EVR-020

```python
# EVR-004: Telefon yok
# System output: missing_fields = ["Telefon"]
# ✅ Correct

# EVR-015: Belgeler eklendi
# System output: missing_fields = []
# ✅ Correct (v0.1'den fix)
```

**Metrik:** Precision, Recall

---

## 📈 Beklenen Sonuçlar (Baseline)

| Sistem | Easy (4) | Moderate (11) | Ambiguous (3) | Ortalama |
|--------|----------|---------------|---------------|----------|
| Rule Engine | 95% | 60% | 40% | ~70% |
| Retrieval | 98% | 85% | 70% | ~85% |
| Full Pipeline | 96% | 88% | 80% | ~88% |

---

## 🐛 v0.1 → v0.1 Bug Fixes

### Issue 1: Inconsistent Ambiguity Handling
**Problem:** `department` tekil, `tags` çoklu, `ambiguity_notes` belirsiz
```json
// v0.1 (yanlış)
"department": "Zabıta Müdürlüğü",
"tags": ["zabıta", "sosyal_hizmetler"],
"ambiguity_notes": "...de eşlik eden birim olarak görülebilir"
```

**Çözüm:** Hybrid format
```json
// v0.1 (doğru)
"primary_department": "Zabıta Müdürlüğü",
"related_departments": ["Sosyal Hizmetler Müdürlüğü"],
"acceptance_criteria": "Zabıta birincil; Sosyal Hizmetler ikincil..."
```

### Issue 2: Missing Fields Inconsistency
**Problem:** EVR-015, EVR-018'de belgeler eklendi ama `missing_fields` hala boş değildi

**Çözüm:** "Ek:" belirtilen belgeler `missing_fields`'dan çıkarıldı

### Issue 3: Tag vs Department Mismatch
**Problem:** `tags`'te "imar" varken `department`'te yok (EVR-008)

**Çözüm:** `related_departments` alanı oluşturuldu, tags'te tüm ilgili birimler tutuldu

---

## 📝 Kullanım Örneği

### Python (Evaluation)
```python
import json

with open('golden_dataset_v0.1.json') as f:
    dataset = json.load(f)

for record in dataset['records']:
    evr_id = record['id']
    doc = record['document']
    primary = record['expected']['primary_department']
    related = record['expected'].get('related_departments', [])
    missing = record['expected']['missing_fields']
    
    # Test et
    system_output = your_model.classify(doc)
    
    # Evaluate
    if system_output == primary:
        print(f"✅ {evr_id}: {primary}")
    elif system_output in related:
        print(f"⚠️ {evr_id}: {system_output} (Related - ikincil)")
    else:
        print(f"❌ {evr_id}: {system_output} (Expected {primary})")
```

---

## 🎓 Dataset Quality Checklist

- ✅ 20 adet kaliteli kayıt
- ✅ 5 evrak türü, 10+ hedef birim
- ✅ Tüm kayıtlar manuel doğrulanmış
- ✅ Metin Sentetik değil (gerçekçi kamu evrakı stili)
- ✅ Ambiguity deliberate ve dokümante
- ✅ Missing fields tanımı açık ve konsistent
- ✅ Test senaryoları tanımlanmış
- ✅ Baseline beklentileri realistik
- ✅ Tekrarlı kayıt yok
- ✅ JSON format valid ve temiz

---
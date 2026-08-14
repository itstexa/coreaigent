# Rule Engine

Bu modül, evrak metnini yapay zekâ kullanmadan basit kurallarla analiz eder.
Amaç final karar üretmek değildir. Aynı metin için Rule Engine ve ilerideki AI
Pipeline sonuçlarını karşılaştırmak için bir başlangıç (baseline) sağlar.

## Ne yapar?

Bir evrak metni verildiğinde aşağıdaki bilgileri üretir:

- Evrak türü: dilekçe, şikayet, bilgi talebi, başvuru formu veya itiraz
- Önerilen müdürlük/birim
- Eksik zorunlu alanlar
- Konuya uygun mevzuat önerileri
- Resmî yazı türü ve basit yazı taslağı

## Kullanım

```python
from services.rules.engine import analyze_with_rules

document_text = "Şikayet: Fabrika dumanı çevre kirliliğine neden oluyor."
result = analyze_with_rules(document_text)

print(result["recommended_department"])
# Çevre Müdürlüğü
```

`result` aşağıdaki alanları içerir:

```python
{
    "document_type": "şikayet",
    "document_type_score": 0.28,
    "purpose": "Şikayet: Fabrika dumanı çevre kirliliğine neden oluyor",
    "recommended_department": "Çevre Müdürlüğü",
    "department_score": 0.40,
    "missing_fields": ["Ad Soyad", "Adres", "Telefon"],
    "legislation_suggestions": ["Çevre Kanunu"],
    "draft_type": "Resmi Yazı",
    "draft": "..."
}
```

Sonuç yalnızca `str`, `float` ve `list` gibi JSON'a dönüştürülebilen değerler
içerir. Bu nedenle doğrudan `json.dumps(result)` kullanılabilir.

## Skorlar ne anlama gelir?

`document_type_score` ve `department_score` **confidence/olasılık değildir**.
Bu değerler yalnızca metinde ilgili kuralın anahtar kelimelerinden ne kadarının
eşleştiğini gösteren heuristic skorlardır.

Örneğin `0.40`, sonucun yüzde 40 doğru olacağı anlamına gelmez. Bu sebeple
Rule Engine, AI çıktısının yerine geçmez; karşılaştırma ve doğrulama amacıyla
kullanılır.

## Testleri çalıştırma

Ek paket kurulumu gerekmez. Depo ana dizinindeyken çalıştırın:

```powershell
python -m unittest services.rules.test_rules -v
```

Testler; dilekçe, şikayet, bilgi talebi, başvuru formu ve itiraz örneklerini
kontrol eder.

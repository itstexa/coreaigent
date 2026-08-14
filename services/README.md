# Services

Bu klasör, CoreAIgent içindeki gerçek servislerin kodları için ayrılmıştır.
Her ekip üyesi geliştirdiği servisi burada kendi klasöründe tutar.

Örnek klasör yapısı:

```text
services/
├── ocr/             # Belgeden metin çıkarır
├── classification/  # Evrak türünü belirler
├── validation/      # Eksik alanları kontrol eder
├── rag/             # Mevzuat ve bilgi araması yapar
├── llm/             # Taslak veya yönlendirme üretir
├── workflow/        # Tüm adımları yönetir
└── rules/           # AI kullanmayan Rule Engine baseline modülü
```

Bir servis eklenirken ilgili klasörde en az bir `Dockerfile` bulunmalıdır.
Servisin hangi endpoint'i sunacağı ve hangi JSON formatını döndüreceği
`contracts/` klasöründeki sözleşmelere uygun olmalıdır.

Örneğin OCR servisi geliştiriliyorsa kod `services/ocr/` altında yer alır ve
`contracts/` içindeki OCR sözleşmesini uygular.

## Rule Engine

`services/rules/`, evrak metnini sabit kurallarla analiz eden bağımsız Python
modülüdür. Final AI çözümü değildir; ileride AI Pipeline sonuçlarıyla
karşılaştırma yapmak için kullanılır. Kullanım ayrıntıları için
[Rule Engine README](rules/README.md) dosyasına bakın.

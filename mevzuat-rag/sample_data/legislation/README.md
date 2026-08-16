# Örnek mevzuat verisi

Bu klasördeki metinler kamuya açık, resmi mevzuattır (kişisel veri veya
başvuru evrakı değildir).

## İçerik ve kaynak

- `3071_dilekce_kanunu.md` — 3071 sayılı Dilekçe Hakkının Kullanılmasına Dair
  Kanun, tam metin (11 madde + geçici madde 1). Kaynak:
  av-saimincekas.com üzerinden doğrulandı, 2026-08-16.
- `2646_resmi_yazisma_yonetmeligi_madde5.md` — Resmî Yazışmalarda
  Uygulanacak Usul ve Esaslar Hakkında Yönetmelik, yalnızca Madde 5 (kağıt
  boyutu/biçim kuralları). Kaynak: web araması sonucu doğrulanmış alıntı,
  2026-08-16.

## Neden sadece 2 belge, plandaki 5 değil

Bu geliştirme oturumunun çalıştığı sandbox ortamından `mevzuat.gov.tr` ve
`resmigazete.gov.tr`'ye doğrudan ağ erişimi kurulamadı (TLS/bağlantı hatası,
hem yerel HTTP client hem gerçek tarayıcı üzerinden denendi). Yasal bir
sistemde uydurma/doğrulanmamış kanun metni bulundurmak gerçek zarar riski
taşıdığından, yalnızca içeriği başka kaynaklardan tam ve doğrulanabilir
şekilde teyit edilebilen 2 belge eklendi. Kalan 3 belge (4982 sayılı Bilgi
Edinme Hakkı Kanunu, 6698 sayılı KVKK, 2577 sayılı İYUK seçili maddeler),
`mevzuat_rag/ingestion/mevzuat_gov_tr.py` konektörü normal internet erişimi
olan bir ortamda doğrulanıp çalıştırıldığında eklenmelidir — bkz. ana
`README.md` ve `NOTES.md`.

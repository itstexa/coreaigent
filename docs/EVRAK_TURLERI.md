# Desteklenecek Evrak Türleri (Görev 15 / 84 / 9)

Otonom karar (kamu kurumu evrak-yazışma alanı, `mevzuat-rag/sample_data`
içindeki 3071 sayılı Dilekçe Kanunu örneğiyle ve şartnamenin "üst yazı, cevap
yazısı, bilgilendirme metni" tanımıyla uyumlu):

| Evrak türü | Zorunlu alanlar | Önerilen birim yönlendirme sinyali |
|---|---|---|
| Dilekçe (genel) | ad-soyad, T.C./iletişim bilgisi, talep konusu, tarih | konu anahtar kelimeleri |
| Bilgi Edinme Başvurusu | başvuran kimliği, talep edilen bilgi/belge, gerekçe | ilgili birim + mevzuat maddesi |
| Şikâyet/İhbar Dilekçesi | şikâyet konusu, taraf bilgisi (varsa), tarih/yer | ilgili denetim/şikâyet birimi |
| İtiraz Dilekçesi | itiraz edilen karar/işlem referansı, gerekçe, süre bilgisi | ilgili karar merciini yönlendirme |
| Resmî Yazı / Üst Yazı (kurum-kurum) | gönderen/alan kurum, konu, referans sayı | ilgili muhatap birim |
| Başvuru Formu (yapılandırılmış) | form alanlarına göre değişken zorunlu alan seti | form türüne göre birim |

Her tür için zorunlu alan kuralları `services/classification/` içindeki
şema/kural dosyasında makine-okunabilir olarak tutulacak (Faz 4, Görev 82/84).

## Eksik bilgi senaryoları (Görev 10) — en az 3, test edilebilir

1. Dilekçede iletişim bilgisi eksik → sistem "eksik: iletişim bilgisi" uyarısı
   üretmeli, taslak üretimini durdurmadan kullanıcıya bildirmeli.
2. İtiraz dilekçesinde itiraz edilen karara referans yok → "eksik: referans
   numarası/tarih" uyarısı.
3. Şikâyet dilekçesinde taraf/olay tarihi belirtilmemiş → "eksik: tarih"
   uyarısı, düşük güven skoruyla işaretlenmeli.

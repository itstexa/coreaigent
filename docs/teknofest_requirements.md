# TEKNOFEST Yapay Zeka Dil Ajanları Yarışması — Senaryo 1 Gereksinimleri

Kaynak: [TEKNOFEST resmi şartname PDF](https://cdn.teknofest.org/media/upload/userFormUpload/2026_TYDA_SARTNAME_Birinci_Senaryo_TR_1_A8mT1.pdf)
(erişim: 2026-08-26). Görev 62'nin çıktısıdır.

## Tema

"Kamu Evrak ve Yazışma Süreçleri İçin Akıllı Agent Destek Sistemi" — CoreAIgent'in
kapsamıyla birebir örtüşüyor.

## Zorunlu iki görev (ikisi de tamamlanmalı, uçtan uca tek senaryo üzerinden
değerlendirilir — parça parça değil)

1. **Görev 1 — Evrak Sınıflandırma ve İçerik Analizi:** OCR/metin okuma, tür
   belirleme, önemli bilgi çıkarma, eksik bilgi tespiti, ilgili mevzuat/yazışma
   kuralı önerisi, kısa özet.
2. **Görev 2 — Resmî Yazı Taslaklama ve Birim Yönlendirme:** üst yazı/cevap
   yazısı/bilgilendirme taslağı, resmî üsluba uygunluk, birim yönlendirme
   önerisi, süreç bilgilendirmesi, gerekirse eksik bilgi talebi.

## Veri kullanımı

Gerçek kamu verisi **yasak**. Sadece açık kaynak metinler, kurgu evrak
örnekleri, sentetik resmî yazışma taslakları, kamuya açık mevzuat metinleri.

## Yöntem serbestisi

Model eğitmek zorunlu değil — açık kaynak modeller, hazır NLP araçları veya
ince ayarlı modeller kullanılabilir. Tek/çoklu agent mimarisi serbest.

## Puanlama (100 puan)

| Kriter | Puan |
|---|---|
| Yöntem ve Teknik Yaklaşım | 35 |
| Uygulama (sınıflandırma doğruluğu, yönlendirme başarımı, özet/taslak kalitesi, eksik bilgi tespiti) | 35 |
| Demo | 15 |
| Yenilikçilik, Özgünlük, Ticarileşme Potansiyeli | 15 |

## Final sunumu ve demo

- 15 dakika (10 dk sunum + 5 dk soru-cevap), sunum dosyası PDF+PPTX.
- Demo gerçek zamanlı veya kayıttan olabilir; kayıttansa jürinin canlı deneme
  talebine cevap verilebilmeli.
- **İnternet kesintisine karşı yedek plan tavsiye edilir** — runtime'da dış
  buluta bağımlı bileşenler (bkz. [TECH_DEBT.md](../TECH_DEBT.md)) demo günü
  risk.
- Türkçe metinler üzerinde çalıştığı gösterilmeli.

## Açık kaynak / lisans zorunluluğu

Geliştirilen kod ve veri kümeleri "Türkiye Açık Kaynak Platformu" GitHub
hesabında açık kaynak bir lisansla (Apache/MIT/GNU) paylaşılmalı.
**Doğrulanmadı:** mevcut `origin` (`github.com:itstexa/coreaigent`) bu
platformun hesabı mı, ayrı bir teslim/fork gerekiyor mu — teyit gerektirir.
`LICENSE` (Apache-2.0) bu görev kapsamında eklendi.

## Takvim (bilgi amaçlı — proje bu takvimden bağımsız, kalite odaklı ilerliyor)

Çevrimiçi süreç 27 Temmuz–26 Ağustos 2026, final 27–28 Ağustos 2026 (Bilişim
Vadisi Kocaeli). Kesin ve güncel tarihler için TEKNOFEST resmî sitesi esastır.

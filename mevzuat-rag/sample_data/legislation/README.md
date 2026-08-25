# Örnek mevzuat verisi

Bu klasördeki metinler kamuya açık, resmi mevzuattır (kişisel veri veya
başvuru evrakı değildir).

## İçerik ve kaynak

- `3071_dilekce_kanunu.md` — 3071 sayılı Dilekçe Hakkının Kullanılmasına Dair
  Kanun, tam metin (11 madde + geçici madde 1). Kaynak:
  av-saimincekas.com üzerinden doğrulandı, 2026-08-16.
- `offline_docs/6698_KVKK.txt` — 6698 sayılı Kişisel Verilerin Korunması
  Kanunu, tam metin (Madde 1-33 + geçici madde 1). Kaynak: mgm.adalet.gov.tr
  resmi PDF nüshası, WebFetch ile indirilip Read (PDF) aracıyla sayfa sayfa
  doğrulanarak transkribe edildi, 2026-08-26.
- `offline_docs/4982_Bilgi_Edinme.txt` — 4982 sayılı Bilgi Edinme Hakkı
  Kanunu, tam metin (Madde 1-33). Kaynak: tubimer.tubitak.gov.tr resmi PDF
  nüshası, aynı yöntemle doğrulandı, 2026-08-26.
- `offline_docs/Resmi_Yazismalarda_Uygulanacak_Usul_ve_Esaslar.txt` — 2646
  Karar Sayılı Resmî Yazışmalarda Uygulanacak Usul ve Esaslar Hakkında
  Yönetmelik (10 Haziran 2020, RG Sayı 31151), tam metin (Madde 1-39 +
  geçici madde 1). Kaynak: iidb.adalet.gov.tr resmi PDF nüshası, aynı
  yöntemle doğrulandı, 2026-08-26.

Bu 3 belge `offline_docs/metadata.json` ile eşleştirilir ve
`mevzuat_rag.ingestion.local_corpus.load_offline_docs()` üzerinden ağa hiç
çıkmadan indekslenir (air-gapped mod, bkz. `mevzuat_gov_tr.py` /
`resmi_gazete.py` içindeki `OFFLINE_MODE` kilidi).

**Not (2026-08-26):** Daha önce burada duran `2646_resmi_yazisma_yonetmeligi_
madde5.md` kaldırıldı — içeriği "Madde 5" diye etiketlenmiş kâğıt boyutu
kuralı, yürürlükteki (2020) yönetmeliğin gerçekte **Madde 6**'sına ait
(Madde 5 "Nüsha sayısı" başlıklıdır). Aynı kanun_no (2646) altında iki farklı
metin tutmak indekste çakışan/çelişen içerik üretiyordu; tam ve doğru metin
artık `offline_docs/Resmi_Yazismalarda_Uygulanacak_Usul_ve_Esaslar.txt`
içinde tek kaynak olarak duruyor.

## Kapsam

Demo kapsamındaki 4 belge (3071, 6698, 4982, 2646) resmi kaynaklardan
doğrulanmış tam metinlerdir. 2577 sayılı İYUK seçili maddeler henüz
eklenmedi — `mevzuat_rag/ingestion/mevzuat_gov_tr.py` air-gapped modda
kilitli olduğundan, gerektiğinde aynı doğrulama yöntemiyle (resmi PDF indir
→ Read ile sayfa sayfa oku → transkribe et) `offline_docs/` altına elle
eklenmelidir.

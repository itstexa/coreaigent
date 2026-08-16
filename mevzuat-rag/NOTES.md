# Notlar — DeepSeek ile RAG testi ve bulgular (2026-08-16)

## Amaç

Retrieval-only pipeline'ı (coreaigent'ta kurulmuştu) gerçek bir LLM'le
uçtan uca test etmek: retrieve edilen mevzuat parçalarından DeepSeek'e
atıflı, sadece kaynağa dayalı ("grounded") bir cevap ürettirmek ve
sonuçlara göre ayar yapmak.

## DeepSeek API key durumu

Ortamdaki (`DEEPSEEK_API_KEY` shell env var, `...4069`) key **geçersizdi**
(401 Authentication Fails). Makinedeki diğer projelerin `.env` dosyalarında
3 farklı DeepSeek key daha bulundu; ikisi (`~/.hermes/.env`,
`~/gptr-venv/.env`) çalışıyor, biri (`~/konya-imar/.env`) de geçersiz.
Bu projenin `.env`'i (gitignored, commit edilmedi) `~/.hermes/.env`'deki
çalışan key ile kuruldu. **Öneri:** hangi key'in "resmi" YAZGIT LinguAI /
kişisel kullanım için geçerli olduğunu teyit edin — ortamdaki eski/iptal
key'i güncelleyin ya da silin, karışıklığa yol açabilir.

## Test sonuçları (gerçek API çağrılarıyla, model=`deepseek-chat`, temperature=0.0)

| Soru | Beklenen davranış | Sonuç |
|---|---|---|
| "Dilekçede hangi bilgiler zorunludur?" | 3071 Madde 4'e atıfla doğru cevap | ✅ Doğru, [1]/[3] gibi referanslarla atıflandırılmış, hukuken tutarlı bir çıkarım yaptı (Madde 6.c'den "aksi halde incelenemez" sonucunu türetti — kaynakta zaten örtük olarak var) |
| "Resmi yazışmalarda kağıt boyutu nedir?" | 2646 Madde 5'e atıfla doğru cevap | ✅ Doğru, A4/A5 ölçüleri ve istisna doğru aktarıldı |
| "Elektronik ortamda güvenli elektronik imza nasıl atılır, hangi sertifika gerekir?" | Corpus'ta YOK → halüsinasyon üretmeden reddetmeli | ✅ Doğru reddetti: *"Verilen mevzuat parçalarında bu sorunun cevabı yok."* — uydurma bilgi üretmedi |

Üçüncü test özellikle önemli: bu bir **hukuki karar-destek** sistemi, yanlış
"kendinden emin" bir cevap üretmek gerçek zarar riski taşır. `SYSTEM_PROMPT`
(`generation.py`) açıkça "cevap yoksa uydurma, açıkça söyle" talimatı
içeriyor ve test bunun çalıştığını doğruladı.

## Yapılan ayarlar

- `temperature=0.0` — tutarlılık/atıf doğruluğu, yaratıcı varyasyondan daha
  önemli bu görevde.
- `config.qdrant_local_path` varsayılanı `/data/qdrant`'tan `./data/qdrant_local`'a
  değiştirildi — orijinal değer yalnızca Docker container içinde (mount
  edilmiş bir volume ile) anlamlıydı, host'ta izin hatası veriyordu.
- `RAGEngine.index_chunks` artık her chunk'ın `source_hash`'ini Qdrant'taki
  mevcut kayıtla karşılaştırıp değişmeyeni atlıyor — yeni dosya eklemek
  ucuz, tüm corpus'u yeniden embed etmiyor.

## Ölçülmedi / doğrulanmadı

- **Score threshold yok:** Düşük alaka skorlu (ör. 0.3 civarı) sonuçlar hâlâ
  LLM'e gönderiliyor; LLM kendi muhakemesiyle doğru reddetti ama bu
  garantili değil — ileride bir `min_score` eşiği (retrieve() sonuçlarını
  filtrelemek için) eklenebilir, özellikle corpus büyüyüp konu dışı ama
  yüksek skorlu sonuçlar çıkmaya başlarsa.
- Sadece 2 gerçek mevzuat belgesiyle test edildi (bkz. ana README'nin
  "Bilinen sınırlar" bölümü) — daha geniş/çeşitli bir corpus'ta faithfulness
  davranışı yeniden değerlendirilmeli.
- `deepseek-reasoner` (DeepSeek'in muhakeme modeli) denenmedi — daha karmaşık
  çok-maddeli sorularda `deepseek-chat`'ten daha iyi performans gösterebilir,
  ama maliyet/gecikme daha yüksek.

## Sonraki adımlar ("büyük projenin ilk adımı" için)

1. Gerçek internet erişimi olan bir ortamdan `mevzuat_gov_tr.py`'yi
   `mevzuat-mcp`'ye karşı doğrulayıp külliyatı genişletin (bkz. ana README).
2. `min_score` eşiği + boş/zayıf sonuç durumunda erken `ask()` reddi ekleyin
   (LLM çağrısı yapmadan önce).
3. LLM-as-judge ile daha büyük, sistematik bir faithfulness/hallucination
   değerlendirmesi kurun (bu notlardaki 3 sorudan fazlası — `eval/golden_set.jsonl`
   şu an yalnızca retrieval için, generation için ayrı bir eval seti yok).
4. Hangi DeepSeek key'in kalıcı olarak kullanılacağına karar verilip
   `.env.example`'da doğru talimatlarla belgelensin.

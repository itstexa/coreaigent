# Tech Debt

## RAG servisi: DeepSeek Cloud API bağımlılığı

Mevcut `mevzuat-rag/ask.py` (ve `mevzuat_rag/llm_client.py`) cevap üretimi için
`DEEPSEEK_API_KEY` ile DeepSeek Cloud API'ye çağrı atıyor. Bu, "Kapalı Ağ /
Air-Gapped" mimari hedefiyle çelişiyor: sistem çalışma zamanında internete
çıkıyor.

Jüri demosu öncesi bu kısmın da yerel `Jamba2-3B-Turkish` (veya yerel vLLM)
endpoint'ine yönlendirilmesi gerekecek.

Not: RAG servisinin iç mimarisi bu görev kapsamında değiştirilmedi
(`mevzuat-rag/` kutu olarak korunuyor); bu sadece bir takip notudur.

## RAG servisi: `retrieve()` da DeepSeek'e çıkıyor (sadece `ask()` değil)

Faz 5'te `services/llm/rag_connector.py`'yi gerçek `RAGEngine.retrieve()`
çağrısıyla test ederken görüldü: sadece kaynak getiren `retrieve()` (cevap
üretmeyen, `want_answer=False` olan) çağrısı bile pipeline'daki HyDE/
Multi-Query aşamaları yüzünden DeepSeek'e 2 kez ağ isteği atıyor. Yani
"air-gapped" ihlali sadece `ask()`'ın cevap üretim adımıyla sınırlı değil —
retrieval'in kendisi de sorgu genişletme için dış API'ye bağımlı.

## RAG + yerel LLM aynı GPU'da (8GB) birlikte çalışmıyor

`services/llm`'in Jamba2-3B-Turkish'i (~5.8GB VRAM) yüklüyken aynı süreçte
RAG'ın embedding modelini (`BAAI/bge-m3`) de yüklemeye çalışmak CUDA OOM'a
ve GPU belleğinin bozulup sonraki Jamba2 çağrılarının da çökmesine yol
açıyordu. Çözüm: `rag_connector.py` artık RAG'ı ayrı bir alt-process'te
(`subprocess`, kendi CUDA context'i) çağırıyor — bu, çökmeyi önlüyor ama
temel VRAM kapasitesi sorununu çözmüyor: bu geliştirme ortamındaki 8GB
kart, Jamba2 + bge-m3'ü aynı anda rahat barındıramıyor (embedding modeli
subprocess içinde de "yüklenemedi" hatası veriyor, muhtemelen kalan VRAM
yetersiz). `services/llm` bu durumda güvenli şekilde boş bağlam ile devam
ediyor (RAG kaynaksız da olsa taslak/yönlendirme üretmeye devam eder) —
ama gerçek demo günü mevzuat kaynaklı taslaklar için ya daha büyük
GPU/VRAM ayrımı ya da servislerin GPU paylaşımını sıraya koyan bir
mekanizma gerekecek.

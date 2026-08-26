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

# DEPLOY — yeni bir cihaza taşıma checklist'i

Geliştirme makinesi (GPU'lu) → edge cihaz → CPU-only sunucu arası, kod
değişmeden. Sırasıyla:

## 1. Repo'yu klonlayın ve profili seçin

```bash
git clone <repo> && cd mevzuat-rag
export RAG_PROFILE=cpu_only   # veya dev_gpu / edge / prod — bkz. config/*.yaml
```

## 2. Bağımlılıkları kurun

```bash
make setup
# eşdeğeri: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

CPU-only bir makinede `torch`'un CUDA wheel'ini indirmemek için (5x daha
büyük, gerekmiyor):

```bash
.venv/bin/pip install torch==2.12.0 --index-url https://download.pytorch.org/whl/cpu
```

## 3. `.env`'i doldurun

```bash
cp .env.example .env
# DEEPSEEK_API_KEY zorunlu (ask()/router/multi_query/hyde/crag için).
# QDRANT_URL boşsa embedded/local Qdrant kullanılır (DATA_DIR altında).
# DEVICE boş bırakılırsa resolve_device() otomatik seçer.
```

Offline/önceden-indirilmiş modelli bir cihazda: `HF_HOME` (veya
`config/*.yaml`'da `paths.models_dir`) modellerin önceden indirildiği cache
dizinine işaret etsin — internet erişimi olmadan da model yüklenebilsin.

## 4. `verify_env.py` çalıştırın — İLK komut bu olmalı

```bash
make verify-env
# eşdeğeri: python scripts/verify_env.py
```

Cihaz, VRAM (GPU'daysa), embedding modeli, Qdrant erişimi, embedding
boyutu, disk alanı kontrol edilir. Herhangi biri **FAIL** verirse, mesajdaki
talimatı uygulayıp tekrar çalıştırın — hiçbir kontrolü atlamayın.

## 5. Qdrant'ı ayağa kaldırın (remote mod kullanıyorsanız)

```bash
docker compose --profile cpu up qdrant -d
# ya da GPU makinede: docker compose --profile gpu up qdrant -d
```

Embedded/local mod kullanıyorsanız (küçük kurulumlar için yeterli) bu adımı
atlayın — `QDRANT_URL` boş bırakılır.

## 6. Corpus'u indeksleyin

```bash
make ingest
# eşdeğeri: python -m mevzuat_rag.ingest_pipeline
```

Farklı bir embedding modeline geçiyorsanız önce MIGRATION.md'yi okuyun —
`QdrantStore` uyumsuz bir index'i fail-fast ile tespit eder ama yine de
doğru koleksiyon adını seçmeniz gerekir.

## 7. Doğrulayın

```bash
make test               # pytest — tests/test_smoke_pipeline.py GPU'suz/API-key'siz geçer
make eval               # golden set Recall@K / MRR
make ask QUERY="Dilekçede hangi bilgiler zorunludur?"
```

`make eval`'da Recall@1/MRR skorları düşükse (bu cihazda farklı bir
embedding modeli/cihaz kullanılıyorsa), `mevzuat_rag/eval/run_ablation.py`
ile hangi aşamanın etkisini kaybettiğini görebilirsiniz:

```bash
python -m mevzuat_rag.eval.run_ablation
```

---

## Docker ile (tek komut)

```bash
docker compose --profile cpu up --build      # CPU
docker compose --profile gpu up --build      # GPU (NVIDIA Container Toolkit gerekir)
```

`data/` ve `models/` volume'leri kalıcıdır — container'ı yeniden
oluşturduğunuzda index/model cache'i kaybolmaz.

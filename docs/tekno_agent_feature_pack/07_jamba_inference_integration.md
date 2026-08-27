# F-07 - Jamba Yerel LLM Entegrasyonu

## Amaç

Resmî yazı, özet ve bildirim üretiminde kullanılacak Jamba modelini bu
repository'nin sabit `llm` servis sınırına bağlamak. Bu paket içinde Jamba
ayrı bir Compose servisi değildir; gerçek model, `llm` container'ının içinde
çalışır.

## Referans doğrulaması

İstenen `/media/serda/home_extra/projects/mamba` ve
`/media/serda/home_extra/projects/jamba` yolları bu çalışma alanında yoktur.
Karar aşağıdaki mevcut kardeş projelerin dosyalarından çıkarılmıştır; bunlar
HTTP kontratı değil, model/runtime referansıdır:

| Referans | Doğrulanan bilgi |
| --- | --- |
| `/media/serda/home_extra/projects/mamba-cpt-tr` | `torch 2.5.1+cu121`, `transformers 4.56.1`, `mamba-ssm 2.2.4`, `causal-conv1d 1.5.0.post8`; Jamba2 Turkish CPT yükleme yolu |
| `/media/serda/home_extra/projects/jamba-sft` | CUDA 12.1 Docker tabanı ve `torch 2.5.1+cu121`, `transformers 4.57.6`, `mamba-ssm 2.2.4`, `causal-conv1d 1.5.0.post8` pinleri |
| `/media/serda/home_extra/projects/santosvbasvuru/ai-worker/app/model_servers/jamba_server.py` | `serda-dev/Jamba2-3B-Turkish`, startup load, GPU/device ayarları, `/health`, `/generate`, `/generate-stream` |

`santosvbasvuru` sunucusu host process'i olarak `8091` portunu kullanır. Bu
repo'nun Docker içi canonical adresi ise `http://llm:8080`'dir; host'taki
`8091` adresi bu stack'e kopyalanmamalıdır.

## Bu repository'deki gerçek kontrat

| Endpoint | Kullanım | Hazır olma davranışı |
| --- | --- | --- |
| `GET /health` | Liveness | Process ayaktaysa `200`; model yüklemez |
| `GET /ready` | Readiness | Model/GPU hazır değilse `503`, hazırsa `200` |
| `POST /generate` | Minimal model API; yalnız `{ "prompt": "..." }` | Hazır değilse `503` |
| `POST /v1/generate` | `contracts/http/manifest.json` içindeki CoreAIgent kontratı | Hatalar `standard-error` envelope ile döner |

`/v1/generate` public contract adaptörü modelin department veya routing id'si
uydurmasına izin vermez; üretim çıktısını `draft` olarak döndürür ve
sınıflandırılmamış hedefi `manual_review` bırakır. F-03 extraction ile F-04/F-05
workflow worker'ları ise kullanıcıdan açık olmayan, kendi prompt/JSON doğrulama
katmanlarına sahip internal çağrıda minimal `/generate` kullanır. Routing kararı
deterministic workflow/taxonomy katmanına aittir.

## Model ve runtime kimliği

- Model: `ai21labs/AI21-Jamba2-3B` (upstream base model)
- Pinned revision: `525c6c8e1d9f5bddedfbdc1dbb0ade2df84230c9`
- Revision yalnızca 40 karakterlik lowercase commit SHA olabilir; `main`
  kullanılamaz.
- Yerel olarak eğitilmiş bir checkpoint denendi ve çıktı kalitesi nedeniyle
  reddedildi; pinned kimlik upstream repo'dur. Başka bir checkpoint
  kullanılacaksa cache bütünlüğü ve GPU smoke yeniden çalıştırılmalıdır.
- İki lane aynı modeli aynı kontrat arkasında sunar:
  - `BACKEND=transformers` (`compose.llm.yaml`): safetensors ağırlıkları
    container içinde CUDA üzerinde yüklenir; ağırlıklar image'a kopyalanmaz,
    `/var/cache/huggingface` kalıcı cache'tir.
  - `BACKEND=llama_cpp` (`compose.llm.gguf.yaml`): NVIDIA GPU'su olmayan
    hostlar için. Ağırlıkları host üzerindeki llama.cpp Vulkan sunucusu tutar
    (pinned `ai21labs_AI21-Jamba2-3B-Q8_0.gguf`, SHA-256 doğrulamalı);
    container yalnızca adapter'dır, GPU rezerve etmez ve torch içermez.

## Logical generation task'ları

Task adları workflow seviyesindedir; hepsi aynı Jamba inference lane'ini
kullanır. Mevcut ortak kontratın izin verdiği task'lar şunlardır:

| Workflow amacı | Contract task | Güvenlik sınırı |
| --- | --- | --- |
| Belge özeti | `summarize` | Yalnız verilen belge/context |
| Resmî yazı taslağı | `draft_reply` | Mevzuat kaynakları ve çıkarılmış alanlar context'e eklenir |
| Kullanıcı bildirimi | `draft_reply` | Prompt içinde `audience=user` ve doğrulanmış case state |
| Hedef birim bildirimi | `draft_reply` | Prompt içinde `audience=unit` ve stable routing ids |
| Routing önerisi | `route_document` | Nihai routing kararı model çıktısından alınmaz |

## Gerçek Jamba'yı Docker ile başlatma

Ön koşul: NVIDIA Container Toolkit, CUDA uyumlu GPU ve model snapshot'ını
içeren bir HF cache. Bu akış gerçek `services/llm` image'ını çalıştırır;
base Compose akışındaki mock servisleri gerçek model gibi sunmaz.

```bash
cp .env.example .env
export HF_CACHE_DIR=/media/serda/home_extra/hf-cache

docker compose -f compose.yaml -f compose.llm.yaml config --quiet
docker compose -f compose.yaml -f compose.llm.yaml up --build -d llm
docker compose -f compose.yaml -f compose.llm.yaml ps llm
curl http://localhost:8085/health
curl http://localhost:8085/ready
```

`/ready` model yüklenene kadar `503` döner. İlk yüklemede model indirmek
gerekiyorsa yalnızca cache hazırlama aşamasında `HF_HUB_OFFLINE=0` kullanın;
yarışma/offline çalıştırmada cache hazırken varsayılan `HF_HUB_OFFLINE=1`
kalmalıdır. Cache'i bind etmek istemeyen operatörler `HF_CACHE_DIR` değerini
vermezse Compose named volume `llm-hf-cache` kullanılır.

Contract smoke:

```bash
curl -X POST http://localhost:8085/v1/generate \
  -H 'content-type: application/json' \
  -d '{
    "schemaVersion":"2.0", "requestId":"req-demo",
    "documentId":"doc-demo", "workflowId":"wf-demo",
    "task":"summarize", "prompt":"Belgeyi Türkçe özetle.",
    "context":["Yalnız verilen metne dayan."]
  }'
```

### NVIDIA GPU'su olmayan host: GGUF lane

Ön koşul yoktur: NVIDIA Container Toolkit gerekmez. Önce host sunucusu:

```powershell
.\scripts\jamba-gguf-server.ps1 -Root D:\coreaigent
```

Script pinned llama.cpp build'ini ve pinned Q8_0 GGUF'u indirir, iki SHA-256
digest'ini de doğrular, pinlenmemiş artifact'ı sunmayı reddeder ve modeli
`http://0.0.0.0:8090` üzerinde servis eder. Container'lar ona
`host.docker.internal` üzerinden ulaştığı için tüm arayüzlere bind eder ve
llama-server varsayılan olarak authentication uygulamaz: Windows firewall
profilini Private tutun veya `-ApiKey <secret>` verip container tarafında aynı
değeri `LLAMA_API_KEY` olarak ayarlayın. Sonra lane'i başlatın:

```bash
docker compose -f compose.yaml -f compose.llm.gguf.yaml up --build -d llm
curl http://localhost:8085/ready
```

Adapter, upstream sunucu pinned `GGUF_FILE` dışında bir dosya sunuyorsa
başlamayı reddeder; sunucu yeniden başlatılırsa kendiliğinden tekrar bağlanır,
bu yüzden başlatma sırası önemli değildir. `/health` ve `/ready`, çalışmayı
gerçekten hangi lane'in sunduğunu `backend` alanında bildirir.

PowerShell wrapper ile aynı gerçek-LLM geliştirme akışı:

```powershell
.\scripts\coreaigent.ps1 dev llm
.\scripts\coreaigent.ps1 test development llm
```

İkinci komutun gerçek modeli test edebilmesi için GPU, cache ve `/ready=200`
gereklidir. Diğer servisler bu modda deterministic contract mock'larıdır.

## Failure contract

- GPU yok veya model yüklenemedi: `/health` canlı kalır, `/ready` `503` döner
  (`gpu_unavailable` CUDA lane, `model_not_ready` GGUF lane).
- Generation timeout: `504`, `category=timeout`, `retryable=true`.
- Model dependency/empty output: `502`, `category=dependency`.
- Geçersiz CoreAIgent payload: `400`, `category=validation`.
- LLM hatası routing state'ini silmez; notification/correspondence adımı
  retryable failure olarak işaretlenmelidir.

## Acceptance kriterleri

- Gerçek referans runtime pinleriyle `services/llm` image'ı build olur.
- `/ready`, model gerçekten yüklenmeden başarılı dönmez.
- `/generate` ve `/v1/generate` aynı singleton model instance'ını kullanır.
- CoreAIgent `/v1/generate` response/error şemaları geçerlidir.
- Dış ücretli API fallback'i yoktur; offline cache yoksa servis hazır olmaz.
- Routing deterministic state olarak korunur; yalnız generation-dependent adım
  başarısız olabilir.

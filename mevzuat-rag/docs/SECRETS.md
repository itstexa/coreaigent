# Secrets Yönetimi

2026-08-22 alt-ajan taramasında bulunan boşluk (bkz. `IMPROVEMENT_IDEAS.md`,
Güvenlik #4) ve o günkü oturumun kendi bulgusu: bu proje etrafında **10 farklı
DeepSeek API key'i** dosya sistemine saçılmış halde bulundu —
`~/.bashrc`, `~/.hermes/.env`, `~/gptr-venv/.env`, `~/konya-imar/.env`,
ve `.bash_history`'deki eski `ANTHROPIC_AUTH_TOKEN` denemeleri. Hepsi
API'ye karşı tek tek test edildi, **10/10 geçersiz** çıktı.

## Neden bu bir sorun

- Hangi key'in "resmi"/kullanımda olan olduğu belirsizleşiyor.
- Rotasyon (bir key'i iptal edip yenisini dağıtmak) imkânsız hale geliyor —
  kaç yerde kopyası olduğu bilinmiyor.
- Düz metin (`.env`, `.bashrc`) — dosya sistemine erişimi olan her şey
  (başka bir proje, bir script, bir yedekleme aracı) key'i okuyabilir.
- `.env` dosyaları gitignore'lu olsa bile (bu projede öyle, doğrulandı —
  `git log --all -p` taramasında hiç key commit edilmemiş), yerel
  dosya sistemindeki çoğalma başlı başına bir risk.

## Kısa vadeli öneri (bugün yapılabilir, key gerekmez)

1. **Tek kaynak:** `.env.example`'da net bir talimat — "DEEPSEEK_API_KEY'i
   yalnızca [platform.deepseek.com](https://platform.deepseek.com)
   hesabından direkt kopyala, başka bir projenin `.env`'inden değil."
2. Eski/kullanılmayan key'leri DeepSeek hesabından **iptal et** — hepsi
   zaten 401 döndüğüne göre muhtemelen zaten iptal edilmiş, ama teyit
   edilmeli.
3. `~/.bashrc`'deki `export DEEPSEEK_API_KEY=...` satırını kaldırıp yerine
   proje bazlı `.env` kullanmayı zorunlu kıl — global shell export'u,
   hangi projenin hangi key'i kullandığını izlemeyi imkânsızlaştırıyor
   (bu oturumda tam olarak bu yüzden karıştı: `.env`'e yazılan key
   hiç kullanılmadı, `RAGConfig.from_env()` sessizce `.bashrc`'deki
   global export'u okudu — bkz. rapor).

## Orta vadeli öneri (gelecek iş)

Gerçek bir secrets manager (1Password CLI, HashiCorp Vault, sops+age gibi)
— tek bir yerden okunan, rotasyonu tek noktadan yapılabilen, erişim logu
tutan bir çözüm. Bu depo ölçeğinde (tek geliştirici, tek proje) şu an
zorunlu değil ama proje/ekip büyüdükçe gerekli olacak.

"""PDF corpus loader — tasarım hedefi: ~1.000.000 PDF'lik bir dizini,
belleğe hepsini yüklemeden, kesintiden sonra kaldığı yerden devam ederek,
ve PII hiçbir zaman chunk/embedding/LLM sınırını geçmeden işleyebilmek.

Üç tasarım kararı, tam bu yüzden:

1. **Akış (streaming), liste değil.** ``iter_pdf_paths`` bir generator —
   ``Path.rglob`` zaten tembel, 1M dosya yolu asla aynı anda bellekte
   değil. ``load_pdf_corpus`` de bir generator — ``ingest_pipeline.run()``
   zaten dokümanları teker teker işliyor (bkz. ``load_fixtures``'ın yerini
   alması), o yüzden burada da hiçbir noktada tüm korpus RAM'e girmiyor.

2. **Checkpoint = devam edebilirlik.** 1M dosyalık bir koşu kesintiye
   uğrayacaktır (OOM, kapatma, hata) — sıfırdan başlamak günler kaybettirir.
   Checkpoint dosyası (JSONL) her işlenen yolu + ucuz bir parmak izi
   (boyut+mtime, tüm dosyayı yeniden okuyup hash'lemek 1M ölçekte pahalı)
   kaydeder; bir sonraki koşu değişmemiş dosyaları atlar.

3. **PII, worker'da, chunk'lanmadan önce redakte edilir.** Her worker
   process kendi PDF'ini okur → metni çıkarır → ``redact_pii`` uygular →
   yalnızca redakte edilmiş metni ana sürece döndürür. Ham (redakte
   edilmemiş) metin worker process'in dışına asla çıkmaz.

Kapsam dışı: taranmış/görüntü PDF'ler (OCR gerektirir, bu modülün işi
değil — bkz. coreaigent'ın ayrı ``ocr`` servisi), gerçek bir dağıtık kuyruk
(Celery/Kafka) — ``multiprocessing.Pool`` tek makinede yeterli, 1M dosyanın
birden fazla makineye dağıtılması ayrı bir ileri adım.
"""
from __future__ import annotations

import json
import logging
import multiprocessing
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from mevzuat_rag.ingestion.base import RawDocument
from mevzuat_rag.ingestion.normalize import normalize_whitespace
from mevzuat_rag.pii import redact_pii

logger = logging.getLogger(__name__)

# --- Tablo-farkında çıkarım: performans stratejisi -------------------------
#
# İlk denediğimiz yaklaşım BUYDU (ve işe YARAMADI — burada dürüstçe not
# ediyoruz): pypdf ile ucuza çıkar, sayfa metnini ucuz bir regex
# heuristiğinden geçir ("tab karakteri var mı, 3+ boşlukla hizalanmış
# sütun var mı, ardışık sayı+birim grubu var mı"), yalnızca işaretlenen
# sayfalar için pdfplumber'ın pahalı ``find_tables()``'ını çağır.
#
# BU HEURİSTİK, gerçek bir ÇİZGİLİ (ruled/bordered) tabloyu SESSİZCE
# KAÇIRIYOR — kamu evrakı ücret tarifelerinde en sık rastlanan tablo türü
# tam olarak bu. Sebep: pypdf, çizgilerle sınırlandırılmış bir tabloyu
# hizalama/boşluk bilgisi OLMADAN, hücre başına AYRI bir satır olarak
# (sütun-öncelikli sırada: "Sınıf", "a) Temel Başvuru", "b) Özel Başvuru",
# "Ücret", ...) çıkarıyor — ne sekme, ne 3+ boşluk, ne de aynı satırda
# birden fazla sütun. Yani heuristiğin aradığı SİNYALİN KENDİSİ pypdf
# çıkarımında hiç oluşmuyor (bkz. tests/test_table_aware_pdf.py'ye giden
# geliştirme sürecinde bulunan gerçek örnek: 3 sütunlu, çizgili bir tablo
# hiçbir heuristiği tetiklemedi). Bu, tam olarak bu modülün çözmeye
# çalıştığı sorunun ta kendisi (tablo hizalamasının pypdf'te kaybolması) —
# o yüzden "kaybolan hizalamaya bakarak tablo var mı anla" heuristiği
# temelden çelişkili: sinyal, tam da yakalamaya çalıştığımız arızanın
# içinde kayboluyor.
#
# Ayrıca ayrı ayrı ölçtük: tek başına ``find_tables()`` çağırmanın maliyeti
# ``extract_text()`` ile HEMEN HEMEN AYNI (30 sayfalık bir belgede ikisi de
# ~1.1s, pypdf'in ~0.1s'sine karşı, ~10x) — ikisi de pdfplumber'ın sayfa
# nesne grafiğini (char/rect/line) kurma maliyetine hakim, algoritmanın
# kendisi ucuz. Yani "önce ucuza tablo var mı diye sor" pdfplumber'IN KENDİ
# tespit fonksiyonuyla da YAPILAMAZ — sorgulamanın kendisi zaten tam
# maliyeti ödüyor.
#
# Sonuç: güvenilir bir ucuz ön-filtre YOK. Bu yüzden BASİT ve DOĞRU olanı
# seçtik (görev tanımının izin verdiği iki seçenekten ikincisi): her
# sayfayı pdfplumber ile işliyoruz, ~10x maliyeti kabul ediyoruz. Bunun
# kabul edilebilir olmasının nedeni: ingestion tek seferlik/toplu bir iş
# (checkpoint'li — değişmemiş dosyalar bir sonraki koşuda zaten atlanıyor,
# bkz. modülün üstündeki tasarım notu #2), sorgu (query) yolunda DEĞİL;
# bir tablonun sessizce düzleşmesi (fiyat/süre karışması gibi hukuki/mali
# sonuçları olabilir) 10x'lik bir toplu-işlem maliyetinden çok daha
# pahalıya mal olur.
def _table_row_to_markdown(row: list[str | None]) -> str:
    def _cell(value: str | None) -> str:
        # "\n" ve "|" hücre içinde olduğu gibi bırakılırsa Markdown satırını
        # bozar (kaçırılmamış bir "|" sütun sayısını değiştirir, "\n" satırı
        # ikiye böler) — ikisi de düzleştirilir/kaçırılır.
        return (value or "").replace("\n", " ").replace("|", "\\|").strip()

    return "| " + " | ".join(_cell(c) for c in row) + " |"


def table_to_markdown(rows: list[list[str | None]]) -> str:
    """pdfplumber'ın ``Table.extract()`` çıktısını (satır listesi, her hücre
    ``str | None``) satır-içine gömülebilir bir Markdown tabloya çevirir.

    Her satırın en başına "|" konur — bu YALNIZCA kozmetik değil, güvenlik
    önlemi: ``legal_structure_parser.py``'deki ``BENT_RE``
    (``^\\s*([a-zçğıöşü])\\)\\s*(.*)$``) yalnızca satırın EN BAŞINDA tek
    harf + ")" görürse eşleşiyor. Bir hücre "a) Temel" gibi bir bent harfiyle
    başlasa bile ("| a) Temel | ... |"), satırın gerçek ilk karakteri "|"
    olduğu için ``BENT_RE`` asla tetiklenmiyor — aynı mantık ``FIKRA_RE``
    (``(`` ile başlamalı) ve ``MADDE_RE`` için de geçerli. Bu, kod incelemesi
    değil, doğrudan bir testle kanıtlanıyor:
    ``tests/test_table_aware_pdf.py::TestBentFikraMisparse``.

    İlk satır başlık satırı olarak kullanılır (gerçekten anlamsal bir
    başlık olup olmadığından bağımsız — kamu evrakı tablolarında ilk satır
    zaten neredeyse hep başlıktır; bu bir yaklaşıklamadır)."""
    if not rows:
        return ""
    header = _table_row_to_markdown(rows[0])
    separator = "|" + "|".join(["---"] * len(rows[0])) + "|"
    body = [_table_row_to_markdown(row) for row in rows[1:]]
    return "\n".join([header, separator, *body])


def _extract_page_with_tables(page: "pdfplumber.page.Page") -> tuple[str, bool]:
    """Bir pdfplumber sayfasından, tabloları BULUNDUKLARI dikey bantta
    satır-içi Markdown olarak koruyarak metin çıkarır.

    Dokümante edilmiş yaklaşıklama (tam genel amaçlı reflow algılama kapsam
    dışı bırakıldı — aşırı mühendislik olurdu): tablolar, ``find_tables()``
    tarafından döndürülen bbox'ların üst (``top``) koordinatına göre
    sıralanıp aralarındaki metin ``page.crop(...)`` ile o dikey bant için
    kesilip alınıyor — yani sayfa TEK SÜTUNLU (üstten alta akan) kabul
    ediliyor. Kamu evrakı PDF'leri (mevzuat, ücret tarifeleri, personel
    listeleri) neredeyse her zaman tek sütunludur, bu yüzden bu ödünü kabul
    ettik. Çok sütunlu bir sayfada (ör. yan yana iki tablo, ya da metin ve
    tablo yan yana) bu yaklaşım metni tabloyla "aynı dikey bantta" görüp
    yanlış sırada verebilir — üretimde bunu fark edip düzeltmenin yolu:
    ``ChunkMetadata.contains_table`` zaten bu sayfanın maddesini işaretliyor
    (bkz. ``_looks_like_table_line``), yani en azından "bu chunk'ta sıra
    bozuk olabilir" sinyali kayıp değil."""
    tables = sorted(page.find_tables(), key=lambda t: t.bbox[1])
    if not tables:
        return page.extract_text() or "", False

    parts: list[str] = []
    cursor = 0.0
    for table in tables:
        top = max(table.bbox[1], cursor)
        if top - cursor > 0.5:
            band = page.crop((0, cursor, page.width, top))
            band_text = band.extract_text() or ""
            if band_text.strip():
                parts.append(band_text)
        parts.append(table_to_markdown(table.extract()))
        cursor = max(cursor, table.bbox[3])

    if page.height - cursor > 0.5:
        tail = page.crop((0, cursor, page.width, page.height))
        tail_text = tail.extract_text() or ""
        if tail_text.strip():
            parts.append(tail_text)

    return "\n".join(parts), True


@dataclass
class PdfIngestStats:
    seen: int = 0
    skipped_unchanged: int = 0
    extracted: int = 0
    failed: int = 0
    pii_redactions: int = 0


def iter_pdf_paths(root: Path) -> Iterator[Path]:
    """rglob tembel bir generator'dür — 1M dosyada bile tüm liste RAM'e girmez."""
    yield from root.rglob("*.pdf")


def _fingerprint(path: Path) -> str:
    """Tüm dosyayı hash'lemek yerine ucuz bir parmak izi: boyut+mtime.
    1M dosyada her birini baştan sona okumak (yalnızca 'değişti mi?' sorusu
    için) darboğaz olur; bu, o maliyeti kabul edilebilir bir hata payıyla
    (aynı saniyede aynı boyutta üzerine yazma gibi nadir durumlar) ortadan
    kaldırır."""
    stat = path.stat()
    return f"{stat.st_size}:{int(stat.st_mtime)}"


def _load_checkpoint(checkpoint_path: Path) -> dict[str, str]:
    if not checkpoint_path.exists():
        return {}
    done: dict[str, str] = {}
    with checkpoint_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") == "ok":
                done[row["path"]] = row["fingerprint"]
    return done


def _append_checkpoint(checkpoint_path: Path, row: dict) -> None:
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_pdf_text(path: Path) -> str:
    """PDF -> düz metin, tablo yapısını KORUYARAK: tespit edilen tablolar
    bulundukları konumda satır-içi Markdown (``| col | col |`` + ``|---|---|``
    ayırıcı satırı) olarak serpiştirilir, düz metnin sonuna atılmaz.

    Her sayfa pdfplumber ile işlenir (pypdf yalnızca şifre çözme kontrolü
    ve pdfplumber'ın tamamen başarısız olduğu nadir durumda geri dönüş
    yolu için kullanılıyor) — bunun neden "yalnızca tablo içeren sayfalarda
    pdfplumber kullan" gibi ucuz bir ön-filtreyle optimize EDİLEMEDİĞİ için
    bu modülün üstündeki "Tablo-farkında çıkarım: performans stratejisi"
    notuna bkz. (özet: denedik, gerçek çizgili tabloları sessizce
    kaçırıyordu — kaldırdık)."""
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        # Parolasız açmayı dene (bazı PDF'ler boş parolayla "encrypted" işaretli).
        reader.decrypt("")

    try:
        with pdfplumber.open(str(path), password="" if reader.is_encrypted else None) as pdf:
            parts = []
            for page in pdf.pages:
                page_text, _ = _extract_page_with_tables(page)
                parts.append(page_text)
    except Exception as exc:
        # pdfplumber'ın hata yüzeyi pypdf kadar öngörülebilir/tipli değil
        # (pdfminer tabanlı, çok çeşitli iç istisnalar fırlatabilir) —
        # burada zarifçe pypdf'in düz metnine geri dön: tablo yapısının
        # kaybolması, bu PDF'in TAMAMEN işlenememesinden her zaman daha
        # iyidir.
        logger.warning(
            "pdfplumber ile çıkarım başarısız oldu (%s): %s — pypdf'in düz metin çıkarımına "
            "geri dönüldü (bu belgede tablo yapısı KORUNMAYACAK)",
            path, exc,
        )
        parts = [page.extract_text() or "" for page in reader.pages]

    return normalize_whitespace("\n".join(parts))


def _process_one(path_str: str) -> dict:
    """Worker process'te çalışır: PDF -> metin -> PII redaksiyonu.
    Ham metin bu fonksiyonun dışına asla çıkmaz — yalnızca redakte edilmiş
    metin ve sayaçlar ana sürece dönüyor."""
    path = Path(path_str)
    try:
        raw_text = extract_pdf_text(path)
    except (PdfReadError, OSError, ValueError) as exc:
        return {"path": path_str, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    if not raw_text.strip():
        return {"path": path_str, "status": "failed", "error": "boş/çıkarılamayan metin (taranmış görüntü olabilir)"}

    redaction = redact_pii(raw_text)
    return {
        "path": path_str,
        "status": "ok",
        "fingerprint": _fingerprint(path),
        "text": redaction.text,
        "pii_counts": redaction.counts,
    }


def load_pdf_corpus(
    root: Path,
    checkpoint_path: Path,
    workers: int = 4,
    chunksize: int = 8,
) -> Iterator[RawDocument]:
    """1M-ölçekli PDF dizinini gezip her belge için redakte edilmiş bir
    ``RawDocument`` üretir. ``ingest_pipeline.run()`` bunu ``load_fixtures()``
    ile aynı şekilde ``for raw_doc in ...:`` ile tüketir — akış tek
    değişmeden kalır, sadece kaynak değişir."""
    done = _load_checkpoint(checkpoint_path)
    stats = PdfIngestStats()

    def _pending() -> Iterator[str]:
        for path in iter_pdf_paths(root):
            stats.seen += 1
            path_str = str(path)
            fp = _fingerprint(path)
            if done.get(path_str) == fp:
                stats.skipped_unchanged += 1
                continue
            yield path_str

    # "spawn", "fork" değil: ana süreç embedding modelini (PyTorch/CUDA) zaten
    # yüklemiş ve çoklu thread'li olabilir — CUDA sonrası fork() bilinen bir
    # kilitlenme/çökme kaynağıdır. Worker'lar zaten torch import etmiyor, o
    # yüzden spawn'ın küçük başlatma maliyeti (yeniden import) tercih edildi.
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(processes=workers) as pool:
        for result in pool.imap_unordered(_process_one, _pending(), chunksize=chunksize):
            if result["status"] != "ok":
                stats.failed += 1
                _append_checkpoint(checkpoint_path, {"path": result["path"], "status": "failed", "error": result["error"]})
                logger.warning("PDF atlandı (%s): %s", result["path"], result["error"])
                continue

            stats.extracted += 1
            stats.pii_redactions += sum(result["pii_counts"].values())
            _append_checkpoint(
                checkpoint_path,
                {"path": result["path"], "status": "ok", "fingerprint": result["fingerprint"]},
            )
            if result["pii_counts"]:
                logger.info("PII redakte edildi (%s): %s", result["path"], result["pii_counts"])

            stem = Path(result["path"]).stem
            yield RawDocument(
                kanun_no=stem,
                kanun_adi=stem,
                url=f"file://{result['path']}",
                raw_text=result["text"],
            )

    logger.info(
        "PDF korpus taraması bitti — görülen: %d, atlanan (değişmemiş): %d, "
        "çıkarılan: %d, başarısız: %d, redakte edilen PII alanı: %d",
        stats.seen, stats.skipped_unchanged, stats.extracted, stats.failed, stats.pii_redactions,
    )

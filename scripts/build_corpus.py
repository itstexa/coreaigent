# -*- coding: utf-8 -*-
"""Rebuild services/workflow/corpus.json as the v2 regulation build.

The v1 build carried one one-sentence chunk per source, which no petition query
could reach at the pinned 0.60 cosine threshold: the best score any real case
produced was 0.44, so every F-04 generation resolved `no_relevant_source` and
no case ever became routable.  v2 keeps the v1 source identities and adds the
article-level text a municipality actually answers with, plus one source per
uncovered request type.

Run from the repository root:  python scripts/build_corpus.py
"""
from __future__ import annotations

import io
import json
from pathlib import Path

CORPUS_VERSION = "demo-municipality-regulations-v2"
TARGET = Path(__file__).resolve().parents[1] / "services" / "workflow" / "corpus.json"

SOURCES: list[dict] = []


def source(source_id: str, title: str, source_type: str, url: str, items) -> None:
    """Append one regulation source with its article-level chunks."""
    chunks = []
    for index, (locator, text) in enumerate(items, 1):
        chunks.append({
            "chunk_id": f"{source_id}-chunk-{index:03d}",
            "locator": locator,
            "excerpt": text[:500],
            # The embedded text carries its own title and locator.  A bare
            # article sentence has no topical anchor, and BGE-M3 scores a
            # petition against it well below the relevance threshold without
            # one.
            "content": f"{title} {locator}. {text}",
        })
    SOURCES.append({
        "source_id": source_id,
        "title": title,
        "source_type": source_type,
        "official_source_url": url,
        "chunks": chunks,
    })


source("REG-001", "3071 sayılı Dilekçe Hakkının Kullanılmasına Dair Kanun", "law",
       "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.3071.pdf", [
    ("Madde 7", "Türk vatandaşlarının ve Türkiye'de ikamet eden yabancıların kendileriyle veya kamu ile ilgili dilek ve şikâyetleri hakkında yetkili makamlara yaptıkları başvuruların sonucu veya yapılmakta olan işlemin safahatı hakkında dilekçe sahiplerine en geç otuz gün içinde gerekçeli olarak cevap verilir. İşlem safahatının duyurulması hâlinde alınan sonuç ayrıca bildirilir."),
    ("Madde 4", "Yetkili makamlara verilen veya gönderilen dilekçelerde, dilekçe sahibinin adı, soyadı ve imzası ile iş veya ikametgâh adresinin bulunması gerekir. Bu bilgileri taşımayan dilekçeler incelenemez."),
    ("Madde 5", "Yetkili olmayan bir kamu kurumuna verilen dilekçeler, ilgili kuruma gönderilir ve bu durum dilekçe sahibine yazılı olarak bildirilir."),
])

source("REG-002", "5393 sayılı Belediye Kanunu", "law",
       "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.5393.pdf", [
    ("Madde 14", "Belediye, mahallî müşterek nitelikte olmak şartıyla imar, su ve kanalizasyon, ulaşım, çevre ve çevre sağlığı, temizlik ve katı atık, zabıta, itfaiye, acil yardım, şehir içi trafik, park ve yeşil alanlar, kültür ve sanat, sosyal hizmet ve yardım, ekonomi ve ticaretin geliştirilmesi hizmetlerini yapar veya yaptırır."),
    ("Madde 15/b", "Belediye, kanunların belediyeye verdiği yetki çerçevesinde yönetmelik çıkarmaya, emir vermeye, yasak koymaya ve uygulamaya, bunlara uymayanlar hakkında mevzuatta öngörülen ceza ve diğer yaptırımları uygulamaya yetkilidir."),
    ("Madde 15/c", "Belediye, gerçek ve tüzel kişilerin faaliyetleri ile ilgili olarak kanunlarda belirtilen izin veya ruhsatı verir ve bu faaliyetleri denetler."),
    ("Madde 51", "Belediye zabıtası, beldede esenlik, huzur, sağlık ve düzenin sağlanmasıyla görevli olup bu amaçla belediye meclisi tarafından alınan ve belediye zabıtası tarafından yerine getirilmesi gereken emir ve yasaklarla bunlara uymayanlar hakkında mevzuatta öngörülen ceza ve diğer yaptırımları uygular."),
])

source("REG-003", "Resmî Yazışmalarda Uygulanacak Usul ve Esaslar Hakkında Yönetmelik", "regulation",
       "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=19825&MevzuatTur=21&MevzuatTertip=5", [
    ("Madde 1", "Bu Yönetmeliğin amacı, kamu kurum ve kuruluşları arasındaki resmî yazışmalara ilişkin usul ve esasları düzenlemektir."),
    ("Madde 10", "Resmî yazışmalarda kullanılacak belgede başlık, sayı, tarih, konu, muhatap, ilgi, metin, imza, ek ve dağıtım bölümleri bulunur. Konu bölümüne belgenin içeriğini yansıtacak kısa bir ifade yazılır."),
    ("Madde 12", "Bir belgeye cevap niteliğinde hazırlanan yazılarda, cevabı verilen belgenin tarih ve sayısı ilgi bölümünde belirtilir. Metin, muhatabın anlayacağı açık ve anlaşılır bir dille yazılır."),
])

source("REG-004", "İşyeri Açma ve Çalışma Ruhsatlarına İlişkin Yönetmelik", "regulation",
       "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=9207&MevzuatTur=21&MevzuatTertip=5", [
    ("Madde 6", "Yetkili idarelerden usulüne uygun olarak işyeri açma ve çalışma ruhsatı alınmadan işyeri açılamaz ve çalıştırılamaz. İşyeri açmak isteyen gerçek veya tüzel kişiler, işyeri açma ve çalışma ruhsatı başvuru ve beyan formunu doldurarak yetkili idareye başvurur."),
    ("Madde 13", "Sıhhî işyerlerinde başvuru üzerine, beyana göre işyeri açma ve çalışma ruhsatı aynı gün düzenlenerek ilgiliye verilir. Ruhsatın verilmesinden sonra en geç bir ay içinde işyeri denetlenir ve mevzuata aykırılık tespit edilmesi hâlinde süre verilerek eksikliklerin giderilmesi istenir."),
    ("Madde 5/j", "Umuma açık istirahat ve eğlence yerlerinde ilgili mevzuatta belirlenen standartlara aykırı biçimde çevreyi rahatsız edecek şekilde gürültü çıkarılamaz; canlı müzik yayını yapılabilmesi için yetkili idarenin izni gerekir."),
    ("Madde 8", "Ruhsat başvurusunda istenen bilgi veya belgelerin eksik olması hâlinde ilgiliye eksiklikler bildirilir ve tamamlanması için süre verilir. Eksiklikler tamamlanmadıkça ruhsat düzenlenemez."),
])

source("REG-005", "5490 sayılı Nüfus Hizmetleri Kanunu", "law",
       "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.5490.pdf", [
    ("Madde 48", "Adres kayıt sistemi, Türkiye'de yerleşim yeri ve diğer adres bilgilerinin elektronik ortamda merkezî olarak tutulduğu sistemdir. Kurumlar hizmet sunumunda adres kayıt sistemindeki adres bilgilerini esas alır."),
    ("Madde 50", "Adres beyanı ile yükümlü kişiler, yerleşim yeri adresine ilişkin değişiklikleri yirmi iş günü içinde nüfus müdürlüğüne bildirmekle yükümlüdür. Bildirim, kimlik ve adres bilgilerini içeren bir beyan ile yapılır."),
    ("Madde 51", "Gerçeğe aykırı adres beyanında bulunanlar ile bildirim yükümlülüğünü süresi içinde yerine getirmeyenler hakkında idarî para cezası uygulanır."),
])

source("REG-006", "2872 sayılı Çevre Kanunu", "law",
       "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.2872.pdf", [
    ("Madde 14", "Kişilerin huzur ve sükûnunu, beden ve ruh sağlığını bozacak şekilde ilgili yönetmeliklerle belirlenen standartlar üzerinde gürültü ve titreşim oluşturulması yasaktır. Gürültü kaynakları için ilgili idare tarafından ölçüm ve denetim yapılır."),
    ("Madde 20/h", "Gürültüye ilişkin sınır değerlere aykırı davranan işletme ve işyerlerine idarî para cezası verilir; aykırılığın giderilmemesi hâlinde faaliyet durdurulabilir."),
    ("Madde 12", "Bu Kanun hükümlerine uyulup uyulmadığının denetimi, yetki devri yapılan belediyeler dâhil ilgili idarelerce yapılır. Denetim sonucu tespit edilen aykırılıklar için gerekli idarî işlem uygulanır."),
])

source("REG-007", "4982 sayılı Bilgi Edinme Hakkı Kanunu", "law",
       "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.4982.pdf", [
    ("Madde 4", "Herkes bilgi edinme hakkına sahiptir. Kurum ve kuruluşlar, bu Kanunda yer alan istisnalar dışındaki her türlü bilgi veya belgeyi başvuranların yararlanmasına sunmak ve bilgi edinme başvurularını etkin, süratli ve doğru sonuçlandırmak üzere gerekli tedbirleri almakla yükümlüdür."),
    ("Madde 11", "Kurum ve kuruluşlar, başvuru üzerine istenen bilgi veya belgeye erişimi onbeş iş günü içinde sağlar. İstenen bilgi veya belgenin başvurulan kurum içindeki başka bir birimden sağlanması hâlinde bu süre otuz iş gününe kadar uzar ve gerekçesi başvurana yazılı olarak bildirilir."),
    ("Madde 6", "Bilgi edinme başvurusu dilekçesinde başvuru sahibinin adı ve soyadı, imzası, oturma yeri veya iş adresi ile istenen bilgi veya belgenin niteliği bulunur. Bu bilgileri içermeyen başvurular işleme alınmaz."),
])

source("REG-008", "2464 sayılı Belediye Gelirleri Kanunu", "law",
       "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.2464.pdf", [
    ("Madde 1", "Belediye vergi, harç ve katılma payları bu Kanunda gösterilen esaslara göre tarh, tahakkuk ve tahsil edilir."),
    ("Madde 77", "İşyeri açma izni harcı, belediye sınırları içinde bir işyerinin açılması hâlinde bir defaya mahsus olmak üzere alınır. Harcın tahakkuku işyerinin alanı esas alınarak yapılır."),
    ("Madde 96", "Bu Kanunda yer alan maktu vergi ve harç tarifeleri belirlenen usule göre güncellenir; belediyeler tahakkuk ve tahsil işlemlerini yürürlükteki tarifelere göre yürütür."),
])

source("REG-009", "213 sayılı Vergi Usul Kanunu", "law",
       "https://www.mevzuat.gov.tr/MevzuatMetin/1.4.213.pdf", [
    ("Madde 116", "Vergi hatası, vergiye müteallik hesaplarda veya vergilendirmede yapılan hatalar yüzünden haksız yere fazla veya eksik vergi istenmesi veya alınmasıdır."),
    ("Madde 122", "Mükellefler, vergi muamelelerindeki hataların düzeltilmesini ilgili idareden yazı ile isteyebilirler. Düzeltme talebi, hatanın tespit edilmesi hâlinde ilgili idare tarafından resen de yerine getirilir."),
    ("Madde 124", "Düzeltme talebi reddolunanlar şikâyet yolu ile ilgili makama başvurabilirler."),
])

source("REG-010", "5070 sayılı Elektronik İmza Kanunu", "law",
       "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.5070.pdf", [
    ("Madde 5", "Güvenli elektronik imza, elle atılan imza ile aynı hukukî sonucu doğurur. Kanunların resmî şekle veya özel bir merasime tabi tuttuğu hukukî işlemler ile teminat sözleşmeleri güvenli elektronik imza ile gerçekleştirilemez."),
    ("Madde 9", "Elektronik sertifika hizmet sağlayıcısı, sertifika sahibinin başvurusu üzerine veya sertifikanın kullanımına ilişkin bir güvenlik sorunu tespit edilmesi hâlinde sertifikayı gecikmeksizin iptal eder ve durumu sertifika sahibine bildirir."),
    ("Madde 10", "Elektronik sertifika hizmet sağlayıcısı, verdiği hizmetin sürekliliğini sağlamak, güvenli ürün ve sistemler kullanmak ve sertifika sahibini hizmete ilişkin arıza ve kesintiler hakkında bilgilendirmekle yükümlüdür."),
])

source("REG-011", "5326 sayılı Kabahatler Kanunu", "law",
       "https://www.mevzuat.gov.tr/MevzuatMetin/1.5.5326.pdf", [
    ("Madde 36", "Başkalarının huzur ve sükûnunu bozacak şekilde gürültüye neden olan kişiye idarî para cezası verilir. Bu kabahat dolayısıyla idarî para cezasına kolluk veya belediye zabıta görevlileri karar verir."),
    ("Madde 32", "Yetkili makamlar tarafından adlî işlemler dışında verilen ve yerine getirilmesi gereken emre aykırı hareket eden kişiye idarî para cezası verilir. Bu madde ancak ilgili kanunda açıkça hüküm bulunan hâllerde uygulanabilir."),
])

source("REG-012", "Kamu Hizmetlerinin Sunumunda Uyulacak Usul ve Esaslara İlişkin Yönetmelik", "regulation",
       "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=200915169&MevzuatTur=3&MevzuatTertip=5", [
    ("Madde 5", "İdare, hizmet sunumunda başvuru sahibinden istenen bilgi ve belgeleri asgarîye indirir, başka idarelerin elinde bulunan bilgi ve belgeleri başvurandan istemez ve başvurunun hangi aşamada olduğunu ilgilisine bildirir."),
    ("Madde 6", "İdare, hizmetlerin elektronik ortamda sunumunda erişilebilirliği ve sürekliliği sağlamak, sistem kesintisi hâlinde başvuru sahiplerini bilgilendirmek ve alternatif başvuru kanalı sunmakla yükümlüdür."),
    ("Madde 8", "Başvuru üzerine yapılan iş ve işlemler öngörülen sürede tamamlanır; süre uzatımı gerektiren hâllerde gerekçesi başvurana bildirilir."),
])


def main() -> None:
    corpus = {"corpus_version": CORPUS_VERSION, "sources": SOURCES}
    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"{TARGET}: {len(SOURCES)} sources, {sum(len(s['chunks']) for s in SOURCES)} chunks")


if __name__ == "__main__":
    main()

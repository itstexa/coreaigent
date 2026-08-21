"""[7] PII Redaksiyon testleri.

TCKN test sabitleri (12345678950, 11111111110, 98765432150) checksum
algoritmasını geçecek şekilde üretilmiş sentetik/uydurma numaralardır —
gerçek bir kişiye ait değildir.
"""
from __future__ import annotations

from mevzuat_rag.pii import redact_pii


def test_valid_tckn_redacted():
    r = redact_pii("Başvuran T.C. Kimlik No: 12345678950 kişidir.")
    assert "12345678950" not in r.text
    assert "[TCKN]" in r.text
    assert r.counts["tckn"] == 1


def test_invalid_11_digit_number_not_redacted():
    # Checksum'ı geçmeyen rastgele 11 haneli bir sayı (ör. dosya/kayıt no) redakte edilmemeli.
    r = redact_pii("Dosya kayıt numarası: 12345678901")
    assert "12345678901" in r.text
    assert "tckn" not in r.counts


def test_madde_kanun_numbers_not_redacted():
    r = redact_pii("3071 sayılı Kanun'un 4. maddesi 2646 sayılı Yönetmelik'e atıfta bulunur.")
    assert "3071" in r.text and "2646" in r.text and "4." in r.text
    assert r.total == 0


def test_phone_redacted_various_formats():
    for phone in ["05321234567", "0532 123 45 67", "+90 532 123 45 67", "0532-123-45-67"]:
        r = redact_pii(f"İletişim: {phone}")
        assert "[TELEFON]" in r.text, phone
        assert r.counts["telefon"] == 1


def test_email_redacted():
    r = redact_pii("E-posta: vatandas.ornek@example.com adresine yazın.")
    assert "[EPOSTA]" in r.text
    assert "vatandas.ornek@example.com" not in r.text


def test_iban_redacted():
    r = redact_pii("IBAN: TR330006100519786457841326 numaralı hesaba yatırılacaktır.")
    assert "[IBAN]" in r.text
    assert "TR330006100519786457841326" not in r.text


def test_multiple_pii_types_in_one_text():
    text = (
        "Ad Soyad: Örnek Vatandaş, TCKN: 98765432150, Tel: 05321234567, "
        "E-posta: ornek@example.com, IBAN: TR330006100519786457841326."
    )
    r = redact_pii(text)
    assert r.counts == {"tckn": 1, "telefon": 1, "eposta": 1, "iban": 1}
    assert r.total == 4
    for leaked in ["98765432150", "05321234567", "ornek@example.com", "TR330006100519786457841326"]:
        assert leaked not in r.text


def test_idempotent_on_already_redacted_text():
    once = redact_pii("TCKN: 11111111110").text
    twice = redact_pii(once).text
    assert once == twice


def test_empty_and_plain_text_unaffected():
    assert redact_pii("").text == ""
    plain = "Bu dilekçe hiçbir kişisel veri içermemektedir."
    r = redact_pii(plain)
    assert r.text == plain
    assert r.total == 0

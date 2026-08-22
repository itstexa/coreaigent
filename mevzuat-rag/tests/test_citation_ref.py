"""[9] citation_ref.py testleri — hem sentetik hem gerçek corpus cümlesiyle."""
from __future__ import annotations

from mevzuat_rag.pipeline.citation_ref import extract_same_kanun_refs


def test_real_corpus_sentence_3071_madde6c():
    # sample_data/legislation/3071_dilekce_kanunu.md MADDE 6.c — corpus'taki
    # tek gerçek çapraz atıf örneği.
    text = "c) 4. maddede gösterilen şartlardan herhangi birini taşımayanlar,"
    assert extract_same_kanun_refs(text, own_madde_no=6) == {4}


def test_self_reference_excluded():
    text = "Bu maddenin uygulanmasında 6. maddede belirtilen usul izlenir."
    assert extract_same_kanun_refs(text, own_madde_no=6) == set()


def test_various_suffix_forms():
    cases = [
        ("5 inci maddesine göre işlem yapılır.", {5}),
        ("7 nci madde uyarınca bildirilir.", {7}),
        ("3 üncü maddesinde belirtilen süre.", {3}),
        ("10. maddesi saklıdır.", {10}),
    ]
    for text, expected in cases:
        assert extract_same_kanun_refs(text, own_madde_no=1) == expected, text


def test_no_false_positive_on_madde_header():
    # "MADDE 6-" bir başlık, çapraz atıf değil — sayı kelimeden SONRA geliyor.
    text = "MADDE 6- Türkiye Büyük Millet Meclisine verilen dilekçelerden;"
    assert extract_same_kanun_refs(text, own_madde_no=None) == set()


def test_no_false_positive_on_unrelated_numbers():
    text = "26 Aralık 1962 tarih ve 140 sayılı Kanun yürürlükten kaldırılmıştır."
    assert extract_same_kanun_refs(text, own_madde_no=9) == set()


def test_multiple_refs_in_one_text():
    text = "Bu husus 3. maddede ve ayrıca 5 inci maddede de düzenlenmiştir."
    assert extract_same_kanun_refs(text, own_madde_no=8) == {3, 5}


def test_empty_text():
    assert extract_same_kanun_refs("", own_madde_no=1) == set()

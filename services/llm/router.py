from typing import Dict

KNOWN_DEPARTMENTS: Dict[str, str] = {
    "İnsan Kaynakları": "insan_kaynaklari",
    "Personel": "insan_kaynaklari",
    "Hukuk": "hukuk",
    "Hukuk İşleri": "hukuk",
    "Mali Hizmetler": "mali_hizmetler",
    "Muhasebe": "mali_hizmetler",
    "Yazı İşleri": "yazi_isleri",
    "Genel Evrak": "yazi_isleri",
    "Bilgi İşlem": "bilgi_islem",
    "Bilgi Teknolojileri": "bilgi_islem",
    "Destek Hizmetleri": "destek_hizmetleri",
    "İdari İşler": "destek_hizmetleri",
    "Vatandaş Hizmetleri": "vatandas_hizmetleri",
    "Halkla İlişkiler": "vatandas_hizmetleri",
}

FEW_SHOT_EXAMPLES = """Örnek 1:
Evrak: Personel memuru Ahmet Yılmaz'ın yıllık izin talebi onaylanmıştır. Maaş ödemesi ay sonunda yapılacaktır.
Birim: İnsan Kaynakları

Örnek 2:
Evrak: Şirket aleyhine açılan tazminat davasına ilişkin itiraz dilekçesi hazırlanmıştır. Hukuki süreç devam etmektedir.
Birim: Hukuk

Örnek 3:
Evrak: 2024 yılı bütçe teklifi hazırlanmış olup, fatura ödemeleri için ek ödenek talep edilmektedir.
Birim: Mali Hizmetler

Örnek 4:
Evrak: Vatandaş tarafından belediye hizmetleri hakkında bilgi edinme başvurusu yapılmıştır. Talebin karşılanması gerekmektedir.
Birim: Vatandaş Hizmetleri

Örnek 5:
Evrak: Kurum içi bilgisayar ağında yaşanan arıza nedeniyle sistemler çalışmamaktadır. Teknik destek gereklidir.
Birim: Bilgi İşlem

Örnek 6:
Evrak: Toplantı salonunun bakım ve temizlik işlemleri için hizmet alımı yapılacaktır.
Birim: Destek Hizmetleri

Örnek 7:
Evrak: Resmi yazışmaların kayıt altına alınması ve arşivlenmesi işlemleri yürütülmektedir.
Birim: Yazı İşleri

"""


def route_document(text: str, model, tokenizer) -> dict:
    if not text or len(text.strip()) < 5:
        return {"department": "manual_review", "confidence": 0.0}

    prompt = FEW_SHOT_EXAMPLES + f"Evrak: {text.strip()}\nBirim:"

    inputs = tokenizer(prompt, return_tensors="pt")
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    import torch
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=10,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
    first_line = generated_text.split("\n")[0].strip()

    for dept_name, dept_value in KNOWN_DEPARTMENTS.items():
        if dept_name.lower() in first_line.lower() or first_line.lower() in dept_name.lower():
            return {"department": dept_value, "confidence": 0.85}

    return {"department": "manual_review", "confidence": 0.3}

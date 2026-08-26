import torch
from typing import List


def check_missing_semantic_fields(text: str, field_names: List[str], model, tokenizer) -> List[str]:
    if not field_names:
        return []

    missing_fields = []
    for field_name in field_names:
        prompt = (
            f"Evrak metni:\n{text}\n\n"
            f"Bu evrakta {field_name} belirtilmiş mi? (evet/hayır):"
        )
        inputs = tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=5,
                do_sample=False,
            )

        generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
        response = tokenizer.decode(generated_ids, skip_special_tokens=True).strip().lower()

        if "hayır" in response or "hayir" in response:
            missing_fields.append(field_name)

    return missing_fields


CONTRADICTION_FEW_SHOT = (
    "Evrak metni:\nAdım Ahmet Yılmaz, 05.01.2024 tarihinde başvurdum.\n\n"
    "Bu evrak metninde birbiriyle çelişen bilgi (ör. iki farklı tarih, iki farklı isim/miktar) var mı? "
    "Varsa kısaca açıkla, yoksa sadece 'yok' yaz.\nCevap: yok\n\n"
    "Evrak metni:\nFatura tutarı 500 TL'dir. Ödenecek toplam tutar 750 TL olarak hesaplanmıştır.\n\n"
    "Bu evrak metninde birbiriyle çelişen bilgi (ör. iki farklı tarih, iki farklı isim/miktar) var mı? "
    "Varsa kısaca açıkla, yoksa sadece 'yok' yaz.\nCevap: var, iki farklı tutar belirtilmiş (500 TL ve 750 TL)\n\n"
)


# Bilinen sınırlama: Jamba2-3B-Turkish bu görevde (açık uçlu çelişki tespiti)
# few-shot'a rağmen bazen gerçek çelişkileri kaçırıyor (bkz. Faz4 test notu).
# missingFields (kapalı uçlu evet/hayır) güvenilir; conflicts en-iyi-çaba niteliğinde.
def check_contradictions(text: str, model, tokenizer) -> List[str]:
    if len(text) < 20:
        return []

    prompt = (
        CONTRADICTION_FEW_SHOT +
        f"Evrak metni:\n{text}\n\n"
        "Bu evrak metninde birbiriyle çelişen bilgi (ör. iki farklı tarih, iki farklı isim/miktar) var mı? "
        "Varsa kısaca açıkla, yoksa sadece 'yok' yaz.\nCevap:"
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=40,
            do_sample=False,
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    response = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
    first_line = response.split("\n")[0].strip()

    if not first_line or first_line.lower().startswith("yok"):
        return []

    # Model bazen düşük güvende promptu/girdi metnini tekrar ediyor (echo);
    # bu durumda güvenilir bir çelişki sinyali yok sayılır.
    echo_markers = ("evrak metni", text.strip()[:25].lower())
    if any(marker and marker in first_line.lower() for marker in echo_markers):
        return []

    return [first_line]

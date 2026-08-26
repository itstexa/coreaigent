import re
import torch
from typing import List


def _dedupe_repetition(text: str) -> str:
    """Greedy decode bazen aynı cümleyi döngüsel tekrar eder; ilk tekrardan
    sonrasını kes."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    seen = set()
    out = []
    for s in sentences:
        key = s.strip().lower()
        if key and key in seen:
            break
        if key:
            seen.add(key)
        out.append(s)
    return " ".join(out).strip()


# Bilinen sınırlama: repetition_penalty/no_repeat_ngram_size döngüsel
# tekrarı (aynı cümlenin N kez basılması) önlüyor, ama serbest-metin uzun
# taslak üretiminde Jamba2-3B-Turkish bazen konudan sapan/tutarsız içerik
# üretebiliyor (bkz. Faz6 uçtan uca test notu). Kısa/kapalı-uçlu görevler
# (sınıflandırma, yönlendirme, evet/hayır alan kontrolü) güvenilir; uzun
# serbest taslak insan gözden geçirmesi gerektiren bir ilk taslak olarak
# değerlendirilmeli, doğrudan gönderim için değil.
def generate_draft(text: str, context: List[str], model, tokenizer) -> str:
    if not text.strip():
        return ""

    few_shot = """Örnek 1:
İlgi: 12.03.2024 tarihli ve 1234 sayılı yazınız.
Konu: Bilgi talebi hakkında.
İlgili talebiniz incelenmiş olup, talep edilen bilgiler ekte sunulmuştur.
Bilgilerinize arz ederim.

Örnek 2:
İlgi: 05.01.2024 tarihli başvurunuz.
Konu: Başvuru süreci hakkında.
Başvurunuz değerlendirmeye alınmış olup, süreç hakkında ayrıca bilgilendirileceksiniz.
Gereğine arz ederim.

"""

    context_part = ""
    if context:
        context_part = "İlgili mevzuat: " + " ".join(context) + "\n\n"

    prompt = few_shot + context_part + f"Gelen evrak:\n{text}\n\nResmi yazı taslağı:"

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=150,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
            repetition_penalty=1.3,
            no_repeat_ngram_size=3,
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
    generated_text = _dedupe_repetition(generated_text)

    if not generated_text or generated_text[:30] == text[:30]:
        return "Sayın ilgili, evrağınız incelenmek üzere alınmıştır. Bilgilerinize arz ederim."

    return generated_text


def summarize(text: str, model, tokenizer) -> str:
    if not text.strip():
        return ""

    prompt = f"Aşağıdaki evrağı 1-2 cümlede özetle:\n{text}\nÖzet:"

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=60,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
            repetition_penalty=1.3,
            no_repeat_ngram_size=3,
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
    generated_text = _dedupe_repetition(generated_text)

    summary_lines = generated_text.split("\n")[:2]
    summary = "\n".join(summary_lines).strip()

    if not summary:
        return text[:150]

    return summary

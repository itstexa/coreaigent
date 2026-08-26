import torch
from typing import List


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

    prompt = few_shot + context_part + f"Resmi yazı taslağı:\n{text}\n\nResmi yazı taslağı:"

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=150,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()

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
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()

    summary_lines = generated_text.split("\n")[:2]
    summary = "\n".join(summary_lines).strip()

    if not summary:
        return text[:150]

    return summary

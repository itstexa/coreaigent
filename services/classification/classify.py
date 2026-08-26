import logging
from datetime import datetime, timezone

import torch

logger = logging.getLogger(__name__)

KNOWN_TYPES = {
    "Dilekçe": "petition",
    "Bilgi Edinme Başvurusu": "information_request",
    "Şikayet Dilekçesi": "complaint",
    "İhbar Dilekçesi": "complaint",
    "İtiraz Dilekçesi": "petition",
    "Resmi Yazı": "official_letter",
    "Başvuru Formu": "application",
    "Fatura": "invoice",
}

FEW_SHOT_EXAMPLES = """Örnek 1:
Sayın yetkili, emekli maaşımın eksik yatırıldığını düşünüyorum. Gereğini arz ederim.
Evrak türü: Dilekçe

Örnek 2:
Kurumunuzdan 2023 yılı bütçe harcamaları hakkında bilgi talep ediyorum.
Evrak türü: Bilgi Edinme Başvurusu

Örnek 3:
Fatura No: 2024-001, Tutar: 1.250,00 TL, Son Ödeme Tarihi: 15.03.2024
Evrak türü: Fatura

"""


def _build_prompt(text: str) -> str:
    return FEW_SHOT_EXAMPLES + f"Gerçek evrak:\n{text}\nEvrak türü:"


def _match_turkce_tur(raw_label: str):
    if not raw_label:
        return None
    normalized = raw_label.strip().lower()
    for tur in KNOWN_TYPES:
        if tur.lower() in normalized or normalized in tur.lower():
            return tur
    return None


def classify_document(text: str, model, tokenizer) -> dict:
    log_extra = {
        "service": "classification",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if not text or len(text.strip()) < 5:
        logger.info("Text too short, skipping model", extra=log_extra)
        return {
            "documentType": "unsupported",
            "classification": "unsupported",
            "extractedFields": {"raw_model_label": None, "matched_turkce_tur": None, "source_text": text or ""},
            "summary": None,
        }

    prompt = _build_prompt(text.strip())
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    try:
        with torch.no_grad():
            outputs = model.generate(
                inputs.input_ids,
                max_new_tokens=15,
                do_sample=False,
                eos_token_id=tokenizer.eos_token_id,
            )
    except Exception as e:
        logger.error(f"Model generation failed: {e}", extra={**log_extra, "error": "model_generation_error"})
        raise

    generated_ids = outputs[0][inputs.input_ids.shape[1]:]
    raw_label = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
    first_line = raw_label.split("\n")[0].strip()

    matched_tur = _match_turkce_tur(first_line)

    if matched_tur:
        document_type = KNOWN_TYPES[matched_tur]
        classification = "processable"
        summary = text.strip()[:200]
    else:
        document_type = "unsupported"
        classification = "manual_review"
        summary = None

    logger.info(
        f"Classification result: type={document_type}, classification={classification}",
        extra={**log_extra, "raw_label": first_line, "matched_tur": matched_tur},
    )

    return {
        "documentType": document_type,
        "classification": classification,
        "extractedFields": {
            "raw_model_label": first_line,
            "matched_turkce_tur": matched_tur,
            "source_text": text.strip(),
        },
        "summary": summary,
    }

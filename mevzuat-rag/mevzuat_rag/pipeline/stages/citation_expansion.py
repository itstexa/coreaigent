"""[9] Atıf Genişletme (GraphRAG-lite) — [4] Parent Document Retrieval'den
sonra, her adayın metninde geçen madde-madde çapraz atıfları (bkz.
``citation_ref.py``) tespit edip, atıf verilen maddeyi de context'e ekler.

Neden burada, CRAG'dan önce: CRAG "kanıt yeterli mi" diye değerlendirirken
atıf verilen maddenin de elinde olması, tek-adımlı embedding benzerliğinin
kaçırdığı ama metnin kendisinin açıkça işaret ettiği kanıtı tamamlıyor —
somut örnek: "Hangi dilekçeler incelenemez?" sorusu Madde 6'yı buluyor,
Madde 6.c "4. maddede gösterilen şartlar" diyor ama "zorunlu bilgiler nedir"
anlamsal olarak çok farklı bir soru olduğu için Madde 4 kendi başına aynı
top-k'ya girmeyebilir — bu stage, metnin kendi atıfını takip ederek onu da
ekliyor.

Token bütçesi [4]'teki gibi ele alınıyor: genişletilen maddeler düşük
öncelikli (skorları orijinal adaydan miras), bütçe zorlanırsa önce onlar
düşer.
"""
from __future__ import annotations

import logging

from mevzuat_rag.models import ChunkMetadata, LegislationChunk
from mevzuat_rag.pipeline.candidate import Candidate
from mevzuat_rag.pipeline.citation_ref import extract_same_kanun_refs
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.token_estimate import estimate_tokens

logger = logging.getLogger("mevzuat_rag.citation_expansion")


class CitationExpansionStage:
    name = "citation_expansion"

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.engine.config.citation_expansion
        store = ctx.engine.store

        existing_keys = {
            (c.chunk.metadata.kanun_no, c.chunk.metadata.madde_no)
            for c in ctx.candidates
            if c.chunk is not None and c.chunk.metadata.madde_no is not None
        }

        to_add: dict[tuple[str, int], Candidate] = {}
        for candidate in ctx.candidates:
            if candidate.chunk is None or candidate.chunk.metadata.madde_no is None:
                continue
            kanun_no = candidate.chunk.metadata.kanun_no
            own_madde = candidate.chunk.metadata.madde_no

            try:
                refs = extract_same_kanun_refs(candidate.text, own_madde)
            except Exception as exc:  # regex üzerinde çalışıyor, pratikte olası değil
                logger.warning("Atıf tespiti başarısız (%s) — bu aday atlanıyor.", exc)
                continue

            for madde_no in refs:
                key = (kanun_no, madde_no)
                if key in existing_keys or key in to_add:
                    continue  # zaten getirilmiş, tekrar eklenmeye gerek yok

                try:
                    siblings = store.get_chunks_by_madde(kanun_no, madde_no)
                except Exception as exc:
                    logger.warning("Atıf genişletme sorgusu başarısız (%s:%s) — %s", kanun_no, madde_no, exc)
                    continue
                if not siblings:
                    continue  # atıf verilen madde corpus'ta yok (ör. yürürlükten kalkmış eski kanun)

                parent_text = "\n".join(s.text for s in siblings)
                template = siblings[0]
                metadata = ChunkMetadata(
                    kanun_no=template.metadata.kanun_no,
                    kanun_adi=template.metadata.kanun_adi,
                    madde_no=madde_no,
                    fikra_no=None,
                    bent=None,
                    kaynak_url=template.metadata.kaynak_url,
                    source_hash=template.metadata.source_hash,
                    durum=template.metadata.durum,
                    mevzuat_turu=template.metadata.mevzuat_turu,
                    contains_table=template.metadata.contains_table,
                )
                chunk = LegislationChunk(
                    id=f"citation_ref:{kanun_no}:{madde_no}",
                    text=parent_text,
                    metadata=metadata,
                    citation=f"{kanun_no} sayılı {template.metadata.kanun_adi}, Madde {madde_no} (atıf üzerinden genişletildi)",
                )
                # Genişletilen madde, kendisine işaret eden adayın skorundan
                # biraz düşük tutulur — doğrudan eşleşme değil, dolaylı atıf.
                to_add[key] = Candidate(
                    id=chunk.id, text=parent_text, score=candidate.score * 0.9,
                    source="citation_expanded", parent_id=f"{kanun_no}:{madde_no}",
                    metadata={"expanded_from": candidate.id}, chunk=chunk,
                )

        if not to_add:
            return ctx

        budget = int(config.context_window_tokens * config.token_budget_fraction)
        used_tokens = sum(estimate_tokens(c.text) for c in ctx.candidates)
        for candidate in sorted(to_add.values(), key=lambda c: c.score, reverse=True):
            cost = estimate_tokens(candidate.text)
            if used_tokens + cost > budget:
                continue
            ctx.candidates.append(candidate)
            used_tokens += cost
            logger.info("Atıf genişletildi: %s", candidate.chunk.citation)

        return ctx

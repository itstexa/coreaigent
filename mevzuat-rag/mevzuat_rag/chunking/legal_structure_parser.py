"""Parses Turkish legislation text into a Madde/Fıkra/Bent tree.

Turkish mevzuat text follows a consistent structural convention:
  MADDE 5- (Başlık varsa parantez ya da büyük harfle)
  (1) Fıkra metni ...
      a) Bent metni ...
      b) Bent metni ...
  (2) Fıkra metni ...

This parser is regex-based, not ML-based: legislation formatting is
regular enough that a state machine is more reliable (and auditable) than a
model here, and citation accuracy matters more than recall on edge cases.
"""
from __future__ import annotations

import re

from mevzuat_rag.models import FikraNode, LegislationDocument, MaddeNode

MADDE_RE = re.compile(r"^\s*MADDE\s+(\d+)\s*[-–—]\s*(.*)$", re.IGNORECASE)
FIKRA_RE = re.compile(r"^\s*\((\d+)\)\s*(.*)$")
BENT_RE = re.compile(r"^\s*([a-zçğıöşü])\)\s*(.*)$", re.IGNORECASE)


def parse_legislation_text(raw_text: str, kanun_no: str, kanun_adi: str, kaynak_url: str) -> LegislationDocument:
    doc = LegislationDocument(kanun_no=kanun_no, kanun_adi=kanun_adi, kaynak_url=kaynak_url)
    current_madde: MaddeNode | None = None
    current_fikra: FikraNode | None = None
    current_bent_letter: str | None = None

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        madde_match = MADDE_RE.match(line)
        if madde_match:
            current_madde = MaddeNode(madde_no=int(madde_match.group(1)), baslik=None)
            doc.maddeler.append(current_madde)
            current_fikra = None
            current_bent_letter = None
            remainder = madde_match.group(2).strip()
            if remainder:
                line = remainder
            else:
                continue

        if current_madde is None:
            # Preamble / non-madde text (başlık, dayanak vb.) — skip, not citable.
            continue

        fikra_match = FIKRA_RE.match(line)
        if fikra_match:
            current_fikra = FikraNode(fikra_no=int(fikra_match.group(1)), bent=None, text="")
            current_madde.fikralar.append(current_fikra)
            current_bent_letter = None
            line = fikra_match.group(2).strip()
            if not line:
                continue

        if current_fikra is None:
            # Madde body with no explicit (1) marker — implicit first fıkra.
            current_fikra = FikraNode(fikra_no=1, bent=None, text="")
            current_madde.fikralar.append(current_fikra)

        bent_match = BENT_RE.match(line)
        if bent_match:
            current_bent_letter = bent_match.group(1).lower()
            bent_node = FikraNode(fikra_no=current_fikra.fikra_no, bent=current_bent_letter, text=bent_match.group(2).strip())
            current_madde.fikralar.append(bent_node)
            continue

        target = current_madde.fikralar[-1]
        target.text = (target.text + " " + line).strip() if target.text else line

    return doc

"""Test oturumu başlamadan önce paket kökündeki .env dosyasını yükler.

Bunsuz, DEEPSEEK_API_KEY gibi değişkenler yalnızca kabuk ortamında set
edilmişse testler geçiyordu; CI/yeni bir geliştirici makinesinde .env dosyası
var olsa bile hiçbir yerde okunmadığından CRAG/router/multi-query/HyDE
aşamalarını içeren testler (ör. test_engine_retrieve_writes_audit_entry)
"OPENAI_API_KEY eksik" hatasıyla düşüyordu — .env'deki gerçek anahtar hiç
devreye girmiyordu.
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

"""Orchestration channel integrations + ServiceRegistry factory.

Lazily instantiates per-channel service clients from settings. Missing creds
leave the field None — nodes raise a clear error at execute time, not at boot.
"""
from __future__ import annotations

from app.config import settings
from app.services.orchestration.node_context import ServiceRegistry


def build_service_registry() -> ServiceRegistry:
    reg = ServiceRegistry()

    if settings.WATI_BASE_URL and settings.WATI_TENANT_ID and settings.WATI_API_TOKEN:
        from app.services.orchestration.integrations.wati import WatiService
        reg.wati = WatiService(
            base_url=settings.WATI_BASE_URL,
            wati_tenant_id=settings.WATI_TENANT_ID,
            api_token=settings.WATI_API_TOKEN,
        )

    if settings.BOLNA_BASE_URL and settings.BOLNA_API_KEY:
        from app.services.orchestration.integrations.bolna import BolnaService
        reg.bolna = BolnaService(
            base_url=settings.BOLNA_BASE_URL,
            api_key=settings.BOLNA_API_KEY,
        )

    # LSQ writer reads creds from existing lsq_client module — no constructor args.
    from app.services.orchestration.integrations.lsq import LsqWriter
    reg.lsq = LsqWriter()

    if settings.SMS_PROVIDER and settings.SMS_API_KEY:
        from app.services.orchestration.integrations.sms import SmsService
        reg.sms = SmsService(
            provider=settings.SMS_PROVIDER,
            api_key=settings.SMS_API_KEY,
            base_url=settings.SMS_BASE_URL,
        )

    return reg

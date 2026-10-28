"""Sincroniza e-mails Gmail (OAuth por funcionário) → cards de prospecção."""

from __future__ import annotations

import base64
import logging
from email.utils import parseaddr

from django.conf import settings
from googleapiclient.discovery import build

from .gmail_oauth import credentials_gmail_for_user, gmail_conectado
from .models import GmailVinculo
from .services import assunto_gatilho_prospeccao, criar_prospeccao_from_email

logger = logging.getLogger(__name__)


def _decode_body(payload: dict) -> str:
    if not payload:
        return ""
    data = payload.get("body", {}).get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(data + "===").decode("utf-8", "replace")
        except Exception:
            pass
    parts = payload.get("parts") or []
    textos = []
    for part in parts:
        mime = (part.get("mimeType") or "").lower()
        if mime == "text/plain":
            textos.append(_decode_body(part))
        elif mime.startswith("multipart/"):
            textos.append(_decode_body(part))
    if textos:
        return "\n".join(t for t in textos if t)
    for part in parts:
        if (part.get("mimeType") or "").lower() == "text/html":
            return _decode_body(part)
    return ""


def _header_map(payload: dict) -> dict[str, str]:
    headers = {}
    for h in payload.get("headers") or []:
        name = (h.get("name") or "").lower()
        if name:
            headers[name] = h.get("value") or ""
    return headers


def _parse_address_list(raw: str) -> list[dict]:
    itens = []
    for chunk in (raw or "").split(","):
        nome, email = parseaddr(chunk.strip())
        if email:
            itens.append({"name": nome, "email": email})
    return itens


def _query_gmail() -> str:
    assunto = assunto_gatilho_prospeccao().replace('"', "")
    label = (
        getattr(settings, "CRM_GMAIL_LABEL", "") or "Oportunidades/Quentes"
    ).strip()
    return f'label:{label} subject:"{assunto}"'


def sincronizar_usuario(user) -> dict:
    stats = {"ok": True, "criados": 0, "ignorados": 0, "erros": 0, "mensagem": ""}
    if not gmail_conectado(user):
        stats["ok"] = False
        stats["mensagem"] = "Gmail não vinculado."
        return stats

    creds = credentials_gmail_for_user(user)
    if creds is None:
        stats["ok"] = False
        stats["mensagem"] = "Credenciais Gmail indisponíveis."
        return stats

    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        query = _query_gmail()
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=25)
            .execute()
        )
        messages = resp.get("messages") or []
        for item in messages:
            mid = item.get("id")
            if not mid:
                continue
            full = (
                service.users()
                .messages()
                .get(userId="me", id=mid, format="full")
                .execute()
            )
            payload = full.get("payload") or {}
            headers = _header_map(payload)
            subject = (headers.get("subject") or "").strip()
            from_name, from_email = parseaddr(headers.get("from") or "")
            body = _decode_body(payload) or (full.get("snippet") or "")
            resultado = criar_prospeccao_from_email(
                {
                    "subject": subject,
                    "body": body,
                    "from_email": from_email,
                    "from_name": from_name,
                    "to": _parse_address_list(headers.get("to") or ""),
                    "cc": _parse_address_list(headers.get("cc") or ""),
                    "message_id": f"gmailapi:{mid}",
                }
            )
            if resultado.get("created"):
                stats["criados"] += 1
            elif resultado.get("ok"):
                stats["ignorados"] += 1
            else:
                stats["erros"] += 1
                logger.info("Gmail sync skip/erro: %s", resultado.get("mensagem"))
        stats["mensagem"] = (
            f"{stats['criados']} criado(s), {stats['ignorados']} já existente(s)."
        )
    except Exception as exc:
        logger.exception("Falha ao sincronizar Gmail do usuário %s", user.pk)
        stats["ok"] = False
        stats["erros"] += 1
        stats["mensagem"] = str(exc)
    return stats


def sincronizar_todas_contas() -> dict:
    total = {"usuarios": 0, "criados": 0, "ignorados": 0, "erros": 0}
    for vinculo in GmailVinculo.objects.select_related("usuario").all():
        user = vinculo.usuario
        if not user or not user.is_active or not vinculo.conectado:
            continue
        total["usuarios"] += 1
        r = sincronizar_usuario(user)
        total["criados"] += r.get("criados", 0)
        total["ignorados"] += r.get("ignorados", 0)
        total["erros"] += r.get("erros", 0)
    return total

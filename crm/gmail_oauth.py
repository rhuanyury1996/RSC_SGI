"""OAuth Gmail dedicado (não usa o fluxo do calendário)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.urls import reverse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from .models import GmailVinculo

logger = logging.getLogger(__name__)

SCOPE_GMAIL = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_EMAIL = "https://www.googleapis.com/auth/userinfo.email"
SCOPE_PROFILE = "https://www.googleapis.com/auth/userinfo.profile"
SCOPES = [SCOPE_GMAIL, SCOPE_EMAIL, SCOPE_PROFILE]


def gmail_oauth_configurado() -> bool:
    return bool(
        getattr(settings, "GOOGLE_CLIENT_ID", "")
        and getattr(settings, "GOOGLE_CLIENT_SECRET", "")
    )


def gmail_redirect_uri(request=None) -> str:
    configured = (getattr(settings, "GOOGLE_GMAIL_REDIRECT_URI", "") or "").strip()
    if configured:
        return configured
    if request is not None:
        return request.build_absolute_uri(reverse("crm_gmail_callback"))
    return "http://127.0.0.1:8000/comercial/gmail/callback/"


def build_gmail_flow(request=None, state: str | None = None) -> Flow:
    if not gmail_oauth_configurado():
        raise RuntimeError(
            "Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no ambiente."
        )
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [gmail_redirect_uri(request)],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, state=state)
    flow.redirect_uri = gmail_redirect_uri(request)
    return flow


def fetch_google_email(credentials: Credentials) -> str:
    try:
        service = build("oauth2", "v2", credentials=credentials, cache_discovery=False)
        info = service.userinfo().get().execute()
        return (info.get("email") or "").strip()
    except Exception:
        logger.exception("Falha ao obter e-mail Google (Gmail OAuth)")
        return ""


def save_gmail_credentials(user, credentials: Credentials, email: str = "") -> GmailVinculo:
    refresh = credentials.refresh_token or ""
    if not refresh:
        existente = GmailVinculo.objects.filter(usuario=user).first()
        if existente and existente.refresh_token:
            refresh = existente.refresh_token

    vinculo, _ = GmailVinculo.objects.update_or_create(
        usuario=user,
        defaults={
            "email": email or "",
            "token": credentials.token or "",
            "refresh_token": refresh,
            "token_uri": credentials.token_uri or "https://oauth2.googleapis.com/token",
            "client_id": credentials.client_id or settings.GOOGLE_CLIENT_ID,
            "client_secret": credentials.client_secret or settings.GOOGLE_CLIENT_SECRET,
            "scopes": " ".join(credentials.scopes or SCOPES),
            "expiry": credentials.expiry,
        },
    )
    return vinculo


def gmail_vinculo_de(user) -> GmailVinculo | None:
    try:
        return user.gmail_vinculo
    except GmailVinculo.DoesNotExist:
        return None


def gmail_conectado(user) -> bool:
    v = gmail_vinculo_de(user)
    return bool(v and v.conectado)


def usuario_precisa_conectar_gmail(user) -> bool:
    if not gmail_oauth_configurado():
        return False
    return not gmail_conectado(user)


def credentials_gmail_for_user(user) -> Credentials | None:
    vinculo = gmail_vinculo_de(user)
    if vinculo is None or not vinculo.conectado:
        return None

    creds = Credentials(
        token=vinculo.token,
        refresh_token=vinculo.refresh_token or None,
        token_uri=vinculo.token_uri,
        client_id=vinculo.client_id or settings.GOOGLE_CLIENT_ID,
        client_secret=vinculo.client_secret or settings.GOOGLE_CLIENT_SECRET,
        scopes=(vinculo.scopes.split() if vinculo.scopes else SCOPES),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        vinculo.token = creds.token or ""
        vinculo.expiry = creds.expiry
        vinculo.save(update_fields=["token", "expiry", "atualizado_em"])
    return creds

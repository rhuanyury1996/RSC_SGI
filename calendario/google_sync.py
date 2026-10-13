from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from .models import EventoCalendario, GoogleCalendarConta

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def google_configurado() -> bool:
    return bool(
        getattr(settings, "GOOGLE_CLIENT_ID", "")
        and getattr(settings, "GOOGLE_CLIENT_SECRET", "")
    )


def redirect_uri(request=None) -> str:
    configured = getattr(settings, "GOOGLE_REDIRECT_URI", "") or ""
    if configured:
        return configured
    if request is not None:
        return request.build_absolute_uri(reverse("google_calendar_callback"))
    return "http://127.0.0.1:8000/calendario/google/callback/"


def build_flow(request=None, state: str | None = None) -> Flow:
    if not google_configurado():
        raise RuntimeError(
            "Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no arquivo .env"
        )
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri(request)],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, state=state)
    flow.redirect_uri = redirect_uri(request)
    return flow


def save_credentials(user, credentials: Credentials, email: str = "") -> GoogleCalendarConta:
    refresh = credentials.refresh_token or ""
    if not refresh:
        existente = GoogleCalendarConta.objects.filter(usuario=user).first()
        if existente and existente.refresh_token:
            refresh = existente.refresh_token

    conta, _ = GoogleCalendarConta.objects.update_or_create(
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
    return conta


def credentials_for_user(user) -> Credentials | None:
    try:
        conta = user.google_calendar
    except GoogleCalendarConta.DoesNotExist:
        return None

    creds = Credentials(
        token=conta.token,
        refresh_token=conta.refresh_token or None,
        token_uri=conta.token_uri,
        client_id=conta.client_id or settings.GOOGLE_CLIENT_ID,
        client_secret=conta.client_secret or settings.GOOGLE_CLIENT_SECRET,
        scopes=(conta.scopes.split() if conta.scopes else SCOPES),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        conta.token = creds.token or ""
        conta.expiry = creds.expiry
        conta.save(update_fields=["token", "expiry", "atualizado_em"])
    return creds


def _evento_para_google_body(evento: EventoCalendario) -> dict:
    descricao = evento.motivo or ""
    if evento.tipo == "day_off" and evento.horas_recuperar:
        descricao = (
            f"{descricao}\n\nHoras a recuperar: {evento.horas_recuperar}h"
            f"\nPeríodo: {evento.recuperacao_inicio} → {evento.recuperacao_fim}"
        ).strip()

    titulo = f"[SGI RSC] {evento.get_tipo_display()}: {evento.titulo}"
    inicio = timezone.localtime(evento.inicio)
    fim = timezone.localtime(evento.fim)

    if evento.dia_inteiro:
        # Google Calendar usa data final exclusiva em eventos de dia inteiro
        fim_exclusive = fim.date() + timedelta(days=1)
        return {
            "summary": titulo,
            "description": descricao,
            "start": {"date": inicio.date().isoformat()},
            "end": {"date": fim_exclusive.isoformat()},
        }

    return {
        "summary": titulo,
        "description": descricao,
        "start": {
            "dateTime": inicio.isoformat(),
            "timeZone": settings.TIME_ZONE,
        },
        "end": {
            "dateTime": fim.isoformat(),
            "timeZone": settings.TIME_ZONE,
        },
    }


def espelhar_evento_google(user, evento: EventoCalendario) -> str | None:
    """Cria o evento no Google Calendar do usuário. Retorna o event id ou None."""
    if not google_configurado():
        return None
    if evento.espelhado_google and evento.google_event_id:
        return evento.google_event_id

    creds = credentials_for_user(user)
    if creds is None:
        return None

    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        body = _evento_para_google_body(evento)
        created = (
            service.events()
            .insert(calendarId="primary", body=body)
            .execute()
        )
        event_id = created.get("id", "")
        if event_id:
            evento.google_event_id = event_id
            evento.espelhado_google = True
            evento.save(update_fields=["google_event_id", "espelhado_google", "atualizado_em"])
        return event_id or None
    except Exception:
        logger.exception("Falha ao espelhar evento %s no Google Calendar", evento.pk)
        return None


def espelhar_pendentes(user, funcionario) -> tuple[int, int]:
    """Espelha eventos futuros ainda não enviados. Retorna (ok, falhas)."""
    pendentes = (
        EventoCalendario.objects.filter(
            funcionario=funcionario,
            espelhado_google=False,
            fim__date__gte=timezone.localdate(),
        )
        .exclude(status="cancelado")
        .order_by("inicio")
    )
    ok = 0
    falhas = 0
    for evento in pendentes:
        if espelhar_evento_google(user, evento):
            ok += 1
        else:
            falhas += 1
    return ok, falhas

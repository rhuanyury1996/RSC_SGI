from django.contrib import admin

from .models import Demanda, EventoCalendario, GoogleCalendarConta


@admin.register(EventoCalendario)
class EventoCalendarioAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "tipo",
        "funcionario",
        "inicio",
        "fim",
        "status",
        "espelhado_google",
        "horas_recuperar",
        "recuperacao_inicio",
        "recuperacao_fim",
    )
    list_filter = ("tipo", "status", "dia_inteiro", "espelhado_google")
    search_fields = ("titulo", "motivo", "funcionario__nome", "funcionario__sobrenome")


@admin.register(Demanda)
class DemandaAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "funcionario",
        "data_prevista",
        "horas",
        "status",
        "origem_day_off",
    )
    list_filter = ("status", "origem_day_off")
    search_fields = ("titulo", "descricao", "funcionario__nome")


@admin.register(GoogleCalendarConta)
class GoogleCalendarContaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "email", "conectado_em", "atualizado_em")
    search_fields = ("usuario__username", "email")
    readonly_fields = ("token", "refresh_token", "client_secret")

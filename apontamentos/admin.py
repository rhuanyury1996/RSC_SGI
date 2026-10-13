from django.contrib import admin

from .models import (
    MarcacaoPonto,
    SolicitacaoDayOff,
    SolicitacaoEdicaoMarcacao,
    SolicitacaoFerias,
)


@admin.register(MarcacaoPonto)
class MarcacaoPontoAdmin(admin.ModelAdmin):
    list_display = ("funcionario", "tipo", "data_hora", "observacao")
    list_filter = ("tipo", "data_hora")
    search_fields = ("funcionario__nome", "funcionario__sobrenome", "observacao")


@admin.register(SolicitacaoEdicaoMarcacao)
class SolicitacaoEdicaoMarcacaoAdmin(admin.ModelAdmin):
    list_display = (
        "marcacao",
        "tipo_solicitacao",
        "solicitado_por",
        "status",
        "criado_em",
        "revisado_por",
        "revisado_em",
    )
    list_filter = ("tipo_solicitacao", "status", "criado_em")
    search_fields = (
        "solicitado_por__nome",
        "solicitado_por__sobrenome",
        "motivo",
        "marcacao__observacao",
    )
    readonly_fields = (
        "tipo_original",
        "data_hora_original",
        "observacao_original",
        "criado_em",
    )


@admin.register(SolicitacaoFerias)
class SolicitacaoFeriasAdmin(admin.ModelAdmin):
    list_display = ("funcionario", "data_inicio", "data_fim", "status")
    list_filter = ("status",)
    search_fields = ("funcionario__nome", "funcionario__sobrenome")


@admin.register(SolicitacaoDayOff)
class SolicitacaoDayOffAdmin(admin.ModelAdmin):
    list_display = ("funcionario", "data", "status")
    list_filter = ("status",)
    search_fields = ("funcionario__nome", "funcionario__sobrenome", "motivo")

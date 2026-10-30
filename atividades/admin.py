from django.contrib import admin

from .models import (
    AtividadeDiaria,
    DiaPlanner,
    EventoAtividade,
    HabitoDia,
    MetaFoco,
    SessaoTempoAtividade,
)


class MetaFocoInline(admin.TabularInline):
    model = MetaFoco
    extra = 0


class HabitoDiaInline(admin.TabularInline):
    model = HabitoDia
    extra = 0


@admin.register(AtividadeDiaria)
class AtividadeDiariaAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "cliente_rsc",
        "responsavel",
        "status",
        "prioridade",
        "quadrante",
        "data_vencimento",
        "planejado_para",
        "tempo_acumulado_segundos",
        "concluida",
    )
    list_filter = (
        "status",
        "prioridade",
        "quadrante",
        "concluida",
        "planejado_para",
        "cliente_rsc",
    )
    search_fields = (
        "titulo",
        "responsavel__nome",
        "responsavel__sobrenome",
        "cliente_rsc__nome",
    )
    autocomplete_fields = ("responsavel", "criado_por", "cliente_rsc")
    filter_horizontal = ("participantes",)
    date_hierarchy = "planejado_para"


@admin.register(EventoAtividade)
class EventoAtividadeAdmin(admin.ModelAdmin):
    list_display = ("atividade", "tipo", "autor", "criado_em")
    list_filter = ("tipo",)
    search_fields = ("atividade__titulo", "texto", "autor__nome")
    autocomplete_fields = ("atividade", "autor")


@admin.register(SessaoTempoAtividade)
class SessaoTempoAtividadeAdmin(admin.ModelAdmin):
    list_display = ("atividade", "funcionario", "inicio", "fim", "segundos")
    list_filter = ("inicio",)
    search_fields = (
        "atividade__titulo",
        "funcionario__nome",
        "funcionario__sobrenome",
    )
    autocomplete_fields = ("atividade", "funcionario")
    date_hierarchy = "inicio"


@admin.register(DiaPlanner)
class DiaPlannerAdmin(admin.ModelAdmin):
    list_display = ("funcionario", "data", "agua_copos", "pomodoros")
    list_filter = ("data",)
    search_fields = ("funcionario__nome", "funcionario__sobrenome")
    autocomplete_fields = ("funcionario",)
    inlines = (MetaFocoInline, HabitoDiaInline)

from django.contrib import admin

from .models import AtividadeDiaria, DiaPlanner, HabitoDia, MetaFoco


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
        "empresa",
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
        "empresa",
    )
    search_fields = (
        "titulo",
        "responsavel__nome",
        "responsavel__sobrenome",
        "empresa__nome",
    )
    autocomplete_fields = ("responsavel", "criado_por", "empresa")
    date_hierarchy = "planejado_para"


@admin.register(DiaPlanner)
class DiaPlannerAdmin(admin.ModelAdmin):
    list_display = ("funcionario", "data", "agua_copos", "pomodoros")
    list_filter = ("data",)
    search_fields = ("funcionario__nome", "funcionario__sobrenome")
    autocomplete_fields = ("funcionario",)
    inlines = (MetaFocoInline, HabitoDiaInline)

from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    AparenciaPrioridade,
    AparenciaStatus,
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



class _CorForm(forms.ModelForm):
    class Meta:
        fields = "__all__"
        widgets = {"cor": forms.TextInput(attrs={"type": "color", "style": "width:4rem;height:2rem;padding:0"})}


class _AparenciaAdmin(admin.ModelAdmin):
    """Só edita nome, cor e ordem: os status/prioridades em si são fixos no sistema."""

    list_display = ("amostra", "nome", "cor", "ordem")
    list_display_links = ("amostra",)
    list_editable = ("nome", "cor", "ordem")

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return (self.chave,) if obj else ()


@admin.register(AparenciaStatus)
class AparenciaStatusAdmin(_AparenciaAdmin):
    chave = "status"

    class form(_CorForm):
        class Meta(_CorForm.Meta):
            model = AparenciaStatus

    def get_changelist_form(self, request, **kwargs):
        kwargs.setdefault("form", self.form)
        return super().get_changelist_form(request, **kwargs)

    @admin.display(description="Como aparece")
    def amostra(self, obj):
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:999px;'
            'font-size:11px;font-weight:700;text-transform:uppercase;'
            'text-shadow:0 0 2px rgba(0,0,0,.35)">{}</span>',
            obj.cor,
            obj.nome,
        )


@admin.register(AparenciaPrioridade)
class AparenciaPrioridadeAdmin(_AparenciaAdmin):
    chave = "prioridade"

    class form(_CorForm):
        class Meta(_CorForm.Meta):
            model = AparenciaPrioridade

    def get_changelist_form(self, request, **kwargs):
        kwargs.setdefault("form", self.form)
        return super().get_changelist_form(request, **kwargs)

    @admin.display(description="Como aparece")
    def amostra(self, obj):
        return format_html(
            '<span style="color:{};font-size:18px">&#9873;</span> {}', obj.cor, obj.nome
        )

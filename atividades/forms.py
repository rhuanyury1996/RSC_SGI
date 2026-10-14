from django import forms
from django.utils import timezone

from crm.models import ItemLista, TipoLista
from funcionarios.models import Funcionario

from .models import AtividadeDiaria, PrioridadeAtividade, StatusAtividade
from .permissions import (
    funcionarios_atribuiveis,
    funcionarios_para_equipe,
    pode_dirigir_atividades,
)


def queryset_clientes_rsc():
    return ItemLista.objects.filter(
        tipo=TipoLista.CLIENTES_RSC, ativo=True
    ).order_by("ordem", "nome")


class AtividadeForm(forms.ModelForm):
    class Meta:
        model = AtividadeDiaria
        fields = (
            "titulo",
            "descricao",
            "cliente_rsc",
            "responsavel",
            "participantes",
            "status",
            "prioridade",
            "quadrante",
            "planejado_para",
            "hora_inicio",
            "hora_fim",
            "data_vencimento",
        )
        widgets = {
            "titulo": forms.TextInput(
                attrs={"placeholder": "Nome da tarefa", "autocomplete": "off"}
            ),
            "descricao": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Descrição opcional"}
            ),
            "planejado_para": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date"}
            ),
            "data_vencimento": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date"}
            ),
            "hora_inicio": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
            "hora_fim": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        }

    def __init__(self, *args, ator=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.ator = ator
        self.fields["descricao"].required = False
        self.fields["cliente_rsc"].required = False
        self.fields["cliente_rsc"].queryset = queryset_clientes_rsc()
        self.fields["cliente_rsc"].empty_label = "RSC"
        self.fields["cliente_rsc"].label = "Empresa"
        self.fields["participantes"].required = False
        self.fields["participantes"].label = "Equipe (grupo)"
        self.fields["participantes"].help_text = (
            "Selecione outras pessoas que trabalham nesta tarefa."
        )
        self.fields["participantes"].widget.attrs.update(
            {"class": "cu-select-equipe", "size": "4"}
        )
        self.fields["planejado_para"].required = True
        self.fields["data_vencimento"].required = False
        self.fields["hora_inicio"].required = False
        self.fields["hora_fim"].required = False
        self.fields["quadrante"].required = False
        self.fields["planejado_para"].input_formats = ["%Y-%m-%d"]
        self.fields["data_vencimento"].input_formats = ["%Y-%m-%d"]
        self.fields["hora_inicio"].input_formats = ["%H:%M", "%H:%M:%S"]
        self.fields["hora_fim"].input_formats = ["%H:%M", "%H:%M:%S"]
        self.fields["planejado_para"].label = "Data"
        self.fields["hora_inicio"].label = "Início"
        self.fields["hora_fim"].label = "Fim"
        if ator is not None:
            self.fields["responsavel"].queryset = funcionarios_atribuiveis(ator)
            self.fields["responsavel"].empty_label = "Selecione o responsável"
            self.fields["participantes"].queryset = funcionarios_para_equipe(
                ator
            ).exclude(pk=ator.pk)
            if self.instance and self.instance.pk and self.instance.responsavel_id:
                self.fields["participantes"].queryset = funcionarios_para_equipe(
                    ator
                ).exclude(pk=self.instance.responsavel_id)
            if not pode_dirigir_atividades(ator):
                self.fields["responsavel"].initial = ator.pk
                self.fields["responsavel"].widget = forms.HiddenInput()
            else:
                self.fields["responsavel"].required = True
                self.fields["responsavel"].widget.attrs.update(
                    {"class": "cu-select-resp"}
                )
        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault("planejado_para", timezone.localdate())
            self.initial.setdefault("status", StatusAtividade.NAO_INICIADO)
            self.initial.setdefault("prioridade", PrioridadeAtividade.MEDIA)
            if ator is not None and not pode_dirigir_atividades(ator):
                self.initial.setdefault("responsavel", ator.pk)

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("hora_inicio")
        fim = cleaned.get("hora_fim")
        if inicio and fim and fim <= inicio:
            self.add_error("hora_fim", "O fim deve ser depois do início.")
        return cleaned


class AtividadeRapidaForm(forms.Form):
    titulo = forms.CharField(
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Adicionar tarefa",
                "autocomplete": "off",
                "class": "cu-quick-input",
            }
        ),
    )
    status = forms.ChoiceField(
        choices=StatusAtividade.choices,
        initial=StatusAtividade.NAO_INICIADO,
        required=False,
        widget=forms.HiddenInput(),
    )
    prioridade = forms.ChoiceField(
        choices=PrioridadeAtividade.choices,
        initial=PrioridadeAtividade.MEDIA,
        required=False,
    )
    responsavel = forms.ModelChoiceField(
        queryset=Funcionario.objects.none(),
        required=False,
    )
    planejado_para = forms.DateField(
        required=False,
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
    )
    hora_inicio = forms.TimeField(
        required=False,
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    hora_fim = forms.TimeField(
        required=False,
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    data_vencimento = forms.DateField(
        required=False,
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
    )
    cliente_rsc = forms.ModelChoiceField(
        queryset=ItemLista.objects.none(),
        required=False,
        empty_label="RSC",
        label="Empresa",
    )

    def __init__(self, *args, ator=None, status_padrao=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.ator = ator
        self.fields["cliente_rsc"].queryset = queryset_clientes_rsc()
        if status_padrao:
            self.fields["status"].initial = status_padrao
        if ator is not None:
            self.fields["responsavel"].queryset = funcionarios_atribuiveis(ator)
            self.fields["responsavel"].empty_label = "Selecione o responsável"
            if not pode_dirigir_atividades(ator):
                self.fields["responsavel"].initial = ator.pk
                self.fields["responsavel"].widget = forms.HiddenInput()
            else:
                self.fields["responsavel"].required = False
                self.fields["responsavel"].initial = ator.pk
        else:
            self.fields["responsavel"].queryset = Funcionario.objects.none()

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("hora_inicio")
        fim = cleaned.get("hora_fim")
        if inicio and fim and fim <= inicio:
            self.add_error("hora_fim", "O fim deve ser depois do início.")
        return cleaned

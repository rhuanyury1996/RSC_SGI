from django import forms
from django.utils import timezone

from .models import (
    MarcacaoPonto,
    SolicitacaoDayOff,
    SolicitacaoEdicaoMarcacao,
    SolicitacaoFerias,
    TipoMarcacao,
)


class SolicitacaoExclusaoMarcacaoForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo da exclusão",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "Por que esta marcação deve ser removida?",
            }
        ),
    )

    def __init__(self, *args, exige_motivo: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.exige_motivo = exige_motivo
        self.fields["motivo"].required = exige_motivo

    def clean_motivo(self):
        motivo = (self.cleaned_data.get("motivo") or "").strip()
        if self.exige_motivo and not motivo:
            raise forms.ValidationError("Informe o motivo da exclusão.")
        return motivo


class MarcacaoPontoForm(forms.ModelForm):
    class Meta:
        model = MarcacaoPonto
        fields = ("tipo", "data_hora", "observacao")
        widgets = {
            "data_hora": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_hora"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        if not self.is_bound and not self.instance.pk:
            self.initial["data_hora"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
            self.initial["tipo"] = TipoMarcacao.ENTRADA


class SolicitacaoEdicaoMarcacaoForm(forms.ModelForm):
    class Meta:
        model = SolicitacaoEdicaoMarcacao
        fields = ("tipo_proposto", "data_hora_proposta", "observacao_proposta", "motivo")
        widgets = {
            "data_hora_proposta": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
            "motivo": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Explique o erro (ex.: bateu saída no horário errado)",
                }
            ),
            "observacao_proposta": forms.TextInput(
                attrs={"placeholder": "Opcional"}
            ),
        }
        labels = {
            "tipo_proposto": "Novo tipo",
            "data_hora_proposta": "Nova data/hora",
            "observacao_proposta": "Nova observação",
            "motivo": "Motivo da correção",
        }

    def __init__(self, *args, marcacao: MarcacaoPonto | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.marcacao = marcacao
        self.fields["data_hora_proposta"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
        ]
        if marcacao and not self.is_bound:
            self.initial.setdefault("tipo_proposto", marcacao.tipo)
            self.initial.setdefault(
                "data_hora_proposta",
                timezone.localtime(marcacao.data_hora).strftime("%Y-%m-%dT%H:%M"),
            )
            self.initial.setdefault("observacao_proposta", marcacao.observacao)

    def clean(self):
        cleaned = super().clean()
        if not self.marcacao:
            return cleaned
        tipo = cleaned.get("tipo_proposto")
        data_hora = cleaned.get("data_hora_proposta")
        obs = (cleaned.get("observacao_proposta") or "").strip()
        if (
            tipo == self.marcacao.tipo
            and data_hora
            and timezone.localtime(data_hora).replace(second=0, microsecond=0)
            == timezone.localtime(self.marcacao.data_hora).replace(second=0, microsecond=0)
            and obs == (self.marcacao.observacao or "").strip()
        ):
            raise forms.ValidationError(
                "Altere ao menos um campo da marcação para solicitar a correção."
            )
        return cleaned


class SolicitacaoFeriasForm(forms.ModelForm):
    class Meta:
        model = SolicitacaoFerias
        fields = ("data_inicio", "data_fim", "observacao")
        widgets = {
            "data_inicio": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "data_fim": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_inicio"].input_formats = ["%Y-%m-%d"]
        self.fields["data_fim"].input_formats = ["%Y-%m-%d"]

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("data_inicio")
        fim = cleaned.get("data_fim")
        if inicio and fim and fim < inicio:
            self.add_error("data_fim", "A data fim deve ser igual ou posterior ao início.")
        return cleaned


class SolicitacaoDayOffForm(forms.ModelForm):
    class Meta:
        model = SolicitacaoDayOff
        fields = ("data", "motivo")
        widgets = {
            "data": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data"].input_formats = ["%Y-%m-%d"]

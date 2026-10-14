from datetime import timedelta
from decimal import Decimal
from math import ceil

from django import forms
from django.utils import timezone

from .models import MAX_HORAS_RECUPERACAO_POR_DIA, EventoCalendario, TipoEvento
from .services import capacidade_periodo


class EventoCalendarioForm(forms.ModelForm):
    class Meta:
        model = EventoCalendario
        fields = (
            "tipo",
            "titulo",
            "motivo",
            "inicio",
            "fim",
            "dia_inteiro",
            "horas_recuperar",
            "recuperacao_inicio",
            "recuperacao_fim",
        )
        widgets = {
            "inicio": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
            "fim": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
            "recuperacao_inicio": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "recuperacao_fim": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "motivo": forms.Textarea(attrs={"rows": 3}),
            "titulo": forms.TextInput(attrs={"placeholder": "Ex.: Day off — consulta"}),
        }

    def __init__(self, *args, funcionario=None, **kwargs):
        self.funcionario = funcionario
        super().__init__(*args, **kwargs)
        self.fields["inicio"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["fim"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["recuperacao_inicio"].input_formats = ["%Y-%m-%d"]
        self.fields["recuperacao_fim"].input_formats = ["%Y-%m-%d"]
        self.fields["horas_recuperar"].required = False
        self.fields["recuperacao_inicio"].required = False
        self.fields["recuperacao_fim"].required = False
        self.fields["horas_recuperar"].help_text = (
            f"Total a recuperar. Máximo {MAX_HORAS_RECUPERACAO_POR_DIA}h por dia no período."
        )
        self.fields["recuperacao_inicio"].help_text = "Primeiro dia para recuperar horas."
        self.fields["recuperacao_fim"].help_text = (
            f"Último dia. Capacidade = dias × {MAX_HORAS_RECUPERACAO_POR_DIA}h."
        )

        if not self.is_bound:
            agora = timezone.localtime().replace(minute=0, second=0, microsecond=0)
            self.initial.setdefault("inicio", agora.strftime("%Y-%m-%dT%H:%M"))
            self.initial.setdefault(
                "fim",
                (agora.replace(hour=18) if agora.hour < 18 else agora).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
            )
            self.initial.setdefault("dia_inteiro", True)
            self.initial.setdefault("tipo", TipoEvento.DAY_OFF)

            horas_padrao = Decimal("7.00")
            if funcionario is not None:
                horas_padrao = funcionario.jornada_diaria_horas() or horas_padrao
            self.initial.setdefault("horas_recuperar", horas_padrao)

            amanha = timezone.localdate() + timedelta(days=1)
            dias_necessarios = max(
                1,
                ceil(float(horas_padrao) / float(MAX_HORAS_RECUPERACAO_POR_DIA)),
            )
            self.initial.setdefault("recuperacao_inicio", amanha.isoformat())
            self.initial.setdefault(
                "recuperacao_fim",
                (amanha + timedelta(days=dias_necessarios - 1)).isoformat(),
            )

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("inicio")
        fim = cleaned.get("fim")
        tipo = cleaned.get("tipo")
        horas = cleaned.get("horas_recuperar")
        rec_ini = cleaned.get("recuperacao_inicio")
        rec_fim = cleaned.get("recuperacao_fim")

        if inicio and fim and fim < inicio:
            self.add_error("fim", "O fim deve ser igual ou posterior ao início.")

        if tipo == TipoEvento.FERIADO:
            cleaned["dia_inteiro"] = True
            cleaned["horas_recuperar"] = None
            cleaned["recuperacao_inicio"] = None
            cleaned["recuperacao_fim"] = None
            if not cleaned.get("titulo"):
                cleaned["titulo"] = "Feriado"
            if inicio:
                # Dia inteiro no mesmo dia do início
                cleaned["fim"] = inicio.replace(
                    hour=23, minute=59, second=59, microsecond=0
                )

        if tipo == TipoEvento.DAY_OFF:
            if not cleaned.get("motivo"):
                self.add_error("motivo", "Informe o motivo do day-off.")
            if horas is None:
                self.add_error("horas_recuperar", "Informe as horas a recuperar.")
            elif horas <= 0:
                self.add_error("horas_recuperar", "Informe um valor maior que zero.")

            if not rec_ini:
                self.add_error(
                    "recuperacao_inicio",
                    "Informe o início do período de recuperação.",
                )
            if not rec_fim:
                self.add_error(
                    "recuperacao_fim",
                    "Informe o fim do período de recuperação.",
                )

            if rec_ini and rec_fim:
                if rec_fim < rec_ini:
                    self.add_error(
                        "recuperacao_fim",
                        "O fim do período deve ser igual ou posterior ao início.",
                    )
                elif inicio and rec_ini < inicio.date():
                    self.add_error(
                        "recuperacao_inicio",
                        "A recuperação deve começar na data do day-off ou depois.",
                    )
                elif horas and horas > 0:
                    capacidade = capacidade_periodo(rec_ini, rec_fim)
                    if Decimal(horas) > capacidade:
                        dias = (rec_fim - rec_ini).days + 1
                        min_dias = int(
                            (Decimal(horas) + Decimal(MAX_HORAS_RECUPERACAO_POR_DIA) - 1)
                            // Decimal(MAX_HORAS_RECUPERACAO_POR_DIA)
                        )
                        self.add_error(
                            "recuperacao_fim",
                            (
                                f"Com no máximo {MAX_HORAS_RECUPERACAO_POR_DIA}h/dia, "
                                f"{horas}h exigem pelo menos {min_dias} dia(s). "
                                f"O período atual tem {dias} dia(s) "
                                f"(capacidade {capacidade}h)."
                            ),
                        )

        if tipo == TipoEvento.REUNIAO and cleaned.get("dia_inteiro"):
            cleaned["dia_inteiro"] = False

        return cleaned

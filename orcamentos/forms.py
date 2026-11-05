"""Formulários do módulo de orçamento GEXCON."""

from __future__ import annotations

import json

from django import forms
from django.utils import timezone

from crm.models import Contato, Empresa

from .gexcon.modelos import PRODUTO_EFFECTS, PRODUTO_ER
from .models import Escopo, TabelaParametros, TipoCliente

PERIODOS_PADRAO = [3, 6, 12]


def periodos_disponiveis(ano: int) -> list[int]:
    tabela = TabelaParametros.objects.filter(ano=ano).first()
    if tabela is None:
        return list(PERIODOS_PADRAO)
    return [int(m) for m in tabela.dados.get("periodos_meses", PERIODOS_PADRAO)]


class OrcamentoForm(forms.Form):
    """Entradas do "Novo orçamento" (seção 2 do procedimento)."""

    empresa = forms.ModelChoiceField(
        label="Empresa",
        queryset=Empresa.objects.none(),
        empty_label="Selecione a empresa",
    )
    contato = forms.ModelChoiceField(
        label="Contato",
        queryset=Contato.objects.none(),
        required=False,
        empty_label="Contato principal da empresa",
    )
    escopo = forms.ChoiceField(
        label="Escopo",
        choices=Escopo.choices,
        initial=Escopo.ER,
        widget=forms.RadioSelect,
    )
    incluir_adicional = forms.BooleanField(
        label="Incluir EFFECTS (usuário adicional)", required=False, initial=True
    )
    periodos = forms.MultipleChoiceField(
        label="Períodos apresentados",
        choices=[],
        widget=forms.CheckboxSelectMultiple,
    )
    tipo_cliente = forms.ChoiceField(
        label="Tipo de cliente", choices=TipoCliente.choices, initial=TipoCliente.NOVO
    )
    vencimento_licenca = forms.DateField(
        label="Vencimento da licença atual",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Renovação: até 1 mês após o vencimento mantém o preço de renovação.",
    )
    treino_effects = forms.BooleanField(label="Treinamento EFFECTS (12 h)", required=False)
    alunos_effects = forms.IntegerField(label="Alunos", required=False, min_value=1, initial=1)
    treino_er = forms.BooleanField(
        label="Treinamento EFFECTS + RISKCURVES (18 h)", required=False
    )
    alunos_er = forms.IntegerField(label="Alunos", required=False, min_value=1, initial=1)
    data = forms.DateField(
        label="Data da proposta",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    sequencial = forms.IntegerField(
        label="Sequencial do dia",
        required=False,
        min_value=1,
        help_text="Em branco: próximo número livre do dia.",
    )

    def __init__(self, *args, pode_sobrescrever_sequencial: bool = False, edicao: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.edicao = edicao
        hoje = timezone.localdate()
        self.fields["data"].initial = hoje
        self.fields["empresa"].queryset = Empresa.objects.filter(ativa=True).order_by("nome")
        self.fields["contato"].queryset = Contato.objects.filter(ativo=True).select_related(
            "empresa"
        )
        ano = hoje.year
        if self.data.get("data"):
            try:
                ano = int(str(self.data["data"])[:4])
            except (TypeError, ValueError):
                pass
        meses = periodos_disponiveis(ano)
        self.fields["periodos"].choices = [(str(m), f"{m} meses") for m in meses]
        self.fields["periodos"].initial = [str(m) for m in meses]
        if edicao:
            # Número e data identificam a proposta: não mudam numa revisão.
            self.fields["data"].disabled = True
            self.fields["data"].help_text = "Não muda na revisão. Para outra data, emita uma nova proposta."
            self.fields.pop("sequencial", None)
        elif not pode_sobrescrever_sequencial:
            del self.fields["sequencial"]

    def clean_contato(self):
        contato = self.cleaned_data.get("contato")
        empresa = self.data.get("empresa")
        if contato and empresa and str(contato.empresa_id) != str(empresa):
            raise forms.ValidationError("Esse contato não pertence à empresa escolhida.")
        return contato

    def clean(self):
        dados = super().clean()
        treinamentos = []
        if dados.get("treino_effects"):
            treinamentos.append(
                {"produto": PRODUTO_EFFECTS, "tipo": "Online", "alunos": dados.get("alunos_effects") or 1}
            )
        if dados.get("treino_er"):
            treinamentos.append(
                {"produto": PRODUTO_ER, "tipo": "Online", "alunos": dados.get("alunos_er") or 1}
            )
        dados["treinamentos"] = treinamentos
        if dados.get("tipo_cliente") == TipoCliente.NOVO:
            dados["vencimento_licenca"] = None
        return dados

    @staticmethod
    def inicial_de(orc) -> dict:
        """Valores do formulário a partir de uma proposta já emitida."""
        treinos = {t["produto"]: t["alunos"] for t in (orc.treinamentos or [])}
        return {
            "empresa": orc.empresa_id,
            "contato": orc.contato_id,
            "escopo": orc.escopo,
            "incluir_adicional": orc.incluir_adicional,
            "periodos": [str(m) for m in orc.periodos],
            "tipo_cliente": orc.tipo_cliente_solicitado,
            "vencimento_licenca": orc.vencimento_licenca,
            "treino_effects": PRODUTO_EFFECTS in treinos,
            "alunos_effects": treinos.get(PRODUTO_EFFECTS, 1),
            "treino_er": PRODUTO_ER in treinos,
            "alunos_er": treinos.get(PRODUTO_ER, 1),
            "data": orc.data,
        }

    def dados_do_pedido(self) -> dict:
        """cleaned_data no formato que `services.calcular` / `services.emitir` esperam."""
        d = self.cleaned_data
        return {
            "empresa": d["empresa"],
            "contato": d.get("contato"),
            "escopo": d["escopo"],
            "incluir_adicional": bool(d.get("incluir_adicional")),
            "periodos": [int(m) for m in d["periodos"]],
            "tipo_cliente": d["tipo_cliente"],
            "vencimento_licenca": d.get("vencimento_licenca"),
            "treinamentos": d.get("treinamentos", []),
            "data": d["data"],
            "sequencial": d.get("sequencial"),
        }


class TabelaParametrosForm(forms.ModelForm):
    """Edição da tabela de um ano; o JSON é validado contra `Parametros`."""

    dados = forms.CharField(
        label="Parâmetros (JSON)",
        widget=forms.Textarea(attrs={"rows": 24, "spellcheck": "false", "class": "mono"}),
    )

    class Meta:
        model = TabelaParametros
        fields = ["ano", "dados"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["ano"].disabled = True
            self.initial["dados"] = json.dumps(self.instance.dados, indent=2, ensure_ascii=False)

    def clean_dados(self):
        from .gexcon.parametros import Parametros

        texto = self.cleaned_data["dados"]
        try:
            dados = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"JSON inválido: {exc}") from exc
        try:
            Parametros.de_dict(dados)
        except (KeyError, ValueError, TypeError) as exc:
            raise forms.ValidationError(f"Parâmetros incompletos: {exc}") from exc
        return dados

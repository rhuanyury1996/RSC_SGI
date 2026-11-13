"""Formulários do orçamento RAVEN."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone

from crm.models import Contato, Empresa

from .models import PagamentoRaven, TabelaRaven, TipoClienteRaven
from .raven.calculo import TRIAL


def _valor(texto) -> Decimal | None:
    if texto in (None, ""):
        return None
    limpo = str(texto).replace("R$", "").replace(" ", "")
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo)
    except InvalidOperation as exc:
        raise forms.ValidationError("Valor inválido. Use o formato 12.460,00.") from exc


def catalogo(ano: int) -> dict:
    """Planos da tabela do ano, no formato do JS do formulário."""
    tabela = TabelaRaven.objects.filter(ano=ano).first()
    if tabela is None:
        return {}
    d = tabela.dados
    return {
        "planos": d.get("planos", {}),
        "faixas": d.get("pacote_horas", []),
        "desconto": d.get("desconto_avista", 0.08),
        "parcelas": d.get("parcelas_boleto", 10),
        "trial_dias": d.get("trial_dias", 3),
        "validade": d.get("validade_dias_padrao", 30),
        "visita": d.get("horas_visita_padrao", 8),
    }


class OrcamentoRavenForm(forms.Form):
    empresa = forms.ModelChoiceField(label="Empresa", queryset=Empresa.objects.none(), empty_label="Selecione a empresa")
    contato = forms.ModelChoiceField(
        label="Contato", queryset=Contato.objects.none(), required=False, empty_label="Contato principal da empresa"
    )
    tipo_cliente = forms.ChoiceField(
        label="Tipo de cliente", choices=TipoClienteRaven.choices, initial=TipoClienteRaven.INDUSTRIA, widget=forms.RadioSelect
    )
    plano = forms.CharField(label="Plano", initial="supernova")
    vigencia = forms.IntegerField(label="Vigência (meses)", required=False, initial=6)
    valor_licenca = forms.CharField(
        label="Valor da licença (R$)", required=False, help_text="Em branco: valor de tabela. Preencha para condição negociada."
    )
    implantacao = forms.BooleanField(label="Implantação em campo (somente indústrias)", required=False)
    valor_implantacao = forms.CharField(label="Valor da implantação (R$)", required=False)
    horas_visita = forms.IntegerField(label="Duração da visita (h)", required=False, min_value=1, max_value=80)
    cidade_visita = forms.CharField(
        label="Cidade/UF da visita", required=False, max_length=120, help_text="Em branco: cidade/UF da empresa no CRM."
    )
    horas_pacote = forms.IntegerField(
        label="Pacote de horas (cadastros e estudos)", required=False, min_value=0, max_value=2000,
        help_text="0 ou em branco: sem pacote. O cliente lança os dados, a menos que contrate o pacote.",
    )
    pagamento = forms.ChoiceField(label="Pagamento", choices=PagamentoRaven.choices, initial=PagamentoRaven.VISTA, widget=forms.RadioSelect)
    validade_dias = forms.IntegerField(label="Validade (dias)", required=False, min_value=1, max_value=365)
    data = forms.DateField(label="Data da proposta", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    sequencial = forms.IntegerField(label="Sequencial do dia", required=False, min_value=1, help_text="Em branco: próximo número livre do dia.")

    def __init__(self, *args, pode_sobrescrever_sequencial: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = timezone.localdate()
        self.fields["data"].initial = hoje
        self.fields["empresa"].queryset = Empresa.objects.filter(ativa=True).order_by("nome")
        self.fields["contato"].queryset = Contato.objects.filter(ativo=True).select_related("empresa")
        ano = hoje.year
        if self.data.get("data"):
            try:
                ano = int(str(self.data["data"])[:4])
            except (TypeError, ValueError):
                pass
        self.catalogo = catalogo(ano)
        self.fields["validade_dias"].initial = self.catalogo.get("validade", 30)
        self.fields["horas_visita"].initial = self.catalogo.get("visita", 8)
        if not pode_sobrescrever_sequencial:
            del self.fields["sequencial"]

    def catalogo_json(self) -> str:
        return json.dumps(self.catalogo, ensure_ascii=False)

    def clean_valor_licenca(self):
        return _valor(self.cleaned_data.get("valor_licenca"))

    def clean_valor_implantacao(self):
        return _valor(self.cleaned_data.get("valor_implantacao"))

    def clean_contato(self):
        contato = self.cleaned_data.get("contato")
        empresa = self.data.get("empresa")
        if contato and empresa and str(contato.empresa_id) != str(empresa):
            raise forms.ValidationError("Esse contato não pertence à empresa escolhida.")
        return contato

    def clean(self):
        dados = super().clean()
        tipo = dados.get("tipo_cliente")
        plano = dados.get("plano")
        planos = (self.catalogo.get("planos") or {}).get(tipo or "", {})
        if plano and plano != TRIAL and plano not in planos:
            self.add_error("plano", "Escolha um plano do tipo de cliente selecionado.")
        if plano != TRIAL and not dados.get("vigencia"):
            self.add_error("vigencia", "Escolha a vigência.")
        if tipo == TipoClienteRaven.CONSULTORIA:
            dados["implantacao"] = False
        return dados

    def dados_do_pedido(self) -> dict:
        d = self.cleaned_data
        return {
            "empresa": d["empresa"],
            "contato": d.get("contato"),
            "tipo_cliente": d["tipo_cliente"],
            "plano": d["plano"],
            "vigencia": d.get("vigencia") or 0,
            "valor_licenca": d.get("valor_licenca"),
            "implantacao": bool(d.get("implantacao")),
            "valor_implantacao": d.get("valor_implantacao"),
            "horas_visita": d.get("horas_visita"),
            "cidade_visita": d.get("cidade_visita") or "",
            "horas_pacote": d.get("horas_pacote") or 0,
            "pagamento": d.get("pagamento") or PagamentoRaven.VISTA,
            "validade_dias": d.get("validade_dias"),
            "data": d["data"],
            "sequencial": d.get("sequencial"),
        }


class TabelaRavenForm(forms.ModelForm):
    dados = forms.CharField(
        label="Planos e preços (JSON)",
        widget=forms.Textarea(attrs={"rows": 24, "spellcheck": "false", "class": "mono"}),
    )

    class Meta:
        model = TabelaRaven
        fields = ["ano", "dados"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["ano"].disabled = True
            self.initial["dados"] = json.dumps(self.instance.dados, indent=2, ensure_ascii=False)

    def clean_dados(self):
        from .raven.calculo import ParametrosRaven

        try:
            dados = json.loads(self.cleaned_data["dados"])
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"JSON inválido: {exc}") from exc
        try:
            ParametrosRaven.de_dict(dados)
        except (KeyError, ValueError, TypeError) as exc:
            raise forms.ValidationError(f"Parâmetros incompletos: {exc}") from exc
        return dados

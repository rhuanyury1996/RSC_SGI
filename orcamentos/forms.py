"""Formulários do módulo de orçamento GEXCON."""

from __future__ import annotations

import json

from django import forms
from django.utils import timezone

from crm.models import Contato, Empresa

from .gexcon.modelos import PRODUTO_EFFECTS, PRODUTO_ER
from .gexcon.precos import rotulo_periodo
from .models import Escopo, TabelaParametros, TipoCliente

PERIODOS_PADRAO = [3, 6, 12]


CATEGORIAS_PADRAO = {"comercial": {"nome": "Comercial", "desconto": 0}}


def opcoes_da_tabela(ano: int) -> dict:
    """Durações, padrão e categorias de licença da tabela do ano (ou o padrão 2026)."""
    tabela = TabelaParametros.objects.filter(ano=ano).first()
    dados = tabela.dados if tabela else {}
    padrao = [int(m) for m in dados.get("periodos_meses", PERIODOS_PADRAO)]
    return {
        "periodos": sorted(int(m) for m in dados.get("periodos_disponiveis", padrao)),
        "padrao": padrao,
        "maximo": int(dados.get("max_periodos_por_proposta", 3)),
        "categorias": dados.get("categorias_licenca", CATEGORIAS_PADRAO),
        "tem_dongle": "Dongle" in dados.get("itens_opcionais", {}),
    }


def periodos_disponiveis(ano: int) -> list[int]:
    return opcoes_da_tabela(ano)["periodos"]


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
    categoria_licenca = forms.ChoiceField(
        label="Categoria de licença",
        choices=[],
        initial="comercial",
        required=False,
        widget=forms.RadioSelect,
        help_text="Desconto do Price Builder sobre a lista (somado ao fator Brasil).",
    )
    unidades = forms.IntegerField(
        label="Licenças por módulo",
        min_value=1,
        max_value=99,
        initial=1,
        required=False,
        help_text="Usuários simultâneos (Concurrent) de cada módulo.",
    )
    dongles = forms.IntegerField(
        label="Dongles (chave física)",
        min_value=0,
        max_value=99,
        initial=0,
        required=False,
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

    def __init__(self, *args, pode_sobrescrever_sequencial: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
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
        opcoes = opcoes_da_tabela(ano)
        self.maximo_periodos = opcoes["maximo"]
        self.fields["periodos"].choices = [(str(m), rotulo_periodo(m)) for m in opcoes["periodos"]]
        self.fields["periodos"].initial = [str(m) for m in opcoes["padrao"]]
        self.fields["periodos"].help_text = (
            f"Até {opcoes['maximo']} por proposta. Acima de 1 ano, o preço é a soma dos anos, "
            "com reajuste multi-ano a partir do 2º ano."
        )
        self.fields["categoria_licenca"].choices = [
            (chave, f"{cat['nome']}" + (f" ({float(cat['desconto']) * 100:.0f}% de desconto)" if float(cat["desconto"]) else ""))
            # Do menor para o maior desconto (o JSON do banco não guarda a ordem).
            for chave, cat in sorted(opcoes["categorias"].items(), key=lambda kv: float(kv[1]["desconto"]))
        ]
        if not opcoes["tem_dongle"]:
            del self.fields["dongles"]
        if not pode_sobrescrever_sequencial:
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
        periodos = dados.get("periodos") or []
        if len(periodos) > getattr(self, "maximo_periodos", 3):
            self.add_error("periodos", f"Escolha até {self.maximo_periodos} períodos.")
        if dados.get("tipo_cliente") == TipoCliente.NOVO:
            dados["vencimento_licenca"] = None
        return dados

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
            "categoria_licenca": d.get("categoria_licenca") or "comercial",
            "unidades": d.get("unidades") or 1,
            "dongles": d.get("dongles") or 0,
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

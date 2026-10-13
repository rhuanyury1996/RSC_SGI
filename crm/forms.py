from django import forms

from funcionarios.models import Funcionario

from .models import (
    ClassificacaoUnidade,
    Contato,
    Empresa,
    EtapaFunil,
    FormaContato,
    Funil,
    ItemLista,
    MotivoFaltaRetorno,
    Oportunidade,
    TipoLista,
    TipoSubfunil,
)


def _queryset_clientes_rsc():
    return ItemLista.objects.filter(tipo=TipoLista.CLIENTES_RSC, ativo=True).order_by(
        "ordem", "nome"
    )


SIM_NAO = (
    ("", "Escolha uma opção"),
    ("true", "Sim"),
    ("false", "Não"),
)


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = (
            "nome",
            "site",
            "nicho",
            "classificacao_unidade",
            "telefone_portaria",
            "telefone_portaria_2",
            "email_geral",
            "cidade",
            "estado",
            "clientes_rsc",
        )
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Digite aqui..."}),
            "site": forms.URLInput(
                attrs={"placeholder": "https://...", "inputmode": "url"}
            ),
            "nicho": forms.Select(),
            "classificacao_unidade": forms.Select(),
            "telefone_portaria": forms.TextInput(
                attrs={
                    "placeholder": "(99) 99999-9999",
                    "class": "js-phone-mask",
                    "inputmode": "tel",
                }
            ),
            "telefone_portaria_2": forms.TextInput(
                attrs={
                    "placeholder": "(99) 99999-9999",
                    "class": "js-phone-mask",
                    "inputmode": "tel",
                }
            ),
            "email_geral": forms.EmailInput(attrs={"placeholder": "Digite aqui..."}),
            "cidade": forms.TextInput(attrs={"placeholder": "Digite aqui..."}),
            "estado": forms.Select(),
            "clientes_rsc": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nicho"].queryset = ItemLista.objects.filter(
            tipo=TipoLista.NICHO_MERCADOLOGICO, ativo=True
        )
        self.fields["nicho"].empty_label = "Escolha uma opção"
        self.fields["classificacao_unidade"].choices = [
            ("", "Escolha uma opção"),
            *ClassificacaoUnidade.choices,
        ]
        self.fields["estado"].empty_label = "Escolha uma opção"
        self.fields["clientes_rsc"].queryset = _queryset_clientes_rsc()
        self.fields["clientes_rsc"].required = False
        self.fields["clientes_rsc"].label = "Visível para clientes RSC"
        for name in (
            "site",
            "nicho",
            "classificacao_unidade",
            "telefone_portaria",
            "telefone_portaria_2",
            "email_geral",
            "cidade",
            "estado",
        ):
            self.fields[name].required = False

    def clean_site(self):
        site = (self.cleaned_data.get("site") or "").strip()
        if site and not site.startswith(("http://", "https://")):
            site = f"https://{site}"
        return site


class ItemListaForm(forms.ModelForm):
    class Meta:
        model = ItemLista
        fields = ("tipo", "nome", "ordem", "ativo")
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Nome do item"}),
            "ordem": forms.NumberInput(attrs={"min": 0}),
        }


class ContatoForm(forms.ModelForm):
    class Meta:
        model = Contato
        fields = (
            "nome",
            "sobrenome",
            "email",
            "telefone_ramal",
            "telefone_whatsapp",
            "responsavel",
            "empresa",
            "clientes_rsc",
        )
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Digite aqui..."}),
            "sobrenome": forms.TextInput(attrs={"placeholder": "Digite aqui..."}),
            "email": forms.EmailInput(attrs={"placeholder": "Digite aqui..."}),
            "telefone_ramal": forms.TextInput(
                attrs={
                    "placeholder": "(99) 99999-9999",
                    "class": "js-phone-mask",
                    "inputmode": "tel",
                }
            ),
            "telefone_whatsapp": forms.TextInput(
                attrs={
                    "placeholder": "(99) 99999-9999",
                    "class": "js-phone-mask",
                    "inputmode": "tel",
                }
            ),
            "empresa": forms.Select(),
            "clientes_rsc": forms.CheckboxSelectMultiple,
        }
        help_texts = {
            "empresa": "Empresa na qual o contato trabalha",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = Empresa.objects.filter(ativa=True).order_by("nome")
        self.fields["empresa"].empty_label = "Escolha uma empresa"
        self.fields["responsavel"].queryset = Funcionario.objects.filter(ativo=True).order_by(
            "nome", "sobrenome"
        )
        self.fields["responsavel"].empty_label = "Adicionar responsável"
        self.fields["responsavel"].required = False
        self.fields["clientes_rsc"].queryset = _queryset_clientes_rsc()
        self.fields["clientes_rsc"].required = False
        self.fields["clientes_rsc"].label = "Visível para clientes RSC"
        self.fields["sobrenome"].required = False
        self.fields["email"].required = False
        self.fields["telefone_ramal"].required = False
        self.fields["telefone_whatsapp"].required = False


class FunilForm(forms.ModelForm):
    class Meta:
        model = Funil
        fields = ("nome", "descricao")
        widgets = {
            "nome": forms.TextInput(
                attrs={"placeholder": "Ex.: Vendas RSC, Expansão BlendDyn…"}
            ),
            "descricao": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Objetivo deste funil (opcional)",
                }
            ),
        }


class EtapaFunilForm(forms.ModelForm):
    class Meta:
        model = EtapaFunil
        fields = ("nome", "ordem")
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Nome da etapa"}),
            "ordem": forms.NumberInput(attrs={"min": 0}),
        }


class OportunidadeForm(forms.ModelForm):
    class Meta:
        model = Oportunidade
        fields = ("funil", "etapa", "empresa", "titulo", "valor", "responsavel")
        widgets = {
            "valor": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "placeholder": "0,00"}
            ),
            "titulo": forms.TextInput(
                attrs={"placeholder": "Ex.: Projeto BlendDyn — Acme"}
            ),
            "empresa": forms.Select(),
            "etapa": forms.Select(),
        }

    def __init__(self, *args, funil: Funil | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = Empresa.objects.filter(ativa=True).order_by("nome")
        self.fields["empresa"].empty_label = "Escolha uma empresa"
        self.fields["responsavel"].queryset = Funcionario.objects.filter(ativo=True).order_by(
            "nome", "sobrenome"
        )
        self.fields["responsavel"].empty_label = "Responsável"
        self.fields["responsavel"].required = False
        self.fields["valor"].required = False
        self.fields["etapa"].required = False

        if funil is not None:
            self.fields["funil"].initial = funil.pk
            self.fields["funil"].widget = forms.HiddenInput()
            self.fields["etapa"].queryset = funil.etapas.all()
            primeira = funil.etapas.first()
            if primeira and not self.is_bound:
                self.initial.setdefault("etapa", primeira.pk)
        elif self.instance.pk and self.instance.funil_id:
            self.fields["etapa"].queryset = self.instance.funil.etapas.all()
        else:
            self.fields["etapa"].queryset = EtapaFunil.objects.none()

    def clean(self):
        cleaned = super().clean()
        funil = cleaned.get("funil")
        etapa = cleaned.get("etapa")
        if etapa and funil and etapa.funil_id != funil.pk:
            self.add_error("etapa", "A etapa não pertence ao funil selecionado.")
        return cleaned


class CardPreVendasForm(forms.ModelForm):
    contato_sucesso = forms.ChoiceField(
        label="Contato com sucesso?",
        choices=SIM_NAO,
        required=False,
    )
    existe_demanda = forms.ChoiceField(
        label="Existe alguma demanda?",
        choices=SIM_NAO,
        required=False,
    )
    formas_contato = forms.MultipleChoiceField(
        label="Formas de contato",
        choices=FormaContato.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Oportunidade
        fields = (
            "empresa",
            "contato",
            "contato_sucesso",
            "existe_demanda",
            "dores_identificadas",
            "data_retorno_envio",
            "formas_contato",
            "motivo_falta_retorno",
            "data_retorno",
            "motivo_sem_oportunidade",
            "escopo_solicitado",
            "funil_venda",
            "responsavel",
            "etapa",
            "observacoes",
        )
        widgets = {
            "dores_identificadas": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Quais dores foram identificadas?"}
            ),
            "data_retorno_envio": forms.DateInput(attrs={"type": "date"}),
            "data_retorno": forms.DateInput(attrs={"type": "date"}),
            "motivo_falta_retorno": forms.Select(),
            "motivo_sem_oportunidade": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Por que não há oportunidade?"}
            ),
            "escopo_solicitado": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Descreva o escopo solicitado"}
            ),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, funil: Funil | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.funil = funil

        self.fields["empresa"].queryset = Empresa.objects.filter(ativa=True).order_by("nome")
        self.fields["empresa"].empty_label = "Selecione a empresa cadastrada"
        self.fields["empresa"].required = True

        empresa_id = None
        if self.is_bound:
            empresa_id = self.data.get("empresa") or None
        elif self.instance.pk and self.instance.empresa_id:
            empresa_id = self.instance.empresa_id
        elif self.initial.get("empresa"):
            empresa_id = self.initial.get("empresa")

        contatos = Contato.objects.filter(ativo=True).select_related("empresa").order_by(
            "nome", "sobrenome"
        )
        if empresa_id:
            contatos = contatos.filter(empresa_id=empresa_id)
        self.fields["contato"].queryset = contatos
        self.fields["contato"].required = True
        self.fields["contato"].empty_label = "Selecione o contato cadastrado"
        self.fields["contato"].help_text = "Apenas contatos já cadastrados na empresa."

        self.fields["responsavel"].queryset = Funcionario.objects.filter(ativo=True).order_by(
            "nome", "sobrenome"
        )
        self.fields["responsavel"].required = False
        self.fields["responsavel"].empty_label = "Responsável"

        funis_venda = Funil.objects.filter(ativo=True, tipo=TipoSubfunil.NEGOCIACOES)
        if funil and funil.cliente_rsc_id:
            funis_venda = funis_venda.filter(cliente_rsc=funil.cliente_rsc)
        self.fields["funil_venda"].queryset = funis_venda.order_by("nome")
        self.fields["funil_venda"].required = False
        self.fields["funil_venda"].empty_label = "Selecione o funil de venda"
        self.fields["funil_venda"].label = "Selecione o funil de venda"
        self.fields["motivo_falta_retorno"].choices = [
            ("", "Selecione o motivo"),
            *MotivoFaltaRetorno.choices,
        ]

        for name in (
            "dores_identificadas",
            "data_retorno_envio",
            "formas_contato",
            "motivo_falta_retorno",
            "data_retorno",
            "motivo_sem_oportunidade",
            "escopo_solicitado",
            "observacoes",
            "etapa",
        ):
            self.fields[name].required = False

        if self.instance.pk:
            if self.instance.contato_sucesso is True:
                self.initial.setdefault("contato_sucesso", "true")
            elif self.instance.contato_sucesso is False:
                self.initial.setdefault("contato_sucesso", "false")
            if self.instance.existe_demanda is True:
                self.initial.setdefault("existe_demanda", "true")
            elif self.instance.existe_demanda is False:
                self.initial.setdefault("existe_demanda", "false")
            formas = self.instance.formas_contato or []
            if isinstance(formas, str):
                formas = [v.strip() for v in formas.split(",") if v.strip()]
            self.initial.setdefault("formas_contato", formas)

        if funil is not None:
            self.fields["etapa"].queryset = funil.etapas.order_by("ordem")
            primeira = funil.etapas.order_by("ordem").first()
            if primeira and not self.is_bound and not self.instance.pk:
                self.initial.setdefault("etapa", primeira.pk)
        elif self.instance.pk and self.instance.funil_id:
            self.fields["etapa"].queryset = self.instance.funil.etapas.order_by("ordem")
        else:
            self.fields["etapa"].queryset = EtapaFunil.objects.none()

    def _bool_from_choice(self, value):
        if value == "true":
            return True
        if value == "false":
            return False
        return None

    def clean_contato(self):
        contato = self.cleaned_data.get("contato")
        empresa = self.cleaned_data.get("empresa")
        if contato and empresa and contato.empresa_id != empresa.pk:
            raise forms.ValidationError("O contato precisa pertencer à empresa selecionada.")
        return contato

    def clean_formas_contato(self):
        return list(self.cleaned_data.get("formas_contato") or [])

    def clean(self):
        cleaned = super().clean()
        cleaned["contato_sucesso"] = self._bool_from_choice(cleaned.get("contato_sucesso"))
        cleaned["existe_demanda"] = self._bool_from_choice(cleaned.get("existe_demanda"))
        return cleaned

    def save(self, commit=True):
        opp = super().save(commit=False)
        opp.contato_sucesso = self.cleaned_data.get("contato_sucesso")
        opp.existe_demanda = self.cleaned_data.get("existe_demanda")
        opp.formas_contato = self.cleaned_data.get("formas_contato") or []
        if opp.empresa_id and not opp.titulo:
            opp.titulo = ""
        if commit:
            opp.save()
            self.save_m2m()
        return opp

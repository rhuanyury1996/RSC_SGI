from django import forms

from .models import CategoriaInformativo, Informativo


class InformativoForm(forms.ModelForm):
    class Meta:
        model = Informativo
        fields = ("categoria", "conteudo")
        widgets = {
            "categoria": forms.RadioSelect,
            "conteudo": forms.Textarea(
                attrs={
                    "rows": 4,
                    "maxlength": 2000,
                    "placeholder": "O que você quer comunicar ao time?",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].choices = CategoriaInformativo.choices
        self.fields["conteudo"].label = "Mensagem"

    def clean_conteudo(self):
        texto = (self.cleaned_data.get("conteudo") or "").strip()
        if len(texto) < 3:
            raise forms.ValidationError("Escreva uma mensagem um pouco mais completa.")
        if len(texto) > 2000:
            raise forms.ValidationError("A mensagem pode ter no máximo 2000 caracteres.")
        return texto

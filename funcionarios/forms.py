from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from .models import Funcionario, SignoSolar, signo_solar_por_data

User = get_user_model()


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Usuário",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "autofocus": True,
                "placeholder": "seu.usuario",
            }
        ),
    )
    password = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "••••••••",
            }
        ),
    )


class PerfilForm(forms.ModelForm):
    """Campos que o próprio funcionário pode editar."""

    class Meta:
        model = Funcionario
        fields = (
            "nome",
            "sobrenome",
            "data_nascimento",
            "signo_solar",
            "foto_perfil",
            "trabalha_segunda",
            "trabalha_terca",
            "trabalha_quarta",
            "trabalha_quinta",
            "trabalha_sexta",
            "hora_entrada",
            "hora_saida",
            "intervalo_almoco_minutos",
        )
        widgets = {
            "data_nascimento": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "signo_solar": forms.RadioSelect(attrs={"class": "signo-radios"}),
            "hora_entrada": forms.TimeInput(attrs={"type": "time"}),
            "hora_saida": forms.TimeInput(attrs={"type": "time"}),
            "intervalo_almoco_minutos": forms.NumberInput(
                attrs={"min": 0, "max": 240, "step": 5}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_nascimento"].input_formats = ["%Y-%m-%d"]
        self.fields["hora_entrada"].input_formats = ["%H:%M", "%H:%M:%S"]
        self.fields["hora_saida"].input_formats = ["%H:%M", "%H:%M:%S"]
        self.fields["signo_solar"].required = False
        self.fields["signo_solar"].choices = [("", "Não informar")] + list(
            SignoSolar.choices
        )
        if not self.instance.signo_solar and self.instance.data_nascimento:
            sugerido = signo_solar_por_data(self.instance.data_nascimento)
            self.fields["signo_solar"].help_text = (
                f"Sugestão pela data de nascimento: {SignoSolar(sugerido).label}."
            )
            if not self.is_bound:
                self.initial.setdefault("signo_solar", sugerido)

    def clean(self):
        cleaned = super().clean()
        dias = [
            cleaned.get("trabalha_segunda"),
            cleaned.get("trabalha_terca"),
            cleaned.get("trabalha_quarta"),
            cleaned.get("trabalha_quinta"),
            cleaned.get("trabalha_sexta"),
        ]
        if not any(dias):
            raise forms.ValidationError(
                "Selecione ao menos um dia de trabalho entre segunda e sexta."
            )
        entrada = cleaned.get("hora_entrada")
        saida = cleaned.get("hora_saida")
        if entrada and saida and saida <= entrada:
            self.add_error("hora_saida", "A saída deve ser posterior à entrada.")
        return cleaned

    def clean_foto_perfil(self):
        from django.core.exceptions import ValidationError

        from .avatar import encode_avatar

        foto = self.cleaned_data.get("foto_perfil")
        self._foto_perfil_data = None
        self._limpar_foto = False
        if foto is False:
            self._limpar_foto = True
            return foto
        if foto:
            try:
                self._foto_perfil_data = encode_avatar(foto)
            except Exception as exc:
                raise ValidationError(
                    "Não foi possível processar a imagem. Use JPG ou PNG."
                ) from exc
        return foto

    def save(self, commit=True):
        instance = super().save(commit=False)
        if getattr(self, "_limpar_foto", False):
            instance.foto_perfil = None
            instance.foto_perfil_data = ""
        elif getattr(self, "_foto_perfil_data", None):
            instance.foto_perfil_data = self._foto_perfil_data
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class AlterarSenhaForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Senha atual"
        self.fields["new_password1"].label = "Nova senha"
        self.fields["new_password2"].label = "Confirmar nova senha"


class FuncionarioAdminForm(forms.ModelForm):
    criar_acesso = forms.BooleanField(
        label="Criar acesso de login",
        required=False,
        initial=True,
        help_text="Gera um usuário para o funcionário entrar no sistema.",
    )
    username = forms.CharField(
        label="Usuário de login",
        required=False,
        max_length=150,
        help_text="Se vazio, será gerado a partir do nome e sobrenome.",
    )
    senha_inicial = forms.CharField(
        label="Senha inicial",
        required=False,
        widget=forms.PasswordInput(render_value=True),
        help_text="Obrigatória ao criar acesso. O funcionário poderá alterá-la no perfil.",
    )

    class Meta:
        model = Funcionario
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and self.instance.usuario_id:
            return cleaned

        criar = cleaned.get("criar_acesso")
        senha = cleaned.get("senha_inicial")
        username = (cleaned.get("username") or "").strip()

        if criar:
            if not senha:
                self.add_error("senha_inicial", "Informe a senha inicial para criar o acesso.")
            if username and User.objects.filter(username__iexact=username).exists():
                self.add_error("username", "Este usuário de login já existe.")
        return cleaned

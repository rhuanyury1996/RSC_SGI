from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from django.utils.text import slugify

from .forms import FuncionarioAdminForm
from .acessos import CAMPOS_ACESSO
from .models import AcessoModulo, Funcionario

User = get_user_model()


@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
    form = FuncionarioAdminForm
    list_display = (
        "foto_miniatura",
        "nome",
        "sobrenome",
        "cargo",
        "setor",
        "centro_custo",
        "responde_a",
        "usuario",
        "ativo",
    )
    list_display_links = ("nome", "sobrenome")
    list_filter = ("cargo", "setor", "centro_custo", "ativo")
    search_fields = ("nome", "sobrenome", "usuario__username")
    autocomplete_fields = ("responde_a",)
    readonly_fields = ("foto_preview", "usuario", "criado_em", "atualizado_em")
    fieldsets = (
        (
            "Dados pessoais",
            {
                "fields": (
                    "nome",
                    "sobrenome",
                    "data_nascimento",
                    "signo_solar",
                    "foto_perfil",
                    "foto_preview",
                )
            },
        ),
        (
            "Organização",
            {
                "fields": (
                    "cargo",
                    "setor",
                    "responde_a",
                    "centro_custo",
                )
            },
        ),
        (
            "Jornada de trabalho",
            {
                "fields": (
                    (
                        "trabalha_segunda",
                        "trabalha_terca",
                        "trabalha_quarta",
                        "trabalha_quinta",
                        "trabalha_sexta",
                    ),
                    "hora_entrada",
                    "hora_saida",
                    "intervalo_almoco_minutos",
                )
            },
        ),
        (
            "Módulos que pode acessar",
            {
                "fields": CAMPOS_ACESSO,
                "description": "Sem acesso: some do menu e a URL é bloqueada. Só ver: abre, mas não salva nada.",
            },
        ),
        (
            "Acesso ao sistema",
            {
                "fields": (
                    "usuario",
                    "criar_acesso",
                    "username",
                    "senha_inicial",
                    "ativo",
                    "criado_em",
                    "atualizado_em",
                )
            },
        ),
    )

    @admin.display(description="Foto")
    def foto_miniatura(self, obj: Funcionario):
        if obj.tem_foto:
            return format_html(
                '<img src="{}" style="width:40px;height:40px;object-fit:cover;border-radius:50%;" />',
                obj.foto_url,
            )
        return "—"

    @admin.display(description="Pré-visualização")
    def foto_preview(self, obj: Funcionario):
        if obj.pk and obj.tem_foto:
            return format_html(
                '<img src="{}" style="max-width:180px;max-height:180px;object-fit:cover;border-radius:8px;" />',
                obj.foto_url,
            )
        return "Nenhuma foto enviada"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("usuario", "responde_a")

    def save_model(self, request, obj, form, change):
        from django.core.files.uploadedfile import UploadedFile

        from .avatar import encode_avatar

        foto = form.cleaned_data.get("foto_perfil") if form is not None else None
        if foto is False:
            if obj.foto_perfil:
                obj.foto_perfil.delete(save=False)
            obj.foto_perfil = None
            obj.foto_perfil_data = ""
        elif isinstance(foto, UploadedFile):
            obj.foto_perfil_data = encode_avatar(foto)
            if obj.foto_perfil:
                obj.foto_perfil.delete(save=False)
            obj.foto_perfil = None

        super().save_model(request, obj, form, change)

        if obj.usuario_id:
            return

        if not form.cleaned_data.get("criar_acesso"):
            return

        username = (form.cleaned_data.get("username") or "").strip()
        if not username:
            base = slugify(f"{obj.nome}.{obj.sobrenome}").replace("-", ".") or f"user{obj.pk}"
            username = base
            suffix = 1
            while User.objects.filter(username__iexact=username).exists():
                suffix += 1
                username = f"{base}{suffix}"

        senha = form.cleaned_data["senha_inicial"]
        user = User.objects.create_user(
            username=username,
            password=senha,
            first_name=obj.nome,
            last_name=obj.sobrenome,
            is_staff=False,
            is_active=obj.ativo,
        )
        obj.usuario = user
        obj.save(update_fields=["usuario"])


@admin.register(AcessoModulo)
class AcessoModuloAdmin(admin.ModelAdmin):
    """Matriz: cada linha um funcionário, cada coluna um módulo. Edita direto na lista."""

    list_display = ("nome_completo_col", "setor", "usuario") + CAMPOS_ACESSO
    list_editable = CAMPOS_ACESSO
    list_display_links = ("nome_completo_col",)
    list_filter = ("setor", "cargo") + CAMPOS_ACESSO
    search_fields = ("nome", "sobrenome", "usuario__username")
    list_per_page = 100
    actions = ["liberar_tudo", "bloquear_comercial"]
    fields = ("nome", "sobrenome", "setor") + CAMPOS_ACESSO
    readonly_fields = ("nome", "sobrenome", "setor")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(ativo=True).select_related("usuario")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Funcionário", ordering="nome")
    def nome_completo_col(self, obj):
        return obj.nome_completo

    @admin.action(description="Liberar todos os módulos (ver e editar)")
    def liberar_tudo(self, request, queryset):
        n = queryset.update(**{c: "editar" for c in CAMPOS_ACESSO})
        self.message_user(request, f"{n} funcionário(s) com acesso total.")

    @admin.action(description="Tirar acesso ao Comercial e Orçamentos")
    def bloquear_comercial(self, request, queryset):
        n = queryset.update(acesso_comercial="nenhum", acesso_orcamentos="nenhum")
        self.message_user(request, f"Comercial bloqueado para {n} funcionário(s).")

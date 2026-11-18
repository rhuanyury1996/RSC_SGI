from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .acessos import niveis_do_usuario
from .models import AcessoModulo, Funcionario

User = get_user_model()


def _funcionario(user, **acessos):
    return Funcionario.objects.create(
        nome=user.username,
        sobrenome="Teste",
        data_nascimento=date(1990, 1, 1),
        cargo="executivo",
        centro_custo="rsc",
        usuario=user,
        **acessos,
    )


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class AcessoFinanceiroTests(TestCase):
    def setUp(self):
        self.ceo = User.objects.create_superuser("rfloriano", password="x")
        self.user = User.objects.create_user("akalahary", password="x")

    def _get(self, user, url="/financeiro/"):
        self.client.force_login(user)
        return self.client.get(url)

    def test_ceo_sempre_acessa(self):
        self.assertEqual(self._get(self.ceo).status_code, 200)

    def test_financeiro_comeca_fechado(self):
        _funcionario(self.user)
        self.assertEqual(self._get(self.user).status_code, 404)
        home = self._get(self.user, "/")
        self.assertNotContains(home, 'title="Financeiro"')

    def test_liberado_no_admin_acessa(self):
        _funcionario(self.user, acesso_financeiro="editar")
        self.assertEqual(self._get(self.user).status_code, 200)
        self.assertEqual(self._get(self.user, "/financeiro/lancamentos/").status_code, 200)
        self.assertContains(self._get(self.user, "/"), 'title="Financeiro"')

    def test_so_ver_abre_mas_nao_grava(self):
        _funcionario(self.user, acesso_financeiro="ver")
        self.assertEqual(self._get(self.user).status_code, 200)
        resp = self.client.post("/financeiro/filtro/entidade/", {"entity_filter": "all"})
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(self.client.session.get("entity_filter"))

    def test_superusuario_que_nao_e_ceo_precisa_ser_liberado(self):
        admin = User.objects.create_superuser("outro.admin", password="x")
        self.assertEqual(self._get(admin).status_code, 404)
        _funcionario(admin, acesso_financeiro="editar")
        self.assertEqual(self._get(admin).status_code, 200)

    def test_sem_funcionario_vinculado_nao_acessa(self):
        self.assertEqual(niveis_do_usuario(self.user)["financeiro"], "nenhum")
        self.assertEqual(self._get(self.user).status_code, 404)

    def test_espaco_continua_do_ceo(self):
        from workspaces.models import Membership, Workspace

        _funcionario(self.user, acesso_financeiro="editar")
        self._get(self.user)
        espaco = Workspace.objects.get(slug="rsc")
        self.assertEqual(espaco.owner, self.ceo)
        self.assertEqual(
            Membership.objects.get(workspace=espaco, user=self.user).role, "member"
        )

    def test_liberar_tudo_nao_libera_financeiro(self):
        func = _funcionario(self.user, acesso_comercial="nenhum")
        self.client.force_login(self.ceo)
        self.client.post(
            "/admin/funcionarios/acessomodulo/",
            {"action": "liberar_tudo", "_selected_action": [func.pk]},
        )
        func.refresh_from_db()
        self.assertEqual(func.acesso_comercial, "editar")
        self.assertEqual(func.acesso_financeiro, "nenhum")

    def test_matriz_do_admin_tem_coluna_financeiro(self):
        self.assertIn("acesso_financeiro", AcessoModuloAdminCampos())


def AcessoModuloAdminCampos():
    from django.contrib import admin

    return admin.site._registry[AcessoModulo].list_editable

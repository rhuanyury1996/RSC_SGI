import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import EstudoClassificacao

ESTADO_MINIMO = {"v": 1, "fontes": [{"id": "f1", "nome": "Furo 2 mm", "pid": "n140"}], "estudo": {"projeto": "Prox", "cliente": "Cliente X", "rev": "1"}}


class SetorTecnicoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("tecnico_teste", "t@t.com", "senha-forte-123")
        self.client.force_login(self.user)

    def _novo(self):
        r = self.client.post(reverse("tecnico_estudo_novo"), {"nome": "Estudo A", "cliente": "Cliente"})
        self.assertEqual(r.status_code, 302)
        return EstudoClassificacao.objects.get(nome="Estudo A")

    def test_lista_abre(self):
        r = self.client.get(reverse("tecnico"))
        self.assertEqual(r.status_code, 200)

    def test_cria_e_abre(self):
        e = self._novo()
        r = self.client.get(reverse("tecnico_estudo", args=[e.pk]))
        self.assertContains(r, reverse("tecnico_estudo_app", args=[e.pk]))

    def test_calculadora_injeta_config_e_permite_iframe(self):
        e = self._novo()
        r = self.client.get(reverse("tecnico_estudo_app", args=[e.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="sgi-ca"')
        self.assertEqual(r.headers.get("X-Frame-Options"), "SAMEORIGIN")

    def test_salvar_grava_estado_e_cabecalho(self):
        e = self._novo()
        r = self.client.post(reverse("tecnico_estudo_salvar", args=[e.pk]), data=json.dumps({"estado": ESTADO_MINIMO}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        e.refresh_from_db()
        self.assertEqual(e.n_fontes, 1)
        self.assertEqual((e.nome, e.cliente, e.revisao), ("Prox", "Cliente X", "1"))

    def test_salvar_rejeita_formato_errado(self):
        e = self._novo()
        r = self.client.post(reverse("tecnico_estudo_salvar", args=[e.pk]), data=json.dumps({"estado": {"v": 2}}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_salvar_bloqueado_para_so_leitura(self):
        e = self._novo()
        with mock.patch("tecnico.permissions.niveis_do_usuario", return_value={"tecnico": "ver"}):
            r = self.client.post(reverse("tecnico_estudo_salvar", args=[e.pk]), data=json.dumps({"estado": ESTADO_MINIMO}), content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_duplicar(self):
        e = self._novo()
        self.client.post(reverse("tecnico_estudo_salvar", args=[e.pk]), data=json.dumps({"estado": ESTADO_MINIMO}), content_type="application/json")
        r = self.client.post(reverse("tecnico_estudo_duplicar", args=[e.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(EstudoClassificacao.objects.count(), 2)


class CarregarEstudoProxTests(TestCase):
    def test_carga_e_idempotente_e_nao_cria_empresa(self):
        import tempfile
        from pathlib import Path

        from django.core.management import call_command

        from crm.models import Empresa

        estado = {
            "v": 1,
            "fontes": [{"id": "f1", "nome": "Balança @25 °C", "pid": "n140", "rt_chave": "balanca"}],
            "fontes_puros": [{"id": "f9", "nome": "Tolueno @25 °C", "pid": "n145", "rt_chave": "balanca"}],
            "custom": [{"id": "u001", "nome": "Mistura 01-RSC", "origem": "mistura", "pendente": True}],
            "over": {"n102": {"pendente": True, "nota": "FDS não enviada"}},
            "estudo": {
                "projeto": "PROX · Planta piloto de tinta base solvente (refazer RT-0001)",
                "cliente": "PROX DO BRASIL",
                "rev": "0",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "prox.json"
            arq.write_text(json.dumps(estado), encoding="utf-8")
            antes = Empresa.objects.count()
            call_command("carregar_estudo_prox", arquivo=str(arq))
            call_command("carregar_estudo_prox", arquivo=str(arq))
            call_command("carregar_estudo_prox", arquivo=str(arq), com_produtos_puros=True)
        self.assertEqual(Empresa.objects.count(), antes)
        estudos = EstudoClassificacao.objects.filter(nome__startswith="PROX · Planta piloto")
        self.assertEqual(estudos.count(), 1)
        estudo = estudos.get()
        self.assertEqual(estudo.cliente, "PROX DO BRASIL")
        self.assertEqual(estudo.revisao, "0")
        self.assertEqual(len(estudo.estado["fontes"]), 2)
        self.assertNotIn("fontes_puros", estudo.estado)

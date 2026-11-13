"""Orçamento RAVEN: cálculo, numeração compartilhada com o GEXCON, emissão, telas e aceite."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase

from crm.models import Contato, Empresa
from funcionarios.models import Cargo, Funcionario

from . import services as services_raven
from .models import OrcamentoRaven, StatusOrcamento, TabelaRaven
from .raven.calculo import ParametrosRaven

JSON_2026 = Path(__file__).resolve().parent / "raven" / "parametros_2026.json"
DATA = date(2026, 11, 13)


def dados_2026() -> dict:
    return json.loads(JSON_2026.read_text(encoding="utf-8"))


class BaseRaven(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tabela = TabelaRaven.objects.create(ano=2026, dados=dados_2026())
        cls.empresa = Empresa.objects.create(
            nome="Ambiental Consultoria", razao_social="AMBIENTAL CONSULTORIA LTDA", nome_curto="Ambiental",
            cnpj="12.345.678/0001-90", logradouro="Rua A, 1", cidade="Blumenau", estado="SC", cep="89000-000", pais="Brasil",
        )
        cls.contato = Contato.objects.create(empresa=cls.empresa, nome="Ana", sobrenome="Souza", email="ana@amb.com.br", principal=True)
        usuario = User.objects.create_user("rhuan", password="x")
        cls.funcionario = Funcionario.objects.create(
            usuario=usuario, nome="Rhuan", sobrenome="Floriano", data_nascimento=date(1990, 1, 1), cargo=Cargo.SOCIO
        )

    def pedido(self, **extra) -> dict:
        base = {
            "empresa": self.empresa, "contato": None, "tipo_cliente": "consultoria", "plano": "profissional",
            "vigencia": 6, "valor_licenca": None, "implantacao": False, "valor_implantacao": None, "horas_visita": None,
            "cidade_visita": "", "horas_pacote": 40, "pagamento": "vista", "validade_dias": 30, "data": DATA, "sequencial": None,
        }
        base.update(extra)
        return base


class CalculoTests(BaseRaven):
    def test_parametros_validos(self):
        ParametrosRaven.de_dict(dados_2026())

    def test_desconto_a_vista_no_total(self):
        res, _ = services_raven.calcular(self.pedido())
        self.assertEqual(res.desconto, Decimal("996.80"))
        self.assertEqual(res.total, Decimal("13311.60"))

    def test_tabela_inexistente(self):
        with self.assertRaises(services_raven.OrcamentoErro):
            services_raven.calcular(self.pedido(data=date(2028, 1, 10)))


class EmissaoTests(BaseRaven):
    def test_emite_com_snapshot_e_html(self):
        orc = services_raven.emitir(self.pedido(), self.funcionario)
        self.assertEqual(orc.numero, "261113-1")
        self.assertEqual(orc.nome_arquivo, "Orc_261113-1_Ambiental_RAVEN.html")
        self.assertEqual(orc.contato, self.contato)
        self.assertEqual(orc.total, Decimal("13311.60"))
        html = bytes(orc.arquivo).decode()
        self.assertIn('"plano": "profissional"', html)
        self.assertIn("261113-1", html)

    def test_sequencial_compartilhado_com_gexcon(self):
        from orcamentos.models import Orcamento

        self.assertEqual(services_raven.proximo_sequencial(DATA), 1)
        services_raven.emitir(self.pedido(), self.funcionario)
        self.assertEqual(services_raven.proximo_sequencial(DATA), 2)
        # o GEXCON também enxerga o número usado pelo RAVEN
        from orcamentos import services as gexcon_services

        self.assertEqual(gexcon_services.proximo_sequencial(DATA), 2)
        self.assertFalse(Orcamento.objects.exists())

    def test_pendencia_bloqueia_emissao(self):
        with self.assertRaises(services_raven.OrcamentoErro):
            services_raven.emitir(self.pedido(tipo_cliente="industria", plano="supernova", vigencia=12), self.funcionario)

    def test_aceite_e_login(self):
        orc = services_raven.emitir(self.pedido(plano="trial"), self.funcionario)
        self.assertTrue(orc.trial)
        self.assertEqual(orc.total, Decimal("1848.40"))
        services_raven.mudar_status(orc, StatusOrcamento.ACEITA, self.funcionario)
        orc.refresh_from_db()
        self.assertIsNotNone(orc.aceite_em)
        self.assertTrue(orc.aguardando_login)
        self.assertEqual((orc.prazo_login - orc.aceite_em).total_seconds(), 48 * 3600)
        services_raven.liberar_login(orc, self.funcionario)
        orc.refresh_from_db()
        self.assertFalse(orc.aguardando_login)


class TelasTests(BaseRaven):
    def setUp(self):
        self.client.force_login(self.funcionario.usuario)

    def test_historico_e_novo_abrem(self):
        services_raven.emitir(self.pedido(), self.funcionario)
        self.assertContains(self.client.get("/orcamentos/raven/"), "261113-1")
        self.assertEqual(self.client.get("/orcamentos/raven/novo/").status_code, 200)

    def test_previa_nao_grava(self):
        resposta = self.client.post(
            "/orcamentos/raven/novo/",
            {"empresa": self.empresa.pk, "tipo_cliente": "consultoria", "plano": "profissional", "vigencia": "6",
             "horas_pacote": "40", "pagamento": "vista", "validade_dias": "30", "data": "2026-11-13", "acao": "previa"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "R$ 13.311,60")
        self.assertEqual(OrcamentoRaven.objects.count(), 0)

    def test_emitir_pela_tela(self):
        resposta = self.client.post(
            "/orcamentos/raven/novo/",
            {"empresa": self.empresa.pk, "tipo_cliente": "consultoria", "plano": "basico", "vigencia": "12",
             "pagamento": "10x", "validade_dias": "15", "data": "2026-11-13", "acao": "emitir"},
        )
        self.assertEqual(resposta.status_code, 302)
        orc = OrcamentoRaven.objects.get()
        self.assertEqual(orc.total, Decimal("14350.00"))
        self.assertEqual(orc.validade, date(2026, 11, 28))
        abrir = self.client.get(f"/orcamentos/raven/{orc.pk}/")
        self.assertEqual(abrir["Content-Type"], "text/html; charset=utf-8")
        baixar = self.client.get(f"/orcamentos/raven/{orc.pk}/download/")
        self.assertIn(orc.nome_arquivo, baixar["Content-Disposition"])

"""Casos obrigatórios da seção 9 do procedimento (tabela 2026, data 04/11/2026)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase

from crm.models import Contato, Empresa
from funcionarios.models import Cargo, Funcionario

from . import services
from .gexcon.modelos import PRODUTO_EFFECTS, PRODUTO_ER, Escopo
from .gexcon.numeracao import limpar_nome, nome_arquivo, numero_proposta
from .gexcon.parametros import Parametros
from .gexcon.precos import formatar_euro, preco_software
from .models import Orcamento, TabelaParametros

JSON_2026 = Path(__file__).resolve().parent / "gexcon" / "parametros_2026.json"
DATA = date(2026, 11, 4)


def dados_2026() -> dict:
    return json.loads(JSON_2026.read_text(encoding="utf-8"))


def params_2026() -> Parametros:
    return Parametros.de_dict(dados_2026())


class PrecoSoftwareTests(TestCase):
    """Preços de software da tabela 2026."""

    def setUp(self):
        self.p = params_2026()

    def test_effects_por_periodo(self):
        esperado = {3: "3.969,00", 6: "7.938,00", 12: "9.450,00"}
        for meses, valor in esperado.items():
            with self.subTest(meses=meses):
                self.assertEqual(formatar_euro(preco_software(PRODUTO_EFFECTS, meses, self.p)), f"€ {valor}")

    def test_effects_riskcurves_por_periodo(self):
        esperado = {3: "9.482,00", 6: "18.963,00", 12: "22.575,00"}
        for meses, valor in esperado.items():
            with self.subTest(meses=meses):
                self.assertEqual(formatar_euro(preco_software(PRODUTO_ER, meses, self.p)), f"€ {valor}")

    def test_usuario_adicional_por_periodo(self):
        esperado = {3: "2.381,00", 6: "4.763,00", 12: "5.670,00"}
        for meses, valor in esperado.items():
            with self.subTest(meses=meses):
                preco = preco_software(PRODUTO_EFFECTS, meses, self.p, adicional=True)
                self.assertEqual(formatar_euro(preco), f"€ {valor}")

    def test_reajuste_novo_10_e_renovacao_5(self):
        dados = dados_2026()
        dados["reajuste_lista"] = {"novo": 0.10, "renovacao": 0.05}
        p = Parametros.de_dict(dados)
        novo = preco_software(PRODUTO_EFFECTS, 12, p, reajuste=p.reajuste_lista["novo"])
        renov = preco_software(PRODUTO_EFFECTS, 12, p, reajuste=p.reajuste_lista["renovacao"])
        self.assertEqual(formatar_euro(novo), "€ 10.395,00")
        self.assertEqual(formatar_euro(renov), "€ 9.923,00")


class NumeracaoTests(TestCase):
    def test_numero_e_nome_do_arquivo(self):
        numero = numero_proposta(DATA, 1)
        self.assertEqual(numero, "261104-1")
        self.assertEqual(
            nome_arquivo(numero, "RME", Escopo.EFFECTS_RISKCURVES),
            "Orc_261104-1_RME_E&R.docx",
        )

    def test_nome_com_caractere_invalido(self):
        self.assertEqual(limpar_nome("ACME S/A"), "ACME SA")


class BaseOrcamentoTestCase(TestCase):
    """Empresa, contato, usuário e tabela 2026 prontos para os testes de emissão."""

    @classmethod
    def setUpTestData(cls):
        cls.tabela = TabelaParametros.objects.create(ano=2026, dados=dados_2026())
        cls.empresa = Empresa.objects.create(
            nome="Refinaria Modelo",
            razao_social="REFINARIA MODELO S.A.",
            nome_curto="RME",
            cnpj="12.345.678/0001-90",
            logradouro="Rua das Indústrias, 100",
            complemento="Distrito Industrial",
            cidade="Paulínia",
            estado="SP",
            cep="13140-000",
            pais="Brasil",
        )
        cls.contato = Contato.objects.create(
            empresa=cls.empresa,
            nome="Ana",
            sobrenome="Souza",
            email="ana@rme.com.br",
            telefone_whatsapp="+55 (19) 99999-0000",
            principal=True,
        )
        usuario = User.objects.create_user("rhuan", password="x")
        cls.funcionario = Funcionario.objects.create(
            usuario=usuario,
            nome="Rhuan",
            sobrenome="Floriano",
            data_nascimento=date(1990, 1, 1),
            cargo=Cargo.SOCIO,
        )

    def pedido(self, **extra) -> dict:
        base = {
            "empresa": self.empresa,
            "contato": None,
            "escopo": Escopo.EFFECTS_RISKCURVES.value,
            "incluir_adicional": True,
            "periodos": [3, 6, 12],
            "tipo_cliente": "novo",
            "vencimento_licenca": None,
            "treinamentos": [],
            "data": DATA,
            "sequencial": None,
        }
        base.update(extra)
        return base


class CalculoTests(BaseOrcamentoTestCase):
    def test_er_com_treinamentos(self):
        """E&R + treinamento EFFECTS (1 aluno) + E+R (2 alunos)."""
        orc, _p, _t = services.calcular(
            self.pedido(
                treinamentos=[
                    {"produto": PRODUTO_EFFECTS, "tipo": "Online", "alunos": 1},
                    {"produto": PRODUTO_ER, "tipo": "Online", "alunos": 2},
                ]
            )
        )
        self.assertEqual(formatar_euro(orc.total_treinamentos), "€ 5.400,00")
        self.assertEqual(formatar_euro(orc.total_servicos), "€ 27.975,00")

    def test_so_effects_sem_treinamento(self):
        orc, params, _t = services.calcular(
            self.pedido(escopo=Escopo.SO_EFFECTS.value, incluir_adicional=False)
        )
        self.assertEqual(formatar_euro(orc.total_servicos), "€ 9.450,00")
        self.assertEqual(orc.linhas_treinamento, [])
        self.assertEqual(params.responsavel(orc.escopo).nome, "Denis Shiguemoto")

    def test_er_somente_seis_meses(self):
        orc, _p, _t = services.calcular(self.pedido(periodos=[6]))
        self.assertEqual(orc.periodos_meses, [6])
        self.assertEqual(orc.periodo_servicos, 6)
        self.assertEqual(formatar_euro(orc.total_servicos), "€ 18.963,00")

    def test_renovacao_fora_do_prazo_vira_cliente_novo(self):
        """Vencimento 30/09/2026: prazo até 30/10/2026; proposta de 04/11 paga como nova."""
        orc, _p, _t = services.calcular(
            self.pedido(tipo_cliente="renovacao", vencimento_licenca=date(2026, 9, 30))
        )
        self.assertEqual(orc.tipo_cliente.value, "novo")
        self.assertTrue(any("30/10/2026" in aviso for aviso in orc.avisos))

    def test_renovacao_sem_vencimento_avisa(self):
        orc, _p, _t = services.calcular(self.pedido(tipo_cliente="renovacao"))
        self.assertEqual(orc.tipo_cliente.value, "renovacao")
        self.assertTrue(any("prazo não verificado" in a for a in orc.avisos))

    def test_data_apos_validade_bloqueia(self):
        with self.assertRaises(services.OrcamentoErro) as ctx:
            services.calcular(self.pedido(data=date(2026, 12, 17)))
        self.assertIn("Atualize os parâmetros", str(ctx.exception))

    def test_empresa_sem_contato_da_erro_claro(self):
        vazia = Empresa.objects.create(nome="Sem Contato Ltda")
        with self.assertRaises(services.OrcamentoErro) as ctx:
            services.calcular(self.pedido(empresa=vazia))
        self.assertIn("Cadastre um contato", str(ctx.exception))

    def test_contato_de_outra_empresa_da_erro(self):
        outra = Empresa.objects.create(nome="Outra S.A.")
        alheio = Contato.objects.create(empresa=outra, nome="João")
        with self.assertRaises(services.OrcamentoErro) as ctx:
            services.calcular(self.pedido(contato=alheio))
        self.assertIn("não pertence", str(ctx.exception))

    def test_treinamento_presencial_sem_preco_e_recusado(self):
        with self.assertRaises(services.OrcamentoErro) as ctx:
            services.calcular(
                self.pedido(
                    treinamentos=[{"produto": PRODUTO_EFFECTS, "tipo": "Presencial", "alunos": 1}]
                )
            )
        self.assertIn("preço cadastrado", str(ctx.exception))

    def test_endereco_em_linhas_ignora_vazios(self):
        self.assertEqual(
            services.linhas_endereco(self.empresa),
            ["Rua das Indústrias, 100", "Distrito Industrial", "Paulínia – SP 13140-000, Brasil"],
        )


class SequencialTests(BaseOrcamentoTestCase):
    def test_proximo_sequencial_do_dia(self):
        self.assertEqual(services.proximo_sequencial(DATA), 1)
        for seq in (1, 3):
            services.emitir(self.pedido(sequencial=seq), self.funcionario)
        self.assertEqual(services.proximo_sequencial(DATA), 4)

    def test_sequencial_reinicia_em_outro_dia(self):
        services.emitir(self.pedido(sequencial=1), self.funcionario)
        self.assertEqual(services.proximo_sequencial(date(2026, 11, 5)), 1)

    def test_sequencial_repetido_e_recusado(self):
        services.emitir(self.pedido(sequencial=1), self.funcionario)
        with self.assertRaises(services.OrcamentoErro):
            services.calcular(self.pedido(sequencial=1))


class EmissaoTests(BaseOrcamentoTestCase):
    def emitir_padrao(self, **extra) -> Orcamento:
        return services.emitir(self.pedido(**extra), self.funcionario)

    def test_snapshot_gravado_no_historico(self):
        orc = self.emitir_padrao(
            treinamentos=[{"produto": PRODUTO_EFFECTS, "tipo": "Online", "alunos": 1}]
        )
        self.assertEqual(orc.numero, "261104-1")
        self.assertEqual(orc.nome_arquivo, "Orc_261104-1_RME_E&R.docx")
        self.assertEqual(orc.validade, date(2026, 12, 16))
        self.assertEqual(orc.contato_id, self.contato.pk)
        self.assertEqual(orc.status, "emitida")
        self.assertEqual(orc.total_servicos, Decimal("24375.00"))
        self.assertEqual(orc.versao_tabela, "XSuite Price Builder 2026 (EUR)")
        self.assertEqual(orc.emitido_por_id, self.funcionario.pk)
        self.assertEqual(len(orc.historico_status), 1)
        self.assertEqual(orc.cliente["nome_curto"], "RME")

    def test_docx_gerado_e_valido(self):
        orc = self.emitir_padrao()
        conteudo = bytes(orc.arquivo)
        self.assertTrue(conteudo.startswith(b"PK"))
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            self.assertIn("word/document.xml", z.namelist())

    def _texto_docx(self, orc: Orcamento, prefixo: str) -> str:
        with zipfile.ZipFile(io.BytesIO(bytes(orc.arquivo))) as z:
            partes = [n for n in z.namelist() if n.startswith(f"word/{prefixo}")]
            return "".join(z.read(n).decode("utf-8") for n in partes)

    def test_assinatura_aparece_uma_vez(self):
        """Armadilha dos w:t extras: "DPR ENGENHARIA" não pode duplicar."""
        orc = self.emitir_padrao()
        self.assertEqual(self._texto_docx(orc, "document.xml").count("DPR ENGENHARIA"), 1)

    def test_rodape_traz_numero_e_data_novos(self):
        orc = self.emitir_padrao()
        rodapes = self._texto_docx(orc, "footer") + self._texto_docx(orc, "header")
        self.assertIn(orc.numero, rodapes)
        self.assertIn("04/11/2026", rodapes)
        self.assertNotIn("260212-3", rodapes)

    def test_mudar_status_registra_historico(self):
        orc = self.emitir_padrao()
        services.mudar_status(orc, "enviada", self.funcionario)
        orc.refresh_from_db()
        self.assertEqual(orc.status, "enviada")
        self.assertEqual([h["status"] for h in orc.historico_status], ["emitida", "enviada"])


class ParametrosPorAnoTests(BaseOrcamentoTestCase):
    def test_cadastrar_tabela_de_outro_ano_sem_mexer_no_codigo(self):
        """Tabela 2027 (previsão): +10% novo, +5% renovação, sem tocar no código."""
        dados = dados_2026()
        dados["versao_tabela"] = "XSuite Price Builder 2027 (previsão)"
        dados["validade_ate"] = "2027-12-16"
        dados["reajuste_lista"] = {"novo": 0.10, "renovacao": 0.05}
        TabelaParametros.objects.create(ano=2027, dados=dados)

        orc, _p, tabela = services.calcular(
            self.pedido(data=date(2027, 3, 10), escopo=Escopo.SO_EFFECTS.value, incluir_adicional=False)
        )
        self.assertEqual(tabela.ano, 2027)
        self.assertEqual(formatar_euro(orc.total_servicos), "€ 10.395,00")

    def test_ano_sem_tabela_da_erro_claro(self):
        with self.assertRaises(services.OrcamentoErro) as ctx:
            services.calcular(self.pedido(data=date(2028, 1, 10)))
        self.assertIn("2028", str(ctx.exception))


class TelasTests(BaseOrcamentoTestCase):
    def setUp(self):
        self.client.force_login(self.funcionario.usuario)

    def test_historico_abre(self):
        services.emitir(self.pedido(), self.funcionario)
        resposta = self.client.get("/orcamentos/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "261104-1")

    def test_novo_mostra_previa_sem_gravar(self):
        resposta = self.client.post(
            "/orcamentos/novo/",
            {
                "empresa": self.empresa.pk,
                "escopo": "E&R",
                "incluir_adicional": "on",
                "periodos": ["3", "6", "12"],
                "tipo_cliente": "novo",
                "data": "2026-11-04",
                "acao": "previa",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "€ 22.575,00")
        self.assertEqual(Orcamento.objects.count(), 0)

    def test_download_devolve_docx(self):
        orc = services.emitir(self.pedido(), self.funcionario)
        resposta = self.client.get(f"/orcamentos/{orc.pk}/download/")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(orc.nome_arquivo, resposta["Content-Disposition"])

    def test_parametros_somente_leitura_para_nao_gestor(self):
        usuario = User.objects.create_user("estagio", password="x")
        Funcionario.objects.create(
            usuario=usuario,
            nome="Iris",
            sobrenome="Lima",
            data_nascimento=date(2003, 5, 20),
            cargo=Cargo.ESTAGIARIO,
        )
        self.client.force_login(usuario)
        resposta = self.client.get("/orcamentos/parametros/")
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.context["pode_editar"])

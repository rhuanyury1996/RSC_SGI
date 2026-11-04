from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from funcionarios.models import Cargo, CentroCusto, Funcionario

from .models import (
    AtividadeDiaria,
    PrioridadeAtividade,
    QuadranteEisenhower,
    SessaoTempoAtividade,
    StatusAtividade,
)
from .services import alterar_status, criar_atividade, iniciar_cronometro, parar_cronometro


class _Base(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("ana", password="ana-123")
        self.outro_user = User.objects.create_user("bruno", password="bruno-123")
        self.ana = self._funcionario(self.user, "Ana", "Silva", Cargo.EXECUTIVO)
        self.bruno = self._funcionario(self.outro_user, "Bruno", "Costa", Cargo.ESTAGIARIO)
        self.hoje = timezone.localdate()
        self.ontem = self.hoje - timedelta(days=1)

    def _funcionario(self, user, nome, sobrenome, cargo):
        return Funcionario.objects.create(
            nome=nome,
            sobrenome=sobrenome,
            data_nascimento=date(1992, 5, 10),
            cargo=cargo,
            centro_custo=CentroCusto.RSC,
            usuario=user,
        )


class CarryOverTests(_Base):
    def test_tarefa_aberta_de_ontem_aparece_hoje(self):
        criar_atividade(
            self.ana,
            titulo="Montar proposta AdecoAgro",
            responsavel=self.ana,
            status=StatusAtividade.EXECUTANDO,
            planejado_para=self.ontem,
        )
        feita = criar_atividade(
            self.ana,
            titulo="Relatório já entregue",
            responsavel=self.ana,
            status=StatusAtividade.REALIZADO,
            planejado_para=self.ontem,
        )
        self.client.force_login(self.user)
        resp = self.client.get(reverse("atividades"), {"formato": "json"})
        self.assertEqual(resp.status_code, 200)
        por_titulo = {t["titulo"]: t for t in resp.json()["tarefas"]}
        self.assertEqual(
            por_titulo["Montar proposta AdecoAgro"]["atraso"], self.ontem.isoformat()
        )
        # Realizada continua visível nas visualizações, mas não conta como atraso.
        self.assertEqual(por_titulo[feita.titulo]["atraso"], "")

    def test_paginas_das_visualizacoes_carregam(self):
        self.client.force_login(self.user)
        for org in ("lista", "quadro", "gantt", "mapa", "status"):
            resp = self.client.get(reverse("atividades"), {"org": org})
            self.assertEqual(resp.status_code, 200, org)
            self.assertContains(resp, 'id="ca-dados"')

    def test_planner_tambem_carrega_atrasada(self):
        criar_atividade(
            self.ana,
            titulo="Montar proposta AdecoAgro",
            responsavel=self.ana,
            status=StatusAtividade.EXECUTANDO,
            planejado_para=self.ontem,
        )
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse("atividades"),
            {"org": "planner", "data": self.hoje.isoformat()},
        )
        self.assertContains(resp, "Montar proposta AdecoAgro")


class PermissaoTests(_Base):
    def setUp(self):
        super().setUp()
        self.tarefa = criar_atividade(
            self.ana,
            titulo="Tarefa da Ana",
            responsavel=self.ana,
            planejado_para=self.hoje,
        )

    def test_editar_sem_permissao_retorna_403(self):
        self.client.force_login(self.outro_user)
        resp = self.client.post(
            reverse("atividade_editar", args=[self.tarefa.pk]),
            {"titulo": "Invadida"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Sem permissão", resp.content.decode())
        self.tarefa.refresh_from_db()
        self.assertEqual(self.tarefa.titulo, "Tarefa da Ana")

    def test_participante_pode_editar(self):
        self.tarefa.participantes.add(self.bruno)
        self.client.force_login(self.outro_user)
        resp = self.client.post(
            reverse("atividade_editar", args=[self.tarefa.pk]),
            {
                "titulo": "Ajuste do participante",
                "responsavel": self.ana.pk,
                "status": StatusAtividade.EXECUTANDO,
                "prioridade": PrioridadeAtividade.MEDIA,
                "quadrante": QuadranteEisenhower.AGENDAR,
                "planejado_para": self.hoje.isoformat(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.tarefa.refresh_from_db()
        self.assertEqual(self.tarefa.titulo, "Ajuste do participante")

    def test_status_sem_permissao_retorna_403(self):
        self.client.force_login(self.outro_user)
        resp = self.client.post(
            reverse("atividade_status", args=[self.tarefa.pk]),
            {"status": StatusAtividade.EXECUTANDO},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()["ok"])


class StatusEndpointTests(_Base):
    def test_responsavel_muda_status(self):
        tarefa = criar_atividade(
            self.ana,
            titulo="Trocar status",
            responsavel=self.ana,
            planejado_para=self.hoje,
        )
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("atividade_status", args=[tarefa.pk]),
            {"status": StatusAtividade.EXECUTANDO},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], StatusAtividade.EXECUTANDO)
        tarefa.refresh_from_db()
        self.assertEqual(tarefa.status, StatusAtividade.EXECUTANDO)


class ValidacaoHorarioTests(_Base):
    def test_hora_fim_antes_do_inicio_rejeita(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("atividades"),
            {
                "acao": "criar",
                "titulo": "Horário inválido",
                "responsavel": self.ana.pk,
                "status": StatusAtividade.NAO_INICIADO,
                "prioridade": PrioridadeAtividade.MEDIA,
                "quadrante": QuadranteEisenhower.AGENDAR,
                "planejado_para": self.hoje.isoformat(),
                "hora_inicio": "18:00",
                "hora_fim": "17:00",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "O fim deve ser depois do início.")
        self.assertFalse(
            AtividadeDiaria.objects.filter(titulo="Horário inválido").exists()
        )

    def test_vencimento_anterior_a_data_rejeita(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("atividades"),
            {
                "acao": "criar",
                "titulo": "Vencimento inválido",
                "responsavel": self.ana.pk,
                "status": StatusAtividade.NAO_INICIADO,
                "prioridade": PrioridadeAtividade.MEDIA,
                "quadrante": QuadranteEisenhower.AGENDAR,
                "planejado_para": self.hoje.isoformat(),
                "data_vencimento": (self.hoje - timedelta(days=2)).isoformat(),
            },
        )
        self.assertContains(resp, "não pode ser anterior à data planejada")

    def test_adicao_rapida_grava_quadrante_agendar(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("atividades"),
            {
                "acao": "criar_rapida",
                "titulo": "Rápida média",
                "responsavel": self.ana.pk,
                "prioridade": PrioridadeAtividade.MEDIA,
                "planejado_para": self.hoje.isoformat(),
            },
        )
        item = AtividadeDiaria.objects.get(titulo="Rápida média")
        self.assertEqual(item.quadrante, QuadranteEisenhower.AGENDAR)

    def test_participante_igual_ao_responsavel_e_ignorado(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("atividades"),
            {
                "acao": "criar",
                "titulo": "Equipe",
                "responsavel": self.ana.pk,
                "participantes": [self.ana.pk, self.bruno.pk],
                "status": StatusAtividade.NAO_INICIADO,
                "prioridade": PrioridadeAtividade.MEDIA,
                "quadrante": QuadranteEisenhower.AGENDAR,
                "planejado_para": self.hoje.isoformat(),
            },
        )
        item = AtividadeDiaria.objects.get(titulo="Equipe")
        ids = set(item.participantes.values_list("pk", flat=True))
        self.assertNotIn(self.ana.pk, ids)
        self.assertIn(self.bruno.pk, ids)


class TimerTests(_Base):
    def _tarefa_em_dupla(self):
        tarefa = criar_atividade(
            self.ana,
            titulo="Em dupla",
            responsavel=self.ana,
            participantes=[self.bruno],
            planejado_para=self.hoje,
        )
        return tarefa

    def test_cada_pessoa_tem_seu_cronometro_na_mesma_tarefa(self):
        tarefa = self._tarefa_em_dupla()
        self.client.force_login(self.user)
        r1 = self.client.post(
            reverse("atividade_cronometro", args=[tarefa.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        ).json()
        self.assertTrue(r1["ativo"])
        self.client.force_login(self.outro_user)
        r2 = self.client.post(
            reverse("atividade_cronometro", args=[tarefa.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        ).json()
        # O clique do Bruno inicia o dele, não para o da Ana.
        self.assertTrue(r2["ativo"])
        self.assertEqual(
            SessaoTempoAtividade.objects.filter(atividade=tarefa, fim__isnull=True).count(), 2
        )
        self.assertEqual({p["id"] for p in r2["tarefa"]["rodando"]}, {self.ana.pk, self.bruno.pk})

        self.client.force_login(self.user)
        r3 = self.client.post(
            reverse("atividade_cronometro", args=[tarefa.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        ).json()
        self.assertFalse(r3["ativo"])
        abertas = SessaoTempoAtividade.objects.filter(atividade=tarefa, fim__isnull=True)
        self.assertEqual([s.funcionario_id for s in abertas], [self.bruno.pk])
        tarefa.refresh_from_db()
        self.assertTrue(tarefa.cronometro_ativo)

    def test_total_soma_as_pessoas(self):
        tarefa = self._tarefa_em_dupla()
        agora = timezone.now()
        iniciar_cronometro(tarefa, self.ana)
        iniciar_cronometro(tarefa, self.bruno)
        SessaoTempoAtividade.objects.filter(funcionario=self.ana).update(
            inicio=agora - timedelta(minutes=30)
        )
        SessaoTempoAtividade.objects.filter(funcionario=self.bruno).update(
            inicio=agora - timedelta(minutes=10)
        )
        tarefa.refresh_from_db()
        parar_cronometro(tarefa, ator=self.ana)
        tarefa.refresh_from_db()
        parar_cronometro(tarefa, ator=self.bruno)
        tarefa.refresh_from_db()
        self.assertAlmostEqual(tarefa.tempo_acumulado_segundos, 40 * 60, delta=5)
        por_pessoa = tarefa.tempo_por_pessoa()
        self.assertAlmostEqual(por_pessoa[self.ana.pk], 30 * 60, delta=5)
        self.assertAlmostEqual(por_pessoa[self.bruno.pk], 10 * 60, delta=5)
        self.assertIsNone(tarefa.cronometro_inicio)

    def test_concluir_para_o_cronometro_de_todos(self):
        tarefa = self._tarefa_em_dupla()
        iniciar_cronometro(tarefa, self.ana)
        iniciar_cronometro(tarefa, self.bruno)
        tarefa.refresh_from_db()
        alterar_status(tarefa, StatusAtividade.REALIZADO, autor=self.ana)
        tarefa.refresh_from_db()
        self.assertIsNone(tarefa.cronometro_inicio)
        self.assertFalse(
            SessaoTempoAtividade.objects.filter(atividade=tarefa, fim__isnull=True).exists()
        )

    def test_detalhe_soma_tempo_por_pessoa(self):
        tarefa = criar_atividade(
            self.ana, titulo="Com tempo", responsavel=self.ana, planejado_para=self.hoje
        )
        agora = timezone.now()
        SessaoTempoAtividade.objects.create(
            atividade=tarefa,
            funcionario=self.ana,
            inicio=agora - timedelta(hours=2),
            fim=agora - timedelta(hours=1),
            segundos=3600,
        )
        SessaoTempoAtividade.objects.create(
            atividade=tarefa,
            funcionario=self.ana,
            inicio=agora - timedelta(minutes=30),
            fim=agora - timedelta(minutes=20),
            segundos=600,
        )
        SessaoTempoAtividade.objects.create(
            atividade=tarefa,
            funcionario=self.bruno,
            inicio=agora - timedelta(seconds=90),
        )
        self.client.force_login(self.user)
        dados = self.client.get(reverse("atividade_detalhe", args=[tarefa.pk])).json()
        linhas = {p["nome"]: p for p in dados["tempo_por_pessoa"]}
        self.assertEqual(linhas["Ana Silva"]["segundos"], 4200)
        self.assertFalse(linhas["Ana Silva"]["rodando"])
        self.assertTrue(linhas["Bruno Costa"]["rodando"])
        self.assertGreaterEqual(linhas["Bruno Costa"]["segundos"], 90)
        self.assertEqual(dados["tempo_por_pessoa"][0]["nome"], "Ana Silva")

    def test_nao_inicia_em_tarefa_realizada(self):
        tarefa = criar_atividade(
            self.ana,
            titulo="Já feita",
            responsavel=self.ana,
            status=StatusAtividade.REALIZADO,
            planejado_para=self.hoje,
        )
        self.client.force_login(self.user)
        resp = self.client.post(reverse("atividade_cronometro", args=[tarefa.pk]))
        self.assertEqual(resp.status_code, 400)
        tarefa.refresh_from_db()
        self.assertIsNone(tarefa.cronometro_inicio)

    def test_um_timer_por_usuario(self):
        primeira = criar_atividade(
            self.ana,
            titulo="Primeira",
            responsavel=self.ana,
            planejado_para=self.hoje,
            hora_inicio=time(9, 0),
            hora_fim=time(10, 0),
        )
        segunda = criar_atividade(
            self.ana,
            titulo="Segunda",
            responsavel=self.ana,
            planejado_para=self.hoje,
            hora_inicio=time(11, 0),
            hora_fim=time(12, 0),
        )
        iniciar_cronometro(primeira, self.ana)
        iniciar_cronometro(segunda, self.ana)
        primeira.refresh_from_db()
        segunda.refresh_from_db()
        self.assertIsNone(primeira.cronometro_inicio)
        self.assertIsNotNone(segunda.cronometro_inicio)


class VisualizacoesTests(_Base):
    def setUp(self):
        super().setUp()
        self.tarefa = criar_atividade(
            self.ana,
            titulo="Contrato Berkan: analisar",
            responsavel=self.ana,
            planejado_para=self.ontem,
        )

    def test_complete_conta_como_concluida(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("atividade_status", args=[self.tarefa.pk]),
            {"status": StatusAtividade.COMPLETE},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.tarefa.refresh_from_db()
        self.assertTrue(self.tarefa.concluida)
        self.assertIsNone(self.tarefa.data_atraso())
        self.assertEqual(resp.json()["tarefa"]["status"], StatusAtividade.COMPLETE)

    def test_campos_muda_prioridade_e_entrega(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("atividade_campos", args=[self.tarefa.pk]),
            {"prioridade": "", "data_vencimento": self.hoje.isoformat()},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.tarefa.refresh_from_db()
        self.assertEqual(self.tarefa.prioridade, PrioridadeAtividade.NENHUMA)
        self.assertEqual(self.tarefa.data_vencimento, self.hoje)
        self.assertEqual(resp.json()["tarefa"]["entrega"], self.hoje.isoformat())

    def test_campos_rejeita_data_invalida(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("atividade_campos", args=[self.tarefa.pk]),
            {"data_vencimento": "31/10/2026"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 400)

    def test_campos_sem_permissao_retorna_403(self):
        self.client.force_login(self.outro_user)
        resp = self.client.post(
            reverse("atividade_campos", args=[self.tarefa.pk]),
            {"titulo": "Invadido"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 403)
        self.tarefa.refresh_from_db()
        self.assertEqual(self.tarefa.titulo, "Contrato Berkan: analisar")

    def test_executor_nao_troca_responsavel(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("atividade_campos", args=[self.tarefa.pk]),
            {"responsavel": self.bruno.pk},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 403)

    def test_reordenar_move_de_coluna(self):
        outra = criar_atividade(
            self.ana, titulo="Outra", responsavel=self.ana, planejado_para=self.hoje
        )
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("atividades_reordenar"),
            {
                "ids": [outra.pk, self.tarefa.pk],
                "movida": self.tarefa.pk,
                "status": StatusAtividade.EM_REVISAO,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.tarefa.refresh_from_db()
        outra.refresh_from_db()
        self.assertEqual(self.tarefa.status, StatusAtividade.EM_REVISAO)
        self.assertEqual((outra.ordem, self.tarefa.ordem), (0, 1))

    def test_reordenar_ignora_tarefa_alheia(self):
        self.client.force_login(self.outro_user)
        self.client.post(
            reverse("atividades_reordenar"),
            {"ids": [self.tarefa.pk]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        resp = self.client.post(
            reverse("atividades_reordenar"),
            {"ids": [self.tarefa.pk], "movida": self.tarefa.pk, "status": "realizado"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 403)
        self.tarefa.refresh_from_db()
        self.assertEqual(self.tarefa.status, StatusAtividade.NAO_INICIADO)

    def test_subtarefa_por_json(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("atividade_subtarefa", args=[self.tarefa.pk]),
            {"titulo": "Ler cláusulas"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        subs = resp.json()["pai"]["subtarefas"]
        self.assertEqual([s["titulo"] for s in subs], ["Ler cláusulas"])

    def test_adicao_rapida_devolve_tarefa(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("atividades"),
            {
                "acao": "criar_rapida",
                "titulo": "Nova no quadro",
                "status": StatusAtividade.ORGANIZANDO,
                "data_vencimento": self.ontem.isoformat(),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        tarefa = resp.json()["tarefa"]
        self.assertEqual(tarefa["status"], StatusAtividade.ORGANIZANDO)
        self.assertEqual(tarefa["entrega"], self.ontem.isoformat())

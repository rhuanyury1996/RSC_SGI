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
    StatusAtividade,
)
from .services import criar_atividade, iniciar_cronometro


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
        resp = self.client.get(
            reverse("atividades"),
            {"data": self.hoje.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Montar proposta AdecoAgro")
        self.assertContains(resp, f"Atrasada desde {self.ontem.strftime('%d/%m')}")
        self.assertNotContains(resp, feita.titulo)

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

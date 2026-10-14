from django.db import models
from django.utils import timezone

from funcionarios.models import Funcionario


class StatusAtividade(models.TextChoices):
    NAO_INICIADO = "nao_iniciado", "Não iniciado"
    EXECUTANDO = "executando", "Executando"
    EM_REVISAO = "em_revisao", "Em revisão"
    REALIZADO = "realizado", "Realizado"


class PrioridadeAtividade(models.TextChoices):
    BAIXA = "baixa", "Baixa"
    MEDIA = "media", "Média"
    ALTA = "alta", "Alta"
    URGENTE = "urgente", "Urgente"


class QuadranteEisenhower(models.TextChoices):
    FAZER = "fazer", "Fazer primeiro"
    AGENDAR = "agendar", "Agendar"
    DELEGAR = "delegar", "Delegar"
    ELIMINAR = "eliminar", "Eliminar"


COPOS_AGUA_META = 10
ML_POR_COPO = 250
HABITOS_PADRAO = (
    ("leitura", "Leitura"),
    ("exercicio", "Exercício"),
    ("estudar_idioma", "Estudar um idioma"),
    ("pausa_descansar", "Pausa para descansar"),
)


STATUS_ORDEM = (
    StatusAtividade.REALIZADO,
    StatusAtividade.EM_REVISAO,
    StatusAtividade.EXECUTANDO,
    StatusAtividade.NAO_INICIADO,
)

STATUS_COR = {
    StatusAtividade.REALIZADO: "ok",
    StatusAtividade.EM_REVISAO: "warn",
    StatusAtividade.EXECUTANDO: "accent",
    StatusAtividade.NAO_INICIADO: "orange",
}


class AtividadeDiaria(models.Model):
    responsavel = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name="atividades",
        verbose_name="Responsável principal",
        help_text="Dono da tarefa na equipe.",
    )
    participantes = models.ManyToManyField(
        Funcionario,
        blank=True,
        related_name="atividades_participando",
        verbose_name="Participantes",
        help_text="Outras pessoas que trabalham nesta atividade em grupo.",
    )
    criado_por = models.ForeignKey(
        Funcionario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atividades_criadas",
        verbose_name="Criado por",
    )
    titulo = models.CharField("Título", max_length=200)
    descricao = models.TextField("Descrição", blank=True)
    cliente_rsc = models.ForeignKey(
        "crm.ItemLista",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atividades",
        verbose_name="Empresa",
        help_text="Em branco = RSC. Opções = Clientes RSC (ex.: DPR, OTILINE, CRITEQ).",
        limit_choices_to={"tipo": "clientes_rsc", "ativo": True},
    )
    status = models.CharField(
        "Status",
        max_length=20,
        choices=StatusAtividade.choices,
        default=StatusAtividade.NAO_INICIADO,
        db_index=True,
    )
    prioridade = models.CharField(
        "Prioridade",
        max_length=10,
        choices=PrioridadeAtividade.choices,
        default=PrioridadeAtividade.MEDIA,
    )
    quadrante = models.CharField(
        "Matriz Eisenhower",
        max_length=12,
        choices=QuadranteEisenhower.choices,
        default=QuadranteEisenhower.AGENDAR,
        db_index=True,
    )
    ordem = models.PositiveIntegerField("Ordem", default=0)
    planejado_para = models.DateField(
        "Planejado para",
        null=True,
        blank=True,
        db_index=True,
        help_text="Dia no planner.",
    )
    data_vencimento = models.DateField("Data de vencimento", null=True, blank=True)
    hora_inicio = models.TimeField("Início (agenda)", null=True, blank=True)
    hora_fim = models.TimeField("Fim (agenda)", null=True, blank=True)
    tempo_acumulado_segundos = models.PositiveIntegerField(
        "Tempo acumulado (s)",
        default=0,
    )
    cronometro_inicio = models.DateTimeField(
        "Cronômetro iniciado em",
        null=True,
        blank=True,
    )
    concluida = models.BooleanField("Concluída", default=False)
    concluida_em = models.DateTimeField("Concluída em", null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Atividade"
        verbose_name_plural = "Atividades"
        ordering = ["status", "ordem", "-criado_em"]

    def __str__(self) -> str:
        return self.titulo

    def membros_equipe(self) -> list:
        """Responsável principal + participantes, sem duplicar."""
        membros = []
        if self.responsavel_id:
            membros.append(self.responsavel)
        try:
            extras = self.participantes.all()
        except ValueError:
            extras = []
        for p in extras:
            if p.pk != self.responsavel_id:
                membros.append(p)
        return membros

    def faz_parte_da_equipe(self, funcionario) -> bool:
        if funcionario is None:
            return False
        if self.responsavel_id == funcionario.id:
            return True
        if not self.pk:
            return False
        return self.participantes.filter(pk=funcionario.id).exists()

    @property
    def empresa_label(self) -> str:
        if self.cliente_rsc_id and self.cliente_rsc:
            return self.cliente_rsc.nome
        return "RSC"

    @property
    def eh_trabalho_interno(self) -> bool:
        return self.cliente_rsc_id is None

    @property
    def cronometro_ativo(self) -> bool:
        return self.cronometro_inicio is not None

    def tempo_atual_segundos(self) -> int:
        total = int(self.tempo_acumulado_segundos or 0)
        if self.cronometro_inicio:
            total += max(
                0, int((timezone.now() - self.cronometro_inicio).total_seconds())
            )
        return total

    def sincronizar_conclusao(self) -> None:
        if self.status == StatusAtividade.REALIZADO:
            if not self.concluida:
                self.concluida = True
                self.concluida_em = self.concluida_em or timezone.now()
        else:
            self.concluida = False
            self.concluida_em = None


def quadrante_por_prioridade(prioridade: str) -> str:
    mapa = {
        PrioridadeAtividade.URGENTE: QuadranteEisenhower.FAZER,
        PrioridadeAtividade.ALTA: QuadranteEisenhower.AGENDAR,
        PrioridadeAtividade.MEDIA: QuadranteEisenhower.DELEGAR,
        PrioridadeAtividade.BAIXA: QuadranteEisenhower.ELIMINAR,
    }
    return mapa.get(prioridade, QuadranteEisenhower.AGENDAR)


class DiaPlanner(models.Model):
    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name="dias_planner",
        verbose_name="Funcionário",
    )
    data = models.DateField("Data", db_index=True)
    agua_copos = models.PositiveSmallIntegerField(
        "Copos de água",
        default=0,
        help_text=f"Meta: {COPOS_AGUA_META} × {ML_POR_COPO} mL",
    )
    pomodoros = models.PositiveSmallIntegerField("Pomodoros concluídos", default=0)
    notas = models.TextField("Notas", blank=True)
    citacao = models.CharField("Citação do dia", max_length=280, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dia do planner"
        verbose_name_plural = "Dias do planner"
        constraints = [
            models.UniqueConstraint(
                fields=["funcionario", "data"],
                name="uniq_planner_funcionario_data",
            )
        ]
        ordering = ["-data"]

    def __str__(self) -> str:
        return f"{self.funcionario} · {self.data}"

    @property
    def agua_ml(self) -> int:
        return int(self.agua_copos or 0) * ML_POR_COPO

    @property
    def agua_meta_ml(self) -> int:
        return COPOS_AGUA_META * ML_POR_COPO


class MetaFoco(models.Model):
    dia = models.ForeignKey(
        DiaPlanner,
        on_delete=models.CASCADE,
        related_name="metas",
        verbose_name="Dia",
    )
    texto = models.CharField("Meta", max_length=200)
    ordem = models.PositiveSmallIntegerField("Ordem", default=0)
    concluida = models.BooleanField("Concluída", default=False)

    class Meta:
        verbose_name = "Meta de foco"
        verbose_name_plural = "Metas de foco"
        ordering = ["ordem", "id"]

    def __str__(self) -> str:
        return self.texto


class HabitoDia(models.Model):
    dia = models.ForeignKey(
        DiaPlanner,
        on_delete=models.CASCADE,
        related_name="habitos",
        verbose_name="Dia",
    )
    chave = models.CharField("Hábito", max_length=40)
    feito = models.BooleanField("Feito", default=False)

    class Meta:
        verbose_name = "Hábito do dia"
        verbose_name_plural = "Hábitos do dia"
        constraints = [
            models.UniqueConstraint(
                fields=["dia", "chave"],
                name="uniq_habito_dia_chave",
            )
        ]

    def __str__(self) -> str:
        return self.chave

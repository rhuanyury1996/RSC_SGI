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


class AtividadeQuerySet(models.QuerySet):
    def ativas(self):
        return self.filter(deletado_em__isnull=True)


class TipoEventoAtividade(models.TextChoices):
    CRIACAO = "criacao", "Criação"
    STATUS = "status", "Status"
    COMENTARIO = "comentario", "Comentário"
    EDICAO = "edicao", "Edição"
    EXCLUSAO = "exclusao", "Exclusão"
    RESTAURACAO = "restauracao", "Restauração"


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
    atividade_pai = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subtarefas",
        verbose_name="Atividade principal",
        help_text="Se preenchido, esta é uma subtarefa.",
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
        help_text="Em branco = sem empresa. Opções = clientes RSC (ex.: DPR, OTILINE, CRITEQ).",
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
    deletado_em = models.DateTimeField("Excluída em", null=True, blank=True, db_index=True)
    deletado_por = models.ForeignKey(
        Funcionario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atividades_excluidas",
        verbose_name="Excluída por",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = AtividadeQuerySet.as_manager()

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
    def eh_subtarefa(self) -> bool:
        return self.atividade_pai_id is not None

    @property
    def empresa_label(self) -> str:
        if self.cliente_rsc_id and self.cliente_rsc:
            return self.cliente_rsc.nome
        return "Sem empresa"

    def data_atraso(self, hoje=None):
        """Dia de origem quando a tarefa passou da data e ainda não foi realizada."""
        hoje = hoje or timezone.localdate()
        if self.status == StatusAtividade.REALIZADO:
            return None
        datas = []
        if self.planejado_para and self.planejado_para < hoje:
            datas.append(self.planejado_para)
        if self.data_vencimento and self.data_vencimento < hoje:
            datas.append(self.data_vencimento)
        return min(datas) if datas else None

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


class SessaoTempoAtividade(models.Model):
    """Trecho de cronômetro atribuído a quem iniciou (para relatório)."""

    atividade = models.ForeignKey(
        AtividadeDiaria,
        on_delete=models.CASCADE,
        related_name="sessoes_tempo",
        verbose_name="Atividade",
    )
    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name="sessoes_tempo_atividade",
        verbose_name="Funcionário",
    )
    inicio = models.DateTimeField("Início")
    fim = models.DateTimeField("Fim", null=True, blank=True)
    segundos = models.PositiveIntegerField("Segundos", default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sessão de tempo"
        verbose_name_plural = "Sessões de tempo"
        ordering = ["-inicio"]
        indexes = [
            models.Index(fields=["funcionario", "inicio"]),
            models.Index(fields=["atividade", "inicio"]),
        ]

    def __str__(self) -> str:
        return f"{self.funcionario} · {self.atividade_id} · {self.segundos}s"

    def segundos_atuais(self) -> int:
        if self.fim:
            return int(self.segundos or 0)
        return max(0, int((timezone.now() - self.inicio).total_seconds()))


def quadrante_por_prioridade(prioridade: str) -> str:
    """Sugestão. O valor gravado é o escolhido no formulário, não este mapa."""
    mapa = {
        PrioridadeAtividade.URGENTE: QuadranteEisenhower.FAZER,
        PrioridadeAtividade.ALTA: QuadranteEisenhower.AGENDAR,
        PrioridadeAtividade.MEDIA: QuadranteEisenhower.AGENDAR,
        PrioridadeAtividade.BAIXA: QuadranteEisenhower.ELIMINAR,
    }
    return mapa.get(prioridade, QuadranteEisenhower.AGENDAR)


def aviso_quadrante(prioridade: str, quadrante: str) -> str:
    """Aviso, sem bloquear, quando prioridade e quadrante se contradizem."""
    if (
        prioridade == PrioridadeAtividade.URGENTE
        and quadrante == QuadranteEisenhower.ELIMINAR
    ):
        return "Urgente com Eliminar é contraditório. O quadrante escolhido foi mantido."
    if (
        prioridade == PrioridadeAtividade.BAIXA
        and quadrante == QuadranteEisenhower.FAZER
    ):
        return "Prioridade baixa com Fazer primeiro é contraditório. O quadrante escolhido foi mantido."
    return ""


class EventoAtividade(models.Model):
    """Histórico e comentários de uma tarefa."""

    atividade = models.ForeignKey(
        AtividadeDiaria,
        on_delete=models.CASCADE,
        related_name="eventos",
        verbose_name="Atividade",
    )
    autor = models.ForeignKey(
        Funcionario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_atividade",
        verbose_name="Autor",
    )
    tipo = models.CharField(
        "Tipo",
        max_length=20,
        choices=TipoEventoAtividade.choices,
        default=TipoEventoAtividade.COMENTARIO,
    )
    texto = models.TextField("Texto", blank=True)
    de_status = models.CharField("De", max_length=20, blank=True)
    para_status = models.CharField("Para", max_length=20, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento da atividade"
        verbose_name_plural = "Eventos da atividade"
        ordering = ["criado_em", "id"]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} · {self.atividade_id}"


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

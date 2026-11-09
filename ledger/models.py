from __future__ import annotations

from django.db import models

from workspaces.models import Workspace


class WorkspaceScopedQuerySet(models.QuerySet):
    def for_workspace(self, workspace: Workspace):
        return self.filter(workspace=workspace)


class WorkspaceScopedManager(models.Manager.from_queryset(WorkspaceScopedQuerySet)):
    pass


class WorkspaceModel(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = WorkspaceScopedManager()

    class Meta:
        abstract = True


class EntryKind(models.TextChoices):
    INCOME = "income", "Receita"
    PROJECTED_SALE = "projected_sale", "Venda projetada"
    FIXED_EXPENSE = "fixed_expense", "Despesa fixa"
    VARIABLE_EXPENSE = "variable_expense", "Despesa variável"
    PROJECTED_PURCHASE = "projected_purchase", "Compra projetada"
    SALARY = "salary", "Salário"
    TAX = "tax", "Imposto a pagar"


class Entity(WorkspaceModel):
    class Kind(models.TextChoices):
        COMPANY = "company", "Empresa"
        PERSONAL = "personal", "Pessoal"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.COMPANY)
    active = models.BooleanField(default=True)
    # Alíquota efetiva em basis points (1700 = 17,00%)
    effective_tax_rate_bps = models.PositiveIntegerField(
        default=1700,
        help_text="Alíquota efetiva em basis points. 1700 = 17%.",
    )

    class Meta:
        unique_together = ("workspace", "name")
        verbose_name_plural = "entities"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Account(WorkspaceModel):
    class Type(models.TextChoices):
        BANK = "bank", "Banco"
        CREDIT_CARD = "credit_card", "Cartão"
        CASH = "cash", "Dinheiro"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=Type.choices)
    closing_day = models.PositiveSmallIntegerField(null=True, blank=True)
    due_day = models.PositiveSmallIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)
    credit_limit_cents = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.entity.name})"


class Category(WorkspaceModel):
    class Kind(models.TextChoices):
        EXPENSE = "expense", "Despesa"
        INCOME = "income", "Receita"

    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("workspace", "parent", "name", "kind")
        verbose_name_plural = "categories"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        if self.parent_id:
            return f"{self.parent.name} › {self.name}"
        return self.name


class Project(WorkspaceModel):
    class Nature(models.TextChoices):
        PROFESSIONAL = "professional", "Profissional"
        PERSONAL = "personal", "Pessoal"

    name = models.CharField(max_length=200)
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="projects")
    nature = models.CharField(
        max_length=20, choices=Nature.choices, default=Nature.PROFESSIONAL
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    budget_cents = models.BigIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def spent_cents(self) -> int:
        total = (
            self.transactions.filter(amount_cents__lt=0).aggregate(
                s=models.Sum("amount_cents")
            )["s"]
            or 0
        )
        return abs(int(total))


class InstallmentPurchase(WorkspaceModel):
    class Nature(models.TextChoices):
        PROFESSIONAL = "professional", "Profissional"
        PERSONAL = "personal", "Pessoal"

    description = models.CharField(max_length=255)
    total_amount_cents = models.BigIntegerField()
    num_installments = models.PositiveIntegerField()
    first_due_date = models.DateField()
    competence_date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    nature = models.CharField(
        max_length=20, choices=Nature.choices, default=Nature.PROFESSIONAL
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL
    )
    reimbursable = models.BooleanField(default=False)
    reimburse_to_entity = models.ForeignKey(
        Entity,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="installment_reimbursements",
    )
    notes = models.TextField(blank=True)
    attachment_path = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.description


class Recurrence(WorkspaceModel):
    class Periodicity(models.TextChoices):
        MONTHLY = "monthly", "Mensal"
        QUARTERLY = "quarterly", "Trimestral"
        YEARLY = "yearly", "Anual"

    class Nature(models.TextChoices):
        PROFESSIONAL = "professional", "Profissional"
        PERSONAL = "personal", "Pessoal"

    description = models.CharField(max_length=255, verbose_name="Descrição")
    amount_cents = models.BigIntegerField()
    periodicity = models.CharField(
        max_length=20, choices=Periodicity.choices, verbose_name="Periodicidade"
    )
    start_date = models.DateField(verbose_name="Início")
    end_date = models.DateField(null=True, blank=True, verbose_name="Término")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name="Conta")
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, verbose_name="Categoria"
    )
    nature = models.CharField(
        max_length=20, choices=Nature.choices, default=Nature.PROFESSIONAL
    )
    entry_kind = models.CharField(
        max_length=32,
        choices=EntryKind.choices,
        default=EntryKind.VARIABLE_EXPENSE,
        verbose_name="Tipo de lançamento",
    )
    employee = models.ForeignKey(
        "Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recurrences",
        verbose_name="Funcionário",
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL
    )
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["description"]
        verbose_name = "Recorrência"
        verbose_name_plural = "Recorrências"

    def __str__(self) -> str:
        return self.description


class Transfer(WorkspaceModel):
    class Kind(models.TextChoices):
        CONTRIBUTION = "contribution", "Aporte"
        WITHDRAWAL = "withdrawal", "Retirada"
        REIMBURSEMENT = "reimbursement", "Reembolso"
        GENERIC = "generic", "Transferência"

    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.GENERIC)
    amount_cents = models.BigIntegerField()
    transfer_date = models.DateField()
    from_entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, related_name="transfers_out"
    )
    to_entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, related_name="transfers_in"
    )
    from_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="transfers_out"
    )
    to_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="transfers_in"
    )
    description = models.CharField(max_length=255)
    source_transaction = models.ForeignKey(
        "Transaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generated_transfers",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-transfer_date"]


class Transaction(WorkspaceModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        PAID = "paid", "Pago"

    class Nature(models.TextChoices):
        PROFESSIONAL = "professional", "Profissional"
        PERSONAL = "personal", "Pessoal"

    # Mantido por compatibilidade com código que usa Transaction.EntryKind
    EntryKind = EntryKind

    competence_date = models.DateField(verbose_name="Data de competência")
    due_date = models.DateField(verbose_name="Data de vencimento")
    amount_cents = models.BigIntegerField(
        help_text="Positivo = receita/entrada; negativo = despesa/saída"
    )
    description = models.CharField(max_length=255, verbose_name="Descrição")
    entry_kind = models.CharField(
        max_length=32,
        choices=EntryKind.choices,
        default=EntryKind.VARIABLE_EXPENSE,
        verbose_name="Tipo de lançamento",
        db_index=True,
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, verbose_name="Categoria"
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name="Conta",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Status",
    )
    nature = models.CharField(
        max_length=20, choices=Nature.choices, verbose_name="Natureza"
    )
    employee = models.ForeignKey(
        "Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
        verbose_name="Funcionário",
    )
    reimbursable = models.BooleanField(default=False, verbose_name="Reembolsável")
    reimburse_to_entity = models.ForeignKey(
        Entity,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reimbursement_targets",
        verbose_name="Reembolsar para",
    )
    reimbursed = models.BooleanField(default=False)
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
        verbose_name="Projeto",
    )
    notes = models.TextField(blank=True, verbose_name="Observações")
    attachment_path = models.CharField(max_length=500, blank=True)

    installment_purchase = models.ForeignKey(
        InstallmentPurchase,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="installments",
    )
    installment_number = models.PositiveIntegerField(null=True, blank=True)
    installment_total = models.PositiveIntegerField(null=True, blank=True)

    recurrence = models.ForeignKey(
        Recurrence,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generated_transactions",
    )
    transfer = models.ForeignKey(
        Transfer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legs",
    )
    paid_at = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-due_date", "-id"]
        verbose_name = "Lançamento"
        verbose_name_plural = "Lançamentos"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(amount_cents=0),
                name="ck_tx_amount_nonzero",
            ),
            models.UniqueConstraint(
                fields=["recurrence", "due_date"],
                name="uq_tx_recurrence_due",
                condition=models.Q(recurrence__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["installment_purchase", "installment_number"],
                name="uq_tx_installment_number",
                condition=models.Q(installment_purchase__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return self.description

    @property
    def is_income(self) -> bool:
        return self.amount_cents > 0

    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone

        return (
            self.status == self.Status.PENDING
            and self.due_date < timezone.localdate()
        )


class Equipment(WorkspaceModel):
    class Nature(models.TextChoices):
        PROFESSIONAL = "professional", "Profissional"
        PERSONAL = "personal", "Pessoal"

    name = models.CharField(max_length=200)
    acquisition_value_cents = models.BigIntegerField()
    acquisition_date = models.DateField()
    owner_entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, related_name="owned_equipment"
    )
    user_entity = models.ForeignKey(
        Entity, on_delete=models.PROTECT, related_name="used_equipment"
    )
    nature = models.CharField(
        max_length=20, choices=Nature.choices, default=Nature.PROFESSIONAL
    )
    useful_life_months = models.PositiveIntegerField()
    residual_value_cents = models.BigIntegerField(default=0)
    serial_number = models.CharField(max_length=120, blank=True)
    installment_purchase = models.ForeignKey(
        InstallmentPurchase,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="equipment_items",
    )
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "equipment"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Client(WorkspaceModel):
    """Cliente que pode arcar com reembolso de viagem."""

    name = models.CharField(max_length=120, verbose_name="Nome")
    active = models.BooleanField(default=True, verbose_name="Ativo")
    notes = models.TextField(blank=True, verbose_name="Observações")

    class Meta:
        unique_together = ("workspace", "name")
        ordering = ["name"]
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self) -> str:
        return self.name


class Employee(WorkspaceModel):
    name = models.CharField(max_length=120, verbose_name="Nome")
    active = models.BooleanField(default=True, verbose_name="Ativo")
    notes = models.TextField(blank=True, verbose_name="Observações")

    class Meta:
        unique_together = ("workspace", "name")
        ordering = ["name"]
        verbose_name = "Funcionário"
        verbose_name_plural = "Funcionários"

    def __str__(self) -> str:
        return self.name


class TravelReimbursementRequest(WorkspaceModel):
    """Solicitação de reembolso de despesas de viagem."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        SUBMITTED = "submitted", "Enviada"
        APPROVED = "approved", "Aprovada"
        REIMBURSED = "reimbursed", "Reembolsada"
        REJECTED = "rejected", "Recusada"

    class PayerType(models.TextChoices):
        CLIENT = "client", "Cliente"
        ENTITY = "entity", "Empresa"

    title = models.CharField(max_length=200, verbose_name="Título")
    traveler_name = models.CharField(max_length=120, verbose_name="Viajante")
    destination = models.CharField(max_length=200, verbose_name="Destino")
    start_date = models.DateField(verbose_name="Início")
    end_date = models.DateField(verbose_name="Fim")
    purpose = models.TextField(blank=True, verbose_name="Motivo / job")

    advance_entity = models.ForeignKey(
        Entity,
        on_delete=models.PROTECT,
        related_name="travel_advances",
        verbose_name="Empresa que pagou",
    )
    advance_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="travel_advances",
        verbose_name="Conta de pagamento",
    )

    payer_type = models.CharField(
        max_length=20,
        choices=PayerType.choices,
        default=PayerType.CLIENT,
        verbose_name="Quem reembolsa",
    )
    bill_to_client = models.ForeignKey(
        Client,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="travel_requests",
        verbose_name="Cliente",
    )
    bill_to_entity = models.ForeignKey(
        Entity,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="travel_bill_tos",
        verbose_name="Empresa reembolsadora",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Status",
    )
    notes = models.TextField(blank=True, verbose_name="Observações")
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    reimbursed_at = models.DateTimeField(null=True, blank=True)
    reimbursement_transaction = models.ForeignKey(
        "Transaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="travel_reimbursements",
        verbose_name="Lançamento de reembolso",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Solicitação de reembolso de viagem"
        verbose_name_plural = "Solicitações de reembolso de viagem"

    def __str__(self) -> str:
        return self.title

    @property
    def total_cents(self) -> int:
        return int(sum(line.amount_cents for line in self.lines.all()))

    @property
    def bill_to_label(self) -> str:
        if self.payer_type == self.PayerType.CLIENT and self.bill_to_client_id:
            return self.bill_to_client.name
        if self.bill_to_entity_id:
            return self.bill_to_entity.name
        return "—"


class TravelExpenseItem(WorkspaceModel):
    class Kind(models.TextChoices):
        FLIGHT = "flight", "Passagem aérea"
        LODGING = "lodging", "Hospedagem"
        MEALS = "meals", "Alimentação"
        TRANSPORT = "transport", "Transporte / locação"
        FUEL = "fuel", "Pedágio e combustível"
        PER_DIEM = "per_diem", "Diárias"
        BAGGAGE = "baggage", "Bagagem e taxas"
        OTHER = "other", "Outros"

    request = models.ForeignKey(
        TravelReimbursementRequest,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Solicitação",
    )
    expense_date = models.DateField(verbose_name="Data da despesa")
    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.OTHER, verbose_name="Tipo"
    )
    description = models.CharField(max_length=255, verbose_name="Descrição")
    amount_cents = models.BigIntegerField(verbose_name="Valor (centavos)")
    receipt_path = models.CharField(
        max_length=500, blank=True, verbose_name="Comprovante"
    )

    class Meta:
        ordering = ["expense_date", "id"]
        verbose_name = "Item de despesa de viagem"
        verbose_name_plural = "Itens de despesa de viagem"

    def __str__(self) -> str:
        return self.description


class TimeEntry(WorkspaceModel):
    """Apontamento de horas por cliente (entrada, almoço e saída)."""

    user = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="time_entries",
        verbose_name="Usuário",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="time_entries",
        verbose_name="Cliente",
    )
    work_date = models.DateField(verbose_name="Data", db_index=True)
    clock_in = models.DateTimeField(null=True, blank=True, verbose_name="Entrada")
    lunch_out = models.DateTimeField(null=True, blank=True, verbose_name="Saída almoço")
    lunch_in = models.DateTimeField(null=True, blank=True, verbose_name="Retorno almoço")
    clock_out = models.DateTimeField(null=True, blank=True, verbose_name="Saída")
    notes = models.TextField(blank=True, verbose_name="Observações")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-work_date", "-clock_in", "-id"]
        verbose_name = "Apontamento"
        verbose_name_plural = "Apontamentos"
        indexes = [
            models.Index(fields=["workspace", "user", "work_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.client} · {self.work_date}"

    @property
    def is_open(self) -> bool:
        return self.clock_in is not None and self.clock_out is None

    @property
    def status_code(self) -> str:
        if self.clock_out:
            return "closed"
        if self.lunch_out and not self.lunch_in:
            return "lunch"
        if self.clock_in:
            return "working"
        return "empty"

    @property
    def status_label(self) -> str:
        return {
            "closed": "Encerrado",
            "lunch": "Em almoço",
            "working": "Trabalhando",
            "empty": "Sem entrada",
        }.get(self.status_code, self.status_code)

    def worked_seconds(self, *, until=None) -> int:
        if not self.clock_in:
            return 0
        end = self.clock_out or until
        if end is None:
            from django.utils import timezone as dj_tz

            end = dj_tz.now()
        total = max(0, int((end - self.clock_in).total_seconds()))
        if self.lunch_out:
            lunch_end = self.lunch_in or (None if self.clock_out else end)
            if lunch_end and lunch_end > self.lunch_out:
                total -= max(0, int((lunch_end - self.lunch_out).total_seconds()))
        return max(0, total)

    def worked_display(self, *, until=None) -> str:
        secs = self.worked_seconds(until=until)
        hours, rem = divmod(secs, 3600)
        minutes, _ = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}"

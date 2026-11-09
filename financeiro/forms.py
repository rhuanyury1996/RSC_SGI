from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from ledger.models import (
    Account,
    Category,
    Client,
    Employee,
    Entity,
    Equipment,
    Project,
    Recurrence,
    TimeEntry,
    Transaction,
    TravelExpenseItem,
    TravelReimbursementRequest,
)
from ledger.money import reais_to_cents
from ledger.services import create_entry_with_optional_recurrence


INPUT = ""  # o visual vem do sgi.css
SELECT = INPUT
CHECK = ""
# HTML5 type=date exige ISO; com LANGUAGE_CODE=pt-br o Django localiza e o campo fica vazio.
DATE_INPUT_FORMATS = ["%Y-%m-%d"]


def _date_input(**extra_attrs):
    attrs = {"class": INPUT, **extra_attrs}
    widget = forms.DateInput(format="%Y-%m-%d", attrs=attrs)
    widget.input_type = "date"
    return widget


def _force_iso_dates(form: forms.BaseForm, *names: str) -> None:
    for name in names:
        field = form.fields.get(name)
        if field is None:
            continue
        field.localize = False
        field.input_formats = DATE_INPUT_FORMATS
        field.widget.format = "%Y-%m-%d"
        if getattr(field.widget, "input_type", None) != "date":
            field.widget.input_type = "date"
        field.widget.attrs.pop("type", None)


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Usuário"
        self.fields["password"].label = "Senha"
        self.fields["username"].widget.attrs["class"] = INPUT
        self.fields["password"].widget.attrs["class"] = INPUT


class SignupForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label="E-mail",
        widget=forms.EmailInput(attrs={"class": INPUT}),
    )
    workspace_name = forms.CharField(
        max_length=120,
        label="Nome do espaço",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "Ex.: Finanças Rhuan"}),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2", "workspace_name")
        labels = {"username": "Usuário"}
        widgets = {
            "username": forms.TextInput(attrs={"class": INPUT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Senha"
        self.fields["password2"].label = "Confirmar senha"
        self.fields["password1"].widget.attrs["class"] = INPUT
        self.fields["password2"].widget.attrs["class"] = INPUT


class MoneyField(forms.CharField):
    def to_python(self, value):
        value = super().to_python(value)
        if value in self.empty_values:
            return None
        return reais_to_cents(value)


class TransactionForm(forms.ModelForm):
    RECURRING_KINDS = {
        Transaction.EntryKind.INCOME,
        Transaction.EntryKind.PROJECTED_SALE,
        Transaction.EntryKind.FIXED_EXPENSE,
        Transaction.EntryKind.VARIABLE_EXPENSE,
        Transaction.EntryKind.SALARY,
    }

    amount = MoneyField(
        label="Valor (R$)",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "0,00"}),
    )
    employee = forms.ModelChoiceField(
        label="Funcionário",
        queryset=Employee.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    is_recurring = forms.BooleanField(
        label="Lançamento recorrente",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": CHECK, "id": "id_is_recurring"}),
    )
    periodicity = forms.ChoiceField(
        label="Periodicidade",
        choices=Recurrence.Periodicity.choices,
        required=False,
        initial=Recurrence.Periodicity.MONTHLY,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    recurrence_start = forms.DateField(
        label="Início da recorrência",
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=_date_input(),
    )
    recurrence_end = forms.DateField(
        label="Término da recorrência",
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=_date_input(),
        help_text="Obrigatório para gerar as parcelas no intervalo. Sem término, gera 12 meses.",
    )

    class Meta:
        model = Transaction
        fields = [
            "description",
            "competence_date",
            "due_date",
            "account",
            "category",
            "nature",
            "status",
            "project",
            "reimbursable",
            "reimburse_to_entity",
            "notes",
        ]
        labels = {
            "description": "Descrição",
            "competence_date": "Competência",
            "due_date": "Vencimento",
            "account": "Conta",
            "category": "Categoria",
            "nature": "Natureza",
            "status": "Status",
            "project": "Projeto",
            "reimbursable": "Reembolsável",
            "reimburse_to_entity": "Reembolsar para",
            "notes": "Observações",
        }
        widgets = {
            "description": forms.TextInput(attrs={"class": INPUT}),
            "competence_date": _date_input(),
            "due_date": _date_input(),
            "account": forms.Select(attrs={"class": SELECT}),
            "category": forms.Select(attrs={"class": SELECT}),
            "nature": forms.Select(attrs={"class": SELECT}),
            "status": forms.Select(attrs={"class": SELECT}),
            "project": forms.Select(attrs={"class": SELECT}),
            "reimbursable": forms.CheckboxInput(attrs={"class": CHECK}),
            "reimburse_to_entity": forms.Select(attrs={"class": SELECT}),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 3}),
        }

    def __init__(self, *args, workspace=None, entry_kind: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        self.created_count = 1
        self.recurrence = None
        self.entry_kind = entry_kind or (
            self.instance.entry_kind
            if self.instance and self.instance.pk
            else Transaction.EntryKind.VARIABLE_EXPENSE
        )
        _force_iso_dates(
            self, "competence_date", "due_date", "recurrence_start", "recurrence_end"
        )
        income_kinds = {
            Transaction.EntryKind.INCOME,
            Transaction.EntryKind.PROJECTED_SALE,
        }
        is_income = self.entry_kind in income_kinds
        self.supports_recurrence = self.entry_kind in self.RECURRING_KINDS
        self.is_salary = self.entry_kind == Transaction.EntryKind.SALARY
        self.is_projected_sale = self.entry_kind == Transaction.EntryKind.PROJECTED_SALE

        if workspace:
            self.fields["account"].queryset = Account.objects.for_workspace(workspace).filter(
                active=True
            )
            cats = Category.objects.for_workspace(workspace).filter(
                active=True, parent__isnull=False
            )
            if is_income:
                cats = cats.filter(kind=Category.Kind.INCOME)
            else:
                cats = cats.filter(kind=Category.Kind.EXPENSE)
                if self.entry_kind == Transaction.EntryKind.SALARY:
                    cats = cats.filter(parent__name="Pessoal/Folha")
                elif self.entry_kind == Transaction.EntryKind.TAX:
                    cats = cats.filter(parent__name="Impostos")
                elif self.entry_kind == Transaction.EntryKind.PROJECTED_PURCHASE:
                    cats = cats.filter(parent__name__in=["Equipamentos", "Operacional", "Viagem"])
            self.fields["category"].queryset = cats
            self.fields["project"].queryset = Project.objects.for_workspace(workspace).filter(
                active=True
            )
            self.fields["project"].required = False
            self.fields["reimburse_to_entity"].queryset = Entity.objects.for_workspace(
                workspace
            ).filter(active=True)
            self.fields["reimburse_to_entity"].required = False
            self.fields["employee"].queryset = Employee.objects.for_workspace(workspace).filter(
                active=True
            )

        if self.is_salary:
            self.fields["employee"].required = True
        else:
            self.fields.pop("employee", None)

        # Receitas / vendas projetadas não usam reembolso
        if is_income:
            self.fields.pop("reimbursable", None)
            self.fields.pop("reimburse_to_entity", None)

        if not self.supports_recurrence or (self.instance and self.instance.pk):
            for name in ("is_recurring", "periodicity", "recurrence_start", "recurrence_end"):
                self.fields.pop(name, None)

        field_order = [
            "description",
            *(["employee"] if self.is_salary and "employee" in self.fields else []),
            "amount",
            "competence_date",
            "due_date",
            *(
                ["is_recurring", "periodicity", "recurrence_start", "recurrence_end"]
                if "is_recurring" in self.fields
                else []
            ),
            "account",
            "category",
            "nature",
            "status",
            "project",
            *(["reimbursable", "reimburse_to_entity"] if "reimbursable" in self.fields else []),
            "notes",
        ]
        self.order_fields([name for name in field_order if name in self.fields])

        if self.instance and self.instance.pk:
            self.fields["amount"].initial = f"{abs(self.instance.amount_cents) / 100:.2f}".replace(
                ".", ","
            )

        if self.entry_kind in {
            Transaction.EntryKind.SALARY,
            Transaction.EntryKind.TAX,
            Transaction.EntryKind.FIXED_EXPENSE,
        }:
            self.fields["nature"].initial = Transaction.Nature.PROFESSIONAL

    def clean(self):
        cleaned = super().clean()
        if not self.supports_recurrence or "is_recurring" not in self.fields:
            return cleaned
        if cleaned.get("is_recurring"):
            start = cleaned.get("recurrence_start") or cleaned.get("due_date")
            end = cleaned.get("recurrence_end")
            if not start:
                self.add_error(
                    "recurrence_start",
                    "Informe o início da recorrência (ou a data de vencimento).",
                )
            elif end and end < start:
                self.add_error("recurrence_end", "O término deve ser igual ou posterior ao início.")
            if not cleaned.get("periodicity"):
                cleaned["periodicity"] = Recurrence.Periodicity.MONTHLY
            cleaned["recurrence_start"] = start
        return cleaned

    def save(self, commit=True):
        if self.instance and self.instance.pk:
            obj = super().save(commit=False)
            amount = abs(self.cleaned_data["amount"])
            obj.entry_kind = self.entry_kind
            if self.entry_kind == Transaction.EntryKind.INCOME:
                obj.amount_cents = amount
            elif self.entry_kind == Transaction.EntryKind.PROJECTED_SALE:
                obj.amount_cents = amount
            else:
                obj.amount_cents = -amount
            if self.is_salary:
                obj.employee = self.cleaned_data.get("employee")
                emp = obj.employee
                if emp and emp.name not in obj.description:
                    obj.description = f"{obj.description} — {emp.name}"
            if self.workspace:
                obj.workspace = self.workspace
            if commit:
                obj.save()
            self.created_count = 1
            return obj

        if not commit:
            return super().save(commit=False)

        is_recurring = bool(self.cleaned_data.get("is_recurring"))
        rec, created = create_entry_with_optional_recurrence(
            workspace=self.workspace,
            entry_kind=self.entry_kind,
            description=self.cleaned_data["description"],
            amount_cents=abs(self.cleaned_data["amount"]),
            account=self.cleaned_data["account"],
            category=self.cleaned_data["category"],
            nature=self.cleaned_data["nature"],
            status=self.cleaned_data["status"],
            competence_date=self.cleaned_data["competence_date"],
            due_date=self.cleaned_data["due_date"],
            project=self.cleaned_data.get("project"),
            employee=self.cleaned_data.get("employee") if self.is_salary else None,
            notes=self.cleaned_data.get("notes") or "",
            reimbursable=self.cleaned_data.get("reimbursable") or False,
            reimburse_to_entity=self.cleaned_data.get("reimburse_to_entity"),
            is_recurring=is_recurring,
            periodicity=self.cleaned_data.get("periodicity") or Recurrence.Periodicity.MONTHLY,
            recurrence_start=self.cleaned_data.get("recurrence_start"),
            recurrence_end=self.cleaned_data.get("recurrence_end"),
        )
        self.recurrence = rec
        self.created_count = len(created)
        return created[0] if created else None


class InstallmentForm(forms.Form):
    description = forms.CharField(
        label="Descrição",
        widget=forms.TextInput(attrs={"class": INPUT}),
    )
    total_amount = MoneyField(
        label="Valor total (R$)",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "0,00"}),
    )
    num_installments = forms.IntegerField(
        label="Nº de parcelas",
        min_value=1,
        max_value=360,
        widget=forms.NumberInput(attrs={"class": INPUT}),
    )
    first_due_date = forms.DateField(
        label="1º vencimento",
        input_formats=DATE_INPUT_FORMATS,
        widget=_date_input(),
    )
    competence_date = forms.DateField(
        label="Competência",
        input_formats=DATE_INPUT_FORMATS,
        widget=_date_input(),
    )
    account = forms.ModelChoiceField(
        label="Conta",
        queryset=Account.objects.none(),
        widget=forms.Select(attrs={"class": SELECT}),
    )
    category = forms.ModelChoiceField(
        label="Categoria",
        queryset=Category.objects.none(),
        widget=forms.Select(attrs={"class": SELECT}),
    )
    nature = forms.ChoiceField(
        label="Natureza",
        choices=Transaction.Nature.choices,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    project = forms.ModelChoiceField(
        label="Projeto",
        queryset=Project.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    notes = forms.CharField(
        label="Observações",
        required=False,
        widget=forms.Textarea(attrs={"class": INPUT, "rows": 2}),
    )

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace:
            self.fields["account"].queryset = Account.objects.for_workspace(workspace).filter(
                active=True
            )
            self.fields["category"].queryset = Category.objects.for_workspace(workspace).filter(
                active=True, kind=Category.Kind.EXPENSE, parent__isnull=False
            )
            self.fields["project"].queryset = Project.objects.for_workspace(workspace).filter(
                active=True
            )


class ProjectForm(forms.ModelForm):
    budget = MoneyField(
        required=False,
        label="Orçamento (R$)",
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "0,00"}),
    )

    class Meta:
        model = Project
        fields = ["name", "entity", "nature", "start_date", "end_date", "notes", "active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT}),
            "entity": forms.Select(attrs={"class": SELECT}),
            "nature": forms.Select(attrs={"class": SELECT}),
            "start_date": _date_input(),
            "end_date": _date_input(),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 3}),
            "active": forms.CheckboxInput(attrs={"class": CHECK}),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        if workspace:
            self.fields["entity"].queryset = Entity.objects.for_workspace(workspace).filter(
                active=True
            )
        if self.instance and self.instance.budget_cents:
            self.fields["budget"].initial = self.instance.budget_cents / 100

    def save(self, commit=True):
        obj = super().save(commit=False)
        budget = self.cleaned_data.get("budget")
        obj.budget_cents = budget
        if self.workspace:
            obj.workspace = self.workspace
        if commit:
            obj.save()
        return obj


class EquipmentForm(forms.ModelForm):
    acquisition_value = MoneyField(
        label="Valor de aquisição (R$)",
        widget=forms.TextInput(attrs={"class": INPUT}),
    )
    residual_value = MoneyField(
        required=False,
        label="Valor residual (R$)",
        widget=forms.TextInput(attrs={"class": INPUT}),
    )

    class Meta:
        model = Equipment
        fields = [
            "name",
            "acquisition_date",
            "owner_entity",
            "user_entity",
            "nature",
            "useful_life_months",
            "serial_number",
            "notes",
            "active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT}),
            "acquisition_date": _date_input(),
            "owner_entity": forms.Select(attrs={"class": SELECT}),
            "user_entity": forms.Select(attrs={"class": SELECT}),
            "nature": forms.Select(attrs={"class": SELECT}),
            "useful_life_months": forms.NumberInput(attrs={"class": INPUT}),
            "serial_number": forms.TextInput(attrs={"class": INPUT}),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
            "active": forms.CheckboxInput(attrs={"class": CHECK}),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        if workspace:
            qs = Entity.objects.for_workspace(workspace).filter(active=True)
            self.fields["owner_entity"].queryset = qs
            self.fields["user_entity"].queryset = qs

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.acquisition_value_cents = self.cleaned_data["acquisition_value"]
        obj.residual_value_cents = self.cleaned_data.get("residual_value") or 0
        if self.workspace:
            obj.workspace = self.workspace
        if commit:
            obj.save()
        return obj


class EntityForm(forms.ModelForm):
    class Meta:
        model = Entity
        fields = ["name", "kind", "active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT}),
            "kind": forms.Select(attrs={"class": SELECT}),
            "active": forms.CheckboxInput(attrs={"class": CHECK}),
        }


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = [
            "entity",
            "name",
            "type",
            "closing_day",
            "due_day",
            "credit_limit_cents",
            "active",
        ]
        widgets = {
            "entity": forms.Select(attrs={"class": SELECT}),
            "name": forms.TextInput(attrs={"class": INPUT}),
            "type": forms.Select(attrs={"class": SELECT}),
            "closing_day": forms.NumberInput(attrs={"class": INPUT}),
            "due_day": forms.NumberInput(attrs={"class": INPUT}),
            "credit_limit_cents": forms.NumberInput(attrs={"class": INPUT}),
            "active": forms.CheckboxInput(attrs={"class": CHECK}),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace:
            self.fields["entity"].queryset = Entity.objects.for_workspace(workspace)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["parent", "name", "kind", "active", "sort_order"]
        widgets = {
            "parent": forms.Select(attrs={"class": SELECT}),
            "name": forms.TextInput(attrs={"class": INPUT}),
            "kind": forms.Select(attrs={"class": SELECT}),
            "active": forms.CheckboxInput(attrs={"class": CHECK}),
            "sort_order": forms.NumberInput(attrs={"class": INPUT}),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace:
            self.fields["parent"].queryset = Category.objects.for_workspace(workspace).filter(
                parent__isnull=True
            )
            self.fields["parent"].required = False


class RecurrenceForm(forms.ModelForm):
    amount = MoneyField(label="Valor (R$)", widget=forms.TextInput(attrs={"class": INPUT}))

    class Meta:
        model = Recurrence
        fields = [
            "description",
            "periodicity",
            "start_date",
            "end_date",
            "account",
            "category",
            "nature",
            "project",
            "active",
            "notes",
        ]
        widgets = {
            "description": forms.TextInput(attrs={"class": INPUT}),
            "periodicity": forms.Select(attrs={"class": SELECT}),
            "start_date": _date_input(),
            "end_date": _date_input(),
            "account": forms.Select(attrs={"class": SELECT}),
            "category": forms.Select(attrs={"class": SELECT}),
            "nature": forms.Select(attrs={"class": SELECT}),
            "project": forms.Select(attrs={"class": SELECT}),
            "active": forms.CheckboxInput(attrs={"class": CHECK}),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        if workspace:
            self.fields["account"].queryset = Account.objects.for_workspace(workspace).filter(
                active=True
            )
            self.fields["category"].queryset = Category.objects.for_workspace(workspace).filter(
                active=True, parent__isnull=False
            )
            self.fields["project"].queryset = Project.objects.for_workspace(workspace).filter(
                active=True
            )
            self.fields["project"].required = False
            self.fields["end_date"].required = False

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.amount_cents = abs(self.cleaned_data["amount"])
        if self.workspace:
            obj.workspace = self.workspace
        if commit:
            obj.save()
        return obj


class TravelRequestForm(forms.ModelForm):
    class Meta:
        model = TravelReimbursementRequest
        fields = [
            "title",
            "traveler_name",
            "destination",
            "start_date",
            "end_date",
            "purpose",
            "advance_entity",
            "advance_account",
            "payer_type",
            "bill_to_client",
            "bill_to_entity",
            "notes",
        ]
        labels = {
            "title": "Título",
            "traveler_name": "Viajante",
            "destination": "Destino",
            "start_date": "Início",
            "end_date": "Fim",
            "purpose": "Motivo / job",
            "advance_entity": "Empresa que pagou",
            "advance_account": "Conta de pagamento",
            "payer_type": "Quem reembolsa",
            "bill_to_client": "Cliente",
            "bill_to_entity": "Empresa reembolsadora",
            "notes": "Observações",
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT}),
            "traveler_name": forms.TextInput(attrs={"class": INPUT}),
            "destination": forms.TextInput(attrs={"class": INPUT}),
            "start_date": _date_input(),
            "end_date": _date_input(),
            "purpose": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
            "advance_entity": forms.Select(attrs={"class": SELECT}),
            "advance_account": forms.Select(attrs={"class": SELECT}),
            "payer_type": forms.Select(attrs={"class": SELECT, "id": "id_payer_type"}),
            "bill_to_client": forms.Select(attrs={"class": SELECT}),
            "bill_to_entity": forms.Select(attrs={"class": SELECT}),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        if workspace:
            self.fields["advance_entity"].queryset = Entity.objects.for_workspace(
                workspace
            ).filter(active=True)
            self.fields["advance_account"].queryset = Account.objects.for_workspace(
                workspace
            ).filter(active=True)
            self.fields["bill_to_client"].queryset = Client.objects.for_workspace(
                workspace
            ).filter(active=True)
            self.fields["bill_to_entity"].queryset = Entity.objects.for_workspace(
                workspace
            ).filter(active=True)
            self.fields["bill_to_client"].required = False
            self.fields["bill_to_entity"].required = False

    def clean(self):
        cleaned = super().clean()
        payer = cleaned.get("payer_type")
        client = cleaned.get("bill_to_client")
        entity = cleaned.get("bill_to_entity")
        if payer == TravelReimbursementRequest.PayerType.CLIENT and not client:
            self.add_error("bill_to_client", "Selecione o cliente que reembolsa.")
        if payer == TravelReimbursementRequest.PayerType.ENTITY and not entity:
            self.add_error("bill_to_entity", "Selecione a empresa que reembolsa.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.workspace:
            obj.workspace = self.workspace
        if obj.payer_type == TravelReimbursementRequest.PayerType.CLIENT:
            obj.bill_to_entity = None
        else:
            obj.bill_to_client = None
        if commit:
            obj.save()
        return obj


class TravelExpenseItemForm(forms.ModelForm):
    amount = MoneyField(
        label="Valor (R$)",
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "0,00"}),
    )

    class Meta:
        model = TravelExpenseItem
        fields = ["expense_date", "kind", "description"]
        labels = {
            "expense_date": "Data",
            "kind": "Tipo",
            "description": "Descrição",
        }
        widgets = {
            "expense_date": _date_input(),
            "kind": forms.Select(attrs={"class": SELECT}),
            "description": forms.TextInput(attrs={"class": INPUT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expense_date"].required = False
        self.fields["description"].required = False
        if self.instance and self.instance.pk and self.instance.amount_cents:
            self.fields["amount"].initial = (
                f"{abs(self.instance.amount_cents) / 100:.2f}".replace(".", ",")
            )

    def clean(self):
        cleaned = super().clean()
        if self.cleaned_data.get("DELETE"):
            return cleaned
        desc = (cleaned.get("description") or "").strip()
        amount = cleaned.get("amount")
        date = cleaned.get("expense_date")
        filled = any([desc, amount, date])
        if filled and (not desc or not amount or not date):
            raise forms.ValidationError(
                "Preencha data, descrição e valor em cada despesa informada."
            )
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.amount_cents = abs(self.cleaned_data["amount"] or 0)
        if commit:
            obj.save()
        return obj


def make_travel_item_formset(extra: int = 3):
    from django.forms import inlineformset_factory

    return inlineformset_factory(
        TravelReimbursementRequest,
        TravelExpenseItem,
        form=TravelExpenseItemForm,
        extra=extra,
        can_delete=True,
        min_num=1,
        validate_min=True,
    )


class TimeClockInForm(forms.Form):
    client = forms.ModelChoiceField(
        label="Cliente",
        queryset=Client.objects.none(),
        widget=forms.Select(attrs={"class": SELECT}),
    )
    notes = forms.CharField(
        label="Observações",
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "Opcional"}),
    )

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace:
            self.fields["client"].queryset = Client.objects.for_workspace(workspace).filter(
                active=True
            )


class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = [
            "client",
            "work_date",
            "clock_in",
            "lunch_out",
            "lunch_in",
            "clock_out",
            "notes",
        ]
        labels = {
            "client": "Cliente",
            "work_date": "Data",
            "clock_in": "Entrada",
            "lunch_out": "Saída almoço",
            "lunch_in": "Retorno almoço",
            "clock_out": "Saída",
            "notes": "Observações",
        }
        widgets = {
            "client": forms.Select(attrs={"class": SELECT}),
            "work_date": _date_input(),
            "clock_in": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"class": INPUT, "type": "datetime-local"},
            ),
            "lunch_out": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"class": INPUT, "type": "datetime-local"},
            ),
            "lunch_in": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"class": INPUT, "type": "datetime-local"},
            ),
            "clock_out": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"class": INPUT, "type": "datetime-local"},
            ),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        if workspace:
            self.fields["client"].queryset = Client.objects.for_workspace(workspace).filter(
                active=True
            )
        self.fields["work_date"].localize = False
        self.fields["work_date"].input_formats = DATE_INPUT_FORMATS
        dt_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
        for name in ("clock_in", "lunch_out", "lunch_in", "clock_out"):
            field = self.fields[name]
            field.required = False
            field.localize = False
            field.input_formats = dt_formats

    def clean(self):
        cleaned = super().clean()
        clock_in = cleaned.get("clock_in")
        lunch_out = cleaned.get("lunch_out")
        lunch_in = cleaned.get("lunch_in")
        clock_out = cleaned.get("clock_out")
        if lunch_out and clock_in and lunch_out < clock_in:
            self.add_error("lunch_out", "Deve ser após a entrada.")
        if lunch_in and lunch_out and lunch_in < lunch_out:
            self.add_error("lunch_in", "Deve ser após a saída para almoço.")
        if lunch_in and not lunch_out:
            self.add_error("lunch_out", "Informe a saída para almoço.")
        if clock_out and clock_in and clock_out < clock_in:
            self.add_error("clock_out", "Deve ser após a entrada.")
        if clock_out and lunch_out and not lunch_in:
            self.add_error("lunch_in", "Informe o retorno do almoço antes da saída.")
        return cleaned

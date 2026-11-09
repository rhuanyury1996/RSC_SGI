"""Seed editável por workspace — só roda se categorias/entidades estiverem vazias."""

from __future__ import annotations

from ledger.models import Account, Category, Client, Employee, Entity
from workspaces.models import Workspace

INITIAL_ENTITIES = [
    ("RSC", Entity.Kind.COMPANY),
    ("BlendDyn", Entity.Kind.COMPANY),
    ("RAVEN", Entity.Kind.COMPANY),
    ("Pessoal", Entity.Kind.PERSONAL),
]

INITIAL_CLIENTS = [
    "CRITEQ",
    "HIDRYCO",
    "DPR",
    "GEXCON",
    "Blusafe",
]

INITIAL_EMPLOYEES = [
    "Jordan M.",
    "Leonardo P.",
    "Denise T.",
    "Augusto K.",
    "Rhuan F.",
    "Eduard S.",
]

EXPENSE_TREE = [
    (
        "Operacional",
        [
            "Software e assinaturas",
            "Serviços terceirizados",
            "Taxas bancárias",
            "Marketing e anúncios",
            "Material de consumo",
        ],
    ),
    ("Pessoal/Folha", ["Pró-labore", "Salários", "Encargos", "Benefícios"]),
    ("Impostos", ["DAS/Simples", "ISS", "IRPJ", "INSS", "IRPF"]),
    (
        "Viagem",
        [
            "Passagem aérea",
            "Hospedagem",
            "Alimentação em viagem",
            "Transporte e locação",
            "Pedágio e combustível",
            "Diárias",
            "Bagagem e taxas",
        ],
    ),
    (
        "Equipamentos",
        [
            "Computadores",
            "Periféricos",
            "Áudio e vídeo",
            "Ferramentas",
            "Móveis",
            "Manutenção e reparos",
            "Licenças de hardware",
        ],
    ),
    (
        "Instalações",
        [
            "Aluguel",
            "Energia",
            "Água",
            "Internet e telefonia",
            "Condomínio",
            "Limpeza",
        ],
    ),
    (
        "Pessoais",
        [
            "Moradia",
            "Mercado",
            "Saúde",
            "Educação",
            "Lazer",
            "Vestuário",
            "Transporte pessoal",
            "Presentes",
            "Pets",
        ],
    ),
    ("Financeiras", ["Juros", "Multas", "Empréstimos", "IOF"]),
]

INCOME_CATEGORIES = [
    "Prestação de serviços",
    "Venda de produtos",
    "Recorrência de contratos",
    "Rendimentos financeiros",
    "Reembolsos recebidos",
    "Outras",
]


def seed_workspace(workspace: Workspace) -> dict[str, int]:
    created_entities = 0
    if not Entity.objects.for_workspace(workspace).exists():
        for name, kind in INITIAL_ENTITIES:
            tax_bps = 1700 if kind == Entity.Kind.COMPANY else 0
            entity = Entity.objects.create(
                workspace=workspace,
                name=name,
                kind=kind,
                active=True,
                effective_tax_rate_bps=tax_bps,
            )
            Account.objects.create(
                workspace=workspace,
                entity=entity,
                name=f"Conta principal — {name}",
                type=Account.Type.BANK,
                active=True,
            )
            created_entities += 1

    created_categories = 0
    if not Category.objects.for_workspace(workspace).exists():
        for order, (parent_name, children) in enumerate(EXPENSE_TREE):
            parent = Category.objects.create(
                workspace=workspace,
                name=parent_name,
                kind=Category.Kind.EXPENSE,
                sort_order=order,
            )
            created_categories += 1
            for child_order, child_name in enumerate(children):
                Category.objects.create(
                    workspace=workspace,
                    parent=parent,
                    name=child_name,
                    kind=Category.Kind.EXPENSE,
                    sort_order=child_order,
                )
                created_categories += 1

        income_root = Category.objects.create(
            workspace=workspace,
            name="Receitas",
            kind=Category.Kind.INCOME,
            sort_order=0,
        )
        created_categories += 1
        for order, name in enumerate(INCOME_CATEGORIES):
            Category.objects.create(
                workspace=workspace,
                parent=income_root,
                name=name,
                kind=Category.Kind.INCOME,
                sort_order=order,
            )
            created_categories += 1

    created_clients = seed_clients(workspace)
    created_employees = seed_employees(workspace)
    return {
        "entities": created_entities,
        "categories": created_categories,
        "clients": created_clients,
        "employees": created_employees,
    }


def seed_clients(workspace: Workspace) -> int:
    """Garante clientes iniciais (idempotente por nome)."""
    created = 0
    existing = set(
        Client.objects.for_workspace(workspace).values_list("name", flat=True)
    )
    for name in INITIAL_CLIENTS:
        if name in existing:
            continue
        Client.objects.create(workspace=workspace, name=name, active=True)
        created += 1
    return created


def seed_employees(workspace: Workspace) -> int:
    """Garante funcionários iniciais (idempotente por nome)."""
    created = 0
    existing = set(
        Employee.objects.for_workspace(workspace).values_list("name", flat=True)
    )
    for name in INITIAL_EMPLOYEES:
        if name in existing:
            continue
        Employee.objects.create(workspace=workspace, name=name, active=True)
        created += 1
    return created

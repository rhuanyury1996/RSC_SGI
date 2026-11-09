"""Estruturas de dados do módulo de orçamento."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum


class Escopo(str, Enum):
    """Escopo da proposta; o valor é o sufixo usado no nome do arquivo."""

    EFFECTS_RISKCURVES = "E&R"
    SO_EFFECTS = "E"


class TipoCliente(str, Enum):
    """Define qual reajuste da lista Gexcon se aplica."""

    NOVO = "novo"
    RENOVACAO = "renovacao"


PRODUTO_EFFECTS = "EFFECTS"
PRODUTO_ER = "EFFECTS + RISKCURVES"


@dataclass(frozen=True)
class Contato:
    """Pessoa de contato do cliente, vinda do cadastro do SGI."""

    id: str
    nome: str
    fone: str = ""
    email: str = ""
    principal: bool = False


class ContatoNaoEncontrado(LookupError):
    pass


@dataclass(frozen=True)
class Cliente:
    """Dados do cliente, vindos da base de dados do SGI."""

    id: str
    razao_social: str
    nome_curto: str  # usado no nome do arquivo/pasta (ex.: "RME")
    cnpj: str
    endereco_linhas: list[str]  # linhas do endereço, na ordem em que aparecem no docx
    contatos: list[Contato] = field(default_factory=list)

    def contato(self, contato_id: str | None = None) -> Contato:
        """Contato escolhido; sem escolha, o principal (ou o primeiro cadastrado)."""
        if not self.contatos:
            raise ContatoNaoEncontrado(f"Cliente {self.razao_social} sem contato cadastrado")
        if contato_id is not None:
            for c in self.contatos:
                if c.id == str(contato_id):
                    return c
            raise ContatoNaoEncontrado(f"Contato {contato_id} não pertence a {self.razao_social}")
        return next((c for c in self.contatos if c.principal), self.contatos[0])


@dataclass(frozen=True)
class PedidoTreinamento:
    produto: str  # PRODUTO_EFFECTS ou PRODUTO_ER
    tipo: str = "Online"
    alunos: int = 1


@dataclass
class PedidoOrcamento:
    cliente_id: str
    escopo: Escopo
    contato_id: str | None = None  # padrão: contato principal do cliente
    incluir_usuario_adicional: bool = True
    treinamentos: list[PedidoTreinamento] = field(default_factory=list)
    data: date | None = None  # padrão: hoje
    sequencial: int | None = None  # padrão: próximo livre do dia
    periodos_meses: list[int] | None = None  # ex.: [6]; padrão: todos dos parâmetros
    tipo_cliente: TipoCliente = TipoCliente.NOVO
    vencimento_licenca: date | None = None  # renovação: vencimento da licença atual
    categoria_licenca: str = "comercial"  # comercial / orgao_publico / academica
    unidades: int = 1  # licenças (usuários simultâneos) de cada módulo
    dongles: int = 0  # chaves físicas (item opcional do Price Builder)


@dataclass(frozen=True)
class LinhaSoftware:
    descricao: str  # linha do modelo docx usada como base
    precos_por_periodo: dict[int, Decimal]  # meses -> preço (total do período)
    rotulo: str = ""  # texto exibido; vazio = a própria descrição
    anual: dict[int, list[Decimal]] = field(default_factory=dict)  # multi-ano: preço de cada ano

    @property
    def texto(self) -> str:
        return self.rotulo or self.descricao


@dataclass(frozen=True)
class LinhaTreinamento:
    produto: str
    tipo: str
    horas: int
    alunos: int
    preco_unitario: Decimal

    @property
    def subtotal(self) -> Decimal:
        return self.preco_unitario * self.alunos


@dataclass(frozen=True)
class Orcamento:
    """Resultado completo; pode ser gravado no SGI além de gerar o docx."""

    numero: str
    data: date
    validade: date
    nome_arquivo: str
    cliente: Cliente
    contato: Contato
    escopo: Escopo
    periodos_meses: list[int]
    linhas_software: list[LinhaSoftware]
    linhas_treinamento: list[LinhaTreinamento]
    tipo_cliente: TipoCliente = TipoCliente.NOVO  # tipo efetivamente aplicado no preço
    avisos: tuple[str, ...] = ()
    categoria_licenca: str = "comercial"
    nome_categoria: str = "Comercial"
    desconto: Decimal = Decimal("0")
    unidades: int = 1

    @property
    def total_treinamentos(self) -> Decimal:
        return sum((l.subtotal for l in self.linhas_treinamento), Decimal("0"))

    @property
    def periodo_servicos(self) -> int:
        """Período usado na linha SERVIÇOS: 12 meses se apresentado, senão o maior apresentado."""
        return 12 if 12 in self.periodos_meses else max(self.periodos_meses)

    @property
    def valor_modulo(self) -> Decimal:
        """Preço do módulo da proposta (E+R no E&R; EFFECTS no só E) no período de SERVIÇOS."""
        produto = PRODUTO_ER if self.escopo is Escopo.EFFECTS_RISKCURVES else PRODUTO_EFFECTS
        linha = next(l for l in self.linhas_software if l.descricao == produto and not l.rotulo.startswith("Dongle"))
        return linha.precos_por_periodo[self.periodo_servicos]

    @property
    def total_servicos(self) -> Decimal:
        """Linha SERVIÇOS do quadro de totais: módulo + treinamentos."""
        return self.valor_modulo + self.total_treinamentos

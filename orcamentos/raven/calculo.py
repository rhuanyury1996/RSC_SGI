"""Cálculo da proposta RAVEN: licença, implantação, pacote de horas, desconto e total."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

INDUSTRIA = "industria"
CONSULTORIA = "consultoria"
TIPOS = (INDUSTRIA, CONSULTORIA)
TRIAL = "trial"
VISTA = "vista"
BOLETO = "10x"
CENTAVO = Decimal("0.01")


def dinheiro(valor) -> Decimal:
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def formatar_real(valor) -> str:
    """R$ 12.460,00"""
    texto = f"{dinheiro(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


@dataclass(frozen=True)
class Plano:
    chave: str
    nome: str
    usuarios: int
    vigencias: tuple[int, ...]
    precos: dict[int, Decimal]


@dataclass(frozen=True)
class FaixaHoras:
    ate: int | None
    valor_hora: Decimal


@dataclass(frozen=True)
class ParametrosRaven:
    versao_tabela: str
    validade_ate: date
    validade_dias_padrao: int
    desconto_avista: Decimal
    parcelas_boleto: int
    trial_dias: int
    prazo_login_horas: int
    horas_visita_padrao: int
    planos: dict[str, dict[str, Plano]]
    pacote_horas: tuple[FaixaHoras, ...]

    @classmethod
    def de_dict(cls, d: dict) -> "ParametrosRaven":
        planos: dict[str, dict[str, Plano]] = {}
        for tipo in TIPOS:
            planos[tipo] = {}
            for chave, p in d["planos"][tipo].items():
                if chave == TRIAL:
                    raise ValueError("'trial' é reservado; não cadastre como plano")
                planos[tipo][chave] = Plano(
                    chave=chave,
                    nome=str(p["nome"]),
                    usuarios=int(p["usuarios"]),
                    vigencias=tuple(int(v) for v in p["vigencias"]),
                    precos={int(m): Decimal(str(v)) for m, v in (p.get("precos") or {}).items()},
                )
            if not planos[tipo]:
                raise ValueError(f"Nenhum plano de {tipo}")
        faixas = tuple(
            FaixaHoras(ate=(int(f["ate"]) if f["ate"] is not None else None), valor_hora=Decimal(str(f["valor_hora"])))
            for f in d["pacote_horas"]
        )
        if not faixas or faixas[-1].ate is not None:
            raise ValueError("A última faixa de pacote_horas precisa ter 'ate': null")
        return cls(
            versao_tabela=str(d["versao_tabela"]),
            validade_ate=date.fromisoformat(d["validade_ate"]),
            validade_dias_padrao=int(d.get("validade_dias_padrao", 30)),
            desconto_avista=Decimal(str(d.get("desconto_avista", "0.08"))),
            parcelas_boleto=int(d.get("parcelas_boleto", 10)),
            trial_dias=int(d.get("trial_dias", 3)),
            prazo_login_horas=int(d.get("prazo_login_horas", 48)),
            horas_visita_padrao=int(d.get("horas_visita_padrao", 8)),
            planos=planos,
            pacote_horas=faixas,
        )

    def plano(self, tipo: str, chave: str) -> Plano:
        if chave == TRIAL:
            return Plano(TRIAL, "Trial", 0, (0,), {0: Decimal("0")})
        try:
            return self.planos[tipo][chave]
        except KeyError as exc:
            raise LookupError(f"Plano '{chave}' não existe para {tipo}") from exc

    def valor_hora(self, horas: int) -> Decimal:
        for faixa in self.pacote_horas:
            if faixa.ate is None or horas <= faixa.ate:
                return faixa.valor_hora
        return self.pacote_horas[-1].valor_hora


@dataclass
class PedidoRaven:
    tipo: str
    plano: str
    vigencia_meses: int
    data: date
    valor_licenca: Decimal | None = None  # vazio: usa a tabela
    implantacao: bool = False
    valor_implantacao: Decimal | None = None
    horas_visita: int | None = None
    cidade_visita: str = ""
    horas_pacote: int = 0
    pagamento: str = VISTA
    validade_dias: int | None = None


@dataclass
class Linha:
    descricao: str
    valor: Decimal | None
    tipo: str  # licenca | implantacao | pacote | desconto


@dataclass
class ResultadoRaven:
    tipo: str
    plano: Plano
    vigencia_meses: int
    trial: bool
    valor_licenca: Decimal | None
    valor_tabela: Decimal | None
    implantacao: bool
    valor_implantacao: Decimal | None
    horas_visita: int | None
    horas_pacote: int
    valor_hora: Decimal | None
    valor_pacote: Decimal
    pagamento: str
    desconto: Decimal
    total: Decimal
    parcela: Decimal | None
    validade: date
    validade_dias: int
    linhas: list[Linha] = field(default_factory=list)
    pendencias: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def calcular(pedido: PedidoRaven, params: ParametrosRaven) -> ResultadoRaven:
    if pedido.tipo not in TIPOS:
        raise ValueError("Tipo de cliente inválido")
    if pedido.data > params.validade_ate:
        raise ValueError(
            f"A tabela {params.versao_tabela} vale até {params.validade_ate:%d/%m/%Y}. Atualize os parâmetros."
        )
    trial = pedido.plano == TRIAL
    plano = params.plano(pedido.tipo, pedido.plano)
    pendencias: list[str] = []
    avisos: list[str] = []

    if trial:
        vig = 0
        valor_tabela = Decimal("0")
        licenca = Decimal("0")
    else:
        vig = int(pedido.vigencia_meses)
        if vig not in plano.vigencias:
            raise ValueError(f"O plano {plano.nome} não tem vigência de {vig} meses")
        valor_tabela = plano.precos.get(vig)
        licenca = dinheiro(pedido.valor_licenca) if pedido.valor_licenca not in (None, "") else valor_tabela
        if licenca is None:
            pendencias.append(f"Informe o valor da licença: o plano {plano.nome} não tem preço de tabela para {vig} meses.")
        elif valor_tabela is not None and licenca != valor_tabela:
            avisos.append(f"Valor negociado: tabela {formatar_real(valor_tabela)}, proposta {formatar_real(licenca)}.")

    implantacao = bool(pedido.implantacao) and pedido.tipo == INDUSTRIA and not trial
    if pedido.implantacao and not implantacao:
        avisos.append("Implantação em campo não se aplica a consultorias nem ao trial; item removido.")
    valor_impl = dinheiro(pedido.valor_implantacao) if implantacao and pedido.valor_implantacao not in (None, "") else None
    horas_visita = (pedido.horas_visita or params.horas_visita_padrao) if implantacao else None
    if implantacao and valor_impl is None:
        pendencias.append("Informe o valor da implantação.")

    horas = max(0, int(pedido.horas_pacote or 0))
    valor_hora = params.valor_hora(horas) if horas else None
    valor_pacote = dinheiro(valor_hora * horas) if horas else Decimal("0")

    pagamento = VISTA if trial else pedido.pagamento
    if pagamento not in (VISTA, BOLETO):
        raise ValueError("Condição de pagamento inválida")
    desconto = dinheiro(licenca * params.desconto_avista) if (not trial and pagamento == VISTA and licenca) else Decimal("0")

    linhas: list[Linha] = []
    if trial:
        linhas.append(Linha(f"Trial da plataforma RAVEN · {params.trial_dias} dias", Decimal("0"), "licenca"))
    else:
        linhas.append(Linha(f"Licenciamento: plano {plano.nome}, {vig} meses (até {plano.usuarios} usuários simultâneos)", licenca, "licenca"))
    if implantacao:
        linhas.append(Linha(f"Implantação (visita a campo de até {horas_visita} h e mapeamento da planta)", valor_impl, "implantacao"))
    if horas:
        linhas.append(Linha(f"Cadastro de estudos existentes: pacote de {horas} horas × {formatar_real(valor_hora)}", valor_pacote, "pacote"))
    if desconto:
        linhas.append(Linha(f"Desconto de {params.desconto_avista * 100:.0f}% no pagamento à vista da licença", -desconto, "desconto"))

    total = dinheiro(sum((l.valor for l in linhas if l.valor is not None), Decimal("0")))
    validade_dias = int(pedido.validade_dias or params.validade_dias_padrao)
    parcela = dinheiro(licenca / params.parcelas_boleto) if (not trial and pagamento == BOLETO and licenca) else None

    return ResultadoRaven(
        tipo=pedido.tipo, plano=plano, vigencia_meses=vig, trial=trial,
        valor_licenca=licenca, valor_tabela=valor_tabela,
        implantacao=implantacao, valor_implantacao=valor_impl, horas_visita=horas_visita,
        horas_pacote=horas, valor_hora=valor_hora, valor_pacote=valor_pacote,
        pagamento=pagamento, desconto=desconto, total=total, parcela=parcela,
        validade=pedido.data + timedelta(days=validade_dias), validade_dias=validade_dias,
        linhas=linhas, pendencias=pendencias, avisos=avisos,
    )


# ------------------------------------------------------------------ numeração

_INVALIDOS = re.compile(r'[<>:"/\\|?*]+')


def numero_proposta(dia: date, sequencial: int) -> str:
    """Mesmo padrão do GEXCON: AAMMDD-sequencial do dia."""
    if sequencial < 1:
        raise ValueError("Sequencial deve ser >= 1")
    return f"{dia:%y%m%d}-{sequencial}"


def nome_arquivo(numero: str, nome_empresa: str) -> str:
    nome = re.sub(r"\s+", " ", _INVALIDOS.sub("", nome_empresa)).strip()
    return f"Orc_{numero}_{nome}_RAVEN.html"

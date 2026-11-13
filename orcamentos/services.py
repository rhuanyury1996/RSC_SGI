"""Integração do orçamento GEXCON com o SGI (CRM, numeração e histórico)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from crm.models import Empresa

from .gexcon.modelos import (
    PRODUTO_EFFECTS,
    PRODUTO_ER,
    Cliente,
    Contato,
    Escopo,
    PedidoOrcamento,
    PedidoTreinamento,
    TipoCliente,
)
from .gexcon.precos import formatar_euro, rotulo_periodo
from .gexcon.servico import gerar_bytes, montar_orcamento
from .models import Orcamento, TabelaParametros


class OrcamentoErro(ValueError):
    """Erro de negócio com mensagem pronta para o usuário."""


# ------------------------------------------------------------------ CRM → proposta


def linhas_endereco(empresa: Empresa) -> list[str]:
    """Logradouro, complemento/bairro, "Cidade – UF CEP, País". Vazias são ignoradas."""
    cidade_uf = " – ".join(p for p in (empresa.cidade.strip(), empresa.estado.strip()) if p)
    terceira = " ".join(p for p in (cidade_uf, empresa.cep.strip()) if p)
    if empresa.pais.strip():
        terceira = f"{terceira}, {empresa.pais.strip()}" if terceira else empresa.pais.strip()
    return [l for l in (empresa.logradouro.strip(), empresa.complemento.strip(), terceira) if l]


def contatos_da_empresa(empresa: Empresa) -> list[Contato]:
    contatos = []
    for c in empresa.contatos.filter(ativo=True).order_by("-principal", "nome", "sobrenome"):
        contatos.append(
            Contato(
                id=str(c.pk),
                nome=c.nome_completo,
                fone=c.telefone_whatsapp or c.telefone_ramal,
                email=c.email,
                principal=c.principal,
            )
        )
    return contatos


def cliente_do_crm(empresa: Empresa) -> Cliente:
    contatos = contatos_da_empresa(empresa)
    if not contatos:
        raise OrcamentoErro(f"{empresa.nome} não tem contato ativo. Cadastre um contato antes de gerar a proposta.")
    return Cliente(
        id=str(empresa.pk),
        razao_social=(empresa.razao_social or empresa.nome).strip(),
        nome_curto=(empresa.nome_curto or empresa.nome).strip(),
        cnpj=empresa.cnpj,
        endereco_linhas=linhas_endereco(empresa),
        contatos=contatos,
    )


def pendencias_cadastro(empresa: Empresa) -> list[str]:
    faltando = []
    if not empresa.cnpj:
        faltando.append("CNPJ")
    if not empresa.logradouro:
        faltando.append("endereço")
    if not empresa.razao_social:
        faltando.append("razão social")
    if not empresa.nome_curto:
        faltando.append("nome curto")
    return faltando


# ------------------------------------------------------------------ parâmetros


def tabela_do_ano(ano: int) -> TabelaParametros:
    tabela = TabelaParametros.objects.filter(ano=ano).first()
    if tabela is None:
        raise OrcamentoErro(f"Não há tabela de parâmetros de {ano}. Cadastre-a em Orçamentos → Parâmetros.")
    return tabela


def proximo_sequencial(dia: date) -> int:
    """Maior N do dia no histórico do SGI (GEXCON e RAVEN) + 1."""
    from .models import OrcamentoRaven

    prefixo = f"{dia:%y%m%d}-"
    maior = 0
    for modelo in (Orcamento, OrcamentoRaven):
        for numero in modelo.objects.filter(numero__startswith=prefixo).values_list("numero", flat=True):
            try:
                maior = max(maior, int(numero.split("-", 1)[1]))
            except (IndexError, ValueError):
                continue
    return maior + 1


# ------------------------------------------------------------------ cálculo e emissão


def montar_pedido(dados: dict) -> PedidoOrcamento:
    treinamentos = [
        PedidoTreinamento(produto=t["produto"], tipo=t.get("tipo", "Online"), alunos=int(t["alunos"]))
        for t in dados.get("treinamentos", [])
    ]
    return PedidoOrcamento(
        cliente_id=str(dados["empresa"].pk),
        escopo=Escopo(dados["escopo"]),
        contato_id=str(dados["contato"].pk) if dados.get("contato") else None,
        incluir_usuario_adicional=bool(dados.get("incluir_adicional")),
        treinamentos=treinamentos,
        data=dados.get("data") or timezone.localdate(),
        sequencial=dados.get("sequencial") or None,
        periodos_meses=[int(m) for m in dados["periodos"]],
        tipo_cliente=TipoCliente(dados.get("tipo_cliente") or "novo"),
        vencimento_licenca=dados.get("vencimento_licenca"),
        categoria_licenca=dados.get("categoria_licenca") or "comercial",
        unidades=int(dados.get("unidades") or 1),
        dongles=int(dados.get("dongles") or 0),
    )


def calcular(dados: dict):
    """(orcamento, parametros, tabela). Lança OrcamentoErro com mensagem amigável."""
    pedido = montar_pedido(dados)
    tabela = tabela_do_ano(pedido.data.year)
    params = tabela.parametros()
    for t in pedido.treinamentos:
        cfg = params.treinamentos.get(t.produto) or {}
        if t.tipo not in cfg.get("precos_lista", {}):
            raise OrcamentoErro(f"Treinamento {t.tipo.lower()} de {t.produto} ainda não tem preço cadastrado.")
    cliente = cliente_do_crm(dados["empresa"])
    try:
        orc = montar_orcamento(pedido, params, cliente, proximo_sequencial)
    except (ValueError, LookupError) as exc:
        raise OrcamentoErro(str(exc).strip("'\"")) from exc
    from .models import OrcamentoRaven

    if pedido.sequencial and (
        Orcamento.objects.filter(numero=orc.numero).exists()
        or OrcamentoRaven.objects.filter(numero=orc.numero).exists()
    ):
        raise OrcamentoErro(f"Já existe a proposta {orc.numero}. Escolha outro sequencial.")
    return orc, params, tabela


def resumo_valores(orc) -> dict:
    """Valores formatados para a pré-visualização."""
    return {
        "numero": orc.numero,
        "arquivo": orc.nome_arquivo,
        "periodos": orc.periodos_meses,
        "rotulos_periodos": [rotulo_periodo(m) for m in orc.periodos_meses],
        "linhas": [
            {
                "descricao": l.texto,
                "precos": [formatar_euro(l.precos_por_periodo[m]) for m in orc.periodos_meses],
                "anual": [
                    {
                        "periodo": rotulo_periodo(m),
                        "anos": [formatar_euro(v) for v in l.anual[m]],
                    }
                    for m in orc.periodos_meses
                    if m in l.anual
                ],
            }
            for l in orc.linhas_software
        ],
        "categoria": orc.nome_categoria,
        "desconto": f"{(orc.desconto * 100):.0f}%",
        "unidades": orc.unidades,
        "treinamentos": [
            {
                "produto": l.produto,
                "tipo": l.tipo,
                "horas": l.horas,
                "alunos": l.alunos,
                "unitario": formatar_euro(l.preco_unitario),
                "subtotal": formatar_euro(l.subtotal),
            }
            for l in orc.linhas_treinamento
        ],
        "total_treinamentos": formatar_euro(orc.total_treinamentos),
        "total_servicos": formatar_euro(orc.total_servicos),
        "periodo_servicos": orc.periodo_servicos,
        "tipo_efetivo": orc.tipo_cliente.value,
        "avisos": list(orc.avisos),
        "contato": orc.contato.nome,
        "validade": orc.validade.strftime("%d/%m/%Y"),
    }


def emitir(dados: dict, autor) -> Orcamento:
    """Calcula, gera o docx e grava no histórico (snapshot dos valores)."""
    for tentativa in range(5):
        orc, params, tabela = calcular(dados)
        conteudo = gerar_bytes(orc, params)
        contato_crm = dados.get("contato") or dados["empresa"].contatos.filter(pk=orc.contato.id).first()
        agora = timezone.now()
        try:
            with transaction.atomic():
                return Orcamento.objects.create(
                    numero=orc.numero,
                    data=orc.data,
                    sequencial=int(orc.numero.split("-")[1]),
                    validade=orc.validade,
                    empresa=dados["empresa"],
                    contato=contato_crm,
                    cliente={
                        "razao_social": orc.cliente.razao_social,
                        "nome_curto": orc.cliente.nome_curto,
                        "cnpj": orc.cliente.cnpj,
                        "endereco_linhas": orc.cliente.endereco_linhas,
                    },
                    contato_dados={
                        "nome": orc.contato.nome,
                        "fone": orc.contato.fone,
                        "email": orc.contato.email,
                    },
                    escopo=orc.escopo.value,
                    periodos=orc.periodos_meses,
                    incluir_adicional=bool(dados.get("incluir_adicional")),
                    tipo_cliente_solicitado=dados.get("tipo_cliente") or "novo",
                    tipo_cliente_efetivo=orc.tipo_cliente.value,
                    vencimento_licenca=dados.get("vencimento_licenca"),
                    categoria_licenca=orc.categoria_licenca,
                    desconto=orc.desconto,
                    unidades=orc.unidades,
                    dongles=int(dados.get("dongles") or 0),
                    linhas_software=[
                        {
                            "descricao": l.texto,
                            "precos": {str(m): str(v) for m, v in l.precos_por_periodo.items()},
                            "anual": {str(m): [str(v) for v in vs] for m, vs in l.anual.items()},
                        }
                        for l in orc.linhas_software
                    ],
                    treinamentos=[
                        {
                            "produto": l.produto,
                            "tipo": l.tipo,
                            "horas": l.horas,
                            "alunos": l.alunos,
                            "preco_unitario": str(l.preco_unitario),
                        }
                        for l in orc.linhas_treinamento
                    ],
                    total_treinamentos=orc.total_treinamentos,
                    total_servicos=orc.total_servicos,
                    avisos=list(orc.avisos),
                    tabela=tabela,
                    versao_tabela=params.versao_tabela,
                    nome_arquivo=orc.nome_arquivo,
                    arquivo=conteudo,
                    emitido_por=autor,
                    historico_status=[
                        {"status": "emitida", "em": agora.isoformat(), "por": getattr(autor, "nome_completo", "")}
                    ],
                )
        except IntegrityError:
            # Outra proposta pegou o mesmo número ao mesmo tempo: recalcula o sequencial.
            if dados.get("sequencial"):
                raise OrcamentoErro("Esse número de proposta acabou de ser usado. Tente outro sequencial.")
            continue
    raise OrcamentoErro("Não foi possível reservar um número para a proposta. Tente de novo.")


def mudar_status(orc: Orcamento, status: str, autor) -> None:
    orc.status = status
    orc.historico_status = list(orc.historico_status or []) + [
        {"status": status, "em": timezone.now().isoformat(), "por": getattr(autor, "nome_completo", "")}
    ]
    orc.save(update_fields=["status", "historico_status"])


TREINAMENTO_PRODUTOS = ((PRODUTO_EFFECTS, "EFFECTS (12 h)"), (PRODUTO_ER, "EFFECTS + RISKCURVES (18 h)"))
ZERO = Decimal("0")

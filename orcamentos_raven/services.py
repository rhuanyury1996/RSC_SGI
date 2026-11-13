"""Integração do orçamento RAVEN com o SGI (CRM, numeração, histórico e aceite)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from crm.models import Empresa

from orcamentos.models import Orcamento  # numeração AAMMDD-N compartilhada com o GEXCON
from orcamentos.services import linhas_endereco, pendencias_cadastro  # noqa: F401  (mesmas regras do GEXCON)

from .models import OrcamentoRaven, StatusOrcamento, TabelaRaven
from .raven.calculo import (
    PedidoRaven,
    ResultadoRaven,
    calcular as calcular_raven,
    formatar_real,
    nome_arquivo,
    numero_proposta,
)
from .raven.documento import gerar_html, preset


class OrcamentoErro(ValueError):
    """Erro de negócio com mensagem pronta para o usuário."""


def tabela_do_ano(ano: int) -> TabelaRaven:
    tabela = TabelaRaven.objects.filter(ano=ano).first()
    if tabela is None:
        raise OrcamentoErro(f"Não há tabela RAVEN de {ano}. Cadastre-a em Orçamentos RAVEN → Parâmetros.")
    return tabela


def proximo_sequencial(dia: date) -> int:
    """Maior N do dia somando GEXCON e RAVEN + 1 (a numeração AAMMDD-N é única na RSC)."""
    prefixo = f"{dia:%y%m%d}-"
    maior = 0
    for modelo in (Orcamento, OrcamentoRaven):
        for numero in modelo.objects.filter(numero__startswith=prefixo).values_list("numero", flat=True):
            try:
                maior = max(maior, int(numero.split("-", 1)[1]))
            except (IndexError, ValueError):
                continue
    return maior + 1


def numero_em_uso(numero: str) -> bool:
    return Orcamento.objects.filter(numero=numero).exists() or OrcamentoRaven.objects.filter(numero=numero).exists()


def contato_escolhido(dados: dict):
    empresa: Empresa = dados["empresa"]
    contato = dados.get("contato")
    if contato:
        return contato
    contato = empresa.contatos.filter(ativo=True).order_by("-principal", "nome", "sobrenome").first()
    if contato is None:
        raise OrcamentoErro(f"{empresa.nome} não tem contato ativo. Cadastre um contato antes de gerar a proposta.")
    return contato


def montar_pedido(dados: dict) -> PedidoRaven:
    return PedidoRaven(
        tipo=dados["tipo_cliente"],
        plano=dados["plano"],
        vigencia_meses=int(dados.get("vigencia") or 0),
        data=dados.get("data") or timezone.localdate(),
        valor_licenca=dados.get("valor_licenca"),
        implantacao=bool(dados.get("implantacao")),
        valor_implantacao=dados.get("valor_implantacao"),
        horas_visita=dados.get("horas_visita"),
        cidade_visita=dados.get("cidade_visita") or "",
        horas_pacote=int(dados.get("horas_pacote") or 0),
        pagamento=dados.get("pagamento") or "vista",
        validade_dias=dados.get("validade_dias"),
    )


def calcular(dados: dict) -> tuple[ResultadoRaven, TabelaRaven]:
    pedido = montar_pedido(dados)
    tabela = tabela_do_ano(pedido.data.year)
    try:
        res = calcular_raven(pedido, tabela.parametros())
    except (ValueError, LookupError, KeyError) as exc:
        raise OrcamentoErro(str(exc).strip("'\"")) from exc
    return res, tabela


def cidade_padrao(empresa: Empresa) -> str:
    return "/".join(p for p in (empresa.cidade.strip(), empresa.estado.strip()) if p)


def resumo_valores(res: ResultadoRaven) -> dict:
    return {
        "linhas": [
            {
                "descricao": l.descricao,
                "valor": "a definir" if l.valor is None else ("− " + formatar_real(-l.valor) if l.valor < 0 else formatar_real(l.valor)),
                "desconto": l.tipo == "desconto",
            }
            for l in res.linhas
        ],
        "total": formatar_real(res.total),
        "pendencias": res.pendencias,
        "avisos": res.avisos,
        "pagamento": (
            "Trial sem custo"
            if res.trial
            else ("À vista, com desconto aplicado na licença" if res.pagamento == "vista" else f"Licença em 10× de {formatar_real(res.parcela)} no boleto")
        ),
        "validade": res.validade.strftime("%d/%m/%Y"),
        "plano": res.plano.nome,
        "usuarios": res.plano.usuarios,
    }


def emitir(dados: dict, autor) -> OrcamentoRaven:
    """Calcula, gera o HTML da proposta e grava no histórico."""
    empresa: Empresa = dados["empresa"]
    contato = contato_escolhido(dados)
    sequencial_fixo = dados.get("sequencial")
    for _tentativa in range(5):
        res, tabela = calcular(dados)
        if res.pendencias:
            raise OrcamentoErro(" ".join(res.pendencias))
        dia = res.validade - timedelta(days=res.validade_dias)
        seq = sequencial_fixo or proximo_sequencial(dia)
        numero = numero_proposta(dia, seq)
        if sequencial_fixo and numero_em_uso(numero):
            raise OrcamentoErro(f"Já existe a proposta {numero}. Escolha outro sequencial.")
        nome_curto = (empresa.nome_curto or empresa.nome).strip()
        cidade = (dados.get("cidade_visita") or cidade_padrao(empresa)).strip()
        html = gerar_html(
            numero,
            preset(res, cliente=nome_curto, contato=contato.nome_completo, cidade=cidade, data=dia),
        )
        agora = timezone.now()
        try:
            with transaction.atomic():
                return OrcamentoRaven.objects.create(
                    numero=numero,
                    data=dia,
                    sequencial=seq,
                    validade=res.validade,
                    validade_dias=res.validade_dias,
                    empresa=empresa,
                    contato=contato,
                    cliente={
                        "razao_social": (empresa.razao_social or empresa.nome).strip(),
                        "nome_curto": nome_curto,
                        "cnpj": empresa.cnpj,
                        "endereco_linhas": linhas_endereco(empresa),
                    },
                    contato_dados={
                        "nome": contato.nome_completo,
                        "fone": contato.telefone_whatsapp or contato.telefone_ramal,
                        "email": contato.email,
                    },
                    tipo_cliente=res.tipo,
                    plano=res.plano.chave,
                    plano_nome=res.plano.nome,
                    usuarios=res.plano.usuarios,
                    vigencia_meses=res.vigencia_meses,
                    trial=res.trial,
                    valor_licenca=res.valor_licenca or Decimal("0"),
                    valor_tabela=res.valor_tabela,
                    implantacao=res.implantacao,
                    valor_implantacao=res.valor_implantacao,
                    horas_visita=res.horas_visita,
                    cidade_visita=cidade if res.implantacao else "",
                    horas_pacote=res.horas_pacote,
                    valor_hora=res.valor_hora,
                    valor_pacote=res.valor_pacote,
                    pagamento=res.pagamento,
                    desconto=res.desconto,
                    total=res.total,
                    linhas=[{"descricao": l.descricao, "valor": None if l.valor is None else str(l.valor), "tipo": l.tipo} for l in res.linhas],
                    avisos=list(res.avisos),
                    tabela=tabela,
                    versao_tabela=tabela.dados.get("versao_tabela", ""),
                    nome_arquivo=nome_arquivo(numero, nome_curto),
                    arquivo=html,
                    emitido_por=autor,
                    historico_status=[
                        {"status": "emitida", "em": agora.isoformat(), "por": getattr(autor, "nome_completo", "")}
                    ],
                )
        except IntegrityError:
            if sequencial_fixo:
                raise OrcamentoErro("Esse número de proposta acabou de ser usado. Tente outro sequencial.")
            continue
    raise OrcamentoErro("Não foi possível reservar um número para a proposta. Tente de novo.")


def mudar_status(orc: OrcamentoRaven, status: str, autor) -> None:
    agora = timezone.now()
    orc.status = status
    if status == StatusOrcamento.ACEITA and orc.aceite_em is None:
        orc.aceite_em = agora
    orc.historico_status = list(orc.historico_status or []) + [
        {"status": status, "em": agora.isoformat(), "por": getattr(autor, "nome_completo", "")}
    ]
    orc.save(update_fields=["status", "aceite_em", "historico_status", "atualizado_em"])


def liberar_login(orc: OrcamentoRaven, autor) -> None:
    """Registra que o login foi enviado ao cliente (prazo: 48 h após o aceite)."""
    if orc.status != StatusOrcamento.ACEITA:
        raise OrcamentoErro("Só propostas aceitas têm login a liberar.")
    agora = timezone.now()
    orc.login_liberado_em = agora
    orc.login_liberado_por = autor
    orc.historico_status = list(orc.historico_status or []) + [
        {"status": "login_liberado", "em": agora.isoformat(), "por": getattr(autor, "nome_completo", "")}
    ]
    orc.save(update_fields=["login_liberado_em", "login_liberado_por", "historico_status", "atualizado_em"])

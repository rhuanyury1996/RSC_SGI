import hmac
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from funcionarios.models import Funcionario
from funcionarios.utils import obter_funcionario

from .forms import (
    CardPreVendasForm,
    ContatoForm,
    EmpresaForm,
    EtapaFunilForm,
    ItemListaForm,
    OportunidadeForm,
)
from .cnpj import CnpjErro, consultar_cnpj
from .gmail_oauth import (
    build_gmail_flow,
    fetch_google_email,
    gmail_oauth_configurado,
    save_gmail_credentials,
)
from .importacao import ImportacaoErro, importar_empresas_contatos
from .models import (
    Contato,
    Empresa,
    EtapaFunil,
    FatorComissionamento,
    FormaContato,
    Funil,
    GmailVinculo,
    ItemLista,
    MotivoFaltaRetorno,
    Oportunidade,
    TipoHistoricoOpp,
    TipoLista,
    TipoSubfunil,
)
from .services import (
    DESCRICOES_ETAPAS_NEGOCIACOES,
    DESCRICOES_ETAPAS_POS_VENDAS,
    DESCRICOES_ETAPAS_PRE_VENDAS,
    ETAPAS_POR_TIPO,
    criar_card_pos_vendas,
    criar_prospeccao_from_email,
    css_coluna_negociacoes,
    css_coluna_pos_vendas,
    css_coluna_pre_vendas,
    fase_campos_pos_vendas,
    funis_agrupados_por_cliente,
    funis_com_contagens,
    garantir_etapas_padrao,
    garantir_funis_para_cliente,
    metricas_comerciais,
    mover_oportunidade,
    registrar_historico,
    soma_pipeline_qs,
    tempo_na_etapa,
)


def _token_webhook_gmail_ok(request) -> bool:
    esperado = (getattr(settings, "CRM_GMAIL_WEBHOOK_TOKEN", "") or "").strip()
    if not esperado:
        return False
    recebido = (
        request.headers.get("X-SGI-Token")
        or request.META.get("HTTP_X_SGI_TOKEN")
        or request.GET.get("token")
        or ""
    ).strip()
    if not recebido and request.body:
        try:
            data = json.loads(request.body.decode("utf-8"))
            recebido = str(data.get("token") or "").strip()
        except (json.JSONDecodeError, UnicodeDecodeError):
            recebido = ""
    return hmac.compare_digest(recebido, esperado)


@csrf_exempt
@require_POST
def webhook_prospeccao_gmail(request):
    """
    Recebe e-mails enviados no Workspace (Apps Script) e cria card
    em RSC · Pré-vendas quando o assunto = gatilho configurado.
    """
    if not (getattr(settings, "CRM_GMAIL_WEBHOOK_TOKEN", "") or "").strip():
        return JsonResponse(
            {"ok": False, "mensagem": "Webhook desabilitado (token não configurado)."},
            status=503,
        )
    if not _token_webhook_gmail_ok(request):
        return JsonResponse({"ok": False, "mensagem": "Não autorizado."}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "mensagem": "JSON inválido."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "mensagem": "Payload inválido."}, status=400)

    resultado = criar_prospeccao_from_email(payload)
    status = 200 if resultado.get("ok") else (422 if resultado.get("skipped") else 400)
    if resultado.get("created"):
        status = 201
    return JsonResponse(resultado, status=status)


@csrf_exempt
@require_POST
def webhook_sincronizar_gmail_oauth(request):
    """Cron/Render: sincroniza Gmail de todos os funcionários já vinculados via OAuth."""
    if not (getattr(settings, "CRM_GMAIL_WEBHOOK_TOKEN", "") or "").strip():
        return JsonResponse(
            {"ok": False, "mensagem": "Webhook desabilitado (token não configurado)."},
            status=503,
        )
    if not _token_webhook_gmail_ok(request):
        return JsonResponse({"ok": False, "mensagem": "Não autorizado."}, status=401)

    from .gmail_sync import sincronizar_todas_contas

    resultado = sincronizar_todas_contas()
    return JsonResponse({"ok": True, **resultado})


def _safe_next_path(request, default_name: str = "home") -> str:
    nxt = (request.GET.get("next") or request.POST.get("next") or "").strip()
    if nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return reverse(default_name)


@login_required
def gmail_conectar(request):
    if not gmail_oauth_configurado():
        messages.error(
            request,
            "Gmail não configurado. Defina GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET.",
        )
        return redirect(_safe_next_path(request))

    flow = build_gmail_flow(request)
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session["gmail_oauth_state"] = state
    request.session["gmail_oauth_next"] = _safe_next_path(request)
    return redirect(auth_url)


@login_required
def gmail_callback(request):
    destino = request.session.pop("gmail_oauth_next", None) or reverse("home")
    if not gmail_oauth_configurado():
        messages.error(request, "Gmail não configurado.")
        return redirect(destino)

    state = request.session.get("gmail_oauth_state")
    if not state or state != request.GET.get("state"):
        messages.error(request, "Falha na autenticação Gmail (state inválido).")
        return redirect(destino)

    if request.GET.get("error"):
        messages.error(request, "Autorização Gmail cancelada.")
        return redirect(destino)

    try:
        flow = build_gmail_flow(request, state=state)
        flow.fetch_token(authorization_response=request.build_absolute_uri())
        credentials = flow.credentials
        email = fetch_google_email(credentials)
        save_gmail_credentials(request.user, credentials, email=email)
        request.session["gmail_popup_dismissed"] = True
        messages.success(
            request,
            f"Gmail conectado{f' ({email})' if email else ''}. "
            "E-mails de prospecção serão sincronizados com o SGI.",
        )
        # Sincroniza na hora
        from .gmail_sync import sincronizar_usuario

        sync = sincronizar_usuario(request.user)
        if sync.get("criados"):
            messages.info(
                request,
                f"{sync['criados']} card(s) de prospecção criado(s) agora.",
            )
    except Exception:
        messages.error(request, "Não foi possível concluir a conexão do Gmail.")
    return redirect(destino)


@login_required
@require_POST
def gmail_adiar_popup(request):
    request.session["gmail_popup_dismissed"] = True
    return redirect(_safe_next_path(request))


@login_required
def gmail_desconectar(request):
    GmailVinculo.objects.filter(usuario=request.user).delete()
    request.session.pop("gmail_popup_dismissed", None)
    messages.info(request, "Gmail desconectado deste usuário.")
    return redirect(_safe_next_path(request))


@login_required
def hub(request):
    metricas = metricas_comerciais()
    return render(
        request,
        "crm/hub.html",
        {
            "total_empresas": Empresa.objects.filter(ativa=True).count(),
            "total_contatos": Contato.objects.filter(ativo=True).count(),
            "total_funis": Funil.objects.filter(ativo=True).count(),
            "total_oportunidades": metricas["total_oportunidades"],
            "pipeline_valor": metricas["pipeline_valor"],
            "recentes": metricas["recentes"],
            "grupos_funis": funis_agrupados_por_cliente()[:6],
        },
    )


@login_required
def empresas(request):
    if request.method == "POST":
        form = EmpresaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Empresa cadastrada.")
            return redirect("crm_empresas")
    else:
        form = EmpresaForm()

    itens = (
        Empresa.objects.filter(ativa=True)
        .select_related("nicho")
        .prefetch_related("clientes_rsc")
        .annotate(
            total_contatos=Count("contatos", distinct=True),
            total_ops=Count("oportunidades", distinct=True),
        )
    )
    return render(request, "crm/empresas.html", {"itens": itens, "form": form})


@login_required
@require_http_methods(["GET"])
def consultar_cnpj_view(request):
    """Proxy JSON para BrasilAPI — preenche formulário de empresa."""
    cnpj = (request.GET.get("cnpj") or "").strip()
    try:
        dados = consultar_cnpj(cnpj)
    except CnpjErro as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=400)
    except Exception:
        return JsonResponse(
            {"ok": False, "erro": "Falha inesperada ao consultar o CNPJ."},
            status=502,
        )
    return JsonResponse({"ok": True, "dados": dados})


@login_required
@require_http_methods(["GET", "POST"])
def importar_base(request):
    """Upload de Excel de empresas + contatos (mesmo formato das bases Bitrix)."""
    next_url = request.POST.get("next") or request.GET.get("next") or reverse(
        "crm_empresas"
    )
    if request.method == "GET":
        return redirect(next_url)

    arq_emp = request.FILES.get("arquivo_empresas")
    arq_con = request.FILES.get("arquivo_contatos")
    if not arq_emp or not arq_con:
        messages.error(
            request,
            "Envie as duas planilhas: Base de empresas e Base de contatos (.xlsx).",
        )
        return redirect(next_url)

    for arq, rotulo in (
        (arq_emp, "empresas"),
        (arq_con, "contatos"),
    ):
        nome = (arq.name or "").lower()
        if not nome.endswith((".xlsx", ".xlsm")):
            messages.error(
                request,
                f"Arquivo de {rotulo} inválido. Use Excel .xlsx.",
            )
            return redirect(next_url)

    try:
        resultado = importar_empresas_contatos(arq_emp, arq_con)
    except ImportacaoErro as exc:
        messages.error(request, str(exc))
        return redirect(next_url)
    except Exception:
        messages.error(
            request,
            "Não foi possível ler as planilhas. Verifique se são arquivos .xlsx válidos.",
        )
        return redirect(next_url)

    messages.success(request, resultado.mensagem())
    for aviso in resultado.avisos[:8]:
        messages.warning(request, aviso)
    if len(resultado.avisos) > 8:
        messages.warning(
            request,
            f"… e mais {len(resultado.avisos) - 8} contato(s) sem empresa.",
        )
    return redirect(next_url)


@login_required
def listas(request):
    tipo = request.GET.get("tipo", TipoLista.NICHO_MERCADOLOGICO).strip()
    if tipo not in TipoLista.values:
        tipo = TipoLista.NICHO_MERCADOLOGICO

    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao == "toggle":
            item = get_object_or_404(ItemLista, pk=request.POST.get("item_id"))
            item.ativo = not item.ativo
            item.save(update_fields=["ativo"])
            if item.tipo == TipoLista.CLIENTES_RSC:
                garantir_funis_para_cliente(item)
            messages.success(
                request,
                f"“{item.nome}” {'ativado' if item.ativo else 'desativado'}.",
            )
            return redirect(f"{request.path}?tipo={item.tipo}")

        form = ItemListaForm(request.POST)
        if form.is_valid():
            item = form.save()
            if item.tipo == TipoLista.CLIENTES_RSC:
                funis = garantir_funis_para_cliente(item)
                messages.success(
                    request,
                    f"Cliente “{item.nome}” cadastrado. Subfunis pré-vendas, negociações e pós-vendas criados.",
                )
                if funis:
                    return redirect("crm_funil_detalhe", pk=funis[0].pk)
            else:
                messages.success(request, "Item adicionado à lista.")
            return redirect(f"{request.path}?tipo={item.tipo}")
    else:
        form = ItemListaForm(initial={"tipo": tipo, "ativo": True})

    itens = (
        ItemLista.objects.filter(tipo=tipo)
        .prefetch_related("funis")
        .order_by("ordem", "nome")
    )
    return render(
        request,
        "crm/listas.html",
        {
            "form": form,
            "itens": itens,
            "tipo_atual": tipo,
            "tipos": TipoLista,
            "eh_clientes_rsc": tipo == TipoLista.CLIENTES_RSC,
        },
    )


@login_required
def contatos(request):
    empresa_form = EmpresaForm()
    funcionario = obter_funcionario(request)

    abrir_popup = False
    form = None

    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao == "criar_empresa":
            empresa_form = EmpresaForm(request.POST)
            if empresa_form.is_valid():
                empresa = empresa_form.save()
                messages.success(
                    request,
                    f"Empresa “{empresa.nome}” cadastrada. Agora vincule ao contato.",
                )
                return redirect(f"{request.path}?empresa={empresa.pk}")
            messages.error(request, "Revise os dados da empresa no popup.")
            abrir_popup = True
        else:
            form = ContatoForm(request.POST)
            if form.is_valid():
                contato = form.save(commit=False)
                if not contato.responsavel_id and funcionario:
                    contato.responsavel = funcionario
                contato.save()
                form.save_m2m()
                messages.success(request, "Contato cadastrado.")
                return redirect("crm_contatos")

    if form is None:
        initial = {}
        empresa_id = request.GET.get("empresa")
        if empresa_id and Empresa.objects.filter(pk=empresa_id, ativa=True).exists():
            initial["empresa"] = empresa_id
        if funcionario:
            initial.setdefault("responsavel", funcionario.pk)
        form = ContatoForm(initial=initial)

    return render(
        request,
        "crm/contatos.html",
        {
            "itens": Contato.objects.filter(ativo=True)
            .select_related("empresa", "responsavel")
            .prefetch_related("clientes_rsc"),
            "form": form,
            "empresa_form": empresa_form,
            "abrir_popup_empresa": abrir_popup,
        },
    )


@login_required
def empresa_editar(request, pk: int):
    empresa = get_object_or_404(Empresa, pk=pk, ativa=True)

    if request.method == "POST":
        form = EmpresaForm(request.POST, instance=empresa)
        if form.is_valid():
            form.save()
            messages.success(request, "Empresa atualizada.")
            return redirect("crm_empresas")
    else:
        form = EmpresaForm(instance=empresa)

    return render(
        request,
        "crm/empresa_editar.html",
        {"form": form, "empresa": empresa},
    )


@login_required
def contato_editar(request, pk: int):
    contato = get_object_or_404(
        Contato.objects.select_related("empresa", "responsavel"),
        pk=pk,
        ativo=True,
    )

    if request.method == "POST":
        form = ContatoForm(request.POST, instance=contato)
        if form.is_valid():
            form.save()
            messages.success(request, "Contato atualizado.")
            return redirect("crm_contatos")
    else:
        form = ContatoForm(instance=contato)

    return render(
        request,
        "crm/contato_editar.html",
        {"form": form, "contato": contato},
    )


@login_required
def funis(request):
    return render(
        request,
        "crm/funis.html",
        {"grupos": funis_agrupados_por_cliente()},
    )


def _subfunis_irmaos(funil: Funil) -> list[Funil]:
    if not funil.cliente_rsc_id:
        return []
    return list(
        Funil.objects.filter(cliente_rsc=funil.cliente_rsc, ativo=True).order_by("ordem")
    )


def _etapas_com_ops(funil: Funil) -> list[EtapaFunil]:
    return list(
        funil.etapas.annotate(valor_total=Sum("oportunidades__valor"))
        .prefetch_related(
            Prefetch(
                "oportunidades",
                queryset=Oportunidade.objects.filter(funil=funil)
                .select_related(
                    "empresa",
                    "responsavel",
                    "contato",
                    "funil_venda",
                    "funil_venda__cliente_rsc",
                    "oportunidade_pai",
                    "oportunidade_pai__empresa",
                    "oportunidade_pai__etapa",
                )
                .order_by("-atualizado_em", "-criado_em"),
            )
        )
        .order_by("ordem", "pk")
    )


def _metricas_coluna(etapa: EtapaFunil, *, com_valor: bool = False) -> None:
    """Contador de cards (e valor acumulado do negócio, se pedido) por coluna."""
    ops = list(etapa.oportunidades.all())
    etapa.cards_count = len(ops)
    if com_valor:
        total = Decimal("0")
        for opp in ops:
            valor = opp.valor_negocio
            if valor is not None:
                total += valor
        etapa.valor_acumulado = total
    else:
        etapa.valor_acumulado = None


@login_required
def funil_detalhe(request, pk: int):
    funil = get_object_or_404(
        Funil.objects.select_related("cliente_rsc"),
        pk=pk,
        ativo=True,
    )
    garantir_etapas_padrao(funil)
    if funil.tipo == TipoSubfunil.PRE_VENDAS:
        return _funil_pre_vendas(request, funil)
    if funil.tipo == TipoSubfunil.NEGOCIACOES:
        return _funil_negociacoes(request, funil)
    if funil.tipo == TipoSubfunil.POS_VENDAS:
        return _funil_pos_vendas(request, funil)
    return _funil_generico(request, funil)


def _funil_pos_vendas(request, funil: Funil):
    return _funil_generico(request, funil, pos_vendas=True)


def _funil_generico(request, funil: Funil, *, pos_vendas: bool = False):
    """Kanban + drawer lateral (Pós-vendas e funis genéricos)."""
    subfunis_irmaos = _subfunis_irmaos(funil)
    funcionario = obter_funcionario(request)
    empresa_form = EmpresaForm()
    abrir_popup_empresa = False
    abrir_nova_opp = False
    form = None
    card_id = request.POST.get("card_id") or request.GET.get("card")
    card_ativo = None
    if card_id:
        card_ativo = (
            Oportunidade.objects.filter(pk=card_id, funil=funil)
            .select_related(
                "empresa",
                "responsavel",
                "contato",
                "etapa",
                "oportunidade_pai",
                "oportunidade_pai__empresa",
                "oportunidade_pai__funil",
                "oportunidade_pai__etapa",
            )
            .first()
        )

    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao == "criar_empresa":
            empresa_form = EmpresaForm(request.POST)
            if empresa_form.is_valid():
                empresa = empresa_form.save()
                messages.success(
                    request,
                    f"Empresa “{empresa.nome}” cadastrada. Vincule na oportunidade.",
                )
                return redirect(f"{request.path}?empresa={empresa.pk}#nova-oportunidade")
            messages.error(request, "Revise os dados da empresa no popup.")
            abrir_popup_empresa = True
            abrir_nova_opp = True
        elif acao == "voltar_etapa" and card_ativo:
            etapa = get_object_or_404(
                EtapaFunil, pk=request.POST.get("etapa_id"), funil=funil
            )
            if card_ativo.etapa_id != etapa.pk:
                card_ativo = mover_oportunidade(card_ativo, etapa, autor=funcionario)
                messages.success(request, f"Card movido para “{etapa.nome}”.")
            return redirect(f"{request.path}?card={card_ativo.pk}")
        elif acao == "atualizar_card" and card_ativo:
            fase = (request.POST.get("fase_salvar") or "").strip()
            if not fase and card_ativo.etapa_id:
                fase = fase_campos_pos_vendas(card_ativo.etapa.nome)

            update_fields = ["atualizado_em"]
            if "valor" in request.POST:
                valor_raw = (request.POST.get("valor") or "").strip().replace(",", ".")
                if valor_raw == "":
                    card_ativo.valor = None
                else:
                    try:
                        card_ativo.valor = Decimal(valor_raw)
                    except (InvalidOperation, ValueError):
                        messages.error(request, "Valor inválido.")
                        return redirect(f"{request.path}?card={card_ativo.pk}")
                update_fields.append("valor")
            if "observacoes" in request.POST:
                card_ativo.observacoes = (request.POST.get("observacoes") or "").strip()
                update_fields.append("observacoes")

            mover_para_finalizado = False
            if pos_vendas and fase == "servico_finalizado":
                agora = timezone.now()

                def _bool_marcado(nome: str) -> bool:
                    return request.POST.get(nome) in ("1", "true", "on", "sim")

                novo_atc = _bool_marcado("atc_enviado")
                novo_psc = _bool_marcado("psc_enviado")
                novo_retorno = _bool_marcado("retorno_recebido")

                if novo_atc and not card_ativo.atc_enviado:
                    card_ativo.atc_enviado_em = agora
                    update_fields.append("atc_enviado_em")
                elif not novo_atc:
                    card_ativo.atc_enviado_em = None
                    update_fields.append("atc_enviado_em")
                card_ativo.atc_enviado = novo_atc
                update_fields.append("atc_enviado")

                if novo_psc and not card_ativo.psc_enviado:
                    card_ativo.psc_enviado_em = agora
                    update_fields.append("psc_enviado_em")
                elif not novo_psc:
                    card_ativo.psc_enviado_em = None
                    update_fields.append("psc_enviado_em")
                card_ativo.psc_enviado = novo_psc
                update_fields.append("psc_enviado")

                if novo_retorno and not card_ativo.retorno_recebido:
                    card_ativo.retorno_recebido_em = agora
                    update_fields.append("retorno_recebido_em")
                    mover_para_finalizado = True
                elif not novo_retorno:
                    card_ativo.retorno_recebido_em = None
                    update_fields.append("retorno_recebido_em")
                card_ativo.retorno_recebido = novo_retorno
                update_fields.append("retorno_recebido")

            card_ativo.save(update_fields=list(dict.fromkeys(update_fields)))
            registrar_historico(
                card_ativo,
                tipo=TipoHistoricoOpp.ATUALIZADO,
                descricao="Campos da fase atualizados.",
                autor=funcionario,
            )

            if mover_para_finalizado:
                etapa_fim = (
                    funil.etapas.filter(nome="Pós-venda finalizado").first()
                    or funil.etapas.filter(nome__icontains="pós-venda finalizado").first()
                )
                if etapa_fim and card_ativo.etapa_id != etapa_fim.pk:
                    card_ativo = mover_oportunidade(
                        card_ativo, etapa_fim, autor=funcionario
                    )
                    messages.success(
                        request,
                        "Retorno recebido — card movido para Pós-venda finalizado.",
                    )
                    return redirect(f"{request.path}?card={card_ativo.pk}")

            messages.success(request, "Card atualizado.")
            return redirect(f"{request.path}?card={card_ativo.pk}")
        elif acao == "atualizar_cadastro" and card_ativo:
            card_ativo.titulo = (request.POST.get("titulo") or card_ativo.titulo).strip()
            resp_id = request.POST.get("responsavel_id") or None
            card_ativo.responsavel_id = resp_id or None
            card_ativo.save(update_fields=["titulo", "responsavel", "atualizado_em"])
            registrar_historico(
                card_ativo,
                tipo=TipoHistoricoOpp.ATUALIZADO,
                descricao="Cadastro do card atualizado.",
                autor=funcionario,
            )
            messages.success(request, "Cadastro atualizado.")
            return redirect(f"{request.path}?card={card_ativo.pk}")
        elif acao == "nota" and card_ativo:
            texto = (request.POST.get("nota") or "").strip()
            if texto:
                registrar_historico(
                    card_ativo,
                    tipo=TipoHistoricoOpp.NOTA,
                    descricao=texto,
                    autor=funcionario,
                )
                messages.success(request, "Nota adicionada.")
            return redirect(f"{request.path}?card={card_ativo.pk}")
        else:
            form = OportunidadeForm(request.POST, funil=funil)
            if form.is_valid():
                opp = form.save(commit=False)
                opp.funil = funil
                if not opp.responsavel_id and funcionario:
                    opp.responsavel = funcionario
                if not opp.etapa_id:
                    opp.etapa = funil.etapas.order_by("ordem").first()
                opp.etapa_desde = timezone.now()
                opp.save()
                registrar_historico(
                    opp,
                    tipo=TipoHistoricoOpp.CRIADO,
                    descricao=f"Card criado na etapa {opp.etapa.nome if opp.etapa else '—'}.",
                    autor=funcionario,
                    etapa_para=opp.etapa,
                )
                messages.success(request, "Oportunidade adicionada ao funil.")
                return redirect(f"{request.path}?card={opp.pk}")
            abrir_nova_opp = True

    if form is None:
        initial = {"responsavel": funcionario.pk if funcionario else None}
        empresa_id = request.GET.get("empresa")
        if empresa_id and Empresa.objects.filter(pk=empresa_id, ativa=True).exists():
            initial["empresa"] = empresa_id
            abrir_nova_opp = True
        form = OportunidadeForm(funil=funil, initial=initial)

    etapas = _etapas_com_ops(funil)
    if pos_vendas:
        ordem_oficial = {
            nome: idx for idx, nome in enumerate(ETAPAS_POR_TIPO[TipoSubfunil.POS_VENDAS])
        }
        etapas.sort(key=lambda e: (ordem_oficial.get(e.nome, e.ordem + 100), e.ordem, e.pk))
        for idx, etapa in enumerate(etapas):
            if etapa.ordem != idx:
                etapa.ordem = idx
                etapa.save(update_fields=["ordem"])
            etapa.coluna_css = css_coluna_pos_vendas(etapa.nome)
            etapa.descricao_fase = DESCRICOES_ETAPAS_POS_VENDAS.get(etapa.nome, "")
            etapa.fase_key = fase_campos_pos_vendas(etapa.nome)
    for etapa in etapas:
        _metricas_coluna(etapa, com_valor=False)
        for opp in etapa.oportunidades.all():
            opp.tempo_etapa = tempo_na_etapa(opp)

    historico = []
    posicao_na_etapa = None
    if card_ativo:
        historico = list(
            card_ativo.historico.select_related("autor", "etapa_de", "etapa_para")[:40]
        )
        card_ativo.tempo_etapa = tempo_na_etapa(card_ativo)
        if card_ativo.etapa_id:
            if pos_vendas:
                card_ativo.etapa.coluna_css = css_coluna_pos_vendas(card_ativo.etapa.nome)
                card_ativo.etapa.fase_key = fase_campos_pos_vendas(card_ativo.etapa.nome)
            ids = list(
                Oportunidade.objects.filter(funil=funil, etapa=card_ativo.etapa)
                .order_by("criado_em")
                .values_list("pk", flat=True)
            )
            if card_ativo.pk in ids:
                posicao_na_etapa = (ids.index(card_ativo.pk) + 1, len(ids))

    total_cards = Oportunidade.objects.filter(funil=funil).count()
    pipeline = soma_pipeline_qs(Oportunidade.objects.filter(funil=funil))

    return render(
        request,
        "crm/funil_kanban.html",
        {
            "funil": funil,
            "etapas": etapas,
            "form": form,
            "empresa_form": empresa_form,
            "pipeline": pipeline,
            "subfunis_irmaos": subfunis_irmaos,
            "abrir_popup_empresa": abrir_popup_empresa,
            "abrir_nova_opp": abrir_nova_opp,
            "card_ativo": card_ativo,
            "historico": historico,
            "posicao_na_etapa": posicao_na_etapa,
            "total_cards": total_cards,
            "is_pos_vendas": pos_vendas,
            "responsaveis": Funcionario.objects.filter(ativo=True).order_by(
                "nome", "sobrenome"
            ),
        },
    )


def _fase_campos_pre_vendas(etapa_nome: str) -> str:
    nome = (etapa_nome or "").lower()
    if "1º contato" in nome or "1o contato" in nome:
        return "primeiro_contato"
    if "retornar" in nome:
        return "retornar_contato"
    if "sem oportunidade" in nome:
        return "sem_oportunidade"
    if "conclu" in nome:
        return "concluido"
    return "geral"


def _parse_decimal_br(raw) -> Decimal | None:
    """Aceita 1234.56, 1.234,56 ou 1234,56."""
    texto = (str(raw) if raw is not None else "").strip()
    if texto == "":
        return None
    texto = texto.replace("R$", "").replace(" ", "")
    if "," in texto and "." in texto:
        # 1.234,56 → 1234.56
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    return Decimal(texto)


def _fase_campos_negociacoes(etapa_nome: str) -> str:
    nome = (etapa_nome or "").lower()
    if "enviada" in nome:
        return "proposta_enviada"
    if "follow" in nome:
        return "follow_up"
    if "confirmada" in nome:
        return "oportunidade_confirmada"
    if "elaborando" in nome:
        return "elaborando"
    if "aguardando" in nome:
        return "aguardando"
    if "perdida" in nome:
        return "perdida"
    if "ganha" in nome:
        return "ganha"
    return ""


def _funil_negociacoes(request, funil: Funil):
    subfunis_irmaos = _subfunis_irmaos(funil)
    funcionario = obter_funcionario(request)
    empresa_form = EmpresaForm()
    abrir_popup_empresa = False
    abrir_nova_opp = False
    form = None
    card_id = request.POST.get("card_id") or request.GET.get("card")
    card_ativo = None
    if card_id:
        card_ativo = (
            Oportunidade.objects.filter(pk=card_id, funil=funil)
            .select_related("empresa", "responsavel", "contato", "etapa")
            .first()
        )

    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao == "criar_empresa":
            empresa_form = EmpresaForm(request.POST)
            if empresa_form.is_valid():
                empresa = empresa_form.save()
                messages.success(
                    request,
                    f"Empresa “{empresa.nome}” cadastrada. Vincule na oportunidade.",
                )
                return redirect(f"{request.path}?empresa={empresa.pk}#nova-oportunidade")
            messages.error(request, "Revise os dados da empresa no popup.")
            abrir_popup_empresa = True
            abrir_nova_opp = True
        elif acao == "voltar_etapa" and card_ativo:
            etapa = get_object_or_404(
                EtapaFunil, pk=request.POST.get("etapa_id"), funil=funil
            )
            if card_ativo.etapa_id != etapa.pk:
                card_ativo = mover_oportunidade(card_ativo, etapa, autor=funcionario)
                messages.success(
                    request, f"Card movido para “{etapa.nome}”."
                )
            return redirect(f"{request.path}?card={card_ativo.pk}")
        elif acao == "atualizar_card" and card_ativo:
            fase = (request.POST.get("fase_salvar") or "").strip() or _fase_campos_negociacoes(
                card_ativo.etapa.nome if card_ativo.etapa else ""
            )
            update_fields = ["atualizado_em"]

            if fase in (
                "oportunidade_confirmada",
                "elaborando",
                "aguardando",
                "",
            ) or (
                "escopo_solicitado" in request.POST
                and fase not in ("proposta_enviada", "follow_up", "ganha", "perdida")
            ):
                card_ativo.escopo_solicitado = (
                    request.POST.get("escopo_solicitado") or ""
                ).strip()
                update_fields.append("escopo_solicitado")

            if fase in (
                "proposta_enviada",
                "elaborando",
                "oportunidade_confirmada",
                "aguardando",
                "",
            ) or ("valor" in request.POST and fase not in ("ganha", "follow_up", "perdida")):
                if "valor" in request.POST:
                    try:
                        card_ativo.valor = _parse_decimal_br(request.POST.get("valor"))
                        update_fields.append("valor")
                    except (InvalidOperation, ValueError):
                        messages.error(request, "Valor da proposta inválido.")
                        return redirect(f"{request.path}?card={card_ativo.pk}")

            arquivo_salvo = False
            if fase == "proposta_enviada":
                intl = request.POST.get("proposta_internacional")
                if intl in ("1", "true", "sim", "Sim"):
                    card_ativo.proposta_internacional = True
                elif intl in ("0", "false", "nao", "não", "Não"):
                    card_ativo.proposta_internacional = False
                else:
                    card_ativo.proposta_internacional = None
                update_fields.append("proposta_internacional")
                arquivo = request.FILES.get("proposta_arquivo")
                if arquivo:
                    card_ativo.proposta_arquivo = arquivo
                    update_fields.append("proposta_arquivo")
                    arquivo_salvo = True

            if fase == "follow_up":
                data_raw = (request.POST.get("data_contato_follow_up") or "").strip()
                card_ativo.data_contato_follow_up = data_raw or None
                update_fields.append("data_contato_follow_up")

            if fase == "perdida":
                card_ativo.observacoes = (request.POST.get("observacoes") or "").strip()
                update_fields.append("observacoes")

            if fase == "ganha":
                try:
                    card_ativo.valor_final_fechado = _parse_decimal_br(
                        request.POST.get("valor_final_fechado")
                    )
                    card_ativo.desconto_concedido = _parse_decimal_br(
                        request.POST.get("desconto_concedido")
                    )
                    pct_comissao = _parse_decimal_br(
                        request.POST.get("percentual_comissao")
                    )
                    pct_bonus = _parse_decimal_br(request.POST.get("percentual_bonus"))
                except (InvalidOperation, ValueError):
                    messages.error(
                        request, "Revise os valores numéricos da proposta ganha."
                    )
                    return redirect(f"{request.path}?card={card_ativo.pk}")

                if pct_comissao is not None and (
                    pct_comissao < 0 or pct_comissao > 100
                ):
                    messages.error(request, "Percentual de comissão deve estar entre 0 e 100.")
                    return redirect(f"{request.path}?card={card_ativo.pk}")
                if pct_bonus is not None and (pct_bonus < 12 or pct_bonus > 35):
                    messages.error(
                        request,
                        "Percentual de bônus do agente deve estar entre 12% e 35%.",
                    )
                    return redirect(f"{request.path}?card={card_ativo.pk}")

                card_ativo.percentual_comissao = pct_comissao
                card_ativo.percentual_bonus = pct_bonus

                # Comissão = % × valor final; bônus = % × comissão
                if (
                    card_ativo.valor_final_fechado is not None
                    and pct_comissao is not None
                ):
                    card_ativo.comissao = (
                        card_ativo.valor_final_fechado * pct_comissao / Decimal("100")
                    ).quantize(Decimal("0.01"))
                else:
                    try:
                        card_ativo.comissao = _parse_decimal_br(
                            request.POST.get("comissao")
                        )
                    except (InvalidOperation, ValueError):
                        card_ativo.comissao = None

                if card_ativo.comissao is not None and pct_bonus is not None:
                    card_ativo.bonus_agente = (
                        card_ativo.comissao * pct_bonus / Decimal("100")
                    ).quantize(Decimal("0.01"))
                else:
                    try:
                        card_ativo.bonus_agente = _parse_decimal_br(
                            request.POST.get("bonus_agente")
                        )
                    except (InvalidOperation, ValueError):
                        card_ativo.bonus_agente = None

                # Valor do negócio = valor final fechado
                card_ativo.valor = card_ativo.valor_final_fechado
                update_fields.extend(
                    [
                        "valor_final_fechado",
                        "desconto_concedido",
                        "percentual_comissao",
                        "percentual_bonus",
                        "comissao",
                        "bonus_agente",
                        "valor",
                    ]
                )

            if "escopo_solicitado" in request.POST and "escopo_solicitado" not in update_fields:
                card_ativo.escopo_solicitado = (
                    request.POST.get("escopo_solicitado") or ""
                ).strip()
                update_fields.append("escopo_solicitado")

            # FileField: save completo garante gravação do arquivo no disco
            campos = list(dict.fromkeys(update_fields))
            if arquivo_salvo:
                card_ativo.save()
            else:
                card_ativo.save(update_fields=campos)
            registrar_historico(
                card_ativo,
                tipo=TipoHistoricoOpp.ATUALIZADO,
                descricao="Campos da fase de negociação atualizados.",
                autor=funcionario,
            )
            if arquivo_salvo:
                messages.success(
                    request,
                    f"Proposta salva: {card_ativo.proposta_arquivo.name.split('/')[-1]}.",
                )
            if fase == "ganha":
                filho = criar_card_pos_vendas(card_ativo, autor=funcionario)
                if filho:
                    messages.success(
                        request,
                        "Card atualizado. Acompanhamento criado em Pós-vendas.",
                    )
                    return redirect(
                        f"{reverse('crm_funil_detalhe', kwargs={'pk': filho.funil_id})}"
                        f"?card={filho.pk}"
                    )
            messages.success(request, "Card atualizado.")
            return redirect(f"{request.path}?card={card_ativo.pk}")
        elif acao == "atualizar_cadastro" and card_ativo:
            card_ativo.titulo = (request.POST.get("titulo") or card_ativo.titulo).strip()
            card_ativo.observacoes = (request.POST.get("observacoes") or "").strip()
            resp_id = request.POST.get("responsavel_id") or None
            card_ativo.responsavel_id = resp_id or None
            card_ativo.save(
                update_fields=["titulo", "observacoes", "responsavel", "atualizado_em"]
            )
            etapa_id = request.POST.get("etapa_id")
            if etapa_id and str(card_ativo.etapa_id or "") != str(etapa_id):
                etapa = get_object_or_404(EtapaFunil, pk=etapa_id, funil=funil)
                card_ativo = mover_oportunidade(card_ativo, etapa, autor=funcionario)
            else:
                registrar_historico(
                    card_ativo,
                    tipo=TipoHistoricoOpp.ATUALIZADO,
                    descricao="Cadastro do card atualizado.",
                    autor=funcionario,
                )
            messages.success(request, "Cadastro atualizado.")
            return redirect(f"{request.path}?card={card_ativo.pk}")
        elif acao == "nota" and card_ativo:
            texto = (request.POST.get("nota") or "").strip()
            if texto:
                registrar_historico(
                    card_ativo,
                    tipo=TipoHistoricoOpp.NOTA,
                    descricao=texto,
                    autor=funcionario,
                )
                messages.success(request, "Nota adicionada.")
            return redirect(f"{request.path}?card={card_ativo.pk}")
        else:
            form = OportunidadeForm(request.POST, funil=funil)
            if form.is_valid():
                opp = form.save(commit=False)
                opp.funil = funil
                if not opp.responsavel_id and funcionario:
                    opp.responsavel = funcionario
                if not opp.etapa_id:
                    opp.etapa = (
                        funil.etapas.filter(nome="Oportunidade confirmada").first()
                        or funil.etapas.order_by("ordem").first()
                    )
                opp.etapa_desde = timezone.now()
                opp.save()
                registrar_historico(
                    opp,
                    tipo=TipoHistoricoOpp.CRIADO,
                    descricao=f"Oportunidade criada em {opp.etapa.nome if opp.etapa else '—'}.",
                    autor=funcionario,
                    etapa_para=opp.etapa,
                )
                messages.success(request, "Oportunidade adicionada ao funil.")
                return redirect(f"{request.path}?card={opp.pk}")
            abrir_nova_opp = True

    if form is None:
        initial = {"responsavel": funcionario.pk if funcionario else None}
        empresa_id = request.GET.get("empresa")
        if empresa_id and Empresa.objects.filter(pk=empresa_id, ativa=True).exists():
            initial["empresa"] = empresa_id
            abrir_nova_opp = True
        form = OportunidadeForm(funil=funil, initial=initial)

    etapas = _etapas_com_ops(funil)
    ordem_oficial = {
        nome: idx for idx, nome in enumerate(ETAPAS_POR_TIPO[TipoSubfunil.NEGOCIACOES])
    }
    etapas.sort(key=lambda e: (ordem_oficial.get(e.nome, e.ordem + 100), e.ordem, e.pk))
    alertas_follow_up = []
    for idx, etapa in enumerate(etapas):
        if etapa.ordem != idx:
            etapa.ordem = idx
            etapa.save(update_fields=["ordem"])
        etapa.coluna_css = css_coluna_negociacoes(etapa.nome)
        etapa.descricao_fase = DESCRICOES_ETAPAS_NEGOCIACOES.get(etapa.nome, "")
        etapa.fase_key = _fase_campos_negociacoes(etapa.nome) or "geral"
        _metricas_coluna(etapa, com_valor=True)
        for opp in etapa.oportunidades.all():
            opp.tempo_etapa = tempo_na_etapa(opp)
            if opp.alerta_follow_up:
                alertas_follow_up.append(opp)

    alertas_follow_up.sort(
        key=lambda o: (o.data_contato_follow_up or timezone.localdate(), o.pk)
    )

    fase_campos = ""
    historico = []
    posicao_na_etapa = None
    if card_ativo and card_ativo.etapa_id:
        fase_campos = _fase_campos_negociacoes(card_ativo.etapa.nome)
        card_ativo.etapa.coluna_css = css_coluna_negociacoes(card_ativo.etapa.nome)
        card_ativo.tempo_etapa = tempo_na_etapa(card_ativo)
        historico = list(
            card_ativo.historico.select_related("autor", "etapa_de", "etapa_para")[:40]
        )
        ids = list(
            Oportunidade.objects.filter(funil=funil, etapa=card_ativo.etapa)
            .order_by("criado_em")
            .values_list("pk", flat=True)
        )
        if card_ativo.pk in ids:
            posicao_na_etapa = (ids.index(card_ativo.pk) + 1, len(ids))

    total_cards = Oportunidade.objects.filter(funil=funil).count()
    pipeline = Decimal("0")
    for etapa in etapas:
        if etapa.valor_acumulado:
            pipeline += etapa.valor_acumulado

    return render(
        request,
        "crm/negociacoes_kanban.html",
        {
            "funil": funil,
            "etapas": etapas,
            "form": form,
            "empresa_form": empresa_form,
            "subfunis_irmaos": subfunis_irmaos,
            "abrir_popup_empresa": abrir_popup_empresa,
            "abrir_nova_opp": abrir_nova_opp,
            "card_ativo": card_ativo,
            "fase_campos": fase_campos,
            "alertas_follow_up": alertas_follow_up,
            "fatores_comissionamento": FatorComissionamento,
            "historico": historico,
            "posicao_na_etapa": posicao_na_etapa,
            "responsaveis": Funcionario.objects.filter(ativo=True).order_by(
                "nome", "sobrenome"
            ),
            "total_cards": total_cards,
            "pipeline": pipeline,
            "mostrar_valor_coluna": True,
        },
    )


def _funil_pre_vendas(request, funil: Funil):
    subfunis_irmaos = _subfunis_irmaos(funil)
    funcionario = obter_funcionario(request)
    empresa_form = EmpresaForm()
    abrir_popup_empresa = False
    abrir_novo_card = False
    form = None
    card_form = None
    card_id = request.POST.get("card_id") or request.GET.get("card")
    card_ativo = None
    if card_id:
        card_ativo = (
            Oportunidade.objects.filter(pk=card_id, funil=funil)
            .select_related("empresa", "responsavel", "contato", "etapa")
            .first()
        )

    if request.method == "POST":
        acao = request.POST.get("acao")

        if acao == "criar_empresa":
            empresa_form = EmpresaForm(request.POST)
            if empresa_form.is_valid():
                empresa = empresa_form.save()
                messages.success(
                    request,
                    f"Empresa “{empresa.nome}” cadastrada. Vincule no card.",
                )
                return redirect(f"{request.path}?empresa={empresa.pk}#novo-card")
            messages.error(request, "Revise os dados da empresa no popup.")
            abrir_popup_empresa = True
            abrir_novo_card = True

        elif acao == "voltar_etapa" and card_ativo:
            etapa = get_object_or_404(
                EtapaFunil, pk=request.POST.get("etapa_id"), funil=funil
            )
            if card_ativo.etapa_id != etapa.pk:
                card_ativo = mover_oportunidade(card_ativo, etapa, autor=funcionario)
                if card_ativo.funil_id != funil.pk:
                    messages.success(
                        request,
                        "Card concluído e enviado para Negociações · Oportunidade confirmada.",
                    )
                    return redirect(
                        f"{reverse('crm_funil_detalhe', kwargs={'pk': card_ativo.funil_id})}?card={card_ativo.pk}"
                    )
                messages.success(request, f"Card movido para “{etapa.nome}”.")
            return redirect(f"{request.path}?card={card_ativo.pk}")

        elif acao == "salvar_card" and card_ativo:
            etapa_antiga_id = card_ativo.etapa_id
            card_form = CardPreVendasForm(request.POST, instance=card_ativo, funil=funil)
            if card_form.is_valid():
                opp = card_form.save(commit=False)
                etapa_nova = card_form.cleaned_data.get("etapa")
                if etapa_nova and etapa_nova.pk != etapa_antiga_id:
                    opp.etapa_id = etapa_antiga_id
                    opp.save()
                    opp = mover_oportunidade(opp, etapa_nova, autor=funcionario)
                else:
                    opp.save()
                registrar_historico(
                    opp,
                    tipo=TipoHistoricoOpp.ATUALIZADO,
                    descricao="Informações do card atualizadas.",
                    autor=funcionario,
                )
                if opp.funil_id != funil.pk:
                    messages.success(
                        request,
                        "Card concluído e enviado para Negociações · Oportunidade confirmada.",
                    )
                    return redirect(
                        f"{reverse('crm_funil_detalhe', kwargs={'pk': opp.funil_id})}?card={opp.pk}"
                    )
                messages.success(request, "Card atualizado.")
                return redirect(f"{request.path}?card={opp.pk}")

        elif acao == "salvar_etapa_campos" and card_ativo:
            formas = request.POST.getlist("formas_contato")
            validas = {c.value for c in FormaContato}
            card_ativo.formas_contato = [f for f in formas if f in validas]
            motivo = (request.POST.get("motivo_falta_retorno") or "").strip()
            motivos_ok = {c.value for c in MotivoFaltaRetorno}
            card_ativo.motivo_falta_retorno = motivo if motivo in motivos_ok else ""
            card_ativo.motivo_sem_oportunidade = (
                request.POST.get("motivo_sem_oportunidade") or ""
            ).strip()
            card_ativo.escopo_solicitado = (request.POST.get("escopo_solicitado") or "").strip()
            data_retorno = (request.POST.get("data_retorno") or "").strip()
            card_ativo.data_retorno = data_retorno or None
            funil_venda_id = request.POST.get("funil_venda") or None
            if funil_venda_id:
                if Funil.objects.filter(
                    pk=funil_venda_id, ativo=True, tipo=TipoSubfunil.NEGOCIACOES
                ).exists():
                    card_ativo.funil_venda_id = funil_venda_id
            else:
                card_ativo.funil_venda = None
            card_ativo.save()
            registrar_historico(
                card_ativo,
                tipo=TipoHistoricoOpp.ATUALIZADO,
                descricao="Campos da etapa atualizados.",
                autor=funcionario,
            )
            messages.success(request, "Campos da etapa salvos.")
            return redirect(f"{request.path}?card={card_ativo.pk}")

        elif acao == "nota" and card_ativo:
            texto = (request.POST.get("nota") or "").strip()
            if texto:
                registrar_historico(
                    card_ativo,
                    tipo=TipoHistoricoOpp.NOTA,
                    descricao=texto,
                    autor=funcionario,
                )
                messages.success(request, "Nota adicionada.")
            return redirect(f"{request.path}?card={card_ativo.pk}")

        elif acao == "criar":
            form = CardPreVendasForm(request.POST, funil=funil)
            if form.is_valid():
                opp = form.save(commit=False)
                opp.funil = funil
                if not opp.responsavel_id and funcionario:
                    opp.responsavel = funcionario
                if not opp.etapa_id:
                    opp.etapa = funil.etapas.order_by("ordem").first()
                opp.etapa_desde = timezone.now()
                opp.save()
                registrar_historico(
                    opp,
                    tipo=TipoHistoricoOpp.CRIADO,
                    descricao=f"Lead capturado na etapa {opp.etapa.nome if opp.etapa else '—'}.",
                    autor=funcionario,
                    etapa_para=opp.etapa,
                )
                messages.success(request, "Card adicionado ao kanban de pré-vendas.")
                return redirect(f"{request.path}?card={opp.pk}")
            abrir_novo_card = True

    if form is None:
        initial = {"responsavel": funcionario.pk if funcionario else None}
        empresa_id = request.GET.get("empresa")
        if empresa_id and Empresa.objects.filter(pk=empresa_id, ativa=True).exists():
            initial["empresa"] = empresa_id
            abrir_novo_card = True
        form = CardPreVendasForm(funil=funil, initial=initial)

    if card_ativo and card_form is None:
        card_form = CardPreVendasForm(instance=card_ativo, funil=funil)

    etapas = _etapas_com_ops(funil)
    # reforça ordem oficial do fluxo de prospecção
    ordem_oficial = {nome: idx for idx, nome in enumerate(ETAPAS_POR_TIPO[TipoSubfunil.PRE_VENDAS])}
    etapas.sort(key=lambda e: (ordem_oficial.get(e.nome, e.ordem + 100), e.ordem, e.pk))
    for idx, etapa in enumerate(etapas):
        if etapa.ordem != idx:
            etapa.ordem = idx
            etapa.save(update_fields=["ordem"])
        etapa.coluna_css = css_coluna_pre_vendas(etapa.nome)
        etapa.descricao_fase = DESCRICOES_ETAPAS_PRE_VENDAS.get(etapa.nome, "")
        etapa.fase_key = _fase_campos_pre_vendas(etapa.nome)
        _metricas_coluna(etapa, com_valor=False)
        for opp in etapa.oportunidades.all():
            opp.tempo_etapa = tempo_na_etapa(opp)

    total_cards = Oportunidade.objects.filter(funil=funil).count()
    historico = []
    posicao_na_etapa = None
    fase_campos = ""
    if card_ativo:
        historico = list(card_ativo.historico.select_related("autor", "etapa_de", "etapa_para")[:40])
        card_ativo.tempo_etapa = tempo_na_etapa(card_ativo)
        if card_ativo.etapa_id:
            ids = list(
                Oportunidade.objects.filter(funil=funil, etapa=card_ativo.etapa)
                .order_by("criado_em")
                .values_list("pk", flat=True)
            )
            if card_ativo.pk in ids:
                posicao_na_etapa = (ids.index(card_ativo.pk) + 1, len(ids))
            fase_campos = _fase_campos_pre_vendas(card_ativo.etapa.nome)
            card_ativo.etapa.coluna_css = css_coluna_pre_vendas(card_ativo.etapa.nome)

    contatos_json = [
        {"id": c.pk, "empresa_id": c.empresa_id, "label": f"{c.nome_completo} ({c.empresa.nome})"}
        for c in Contato.objects.filter(ativo=True).select_related("empresa").order_by(
            "nome", "sobrenome"
        )
    ]

    return render(
        request,
        "crm/pre_vendas_kanban.html",
        {
            "funil": funil,
            "etapas": etapas,
            "form": form,
            "card_form": card_form,
            "empresa_form": empresa_form,
            "subfunis_irmaos": subfunis_irmaos,
            "abrir_popup_empresa": abrir_popup_empresa,
            "abrir_novo_card": abrir_novo_card,
            "card_ativo": card_ativo,
            "historico": historico,
            "posicao_na_etapa": posicao_na_etapa,
            "total_cards": total_cards,
            "contatos_json": json.dumps(contatos_json),
            "fase_campos": fase_campos,
        },
    )


@login_required
@require_POST
def funil_mover_card(request, pk: int):
    funil = get_object_or_404(Funil, pk=pk, ativo=True)
    funcionario = obter_funcionario(request)
    opp = get_object_or_404(
        Oportunidade, pk=request.POST.get("oportunidade_id"), funil=funil
    )
    etapa = get_object_or_404(EtapaFunil, pk=request.POST.get("etapa_id"), funil=funil)
    opp = mover_oportunidade(opp, etapa, autor=funcionario)
    payload = {
        "ok": True,
        "oportunidade_id": opp.pk,
        "etapa_id": opp.etapa_id,
        "etapa_nome": opp.etapa.nome if opp.etapa else "",
        "tempo_etapa": tempo_na_etapa(opp),
    }
    if opp.funil_id != funil.pk:
        payload["promovido"] = True
        payload["redirect_url"] = (
            f"{reverse('crm_funil_detalhe', kwargs={'pk': opp.funil_id})}?card={opp.pk}"
        )
    return JsonResponse(payload)

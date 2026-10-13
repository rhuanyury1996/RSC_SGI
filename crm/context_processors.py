from .services import nav_funis_sidebar


def funis_nav(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"nav_funis_clientes": []}

    funil_ativo_id = None
    match = getattr(request, "resolver_match", None)
    if match and match.url_name == "crm_funil_detalhe":
        try:
            funil_ativo_id = int(match.kwargs.get("pk"))
        except (TypeError, ValueError):
            funil_ativo_id = None

    return {"nav_funis_clientes": nav_funis_sidebar(funil_ativo_id)}

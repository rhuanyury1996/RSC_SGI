from .gmail_oauth import gmail_conectado, gmail_oauth_configurado, usuario_precisa_conectar_gmail
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


def gmail_vinculo(request):
    """Pop-up de vínculo Gmail após o login (fluxo próprio do CRM)."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            "mostrar_popup_google_gmail": False,
            "google_gmail_conectado": False,
            "google_oauth_configurado": False,
        }
    configurado = gmail_oauth_configurado()
    conectado = gmail_conectado(request.user) if configurado else False
    precisa = configurado and usuario_precisa_conectar_gmail(request.user)
    dismissed = bool(request.session.get("gmail_popup_dismissed"))
    return {
        "google_oauth_configurado": configurado,
        "google_gmail_conectado": conectado,
        "mostrar_popup_google_gmail": bool(precisa and not dismissed),
    }

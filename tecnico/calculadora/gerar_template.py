"""Gera templates/tecnico/calculadora.html a partir da calculadora independente.

A calculadora é mantida como um único HTML (classificacao_areas.html, nesta pasta),
que também funciona aberto direto no navegador. Este script embrulha o arquivo
em {% verbatim %} (o JavaScript usa ${...} e chaves que o Django leria como
template) e injeta, antes do primeiro <script>, o JSON do estudo:

    {{ config|json_script:"sgi-ca" }}

Uso (na raiz do projeto):
    python tecnico/calculadora/gerar_template.py
"""
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ORIGEM = AQUI / "classificacao_areas.html"
DESTINO = AQUI.parent.parent / "templates" / "tecnico" / "calculadora.html"


def gerar() -> Path:
    html = ORIGEM.read_text(encoding="utf-8")
    if "{% endverbatim %}" in html:
        raise SystemExit("O HTML de origem contém {% endverbatim %}: não dá para embrulhar.")
    i = html.index("<script>")
    corpo = (
        "{% verbatim %}" + html[:i] + "{% endverbatim %}"
        + '{{ config|json_script:"sgi-ca" }}\n'
        + "{% verbatim %}" + html[i:] + "{% endverbatim %}\n"
    )
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(corpo, encoding="utf-8")
    return DESTINO


if __name__ == "__main__":
    print("Gerado:", gerar())

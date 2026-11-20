# Setor Técnico · Classificação de áreas

Estudos de classificação de áreas conforme a ABNT NBR IEC 60079-10-1 (Anexos A, B e C),
com dispersão complementar pelo Yellow Book (TNO CPR 14E) e Purple Book (TNO CPR 18E),
memorial de cálculo no formato do **Apêndice C** do relatório técnico RSC e listas C.1/C.2.

## Como está organizado

| Caminho | O que faz |
|---|---|
| `calculadora/classificacao_areas.html` | Calculadora completa (fonte da verdade). Funciona também aberta direto no navegador. |
| `calculadora/gerar_template.py` | Gera `templates/tecnico/calculadora.html` a partir do HTML acima. |
| `models.py` | `EstudoClassificacao`: cabeçalho (projeto, cliente, revisão, status) + `estado` (JSON da calculadora). |
| `views.py` | Lista, criar, abrir (iframe), calculadora, salvar (POST JSON), baixar JSON, duplicar, status. |
| `permissions.py` | `pode_editar_tecnico`: nível "editar" no módulo `tecnico`. |
| `templates/tecnico/` | `estudos.html` (lista), `estudo.html` (tela com o iframe), `calculadora.html` (gerado). |

## Fluxo

1. **Setor Técnico → Classificação de áreas → Novo estudo** cria o registro e abre a tela do estudo.
2. A tela do estudo carrega a calculadora num iframe (`/tecnico/classificacao/<id>/app/`).
3. A calculadora recebe o estado em `<script id="sgi-ca" type="application/json">` e, a cada alteração,
   grava por `POST /tecnico/classificacao/<id>/salvar/` (JSON, com CSRF). O status aparece no topo
   ("Salvo no SGI às 14:32"). Também guarda uma cópia no navegador como reserva.
4. Quem tem "Só ver" no módulo abre a calculadora com aviso de leitura e nada é gravado (o servidor responde 403).

## Atualizar a calculadora

Edite ou substitua `calculadora/classificacao_areas.html` e rode:

```bash
python tecnico/calculadora/gerar_template.py
```

Nunca edite `templates/tecnico/calculadora.html` à mão: ele é sobrescrito pelo gerador.

## Cores do gráfico da nuvem

Na legenda do gráfico "Vista lateral da nuvem" cada linha (50 % do LIE, LIE e LSE) tem um seletor de cor.
A escolha é gravada no estado do estudo (`estado.cores`) e vale para quem abrir o estudo depois;
"Restaurar cores" volta ao padrão. Fora do SGI fica no `localStorage`.

## Divergências em relação ao prompt de integração

- Última migração de `funcionarios` era a `0007`; a nova é `0008_acesso_tecnico`. A do `crm` era a `0026`.
- As telas passam `pode_editar` (booleano) ao template, o que sobrepõe o dicionário `pode_editar` do
  context processor nessas páginas. O `base.html` não usa essa variável; se passar a usar, renomeie.

## Próximas etapas

1. Banco de produtos compartilhado entre estudos (modelo `ProdutoTecnico`), em vez de cada estudo guardar os seus.
2. Exportar o Apêndice C para `.docx` no servidor com o modelo oficial do relatório RSC (como no `orcamentos`, com `python-docx`).
3. Histórico de revisões do estudo (um snapshot do `estado` por revisão emitida).
4. Novos cálculos: SLAB (gás denso), evaporação de poça (inclusive de mistura) e esvaziamento transiente do vaso.

## Testes

```bash
python manage.py test tecnico
```

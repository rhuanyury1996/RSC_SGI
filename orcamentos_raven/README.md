# Módulo Orçamento RAVEN (`orcamentos_raven`)

App Django próprio, ligado ao CRM e ao módulo Orçamentos (GEXCON) como descrito abaixo.

Mesmo fluxo do GEXCON (CRM → prévia → emitir → histórico → status), para a
plataforma RAVEN. Fica em **Área Comercial → Orçamentos RAVEN** (`/orcamentos/raven/`).

| Caminho | O que faz |
|---|---|
| `raven/calculo.py` | Planos, licença, implantação, pacote de horas, desconto à vista, total e numeração. Não depende do Django. |
| `raven/parametros_2026.json` | Planos e preços 2026 (indústria e consultoria), faixas do pacote de horas, desconto à vista (8%), 10× no boleto, trial de 3 dias, login em 48 h. |
| `raven/documento.py` + `modelos_html/proposta_raven.html` | Gera a proposta A4 em HTML com os valores travados. O usuário abre no navegador e imprime/salva em PDF. |
| `models.py` | `TabelaRaven` (um registro por ano) e `OrcamentoRaven` (snapshot, HTML, status, aceite e login). |
| `services.py` / `views.py` / `forms.py` | CRM, cálculo, emissão, aceite e liberação de login. |
| `templates/orcamentos_raven/` | Telas: novo, histórico e parâmetros. |

## Instalar

```bash
python manage.py migrate                 # cria TabelaRaven e OrcamentoRaven
python manage.py seed_parametros_raven   # cadastra a tabela RAVEN 2026
python manage.py test orcamentos_raven
```

## Regras

- Empresa e contato vêm do CRM (mesma regra do GEXCON: precisa de contato ativo; o principal vem pré-selecionado).
- Numeração `AAMMDD-N` **compartilhada com o GEXCON**: o sequencial do dia considera as duas tabelas.
  Arquivo: `Orc_AAMMDD-N_NomeCurto_RAVEN.html`.
- Licença: valor de tabela do plano/vigência; pode ser substituído por valor negociado (fica o aviso).
  Sem preço de tabela (Beyond, Enterprise, 12 meses da indústria) a emissão exige o valor.
- À vista: 8% de desconto sobre a licença, abatido no total. 10× no boleto: sem desconto.
- Implantação em campo só para indústria (não existe para consultoria nem trial).
- Pacote de horas (cadastros e estudos): até 40 h R$ 46,21/h, até 80 h R$ 37,48/h, acima R$ 25,82/h.
- Trial: 3 dias, R$ 0,00.
- Status **Aceita** grava o aceite e abre o prazo de 48 h para liberar o login; o histórico avisa
  as propostas aceitas sem login e o botão **Marcar liberado** registra quem liberou e quando.

Para mudar preços de um ano: **Orçamentos RAVEN → Parâmetros** (gestores). Para mudar textos
da proposta, atualize `modelos_html/proposta_raven.html` (gerado a partir do projeto do site).

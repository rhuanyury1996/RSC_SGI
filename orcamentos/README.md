# Módulo Orçamento GEXCON

Gera as propostas de software GEXCON (EFFECTS e EFFECTS + RISKCURVES) em `.docx`
a partir do modelo oficial, com preços calculados, dados do cliente vindos do CRM
do SGI e histórico gravado no banco.

## Como está organizado

| Caminho | O que faz |
|---|---|
| `gexcon/` | Regras validadas (preços, numeração, gerador do docx). Não depende do Django. |
| `gexcon/parametros_2026.json` | Tabela 2026, usada como semente. |
| `modelos_docx/modelo_orcamento_gexcon.docx` | Modelo oficial da proposta. |
| `models.py` | `TabelaParametros` (um registro por ano) e `Orcamento` (snapshot + arquivo). |
| `services.py` | Ponte com o CRM: endereço, contatos, sequencial, cálculo e emissão. |
| `views.py` / `templates/orcamentos/` | Telas: novo, histórico e parâmetros. |

## Instalar

```bash
pip install -r requirements.txt          # inclui python-docx
python manage.py migrate
python manage.py seed_parametros_orcamento          # cadastra a tabela 2026
```

O link fica em **Área Comercial → Orçamentos** na barra lateral.

## Cadastrar a tabela de um novo ano

Sem mexer em código: **Orçamentos → Parâmetros → Cadastrar tabela de um novo ano**
(só gestores: gerente, sócio, supervisor ou admin). Copie o JSON do ano vigente e
ajuste `versao_tabela`, `precos_lista`, `reajuste_lista`, `validade_ate` e os
treinamentos. O JSON é validado antes de salvar.

Pela linha de comando:

```bash
python manage.py seed_parametros_orcamento --ano 2027 --arquivo caminho/parametros_2027.json
```

A proposta usa a tabela do **ano da data da proposta**. Data depois de
`validade_ate` bloqueia a emissão com a mensagem "atualize os parâmetros".

## Dados que o CRM precisa ter

Em **Empresas**, a proposta usa razão social, nome curto, CNPJ e endereço
(logradouro, complemento/bairro, cidade, UF, CEP, país) — a consulta de CNPJ
preenche esses campos quando estão vazios. Cada empresa precisa de pelo menos um
contato ativo; marque o **contato principal** para ele vir pré-selecionado.

## Onde fica o arquivo

O `.docx` é gravado no próprio banco, junto com o orçamento, e baixado pela tela
de histórico. O SGI roda no Render, que não enxerga `G:\Drives compartilhados`.

**Próximo passo (não implementado):** salvar também no Google Drive, na pasta
`GEXCON\Propostas\<ANO>\<NomeCurto>\3. Propostas`, criando a pasta a partir de
`__PastaPadrao` e removendo a cópia vazia do modelo. Precisa de uma conta de
serviço do Google Drive e do id da pasta raiz em variável de ambiente. Enquanto
isso, o sequencial do dia considera só o histórico do SGI — propostas antigas que
existam apenas no Drive não entram na contagem.

## Testes

```bash
python manage.py test orcamentos
```

Cobrem os casos obrigatórios da seção 9 do procedimento: preços por período,
usuário adicional, reajustes, prazo de renovação, bloqueio por validade,
numeração e nome do arquivo, sequencial do dia, assinatura sem duplicar e rodapé
com o número novo.

## Opções do XSuite Price Builder 2026 (EFFECTS e E+R)

Mesma conta do Deal Builder da planilha `251215-XSuite-Price-Builder-2026 EURO_DPR.xlsx`:

- Ano 1 = lista × modificador da duração × licenças × (1 − desconto + fator Brasil 5%)
- Durações: 1 a 6 meses (0,14 por mês), 1 ano, 2 a 5 anos. Acima de 1 ano, cada ano extra
  sobe `fator_multi_ano` (5%) e a proposta mostra o total do período (até 3 colunas).
- Licenças por módulo (Concurrent) e Dongle (€ 750, item avulso).
- Categoria de licença (`categorias_licenca`): comercial 0%, órgão público 45%, acadêmica 90%.
  O desconto entra somado ao fator Brasil, como na planilha. A acadêmica segue os Termos
  Gexcon (jan/2024) item 3.2 e a proposta mostra os avisos dessas regras.
- `python manage.py seed_parametros_orcamento` completa tabelas antigas com essas chaves
  sem alterar os valores já cadastrados.

---

# Orçamento RAVEN

Mesmo fluxo do GEXCON (CRM → prévia → emitir → histórico → status), para a
plataforma RAVEN. Fica em **Área Comercial → Orçamentos RAVEN** (`/orcamentos/raven/`).

| Caminho | O que faz |
|---|---|
| `raven/calculo.py` | Planos, licença, implantação, pacote de horas, desconto à vista, total e numeração. Não depende do Django. |
| `raven/parametros_2026.json` | Planos e preços 2026 (indústria e consultoria), faixas do pacote de horas, desconto à vista (8%), 10× no boleto, trial de 3 dias, login em 48 h. |
| `raven/documento.py` + `modelos_html/proposta_raven.html` | Gera a proposta A4 em HTML com os valores travados. O usuário abre no navegador e imprime/salva em PDF. |
| `models.py` | `TabelaRaven` (um registro por ano) e `OrcamentoRaven` (snapshot, HTML, status, aceite e login). |
| `services_raven.py` / `views_raven.py` / `forms_raven.py` | CRM, cálculo, emissão, aceite e liberação de login. |
| `templates/orcamentos/raven/` | Telas: novo, histórico e parâmetros. |

## Instalar

```bash
python manage.py migrate                 # cria TabelaRaven e OrcamentoRaven (0004)
python manage.py seed_parametros_raven   # cadastra a tabela RAVEN 2026
python manage.py test orcamentos
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

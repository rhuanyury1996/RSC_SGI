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
| `views.py` / `templates/orcamentos/` | Telas: novo, detalhe, edição, histórico e parâmetros. |

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

## Editar uma proposta

A tela de detalhe tem **Editar**. Salvar cria uma **revisão**: a proposta é
recalculada, o `.docx` é refeito e o que mudou (escopo, períodos,
contato, treinamentos, total) fica registrado no histórico de edições, com quem
e quando. O número e a data não mudam na revisão — para outra data, emita uma
proposta nova. Edita quem emitiu; gestores editam qualquer uma.

## Onde fica o arquivo

O `.docx` é gravado no próprio banco, junto com o orçamento, e baixado pela tela
de detalhe. O SGI roda no Render, que não enxerga `G:\Drives compartilhados`.

**Próximo passo (não implementado):** salvar também no Google Drive, na pasta
`GEXCON\Propostas\<ANO>\<NomeCurto>\3. Propostas`, criando a pasta a partir de
`__PastaPadrao` e removendo a cópia vazia do modelo. Precisa de uma conta de
serviço do Google Drive e do id da pasta raiz em variável de ambiente. Enquanto
isso, o sequencial do dia considera só o histórico do SGI — propostas antigas que
existam apenas no Drive não entram na contagem.

**PDF:** fora de escopo. Converter `.docx` com fidelidade exige LibreOffice ou
Word, e o runtime Python nativo do Render não permite instalar pacote de
sistema. Se um dia virar prioridade, o caminho é trocar o serviço para Docker
com LibreOffice, ou converter pelo Google Drive.

## Testes

```bash
python manage.py test orcamentos
```

Cobrem os casos obrigatórios da seção 9 do procedimento: preços por período,
usuário adicional, reajustes, prazo de renovação, bloqueio por validade,
numeração e nome do arquivo, sequencial do dia, assinatura sem duplicar e rodapé
com o número novo.

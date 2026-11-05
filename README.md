# ERP Teco + Nona — homologação

Sistema web Django / PostgreSQL em português, com pedidos, produção por turno, entregas, financeiro e documentos comerciais não fiscais. Cada empresa começa em configuração/teste e pode ativar a operação gerencial depois da conferência em **Começar operação**. NF-e/NFC-e própria permanece uma etapa futura.

## Para quem não programa

A instalação na internet está explicada em [Hospedagem: passo a passo](docs/HOSPEDAGEM_PASSO_A_PASSO.md). Depois de criar o primeiro acesso, abra **Como usar** dentro do sistema. O botão **Preparar meus exemplos de teste** dispensa comandos.

Fluxo operacional: **Começar operação → conferir cadastros → ativar empresa → lançar pedidos pela data da entrega → conferir produção → imprimir comprovantes não fiscais → confirmar entrega → fechamento do cliente**. Preços ausentes bloqueiam emissão; nenhum preço ou CNPJ é inventado. [Começar hoje](docs/COMECE_HOJE.md) explica o primeiro dia.

Dados antigos só entram na tela autenticada **Dados antigos**. Aprovar uma revisão não cria pedido ou cobrança e não ativa recorrência. As 101 regras legadas são candidatas desativadas. Notas de 01–04/11/2026 são auditoria e 05/11 é previsão.

## Desenvolvimento local

Python 3.12 e PostgreSQL 16. A tarefa de nuvem já é isolada: use o checkout existente, sem criar worktree.

```sh
docker compose up -d db
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver 0.0.0.0:8000
```

`/` pedidos; `/ajuda/` guia; `/staging/` dados antigos; `/cadastros/clientes/` cadastros; `/fechamento/` relatório do mês; `/auditoria/` histórico do administrador. A chave SETUP_KEY habilita a tela de primeiro acesso somente enquanto não existir administrador ativo. Não há senha fixa.

`seed_demo` cria somente cadastros e regras artificiais, sem preços ou CNPJ; é repetível. Na hospedagem, execute pela tela **Como usar**, pelo botão de demonstração. Não carrega dados privados que não estejam presentes localmente.

A tela de entrada em `/accounts/login/` usa o logo principal branco/verde e layout próprio para computador e celular, com usuário, senha e botão mostrar/ocultar. A autenticação continua sendo a do Django, com CSRF e retorno à página solicitada. O link de configuração inicial aparece somente quando a instalação ainda pode criar seu primeiro administrador.

Alternativa em containers: `docker compose up --build`. Migrations executadas pelo serviço web. No ambiente de nuvem com CA de proxy, construa com `docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t gestao-web .`. Preserve proxy/TLS; nunca desative verificações.

Credenciais padrão `teco / dev-only` são exclusivamente para o banco local. Para hospedagem, configure DATABASE_URL, DJANGO_DEBUG=0, DJANGO_SECRET_KEY, SETUP_KEY e hosts. O Render Blueprint usa PostgreSQL externo com TLS verificado e Gunicorn; não cria banco pago. O Compose publica portas apenas em loopback.

## Testes

```sh
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py test -v 2
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py check_restore
```

174 testes passaram sem testes ignorados: [matriz de evidências](docs/ACEITE.md). Restauração de teste exige usuário PostgreSQL autorizado a criar um banco separado e efêmero; jamais substitui a origem. Não é configuração de backup durável da hospedagem.

## Organização e limites

`core/models.py` e migrations: entidades e constraints; `services.py`: planejamento/staging; `workflow.py`: transações de homologação; `pdf.py`: PDFs; `backup.py`: verificação de restauração; `forms.py` e templates: operação guiada. Documento armazenado privadamente no PostgreSQL com hash. Auditoria protegida por trigger contra alteração/exclusão, preservado o papel administrativo do DBA.

[Etapa 1](docs/ETAPA_1.md), [Etapa 2 e pendências](docs/ETAPA_2.md). Ainda pendentes: emissão fiscal própria homologada, MFA, backup durável criptografado/agendado, devoluções parciais, correções pós-fechamento, compartilhamento de clientes com vigências, integração fiscal e teste físico da impressora.

Este repositório é público. As fontes privadas (`reference/`, planilhas, CSVs originais e arquivos de credenciais) ficam fora do versionamento. Nesta tarefa estão no ZIP anexado e em `/workspace/erp-reference`; na hospedagem, carregue CSVs pela área protegida do ERP. Macros VBA não são executadas.


## Evolução gerencial — novembro de 2026

Página inicial com painel, filtros por período/empresa, faturamento e rankings de vendas reais emitidas, vencimentos em atraso e alerta de estoque. Pedidos de teste não entram no faturamento. Após ativar a empresa, pedidos operacionais emitidos alimentam os indicadores comerciais; pedidos de teste ficam fora desses totais.

Produtos permitem cadastrar e alterar o preço padrão diretamente no formulário, sem datas. A ficha do cliente reúne observações, condições negociadas por produto, rotinas, pedidos novos e contas. A aba **Preços** oferece **Alterar preço** em cada condição. O valor entra em uso imediatamente e fica sem prazo de término; trocas no mesmo dia são permitidas e o histórico é registrado automaticamente. Documentos emitidos preservam seus valores. Contas a receber e recebimentos parciais têm registro manual confirmado e auditoria; não há envio automático de cobrança, conciliação bancária ou criação de dívida pela planilha.

Estoque: cadastro de insumos/produtos, mínimo, entradas e saídas justificadas. Não permite saldo negativo, inclusive por retroatividade. Consumo, perdas e saldo inicial são movimentos manuais; não há baixa por ficha técnica automática.

Em **Rotinas de compra → Analisar planilha**, selecione a empresa, o arquivo XLSM/XLSX e o início das novas rotinas. O importador lê apenas abas `D-outubro-AA_MD`; não executa VBA. Cadastra clientes/produtos e rotinas estáveis por dia da semana, preservando observações. **Nunca importa pedidos antigos, preços presumidos ou contas a receber.** Duas vias contam uma vez; divergências, descrições compostas e padrões variáveis são sinalizados. Critério: moda positiva em pelo menos 60% das datas disponíveis daquele dia, mínimo duas ocorrências, sem empate. Datas sem aba não são tratadas como ausência. Reenvio do mesmo arquivo não duplica cadastros. Rotinas já ativas exigem comparação manual antes de substituir.

As abas MD são tratadas como turno noturno; o horário fica pendente (`00:00`) e deve ser conferido na ficha da rotina antes do uso. Quantidades alteradas numa rotina não sobrescrevem pedidos já preparados. Produtos da mesma entrega importada são agrupados num pedido novo por cliente/data/identificação; os agrupamentos respeitam cliente, identificação de entrega, horário e turno, como a automação.

O relatório privado por cliente pode ser gerado sem cadastrar nada:

```sh
.venv/bin/python scripts/analyze_routines.py /caminho/planilha.xlsm --output /caminho/privado
```

Ele gera HTML pesquisável e XLSX sem macros. Grave os relatórios fora do repositório público. A planilha original e dados de clientes nunca devem ser commitados. A migração `0005` adiciona estruturas sem apagar dados existentes. A atualização não limpa pedidos ou exemplos que já estiverem na hospedagem.

Para detalhes de publicação e verificação: [Evolução gerencial](docs/ETAPA_3.md).


### Produção, logística e fechamento aprovado

Em **Produção realizada**, a equipe registra lotes, quantidade produzida, perdas e responsáveis; o sistema compara com o planejado por empresa/produto/unidade e preserva o custo do lote. Produtos mostram custo unitário, valor de venda e lucro/margem brutos estimados.

Em **Rotas e motoristas**, cadastre os responsáveis e a sequência de clientes. **Romaneios e malotes** gera PDFs dos pedidos novos emitidos e separa pagamento informado de dinheiro conferido. Diferenças impedem baixa financeira; contas vinculadas de pedidos reais só recebem baixa após conferência. PIX/cartão são informados e exigem conferência própria. A interface Equipe cria acessos individuais de Produção, Entregas e Financeiro.

**Fechamento de clientes** aceita mês ou período livre, gera PDF preservado de entregas confirmadas, registra envio/aprovação/ressalva e exporta CSV após aprovação. Não envia mensagens, não emite NF-e e não cria dívida automaticamente. O mesmo pedido não entra em dois fechamentos ativos.

[Rotina prática da fábrica](docs/ROTINA_DA_FABRICA.md) descreve responsabilidades e conferências diárias/mensais. As migrations `0005`–`0024` são aditivas e não apagam pedidos da hospedagem. A emissão de NF-e continua no ambiente fiscal externo; a operação gerencial e os comprovantes de entrega são ativados por empresa.


### Notinhas e finalização conforme a automação

Em Pedidos e produção, informe padeiros noturno/diurno e separação, confira os turnos e use **Finalizar dia e gerar PDFs**. Gera as quatro notinhas por A4 (via empresa sem valores e via cliente com valores), identificadas por TECO/NONA, e o PDF geral/noturno/diurno de produção. O IBIS permanece em A4 retrato com etiquetas de 40×60 mm no verso, por escolha do usuário. [Detalhes e limite da conferência física](docs/IMPRESSAO_REFERENCIA.md). A finalização exige CNPJ da emissora; o teste isolado de notinhas continua identificado como homologação. As migrations atuais vão até `0024`.


### Contas a pagar e XML de compras

**Contas a pagar → Importar XML de compra** recebe NF-e 4.00 completa, confere chave/dados e CNPJ destinatário, cadastra o fornecedor e mostra fatura/duplicatas. Após conferência, gera todas as parcelas de forma idempotente. Se faltarem vencimentos, pede as datas; não presume pagamento nem prazo. O XML original permanece privado no PostgreSQL com hash. DTDs/entidades externas são rejeitados. A importação não valida assinatura digital nem consulta a situação atual na SEFAZ.

Pagamentos de fornecedores são registros internos, parciais ou totais, com comprovante/referência, sem movimentação bancária automática. XMLs de homologação geram contas de teste, fora dos totais reais. Há cadastro de despesas sem XML e fornecedores, isolamento por empresa e novo resumo de compromissos no painel.

O objetivo fiscal confirmado pelo usuário é substituir os emissores atuais por este ERP. TECO usa hoje Sistema Imagem e NONA usa Multicomp; a migration `0014` registra essa informação apenas quando o campo da empresa está vazio. **Emissão fiscal própria ainda não está implementada**: não há assinatura de NF-e/NFC-e, transmissão, autorização ou eventos SEFAZ. [Fluxo de compras e transição fiscal](docs/COMPRAS_XML_E_FISCAL.md) define o que está entregue e a próxima etapa. Não há dependência planejada de integrar Imagem ou Multicomp para a futura emissão própria.


### Ordem de compra do cliente

Informe a OC no pedido, antes da emissão, ou no fechamento por período quando a referência chegar apenas no faturamento mensal. As notinhas, romaneios, PDF de fechamento e CSV aprovado preservam a referência. A OC do fechamento preenche apenas pedidos sem OC, sem substituir referências próprias dos pedidos. O cliente pode ser configurado para exigir OC antes de emitir a notinha. Documentos já emitidos não são alterados.


### Propostas comerciais

**Propostas comerciais → Nova proposta** gera PDF A4 seguindo os blocos do DOCX fornecido: destinatário, descrição/investimento, cardápio, total, condições, validade e assinatura. A empresa selecionada determina a marca: NONA usa o novo logo branco/verde; TECO usa o mesmo logo das suas notinhas. Aceita serviços livres e produtos, com preço informado ou vigente, incluindo condição negociada do cliente. Rascunhos permitem adicionar/remover itens; PDFs gerados ficam preservados e alterações posteriores criam uma revisão.

O administrador configura o **Cabeçalho** de cada empresa, manualmente ou importando o DOCX privado. Por escolha do usuário, os dados do novo modelo da NONA são a referência das propostas. Esses dados são configuração privada no banco, e precisam ser carregados na hospedagem após publicar; não são enviados ao GitHub. O cadastro fiscal e documentos anteriores são preservados. Há registro manual de envio, aceite/recusa e perfil de equipe Comercial. Propostas não criam pedidos, contas ou emissão fiscal automaticamente. [Como usar e publicar](docs/PROPOSTAS_COMERCIAIS.md).


### Cadastros durante o pedido

Em **Novo pedido**, selecione a empresa e use **Novo cliente** ao lado do destinatário ou **Novo produto** na linha do item. As caixas oferecem os mesmos dados dos cadastros, incluindo observações do cliente e unidade/custo/preço de venda do produto. Ao salvar, o registro é persistido e selecionado sem recarregar o pedido; horário, quantidades, OC e observações permanecem. É possível adicionar mais linhas e novos produtos durante o lançamento. Cadastros feitos nessas caixas continuam disponíveis mesmo se o pedido ainda não tiver sido salvo. As permissões de administrador para cadastrar clientes/produtos foram mantidas. [Detalhes de preços e primeiro pedido](docs/PEDIDOS_E_PRECOS.md).


### Dias recorrentes e preços no cadastro do cliente

No cadastro do cliente, inclusive na caixa aberta durante o pedido, marque os dias da semana e cadastre preços negociados por produto. No primeiro pedido, **Repetir este pedido nos dias recorrentes do cliente** usa os itens, quantidades, horário e turno como rotina ativa. Também há campo de preço negociado por item do pedido e configuração de produto/quantidade recorrente na ficha do cliente.

Ao abrir **Pedidos e produção** numa data atual ou futura, as novas rotinas automáticas autorizadas entram no planejamento uma única vez. A geração exige a permissão de preparar o dia; registros antigos/importados continuam com preparação manual por padrão. Não há geração retroativa ao consultar datas passadas. Alterar os dias do cliente atualiza suas rotinas automáticas e preserva pedidos já preparados. A migration `0019` adiciona campos com valores vazios/desativados, sem criar pedidos existentes ou alterar preços. [Fluxo detalhado](docs/PEDIDOS_E_PRECOS.md).


### Começar do zero e ativar a operação

**Começar operação** (`/comecar/`) mostra as pendências das empresas e permite ativar os pedidos operacionais após conferência do administrador. A migration `0021` retira da programação as rotinas antigas com preparo manual, preservando as rotinas novas explicitamente confirmadas pelo usuário, cadastros, preços, pedidos e documentos. Há uma ação protegida para retirar também todas as rotinas atuais se o administrador quiser reiniciar. Rotinas retiradas continuam no histórico e não podem ser reativadas pelas telas usuais.

Modo operacional mantém pedidos de teste separados, emite comprovantes de entrega não fiscais, alimenta vendas gerenciais e permite entrega/fechamento/malote. Não habilita transmissão de NF-e/NFC-e nem cobrança bancária automática. A permissão de preparar dias foi incluída no perfil Produção, dentro da empresa do colaborador, sem permissões financeiras.

A data da produção/entrega escolhida acompanha Novo pedido; o horário do lançamento é registrado separadamente. Produção realizada permite registrar o lote feito hoje e relacioná-lo aos pedidos/entregas de amanhã, mantendo a data física correta. Confirmação de entrega operacional futura é bloqueada até a data prevista. [Roteiro completo do primeiro dia](docs/COMECE_HOJE.md).

# Começar hoje com a produção de amanhã

Use o serviço e o banco já existentes no Render/Neon. A atualização retira as rotinas pré-cadastradas da programação e preserva clientes, produtos, preços, pedidos e documentos. A ativação operacional é feita por empresa depois da conferência dos cadastros.

## 1. Publicar a atualização

No Render, abra o serviço `teco-nona-homologacao`, confirme a branch `feat/gestao-rotinas-dashboard` e use **Manual Deploy → Deploy latest commit**. Aguarde **Live**. A inicialização aplica as migrations até `0024`. O nome/endereço do serviço pode continuar o mesmo; a tela identifica a operação ativada no cadastro da empresa.

## 2. Abrir Começar operação

Entre com seu usuário administrador e abra **Começar operação** no menu. A tela mostra as pendências de TECO e NONA separadamente. As rotinas importadas e pré-cadastradas antigas ficam retiradas, com histórico preservado. Rotinas novas explicitamente confirmadas no fluxo do cliente são mantidas. Se quiser retirar também rotinas que você criou para conferência, use **Recomeçar toda a programação novamente**.

## 3. Conferir as empresas

Em **Cadastros → Empresas**, confira os dados próprios de cada emissora: CNPJ, razão social, endereço e telefone. Não use dados de uma empresa na outra. O cabeçalho das propostas é uma configuração separada; confira também o cadastro da empresa usado nas notinhas.

## 4. Produtos, clientes e preços

Em **Produtos**, confira nome e unidade do item (UN, KG, pacote etc.). O catálogo é compartilhado: cadastre cada produto uma vez para usá-lo tanto na TECO quanto na NONA. Isso também vale para novos produtos cadastrados durante o pedido. Preencha custo de produção por unidade e valor de venda padrão, disponível nas duas empresas. Você pode alterar o preço sem informar datas.

Na ficha de cada cliente, confira a empresa, nome/razão social, CPF/CNPJ quando aplicável, endereço de entrega e contato. Marque os dias recorrentes e informe os preços negociados por produto. Os valores do cliente têm prioridade sobre uma condição específica da empresa e sobre o preço padrão do catálogo. A empresa escolhida no pedido determina a marca da notinha e o faturamento. Exigência de OC pode ser marcada no cliente; nesse caso, preencha a referência antes de imprimir.

Para ativar uma empresa, basta ter ao menos um cliente ativo, um produto ativo e um preço para começar. Complete os demais itens conforme lançar seus pedidos; um produto usado sem preço bloqueia a impressão, em vez de presumir um valor.

## 5. Ativar a operação gerencial

Volte a **Começar operação**, confira os itens e use **Ativar operação desta empresa** para TECO e NONA quando estiverem prontas. Novos pedidos passam a ser operacionais e alimentam os indicadores comerciais após a emissão. Pedidos antigos de teste continuam preservados e ficam fora da programação e dos indicadores de vendas operacionais.

As notinhas operacionais são **comprovantes de entrega não fiscais**. A ativação não habilita NF-e/NFC-e pelo ERP. Continue emitindo NF-e no Sistema Imagem para TECO e na Multicomp para NONA até a implantação da emissão própria.

## 6. Lançar hoje os pedidos de amanhã

Na tela **Começar operação**, use **Lançar pedido para amanhã**. Também pode abrir **Pedidos e produção**, escolher amanhã e clicar em **Novo pedido**. A data selecionada acompanha o formulário.

Preencha cliente, produtos, quantidades, horário e turno. Se produzir hoje à noite para entregar amanhã cedo, a data da entrega/pedido é amanhã. O horário em que você cadastrou fica registrado separadamente como data de lançamento.

Use **Novo cliente** e **Novo produto** nas caixas, quando precisar. Você também pode informar o preço específico do cliente na linha do pedido. No primeiro pedido, confira **Repetir este pedido** somente se esses produtos e quantidades forem o padrão nos dias marcados. Ao abrir uma próxima data marcada, os pedidos entram automaticamente no planejamento; consultar a mesma data novamente não duplica nem desfaz ajustes.

## 7. Conferir e imprimir

Abra a produção de amanhã, confira produtos/quantidades por turno e informe padeiros e separação. Salve os responsáveis, use **Conferir produção** e depois **Finalizar dia e gerar PDFs**. Abra o PDF de notinhas e o planejamento geral/noturno/diurno.

Imprima em A4, tamanho real/100%. Notinhas comuns usam quatro blocos por folha; IBIS usa retrato, notinha na frente e etiquetas no verso. Confira a primeira folha na impressora antes do restante.

## 8. Registrar o que foi realmente produzido

Em **Produção realizada**, informe a data em que o lote foi efetivamente produzido. Em **Produção para os pedidos / entregas de**, informe a data da programação correspondente.

Exemplo: lote produzido hoje à noite, destinado às entregas de amanhã. Data produzida = hoje; data dos pedidos/entregas = amanhã. A comparação de amanhã mostrará esse lote junto dos pedidos corretos. Informe total produzido, perdas, responsável e motivo. O planejamento e a impressão não lançam produção realizada automaticamente.

## 9. Entregas e dinheiro

Cadastre motoristas/rotas e a sequência de clientes. Depois de emitir as notinhas, gere o romaneio. Registre a entrega com evidência somente na data prevista ou depois. Registre o dinheiro informado por cliente e confira o malote no retorno. Divergência impede baixa financeira; PIX/cartão precisam de conferência própria.

Em **Contas a receber**, registre valores/vencimentos confirmados e os recebimentos. A notinha não cria uma dívida automaticamente. Contas a pagar podem ser digitadas ou criadas a partir de XML de compra conferido. Verifique diariamente atrasos e compromissos no painel.

## 10. Fechamento e rotina da equipe

No período combinado, gere o fechamento do cliente com as entregas confirmadas, envie o PDF e registre a aprovação recebida. O CSV aprovado apoia a emissão no sistema fiscal atual.

Crie um acesso individual por colaborador. O perfil Produção prepara os próprios dias e registra lotes, sem permissão financeira. Confira no painel do Neon a recuperação disponível no plano e mantenha uma rotina de cópia do banco/documentos.

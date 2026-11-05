# Preços e cadastros durante o pedido

## Catálogo compartilhado TECO e NONA

Cadastre cada produto apenas uma vez. Todos os produtos existentes e novos das duas marcas ficam disponíveis para pedidos, rotinas, preços do cliente, produção realizada e propostas de ambas. A empresa do pedido/proposta determina a marca e os dados do documento; a origem do cadastro do produto não muda a empresa da venda. Clientes, pedidos e financeiro mantêm seu vínculo e as permissões por empresa.

O preço padrão informado no produto é compartilhado. Na aba Preços, uma condição padrão da outra empresa pode substituir esse valor para suas vendas; condições aparecem identificadas na tabela. Selecionar a empresa do cadastro atualiza o próprio padrão do catálogo. A prioridade é: valor negociado do cliente, condição padrão da empresa da venda e padrão do catálogo. Cada condição mantém seu histórico.

## Alterar o preço sem datas

Em **Produtos**, abra o item, altere o valor de venda e salve. O preço atual aparece preenchido. Deixar o valor em branco mantém o preço já cadastrado. Também é possível abrir a aba **Preços**, clicar em **Alterar preço** e informar apenas o novo valor.

Na ficha do cliente, escolha o produto e informe o valor negociado. Essa condição tem prioridade sobre o preço padrão para aquele cliente; a alteração do preço padrão não muda suas condições particulares.

Não há data de início/fim no cadastro de preços. O novo valor entra em uso na data da alteração e fica sem prazo de término, até ser alterado novamente. É possível fazer várias trocas no mesmo dia. Ao trocar uma condição, cadastros futuros anteriores daquela mesma empresa/produto/cliente são marcados como substituídos, preservando os dados e evitando que revertam a alteração depois.

O histórico é automático. Valores de dias anteriores ficam disponíveis para consulta; trocas no mesmo dia ficam preservadas como versões substituídas, com auditoria de autor e horário. Documentos, propostas, pedidos emitidos e fechamentos mantêm seus valores congelados. Reimprimir não recalcula preços. A mudança não reprecifica documentos já emitidos nem altera as condições negociadas de outros clientes ou as condições específicas de outras empresas. A alteração do padrão do catálogo vale para as duas marcas quando não existe uma condição mais específica.

## Cadastrar enquanto lança o pedido

1. Abra **Novo pedido** e escolha a empresa.
2. Ao lado de Cliente, clique em **Novo cliente**. Complete os dados e salve. O cliente é cadastrado e selecionado automaticamente.
3. Na linha do produto, clique em **Novo produto**. Informe nome, unidade, custo de produção e preço padrão de venda; salve para selecionar o novo produto na linha.
4. Informe a quantidade. Use **Adicionar item** para novas linhas e repita o cadastro quando necessário.
5. Confira OC, data, horário, responsáveis e observações, e salve o pedido.

As caixas mantêm a empresa escolhida no pedido. Cancelar a caixa preserva o que já estava digitado no pedido. Salvar um cadastro não recarrega a página e mantém os outros campos/itens. Cliente/produto salvo já fica disponível no catálogo mesmo se o pedido ainda estiver sendo preenchido. Erros aparecem dentro da própria caixa para correção. O botão fica bloqueado durante o salvamento, e uma repetição da mesma solicitação é idempotente no servidor.

As permissões existentes de cadastro são mantidas: somente administrador cria clientes/produtos e altera preços. A criação pelo pedido usa os mesmos formulários, validações e registro de auditoria dos cadastros.

## Publicação e validação

O comando de inicialização deve aplicar a migration `0024`; o build deve executar `collectstatic` para publicar o estilo e o JavaScript das caixas. Os comandos já estão em `render.yaml`. A migração não apaga preços, pedidos ou documentos e não altera valores existentes por conta própria.

185 testes PostgreSQL no conjunto completo, incluindo oito cenários de preço, seis de cadastro durante o pedido e 11 de catálogo compartilhado. Cobertura de versões no mesmo dia, preços anteriores/futuros, condição negociada, custo/valor zero, dados inválidos, isolamento/permissões, CSRF, idempotência e preservação de notinha, proposta e fechamento. No navegador foram feitos cliente e produto novos, validação/correção, seleção automática, alteração repetida de preço e salvamento de pedido com seus dados preservados, em banco separado de exemplos. As telas e as caixas também foram conferidas no celular.


## Dias e preços ao cadastrar o cliente

No cadastro comum ou na caixa **Novo cliente**, marque segunda a domingo em **Dias recorrentes de pedido**. No bloco **Preços negociados deste cliente**, selecione produto e valor; use **Outro preço por produto** para mais condições. Linhas vazias usam o preço padrão. A validação impede preços duplicados por produto ou produtos indisponíveis para a empresa, e erro em um preço não deixa um cadastro parcial.

Os dias são uma preferência salva; os produtos e as quantidades precisam ser definidos para compor a produção. Ao lançar o primeiro pedido desse cliente, a opção **Repetir este pedido** vem marcada ao selecionar o cliente com dias e ainda sem rotina. Confira produtos, quantidades, horário e turno e salve. A rotina começa na data desse pedido, sem retroagir antes de hoje. Se for um pedido avulso, desmarque a repetição. Preços informados por item ficam cadastrados para aquele cliente, sem alterar o padrão dos demais.

Ao abrir **Pedidos e produção** numa data atual/futura, o sistema prepara automaticamente as rotinas confirmadas para aquele dia, desde que o acesso tenha permissão de preparar produção. O primeiro pedido já lançado é reconhecido e não é duplicado. Abrir novamente a mesma data preserva pedidos e ajustes. Datas passadas e rotinas importadas continuam dependendo do preparo manual existente; a atualização não importa pedidos antigos nem ativa o legado.

Na ficha do cliente, o bloco **Dias recorrentes e pedido habitual** permite adicionar produto, quantidade, preço opcional, horário e turno. Alterar os dias em **Editar cadastro** atualiza as rotinas automáticas. Desmarcar todos os dias interrompe novos preparos; pedidos já preparados permanecem para conferência/ajuste. Uma rotina suspensa individualmente continua suspensa ao alterar os dias. Não há emissão automática, cobrança ou confirmação de produção realizada por marcar os dias.


## Ativar o uso e preparar amanhã hoje

Use [Começar hoje](COMECE_HOJE.md) e a tela Começar operação para conferir cadastros e ativar cada empresa. As rotinas antigas foram retiradas da programação na migration `0021`; novos pedidos recorrentes são configurados individualmente. Depois da ativação, novos pedidos são operacionais, com comprovantes não fiscais.

Ao abrir a produção de amanhã e clicar em Novo pedido, a data escolhida acompanha o formulário. O lançamento de hoje e a entrega de amanhã ficam separados. Em Produção realizada, data física = quando o lote foi produzido; campo de pedidos/entregas = data da programação correspondente.


Catálogo compartilhado conferido no navegador: produto criado pela TECO selecionado em pedido operacional da NONA, preço do cliente salvo, produto disponível também na caixa de preços do novo cliente, documento emitido com identidade NONA e tela sem transbordamento em 390 px. Dados artificiais somente no banco separado de demonstração. A base principal permanece com 46 clientes, 20 produtos (os mesmos 20 disponíveis para cada marca), zero pedidos e zero rotinas ativas.

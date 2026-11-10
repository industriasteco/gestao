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

O comando de inicialização deve aplicar as migrations até `0025`; o build deve executar `collectstatic` para publicar o estilo e o JavaScript das caixas. Os comandos já estão em `render.yaml`. A migração não apaga preços, pedidos ou documentos e não altera valores existentes por conta própria.

185 testes PostgreSQL no conjunto completo, incluindo oito cenários de preço, seis de cadastro durante o pedido e 11 de catálogo compartilhado. Cobertura de versões no mesmo dia, preços anteriores/futuros, condição negociada, custo/valor zero, dados inválidos, isolamento/permissões, CSRF, idempotência e preservação de notinha, proposta e fechamento. No navegador foram feitos cliente e produto novos, validação/correção, seleção automática, alteração repetida de preço e salvamento de pedido com seus dados preservados, em banco separado de exemplos. As telas e as caixas também foram conferidas no celular.


## Dias e preços ao cadastrar o cliente

No cadastro comum ou na caixa **Novo cliente**, marque segunda a domingo em **Dias recorrentes de pedido**. No bloco **Preços negociados deste cliente**, selecione produto e valor; use **Outro preço por produto** para mais condições. Linhas vazias usam o preço padrão. A validação impede preços duplicados por produto ou produtos indisponíveis para a empresa, e erro em um preço não deixa um cadastro parcial.

Os dias são uma preferência salva; os produtos e as quantidades precisam ser definidos para compor a produção. Ao lançar o primeiro pedido desse cliente, a opção **Repetir este pedido** vem marcada ao selecionar o cliente com dias e ainda sem rotina. Confira produtos, quantidades, horário e turno e salve. A rotina começa na data desse pedido, sem retroagir antes de hoje. Se for um pedido avulso, desmarque a repetição. Preços informados por item ficam cadastrados para aquele cliente, sem alterar o padrão dos demais.

Ao abrir **Pedidos e produção** numa data atual/futura, o sistema prepara automaticamente as rotinas confirmadas para aquele dia, desde que o acesso tenha permissão de preparar produção. O primeiro pedido já lançado é reconhecido e não é duplicado. Abrir novamente a mesma data preserva pedidos e ajustes. Datas passadas e rotinas importadas continuam dependendo do preparo manual existente; a atualização não importa pedidos antigos nem ativa o legado.

Na ficha do cliente, o bloco **Dias recorrentes e pedido habitual → Definir produto, quantidade e dias** permite escolher os dias de cada produto, além da quantidade, preço opcional, horário e turno. Exemplo: salve 60 pães para segunda, quarta e sexta; depois salve 250 de outro produto somente para sexta. Use a mesma identificação da entrega, horário e turno para que os dois produtos componham um único pedido na sexta. Segunda e quarta terão apenas os 60 pães.

Também é possível usar quantidades diferentes do mesmo produto em dias distintos: salve a quantidade e marque os dias correspondentes. Salvar novamente o mesmo produto na mesma entrega define a nova quantidade apenas nos dias selecionados, sem somá-la ao cadastro anterior. Os outros dias e produtos são preservados. Na tabela **Rotina de compra por produto e dia**, use **Editar dias e quantidade** para ajustar uma linha existente ou suspender a rotina. O preço opcional continua sendo uma condição do produto para o cliente, válida em todos os dias.

As rotinas configuradas dessa forma têm dias próprios. Alterar os dias gerais em **Editar cadastro** atualiza somente as rotinas que acompanham esses dias (como as criadas por **Repetir este pedido**), preservando as de dias próprios. Desmarcar todos os dias gerais interrompe apenas as rotinas que os acompanham. Ao alterar os dias diretamente em **Editar dias e quantidade**, a linha passa a usar dias próprios. Uma rotina suspensa continua suspensa ao alterar os dias gerais.

A migration `0025` acrescenta essa distinção mantendo o comportamento das rotinas existentes. Não apaga cadastros nem altera quantidades ou dias já salvos. Pedidos já preparados, seus ajustes e documentos são preservados; mudanças na rotina valem para os próximos preparos. Não há emissão automática, cobrança ou confirmação de produção realizada por marcar os dias.

Validação desta alteração: 193 testes PostgreSQL aprovados, incluindo o exemplo de 60 + 250 na sexta, quantidades diferentes do mesmo produto, reenvio sem duplicação, preservação de pedidos preparados, dias inválidos e permissões.


## Ativar o uso e preparar amanhã hoje

Use [Começar hoje](COMECE_HOJE.md) e a tela Começar operação para conferir cadastros e ativar cada empresa. As rotinas antigas foram retiradas da programação na migration `0021`; novos pedidos recorrentes são configurados individualmente. Depois da ativação, novos pedidos são operacionais, com comprovantes não fiscais.

Ao abrir a produção de amanhã e clicar em Novo pedido, a data escolhida acompanha o formulário. O lançamento de hoje e a entrega de amanhã ficam separados. Em Produção realizada, data física = quando o lote foi produzido; campo de pedidos/entregas = data da programação correspondente.


Catálogo compartilhado conferido no navegador: produto criado pela TECO selecionado em pedido operacional da NONA, preço do cliente salvo, produto disponível também na caixa de preços do novo cliente, documento emitido com identidade NONA e tela sem transbordamento em 390 px. Dados artificiais somente no banco separado de demonstração. A base principal permanece com 46 clientes, 20 produtos (os mesmos 20 disponíveis para cada marca), zero pedidos e zero rotinas ativas.

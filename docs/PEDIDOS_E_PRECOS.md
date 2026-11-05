# Preços e cadastros durante o pedido

## Alterar o preço sem datas

Em **Produtos**, abra o item, altere o valor de venda e salve. O preço atual aparece preenchido. Deixar o valor em branco mantém o preço já cadastrado. Também é possível abrir a aba **Preços**, clicar em **Alterar preço** e informar apenas o novo valor.

Na ficha do cliente, escolha o produto e informe o valor negociado. Essa condição tem prioridade sobre o preço padrão para aquele cliente; a alteração do preço padrão não muda suas condições particulares.

Não há data de início/fim no cadastro de preços. O novo valor entra em uso na data da alteração e fica sem prazo de término, até ser alterado novamente. É possível fazer várias trocas no mesmo dia. Ao trocar uma condição, cadastros futuros anteriores daquela mesma empresa/produto/cliente são marcados como substituídos, preservando os dados e evitando que revertam a alteração depois.

O histórico é automático. Valores de dias anteriores ficam disponíveis para consulta; trocas no mesmo dia ficam preservadas como versões substituídas, com auditoria de autor e horário. Documentos, propostas, pedidos emitidos e fechamentos mantêm seus valores congelados. Reimprimir não recalcula preços. A mudança não reprecifica documentos já emitidos nem altera preços de outros clientes ou empresas.

## Cadastrar enquanto lança o pedido

1. Abra **Novo pedido** e escolha a empresa.
2. Ao lado de Cliente, clique em **Novo cliente**. Complete os dados e salve. O cliente é cadastrado e selecionado automaticamente.
3. Na linha do produto, clique em **Novo produto**. Informe nome, unidade, custo de produção e preço padrão de venda; salve para selecionar o novo produto na linha.
4. Informe a quantidade. Use **Adicionar item** para novas linhas e repita o cadastro quando necessário.
5. Confira OC, data, horário, responsáveis e observações, e salve o pedido.

As caixas mantêm a empresa escolhida no pedido. Cancelar a caixa preserva o que já estava digitado no pedido. Salvar um cadastro não recarrega a página e mantém os outros campos/itens. Cliente/produto salvo já fica disponível no catálogo mesmo se o pedido ainda estiver sendo preenchido. Erros aparecem dentro da própria caixa para correção. O botão fica bloqueado durante o salvamento, e uma repetição da mesma solicitação é idempotente no servidor.

As permissões existentes de cadastro são mantidas: somente administrador cria clientes/produtos e altera preços. A criação pelo pedido usa os mesmos formulários, validações e registro de auditoria dos cadastros.

## Publicação e validação

O comando de inicialização deve aplicar a migration `0018`; o build deve executar `collectstatic` para publicar o estilo e o JavaScript das caixas. Os comandos já estão em `render.yaml`. A migração não apaga preços, pedidos ou documentos e não altera valores existentes por conta própria.

149 testes PostgreSQL no conjunto completo, incluindo oito cenários de preço e seis de cadastro durante o pedido. Cobertura de versões no mesmo dia, preços anteriores/futuros, condição negociada, custo/valor zero, dados inválidos, isolamento/permissões, CSRF, idempotência e preservação de notinha, proposta e fechamento. No navegador foram feitos cliente e produto novos, validação/correção, seleção automática, alteração repetida de preço e salvamento de pedido com seus dados preservados, em banco separado de exemplos. As telas e as caixas também foram conferidas no celular.

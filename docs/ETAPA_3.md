# Evolução gerencial e rotinas de compra

O cliente inicia seus pedidos do zero. A planilha é usada apenas para reconhecer comportamento de compra, preservar observações e preparar cadastros/rotinas. Não existe importação de pedidos históricos, faturamento ou inadimplência presumida.

## Entrega

Painel gerencial responsivo, ficha do cliente, preços padrão no produto, preços negociados com vigência, contas a receber/recebimentos parciais e estoque por movimentos. Roteiro de navegação em português, estados vazios explícitos e atalhos da gestão para produção.

As 26 abas disponíveis de outubro de 2026 trazem 46 nomes de clientes e 20 descrições de produto utilizáveis após normalização conservadora. Faltam 22–26/10. A análise encontrou 145 combinações estáveis de cliente/produto/dia e 156 padrões variáveis. Não são 145 clientes. Há 39 ocorrências de leitura a conferir, incluindo cliente vazio, descrições compostas/ausentes e divergência entre vias. Nomes e detalhes privados ficam fora deste documento e do GitHub.

O teste local da planilha real cadastrou apenas cadastros/rotinas, com **0 pedidos e 0 contas a receber**. Esse banco é separado do banco hospedado. A interface permite repetir a preparação na hospedagem com o arquivo original, sem duplicação pelo hash.

## Validação

57 testes PostgreSQL passaram: 42 anteriores e 15 novos, sem ignorados. Cobertura nova: importação sem pedidos/contas, idempotência, moda por dia, lacunas, agrupamento dos itens por cliente, preservação de ajustes, preços negociados e histórico, recebimentos parciais, sobrepagamento, datas futuras, estoque negativo/retroativo, isolamento por empresa, painel sem faturamento de teste, rotas e divergência entre vias. `check`, migrations sem alterações pendentes e `diff --check` aprovados.

## Publicar em homologação

1. Publicar o código revisado na branch usada pelo serviço Render.
2. O comando atual de inicialização do Render aplica migrations antes do Gunicorn; confirmar conclusão de `0005` no deploy.
3. Acessar o sistema com a conta existente. A página inicial abre o painel; `/?date=AAAA-MM-DD` mantém compatibilidade com a produção diária.
4. Em Produtos, cadastrar preços confirmados. Na ficha do cliente, definir exceções negociadas.
5. Em Rotinas, analisar a planilha original, selecionar TECO e a data de início futura. Confirmar que a ação cadastra somente clientes/produtos/rotinas.
6. Conferir horários, observações e itens ambíguos. Preparar uma nova data apenas quando desejar criar os novos pedidos.

A migração é aditiva. Não apaga pedidos já existentes na hospedagem e não altera preços existentes. Os dados privados não são enviados ao GitHub. Não compartilhar chaves do Render, banco ou senhas pelo chat.

## Limites operacionais

O fluxo comercial existente continua em homologação, sem cobrança real. A autorização para vendas reais exige uma etapa própria; os novos painéis não substituem essa validação. Faturamento/rankings consideram apenas pedidos reais emitidos com preço congelado, excluindo testes; contas a receber são registros manuais confirmados e independentes dos pedidos nesta versão. Estoque não tem ficha técnica nem baixa automática. Integração fiscal, conciliação bancária, backup durável agendado e MFA continuam pendentes.

# Evolução gerencial e rotinas de compra

O cliente inicia seus pedidos do zero. A planilha é usada apenas para reconhecer comportamento de compra, preservar observações e preparar cadastros/rotinas. Não existe importação de pedidos históricos, faturamento ou inadimplência presumida.

## Entrega

Painel gerencial responsivo, ficha do cliente, preços padrão no produto, preços negociados com vigência, contas a receber/recebimentos parciais e estoque por movimentos. Roteiro de navegação em português, estados vazios explícitos e atalhos da gestão para produção.

As 26 abas disponíveis de outubro de 2026 trazem 46 nomes de clientes e 20 descrições de produto utilizáveis após normalização conservadora. Faltam 22–26/10. A análise encontrou 145 combinações estáveis de cliente/produto/dia e 156 padrões variáveis. Não são 145 clientes. Há 39 ocorrências de leitura a conferir, incluindo cliente vazio, descrições compostas/ausentes e divergência entre vias. Nomes e detalhes privados ficam fora deste documento e do GitHub.

O teste local da planilha real cadastrou apenas cadastros/rotinas, com **0 pedidos e 0 contas a receber**. Esse banco é separado do banco hospedado. A interface permite repetir a preparação na hospedagem com o arquivo original, sem duplicação pelo hash.

## Validação

109 testes PostgreSQL passaram: 42 anteriores e 67 novos, sem ignorados. Cobertura nova: importação sem pedidos/contas, idempotência, moda por dia, lacunas, agrupamento dos itens por cliente, preservação de ajustes, preços negociados e histórico, recebimentos parciais, sobrepagamento, datas futuras, estoque negativo/retroativo, isolamento por empresa, painel sem faturamento de teste, rotas e divergência entre vias. `check`, migrations sem alterações pendentes e `diff --check` aprovados.

## Publicar em homologação

1. Publicar o código revisado na branch usada pelo serviço Render.
2. O comando atual de inicialização do Render aplica migrations antes do Gunicorn; confirmar conclusão das migrations até `0019` no deploy.
3. Acessar o sistema com a conta existente. A página inicial abre o painel; `/?date=AAAA-MM-DD` mantém compatibilidade com a produção diária.
4. Em Produtos, cadastrar preços confirmados. Na ficha do cliente, definir exceções negociadas.
5. Em Rotinas, analisar a planilha original, selecionar TECO e a data de início futura. Confirmar que a ação cadastra somente clientes/produtos/rotinas.
6. Conferir horários, observações e itens ambíguos. Preparar uma nova data apenas quando desejar criar os novos pedidos.

As migrations são aditivas. Não apaga pedidos já existentes na hospedagem e não altera preços existentes. Os dados privados não são enviados ao GitHub. Não compartilhar chaves do Render, banco ou senhas pelo chat.

## Limites operacionais

O fluxo comercial existente continua em homologação, sem cobrança real. A autorização para vendas reais exige uma etapa própria; os novos painéis não substituem essa validação. Faturamento/rankings consideram apenas pedidos reais emitidos com preço congelado, excluindo testes; contas a receber são registros manuais confirmados e independentes dos pedidos nesta versão. Estoque não tem ficha técnica nem baixa automática. Integração fiscal, conciliação bancária, backup durável agendado e MFA continuam pendentes.


## Ampliação operacional

Lotes de produção realizada, perdas, responsável e custo preservado; comparação com o planejado por empresa/produto/unidade. Custo, venda e margem bruta na ficha do produto. Rotas, motoristas, paradas e romaneios PDF preservados, com retorno por cliente. Malotes com valor declarado versus contado e registro de diferenças. Nenhuma conta baixa quando há divergência, pedido de teste ou ausência de vínculo financeiro.

Perfis individuais em Equipe: Produção registra os lotes; Entregas relata a rota sem conferir malote; Financeiro registra contas, confere malotes e faz fechamento. Senhas não entram em auditoria. O fechamento por cliente usa período livre, entregas confirmadas e preços congelados; PDF preservado, envio registrado manualmente, aprovação com evidência e CSV de apoio ao ambiente fiscal. Correções após aprovação e emissão fiscal integrada permanecem fora desta etapa.

Os 24 testes operacionais adicionais cobrem produção/custos/perdas, comparação, romaneios idempotentes e snapshots, uma rota por pedido, dinheiro informado versus conferido, divergências, PIX sem caixa fictício, PDFs, perfis, fechamento por período, duplicidade, aprovação, exportação e proteção do pedido incluído no fechamento.


## Fluxo da automação e notinhas

[Referência de impressão](IMPRESSAO_REFERENCIA.md) registra o fluxo conferido no XLSM e a escolha expressa do usuário pelo IBIS retrato frente/verso. Finalizar dia agrupa os pedidos emitidos num PDF com TECO/NONA e gera outro com produção geral/noturna/diurna. Endereço/telefone/e-mail da emissora e responsáveis ficam preservados na emissão. Arquivos mistos exigem acesso a todas as empresas. Quantidade zero fica fora; dados incompletos revertem o lote.

A suite final tem **89 testes**, sem ignorados. Os oito testes adicionais desta etapa verificam agrupamento manual conforme a automação, finalização multimarcas, escopo do PDF, falha atômica, pré-requisitos, quantidade zero/responsáveis, paginação/totais por parte e carregamento apenas dos dados das emissoras. Após o ajuste final da grade, 18 testes de impressão/fechamento foram repetidos com sucesso. As 13 telas principais foram abertas em navegador no tamanho de celular, sem erro HTTP, JavaScript ou transbordamento horizontal. A impressão física permanece sujeita à conferência das amostras.


## Contas a pagar / XML e objetivo fiscal próprio

[Fluxo de compras e transição fiscal](COMPRAS_XML_E_FISCAL.md). Leitura segura de NF-e 4.00 recebida, fornecedor, fatura/duplicatas e conferência antes de gerar contas. Parcelas sem datas exigem programação manual; valores e datas existentes no XML são preservados. Pagamentos parciais, cancelamento interno de contas sem pagamentos, arquivo XML privado com hash, isolamento por empresa e separação entre ambiente de teste/produção.

O usuário confirmou o objetivo de substituir Imagem/Multicomp por um ERP fiscal único, posteriormente. A emissão própria e sua homologação ainda são uma etapa futura. Cadastro atual: TECO / Sistema Imagem; NONA / Multicomp. Esses dados são informativos e não configuram conexões.

**109 testes aprovados**, sem ignorados, incluindo 20 novos de importação, duplicidade, XML inseguro, totais/vencimentos, destinatário, pagamento parcial, permissões, telas e cadastro de empresa. Fluxo navegador com XML artificial: upload → conferência → geração de duas parcelas → pagamento parcial → consulta de saldo, também no celular. Nenhuma nota real nem pagamento bancário foi criado nos testes. A nova marca da NONA nas notinhas também passou nos nove testes de impressão executados nesta etapa.


## Ordem de compra do cliente

Campo de número/referência da OC no pedido e no fechamento por período. Preservado no snapshot da emissão, notinhas comuns/IBIS, romaneio, PDFs de fechamento e exportação CSV. OC comum do fechamento preenche somente referências ausentes nos pedidos; dados previamente emitidos são preservados. Exigência antes da emissão configurável por cliente. A suite passou para **118 testes**, com nove novos cenários de OC, emissão, congelamento, fechamento e exportação.

## Propostas comerciais

[Fluxo e publicação](PROPOSTAS_COMERCIAIS.md). Cadastro de propostas/serviços, PDF A4 baseado no DOCX, marca por empresa, cabeçalhos privados separados, preços negociados, revisão e resposta manual. O usuário confirmou os dados do novo modelo para o cabeçalho das propostas da NONA. Nenhum pedido ou cobrança é criado por proposta. Migration `0017` aditiva; perfil Comercial na equipe. **135 testes** na suite completa, incluindo 17 cenários de propostas, sem ignorados.

## Preços sem datas e cadastros no pedido

[Fluxo de lançamento](PEDIDOS_E_PRECOS.md). Troca direta do preço padrão ou negociado, sem datas no formulário e sem bloqueio por alteração anterior no mesmo dia. Histórico automático, preços futuros anteriores substituídos apenas para a condição editada e documentos emitidos preservados. Migration `0018` adiciona a marca de substituição sem apagar preços existentes. Novo cliente/produto em caixas dentro do pedido, com seleção automática e preservação do rascunho; repetição da mesma solicitação não duplica cadastros. **149 testes**, incluindo oito cenários de preço e seis de cadastro durante o pedido, sem ignorados.


## Dias recorrentes e preços no cliente

Cadastro de segunda a domingo com caixas de seleção, preços negociados por produto no mesmo formulário e no cadastro rápido. O primeiro pedido pode definir a rotina semanal; preços específicos também podem ser informados nas linhas do pedido. A ficha do cliente permite incluir produtos/quantidades recorrentes e sincroniza mudanças dos dias nas rotinas automáticas.

As novas rotinas autorizadas são preparadas quando um usuário com permissão abre a produção de uma data atual/futura. A operação é idempotente, respeita dias selecionados, início, suspensão e escopo da empresa, e mantém pedidos já preparados e ajustados. Não emite PDFs nem registra produção realizada por conta própria. As rotinas legadas não recebem essa ativação pela migration `0019`. **158 testes** no conjunto completo, incluindo nove novos cenários de configuração, preços, datas, permissões e preservação.

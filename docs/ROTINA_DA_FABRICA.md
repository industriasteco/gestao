# Rotina de gestão da fábrica

O objetivo é ter uma pessoa responsável por cada registro e um horário para conferir exceções. O gerente acompanha os desvios, em vez de refazer o trabalho da equipe.

## Antes de começar

1. Revise os clientes e produtos reconhecidos na planilha. Confirme horários, embalagens, instruções e quantidades variáveis. Não há pedidos de outubro importados.
2. Cadastre custo unitário e preço padrão em Produtos. Inclua no custo informado os componentes que deseja considerar: ingredientes, embalagem, mão de obra e energia. O sistema mostra lucro bruto estimado, não lucro líquido contábil.
3. Ao cadastrar o cliente, complete endereço, contato e CPF/CNPJ confirmado, marque os dias recorrentes e registre os preços especiais por produto. Informe apenas o valor, sem datas de vigência. No primeiro pedido, use Repetir este pedido para definir os produtos/quantidades da rotina.
4. Em Estoque, cadastre insumos, unidade e mínimo. Registre a contagem inicial como entrada. O saldo depende dos movimentos lançados, não das quantidades planejadas.
5. Cadastre motoristas, veículos e rotas. Adicione os clientes na ordem de entrega e suas instruções.
6. Em Equipe, crie uma conta individual por pessoa, com empresa e perfil. Não compartilhe a conta do administrador.

## Antes de cada turno

Nos primeiros pedidos, use **Novo pedido → Novo cliente** e **Novo produto** para cadastrar sem sair do lançamento. Ao salvar a caixa, o cliente/produto já fica cadastrado e selecionado; os dados digitados no pedido são mantidos. O novo produto permite informar unidade, custo e valor de venda. Se precisar trocar um valor, abra **Produtos** ou **Preços → Alterar preço**: o valor permanece ativo até a próxima alteração, inclusive com várias trocas no mesmo dia. O histórico é automático e documentos emitidos mantêm os valores originais.

Ao abrir a produção de uma data atual/futura com o acesso autorizado a preparar o dia, os novos pedidos recorrentes são preparados automaticamente conforme os dias marcados. O responsável confere as mudanças solicitadas pelos clientes; o botão Preparar dia continua disponível para as rotinas manuais existentes. Preparar novamente não duplica pedidos nem desfaz ajustes. O planejamento mostra a quantidade por produto e turno. Produtos, unidades ou instruções pendentes precisam ser esclarecidos antes de produzir.

O padeiro consulta o planejamento. A equipe registra cada lote ou fechamento de turno: produto, quantidade total produzida, quantidade perdida, responsável e motivo das perdas. A quantidade útil é o total menos as perdas. A comparação por empresa/produto evidencia falta ou excedente.

Se produziu hoje para entregar amanhã, registre a data física de hoje e a data de pedidos/entregas de amanhã no lote. A comparação usa a programação correspondente.

O custo da produção é preservado no lote. Alterar o custo do produto depois não muda esse registro. Sem custo cadastrado, a perda aparece em quantidade, mas fica fora do total monetário de perdas conhecidas.

## Na saída das entregas

Informe os padeiros de cada turno e o responsável pela separação. Confira a produção e use Finalizar dia para gerar o PDF único das notinhas e o PDF com produção geral/noturna/diurna. As notinhas usam a empresa vinculada ao cliente: TECO ou NONA. Pedidos com quantidade zero não são emitidos. No IBIS, imprima A4 retrato, notinha na frente e etiquetas no verso, tamanho real/100%.

Depois de ativar a empresa, confira os pedidos e emita os comprovantes de entrega não fiscais. Gere o romaneio da rota/data e imprima o PDF. O documento mantém a sequência de clientes, endereço, produtos, instruções e valores conhecidos. Um pedido não pode pertencer a dois romaneios.

O romaneio preserva o conteúdo da saída. Se a operação mudar depois, revise o documento antes de entregar; o sistema não substitui silenciosamente o que foi impresso.

## No retorno do motorista

O perfil Entregas registra, para cada cliente, se entregou, como o pagamento foi informado, o dinheiro recebido e a observação/comprovante. Quem não pagou deve ser registrado com zero e a observação. PIX e cartão são relatos sujeitos à conferência bancária, não dinheiro no malote.

O Financeiro conta o malote e registra o número, o total contado e qualquer diferença. O sistema compara com o dinheiro informado pelo motorista. Se houver diferença, exige explicação e não baixa contas. A reconferência preserva auditoria. Depois de conferido, o malote e os relatos ficam protegidos contra substituição por esta interface.

Só há baixa financeira quando a conta foi vinculada ao cliente correto, o pedido é real e o malote confere. Pedidos de teste nunca baixam contas reais. Dinheiro conferido sem conta vinculada permanece sinalizado para acompanhamento.

## No fim do dia

O gerente consulta a produção realizada, falta/excedente, perdas e motivos. Confere malotes pendentes/divergentes e insumos no mínimo. O Financeiro registra contas e recebimentos confirmados. A inadimplência vem dos vencimentos e saldos, nunca de estimativa da planilha.

A rotina recomendada é uma conferência curta antes de liberar o turno e outra no retorno dos motoristas. Defina os horários conforme a operação real e atribua um responsável substituto para cada registro.

## No último dia do mês ou no período combinado

1. Abra Fechamento de clientes e selecione empresa, cliente, início e fim.
2. Consulte as entregas. Só entram pedidos emitidos com entrega confirmada e preços preservados.
3. Gere o demonstrativo e baixe o PDF. Envie você mesmo pelo e-mail ou WhatsApp combinado.
4. Registre o envio e aguarde a resposta. Registre aprovação apenas com evidência recebida do cliente. Se houver ressalva, registre o pedido de revisão.
5. Após a aprovação, exporte os itens em CSV para apoiar a emissão no ambiente fiscal. Verifique dados tributários e valores no sistema fiscal. O ERP não emite NF-e nesta versão.

O demonstrativo é o total fornecido, não uma nova dívida. Recebimentos e saldo financeiro são controlados separadamente. O mesmo pedido não entra em dois fechamentos ativos. Fechamentos aprovados não são cancelados pela interface comum; correções posteriores precisam de procedimento próprio.

## O que o painel ajuda a encontrar

- Falta de registros: produtos sem custo, lotes sem custo e produção ainda não lançada.
- Desperdício: perdas em quantidade e custo conhecido, excedente em relação aos pedidos e seus motivos.
- Problemas na entrega: clientes não entregues, dinheiro apenas informado, malotes pendentes ou divergentes.
- Risco de caixa: contas vencidas, clientes há mais tempo em atraso e recebimentos parciais.
- Reposição: itens no mínimo ou abaixo dele, conforme o estoque registrado.
- Oportunidades comerciais: vendas e clientes mais relevantes quando houver operação real emitida. Não use pedidos de teste como faturamento.

## Limites desta etapa

A operação gerencial é ativada por empresa em Começar operação. Estoque e custos são informados, sem ficha técnica automática ou integração bancária. Não há cálculo de lucro líquido, emissão fiscal integrada, baixa automática de insumos por receita ou correção automática após aprovação fiscal. A implantação e a conferência dos dados reais devem preceder a operação definitiva.


## Compras e contas a pagar

Receba o XML completo do fornecedor e abra Contas a pagar → Importar XML de compra. Selecione TECO ou NONA, confira o CNPJ, o fornecedor e as duplicatas, e confirme para gerar todas as parcelas. Se faltarem datas no XML, complete o combinado com o fornecedor. Não presuma vencimento ou pagamento.

O Financeiro acompanha contas vencidas e próximas de vencer, registra pagamentos já realizados e mantém os comprovantes/referências. Pagamentos parciais deixam saldo. Reenvio da mesma nota não duplica parcelas. O ERP não paga boletos ou transfere dinheiro e não altera estoque automaticamente com essa importação.

## Objetivo fiscal: substituir os emissores atuais

O objetivo final é emitir pelo próprio ERP, substituindo Sistema Imagem (TECO) e Multicomp (NONA). Essa emissão ainda precisa ser implementada e homologada com os dados tributários e o certificado de cada empresa. Antes da transição definitiva, validar autorização, rejeições/recuperação, eventos, numeração/série e guarda dos XMLs. As notinhas de entrega continuam sendo documentos não fiscais.

A importação de XMLs de compras e o financeiro já estão disponíveis no projeto; não equivalem à emissão de NF-e/NFC-e. O roteiro está em COMPRAS_XML_E_FISCAL.md.

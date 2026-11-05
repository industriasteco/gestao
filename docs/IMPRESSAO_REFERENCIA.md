# Referência da automação e impressão

Arquivo fornecido: Controle_Teco_Visual_Clean_Logos_IBIS_Retrato_NonaRealce.xlsm. A estrutura, as configurações de planilha, os logotipos e o módulo VBA incorporado foram lidos sem executar macros. Dados de clientes, pedidos, histórico e código VBA extraído permanecem fora do repositório público.

## Fluxo preservado

Cadastros → pré-carregar fixos → ajustar quantidades → conferir turnos → finalizar o dia → imprimir notinhas/produção → confirmar entrega → fechamento por cliente/período → aprovação → ambiente fiscal externo.

- A empresa da notinha vem do vínculo explícito do cliente e é congelada no pedido emitido. Não inferimos NONA por nome, histórico ou CNPJ de outra empresa.
- Os fixos do mesmo cliente, entrega, horário e turno são agrupados. O preparo preserva ajustes e não duplica pedidos já preparados, inclusive após edição dos responsáveis ou do horário da rotina.
- A tela permite informar padeiro noturno, padeiro diurno e responsável pela separação. A finalização exige turnos conferidos, padeiros e CNPJ da emissora.
- Quantidade zero fica fora da emissão. Preços ausentes impedem finalizar. Qualquer falha reverte a emissão do lote inteiro.
- Finalizar dia gera PDF único das notinhas e outro PDF com resumo geral/noturno/diurno. Repetição retorna os documentos existentes se o conjunto emitido não mudou.
- PDFs de lote que abrangem duas empresas só podem ser abertos por usuários com acesso a todas as empresas incluídas.

## Notinhas comuns

Duas vias lado a lado por pedido; dois pedidos/quatro vias por A4 retrato. Dez itens por parte. Colunas com as proporções do VBA: quantidade 20%, descrição 50%, preço 20%, valor 10%. Nome/logotipo e dados da emissora; cliente, data, entrega, endereço; quantidade e total da folha; padeiro, separação e visto do recebedor. Via empresa sem preços e sem totais financeiros, via cliente com valores. Pedidos maiores são paginados por parte, sem perda de itens.

O logotipo TECO foi preservado a partir do arquivo fornecido, inclusive sua transparência. A pedido do usuário, as novas notinhas da NONA usam a marca conjunta em branco e verde aplicada no painel, com espaço ampliado no cabeçalho. A seleção continua pelo código da emissora (NONA / NONA CECÍLIA); razão social, CNPJ e demais dados pertencem à NONA. Isso também vale para o cabeçalho IBIS quando a emissora for NONA. PDFs já armazenados não são sobrescritos.

O renderizador PDF usa fontes padrão, pois Aptos/Arial do Excel não estão embutidas no arquivo. Isso exige conferir a amostra e uma impressão física; a leitura do VBA não comprova equivalência de pixels com um PDF emitido pelo Excel ou comportamento da impressora.

## IBIS: decisão explícita do usuário

O nome do arquivo diz Retrato, mas o VBA incorporado contém orientação paisagem. O usuário confirmou que deve prevalecer **A4 retrato, notinha na frente e etiquetas no verso, como o ERP anterior**. Portanto não foi copiada a orientação paisagem da macro.

Cada parte do IBIS tem quatro páginas: frente da via empresa, verso da via empresa, frente da via cliente, verso da via cliente. Cada verso tem grade 5 × 2 com etiquetas de **40 × 60 mm**, em escala real, sem ajuste ao papel. Conferir na impressora o modo frente/verso e a borda de virada. O teste automatizado confere A4 retrato, quantidade e dimensões dos dez retângulos.

## Amostras e validação

Foram gerados PDFs de amostra com nomes e valores explicitamente artificiais, fora do banco e do repositório. Conferir as notinhas comuns TECO/NONA e o IBIS antes da liberação operacional. A homologação mantém a marca de teste; não há autorização para cobrança real.

A configuração das emissoras pode ser carregada em Cadastros → Empresas → Carregar dados da planilha de automação. A operação lê apenas EMPRESAS e preenche campos vazios. Não importa pedidos, histórico, clientes ou vínculos de empresa em branco.

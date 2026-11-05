# Propostas comerciais

O menu **Propostas comerciais** reúne orçamentos da NONA e da Panificadora do TECO. O PDF segue a estrutura e as cores do modelo DOCX fornecido: identificação da empresa, título/resumo, destinatário, tabela de investimento, cardápio em duas colunas, total destacado, condições, validade, observações e responsável. O logo é escolhido pela empresa: a nova marca branca/verde na NONA; o mesmo arquivo das notinhas TECO na Panificadora. O watermark segue a mesma marca.

## Preparar uma proposta

1. Abra **Nova proposta** e escolha a empresa.
2. Selecione um cliente cadastrado ou preencha o destinatário. Para cliente cadastrado, nome/documento/endereço em branco são preenchidos pelo cadastro.
3. Informe o serviço/evento, resumo, data e validade. O prazo padrão é 60 dias e pode ser alterado.
4. Adicione serviços livres ou produtos do catálogo. Em produtos, preço em branco usa a condição vigente do cliente ou o preço padrão; preço ausente ou sobreposto pede conferência. Para serviço livre, informe o valor. O orçamento não altera preços do cadastro.
5. Preencha cardápio (um item por linha), condições, observações e responsável. Salve e confira o rascunho; marque **Excluir** para remover um item antes de gerar o PDF.
6. Gere e abra o PDF. Envie pelo canal combinado e registre o envio e a resposta na ficha. Nenhuma mensagem é enviada automaticamente.

Itens e totais usam decimais, com arredondamento de cada subtotal para centavos. Até quatro serviços e oito itens curtos de cardápio cabem em uma página, conforme o exemplo conferido. Textos extensos e listas maiores continuam em páginas adicionais com cabeçalho da tabela e rodapé; não são cortados para caber artificialmente.

## Identificação das empresas

Em **Propostas comerciais → Cabeçalho**, o administrador pode editar dados de cada empresa ou importar o modelo DOCX. A importação lê apenas o texto do cabeçalho/responsável, valida a marca e não executa macros, links ou conteúdo externo. Os logos são os configurados no projeto.

O usuário confirmou que as propostas da NONA devem usar endereço/telefone e demais dados do novo modelo. Isso configura um perfil exclusivo para propostas e preserva o cadastro fiscal e as notinhas. Campos vazios usam os dados existentes da empresa. O responsável pode ser definido no cabeçalho e alterado por proposta.

As informações privadas permanecem no banco. O documento original, seus contatos e os clientes não entram no repositório público.

## Preservação e acesso

Gerar novamente uma proposta já gerada devolve os mesmos bytes. Alterações de dados da empresa, catálogo ou código do layout não reescrevem o PDF. **Criar revisão** abre um novo rascunho e mantém o vínculo com a versão anterior. Envio e resposta são registrados manualmente com evidência e auditoria; cancelamento bloqueia o download corrente, preservando o documento para auditoria.

Somente usuários autorizados e vinculados à empresa acessam as propostas. O perfil **Comercial** pode preparar propostas e consultar cadastros/preços, sem permissão financeira. Apenas administrador configura cabeçalhos. Aceitar uma proposta não cria pedido recorrente, dívida ou nota fiscal.

## Publicação e conferência

Esta implementação foi validada no ambiente de desenvolvimento. Publicar o código não transfere o banco local nem os arquivos privados.

1. Publicar a branch revisada no serviço de homologação e conferir a migration `0017`.
2. Acessar cada **Cabeçalho** com administrador. Para NONA, carregar o DOCX fornecido e conferir os dados; para TECO, conferir os dados próprios da Panificadora.
3. Gerar propostas de conferência para as duas empresas e verificar marca, destinatário, unidades, valores, prazo, responsável e impressão A4.

Validação automatizada: 17 cenários de propostas, incluindo marcas distintas, paginação sem perda de itens, preço negociado, exclusão de item em rascunho, isolamento por empresa, importação de cabeçalho, revisão, preservação do PDF, permissões e ausência de lançamentos operacionais/financeiros. A suite completa atual contém 135 testes. Também foram conferidas as telas no navegador e no celular, sem transbordamento horizontal.

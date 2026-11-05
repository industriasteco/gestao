# Compras, contas a pagar e caminho para um ERP fiscal único

O objetivo confirmado é deixar de usar os dois emissores atuais e operar com gestão e emissão fiscal no próprio ERP. Hoje a TECO usa Sistema Imagem e a NONA usa Multicomp. Esses nomes ficam no cadastro das empresas apenas como referência da transição, não como integração já funcionando.

## Entregue: contas a pagar por XML

1. Em Cadastros → Empresas, abra a empresa e confira o CNPJ destinatário. Os dados das notinhas já emitidas não são alterados.
2. Abra Contas a pagar → Importar XML de compra. Selecione a empresa e o XML completo fornecido pelo vendedor.
3. Confira fornecedor, total da nota, valor financeiro da fatura e duplicatas. A chave de acesso e o CNPJ destinatário são verificados antes de gravar.
4. Confirme para gerar todas as parcelas em uma ação. A mesma nota não cria um segundo fornecedor ou novas parcelas ao reenviar.
5. Se a duplicata não tiver vencimento, complete a data. Se não houver duplicatas, informe o parcelamento combinado com o fornecedor. Não há prazo presumido.
6. Registre pagamentos já realizados e sua referência/comprovante. Pagamento parcial mantém o saldo em aberto. Nenhum boleto é pago e nenhuma transferência é realizada pelo ERP.

O XML é guardado privadamente no banco com hash de integridade, sem publicação no GitHub. O formato aceito é NF-e 4.00 completa com protocolo (`nfeProc`), modelos 55/65. Não aceita DANFE em PDF, resumo de nota, evento de cancelamento, NFS-e ou arquivo ZIP.

A soma das duplicatas deve corresponder à fatura. Valores acima do total da nota ou vencimentos anteriores à emissão são rejeitados. Uma diferença entre valor total e fatura é sinalizada e não é tratada como pagamento. Duplicatas com datas ausentes podem ser completadas sem alterar valores, referências ou datas já presentes no XML.

O importador verifica a estrutura necessária, o dígito da chave e a correspondência de campos. **Não verifica criptograficamente a assinatura nem consulta a situação atual/cancelamento na SEFAZ.** O operador precisa conferir a compra e o documento recebido antes de gerar a obrigação. O status de autorização lido do arquivo é uma informação do arquivo, não uma consulta oficial.

Notas de homologação geram contas de teste, identificadas e excluídas dos totais reais. Importar XML não registra estoque, custos, preços de venda ou quitação. Itens da nota aparecem para conferência.

## Outros recursos financeiros entregues

Cadastro/edição de fornecedores; despesas sem XML; filtros por empresa, fornecedor, referência e situação; saldos a pagar, vencidos e próximos de vencer; pagamentos parciais e histórico por responsável. Uma conta sem pagamento pode ser cancelada internamente com motivo, preservando o registro. Isso não cancela uma NF-e. Uma nota em revisão pode ser arquivada sem financeiro; isso não significa que foi paga.

O perfil Financeiro tem os acessos do módulo. Produção e Entregas não recebem essas permissões. A migration `0014` preenche o emissor atual de TECO/NONA somente se estiver vazio, preservando configuração já feita. O sistema não guarda credenciais ou certificados nesse campo.

## Etapa futura: emitir pelo próprio ERP

A meta é que o usuário opere por uma única interface, sem depender do Sistema Imagem ou Multicomp para emitir. O componente fiscal terá que ser implementado e mantido conforme os serviços e leiautes vigentes. A decisão técnica entre comunicação direta e um componente fiscal específico deve ser tomada antes de contratar qualquer serviço; nenhuma contratação foi feita nesta tarefa.

A implementação deve contemplar:

- Cadastro fiscal confirmado de cada CNPJ: inscrição estadual, regime tributário, endereço/código do município e credenciamento pertinente.
- Regras fiscais dos produtos e operações, conferidas com o responsável fiscal: NCM, CFOP, CST/CSOSN e demais campos aplicáveis.
- Certificado e configurações próprias de cada empresa, com armazenamento seguro e segregação de acesso; CSC quando aplicável à NFC-e. Segredos não devem ser enviados pelo chat nem commitados.
- Numeração/série por CNPJ e modelo, começando a partir do último documento autorizado nos emissores atuais, para impedir colisão de números.
- Assinatura do XML, transmissão, tratamento de rejeições, consulta e confirmação de autorização, protocolo e geração de DANFE/DANFE-NFC-e a partir do resultado oficial.
- Repetição segura após falha/rede, sem notas duplicadas; cancelamento, inutilização e demais eventos cabíveis, com auditoria.
- Armazenamento dos XMLs/protocolos, acesso para o contador e backup durável. O teste de restauração existente não substitui essa rotina de backup.
- Ambientes de homologação e produção separados, com controles para impedir que uma operação de teste vire emissão real.

## Transição antes de dispensar os emissores atuais

Validar o cadastro e as regras com o responsável fiscal. Testar emissão, rejeição/recuperação e eventos em homologação. Preparar a continuidade de número/série e a guarda dos XMLs anteriores. Validar o fluxo autorizado em produção e a conferência com a contabilidade. Somente depois concluir a substituição dos emissores.

A emissão pelo próprio ERP **ainda não está habilitada nesta entrega**. Notinhas, romaneios e fechamentos continuam sendo documentos comerciais não fiscais. A exportação CSV de fechamento aprovado serve de apoio à conferência durante a transição; não é um leiaute de importação homologado para Imagem ou Multicomp.

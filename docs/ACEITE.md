# Evidências de homologação automatizada — etapa 2

Atualização gerencial atual: **185 testes** no conjunto completo, sem ignorados. Inclui contas a pagar/XML, ordem de compra, 17 cenários de propostas comerciais e 14 cenários de preços/cadastros durante o pedido e nove de dias recorrentes/preços do cliente. As evidências históricas da etapa 2 abaixo correspondem ao conjunto original; [evolução e validações posteriores](ETAPA_3.md) e [propostas](PROPOSTAS_COMERCIAIS.md) descrevem o escopo atual.

Tela de login atualizada: repetidos os três testes existentes de primeiro acesso, CSRF e escopo. No navegador: redirecionamento de entrada sem sessão, logo/arquivos estáticos, senha visível/oculta, mensagem de credenciais inválidas sem reapresentar a senha, autenticação com usuário temporário, retorno à página solicitada e logout. Larguras de 320, 390, 768 e 1440 pixels conferidas sem transbordamento. `check`, coleta dos arquivos estáticos e `diff --check` aprovados. Nenhuma migração ou mudança de senha existente.

Execução final em PostgreSQL: **42 testes passaram; nenhum ignorado; nenhuma falha.** A suite usa dados artificiais e, onde disponíveis localmente, os CSVs privados reais em staging. No GitHub público, fontes privadas são substituídas por fixtures explicitamente artificiais para permitir reprodução dos testes sem expor clientes.

| Critério | Evidência automatizada de homologação |
|---|---|
| CT-01 | Preparar dia duas vezes preserva quantidade ajustada e um único pedido |
| CT-02 | Dois horários geram dois pedidos; totalização por turno; PDF comum com quatro vias para dois pedidos |
| CT-03 | Produção consolidada; documentos e fechamento isolados por empresa; acesso por vínculo |
| CT-04 | Falta de turno impede conferência |
| CT-05 | Falta de preço bloqueia resolução/emissão; operação real permanece bloqueada |
| CT-06 | Reajuste não modifica snapshot, PDF nem fechamento já aprovado |
| CT-07 | Cancelamento exclui produção e elegibilidade do fechamento, com evento preservado |
| CT-08 | Motivo e autorização especial após emissão; PDF anterior preservado como superado |
| CT-09 | PDF IBIS com quatro páginas A4 retrato e dez retângulos exatos de 40×60 mm em cada verso |
| CT-10 | Duas vias por pedido; via empresa sem valores; quatro blocos por A4 |
| CT-11 | PDF diário da empresa sem duplicação em tentativas repetidas |
| CT-12 | Trinta pedidos em um fechamento, PDF paginado com todos os números e total decimal correto |
| CT-13 | Oitenta e duas linhas históricas só em staging; zero pedidos |
| CT-14 | Trinta e uma linhas de previsão só em staging; zero pedidos |
| CT-15 | Cento e uma candidatas inativas; nenhuma regra operacional legada criada |
| CT-16 | Reimpressão retorna mesmo registro e mesmos bytes, sem novo pedido |
| CT-17 | Falha simulada de PDF reverte transação e snapshots; repetição posterior recupera com um documento |
| CT-18 | Backup lógico restaurado em PostgreSQL separado, com contagem de pedidos/auditoria e hash/conteúdo de PDF verificados |
| CT-19 | Operador sem permissão bloqueado no fechamento; tentativa registrada |
| CT-20 | Conciliação exige revisão, número original, evidência e motivo; duplicação bloqueada; zero novos pedidos/documentos |

Outros testes: constraints no banco, auditoria imutável, quantidade zero, escopo de documentos, suspensão por data, múltiplos itens, primeiro acesso protegido e uso único, upload privado validado, formulários, CSRF, todas as telas operacionais e documentos diários marcados como superados após cancelamento.

Migrations sem alterações pendentes; `manage.py check` e `check --deploy` sem problemas nas configurações verificadas. Gunicorn iniciado para validação funcional por HTTP. Build Docker da etapa 1 foi validado; nova configuração de hospedagem usa Python/Gunicorn e dependências fixadas.

## O que esses testes não demonstram

Não comprovam impressão física com régua, autorização contábil, confirmação dos dados reais, funcionamento de um provedor externo ainda não implantado, backup agendado/criptografado ou desempenho sob concorrência intensa. Toda emissão/entrega/fechamento automatizada aqui usa pedidos artificiais. Não há liberação para cobrança real.


Preços e cadastros no pedido: [fluxo e validação](PEDIDOS_E_PRECOS.md). Foram conferidas a preservação dos valores de documentos emitidos, alterações repetidas sem datas, condição por cliente, idempotência dos novos cadastros, CSRF e permissões. A primeira execução após adicionar os arquivos do modal apontou manifesto estático local desatualizado; a coleta de arquivos estáticos foi atualizada antes da execução final.


Dias recorrentes/preços no cliente: testes cobrem cadastro comum e rápido com dias/preços, repetição idempotente do primeiro pedido, planejamento somente nos dias marcados, ausência de geração retroativa ou por acesso sem permissão, preservação de rotinas manuais/suspensas e pedidos ajustados, alteração dos dias, preço específico e validação atômica por empresa. No navegador foram conferidos dias e preço na caixa, correção de duplicidade, repetição na segunda-feira seguinte, ausência na terça não marcada, ficha do cliente e celular.


Início operacional: 16 cenários adicionais aprovados de retirada de pré-cadastros, ativação por empresa, separação entre pedido operacional e teste, emissão comum/IBIS não fiscal, fechamento/indicadores, romaneio/malote, perfil Produção e datas de lançamento/entrega/produção. O conjunto completo passou com **174 testes**. As restrições originais da etapa 2 refletem a versão anterior; a ativação atual está descrita em [Começar hoje](COMECE_HOJE.md).


Catálogo compartilhado: 11 novos cenários aprovados para disponibilidade das duas marcas sem cópias, produtos novos no cadastro comum/rápido, prioridade de preços, ativação com catálogo da outra marca, preços do cliente, rotina automática, emissão real não fiscal com a marca da venda e PDF preservado, proposta, produção/custo e proteção de clientes/condições de outra empresa. O conjunto completo passou com **185 testes**, sem ignorados. A disponibilidade compartilhada não cria pedidos, preços ou rotinas por conta própria e não exige nova migration.

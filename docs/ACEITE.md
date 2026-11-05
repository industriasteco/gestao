# Evidências de homologação automatizada — etapa 2

Atualização gerencial atual: **135 testes** no conjunto completo, sem ignorados. Inclui contas a pagar/XML, ordem de compra e 17 cenários de propostas comerciais. As evidências históricas da etapa 2 abaixo correspondem ao conjunto original; [evolução e validações posteriores](ETAPA_3.md) e [propostas](PROPOSTAS_COMERCIAIS.md) descrevem o escopo atual.

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

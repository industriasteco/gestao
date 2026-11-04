# Etapa 2 — homologação guiada e preparação da hospedagem

## Implementado

Pedidos manuais com múltiplos itens e chave de repetição; ajuste de itens; recorrências com itens adicionais e exceção/suspensão por data; responsáveis; documentos de homologação com snapshots; confirmação de entrega independente; liberação explícita; fechamento por empresa/cliente com todos os pedidos elegíveis; cancelamento com preservação documental e autorização especial após emissão; conciliação histórica com evidência e número original único, sem criar faturamento.

PDFs: comprovantes comuns com duas vias, quatro blocos por A4; via empresa sem valores; IBIS A4 retrato em quatro páginas por parte, verso de cada via com grade 5×2 de 40×60 mm. Hashes, conteúdo binário privado no PostgreSQL, versão e reimpressão idempotente. Consolidação diária por empresa sem duplicar pedidos.

Telas em português: cadastros, pedido detalhado com prévia e confirmação, fechamento, auditoria e guia. Primeiro administrador criado com chave de instalação, senhas validadas e tela desabilitada após primeiro uso. Botão para preparar exemplos sem terminal. Upload CSV autenticado com validação e staging idempotente.

Hospedagem preparada: Render gratuito + Neon externo, conexão PostgreSQL com TLS verificado, Gunicorn e WhiteNoise, cookies seguros/HTTPS em modo hospedado, Blueprint e guia. Contas e implantação externa ainda não foram realizadas nesta tarefa.

## Arquivos

`core/workflow.py`, `core/pdf.py`, `core/backup.py`, `core/forms.py`, `core/operator_views.py`, `core/access.py`, modelos/migration 0004, templates, testes; `config/`, `render.yaml`, dependências e guias. A auditoria continua protegida por trigger no banco. Fontes privadas em `reference/` excluídas do GitHub público; podem ser carregadas pela área autenticada.

## Limites

Não é liberação para operação real. Pedidos financeiros sintéticos apenas; CNPJ não é inventado e aparece como pendente no PDF de teste. Preços precisam ser informados e válidos. As 101 sugestões legadas ficam no staging, sem ativação ou conversão automática. Vínculos cliente/empresa ainda usam cadastros separados por empresa; compartilhamento com vigências exige evolução. Grades de produção contemplam planejamento; registro de assado/perdas, devoluções parciais e correções após fechamento ainda estão pendentes. Não há integração fiscal, MFA, rotina de backup criptografado agendada ou homologação física da impressora.

A restauração automatizada usa banco PostgreSQL separado e efêmero, conferindo pedidos, auditoria e conteúdo/hash dos PDFs; não configura retenção de backups em hospedagem. Ambiente com usuário SQL sem CREATE DATABASE precisa de operador específico para esse teste.

## O que o usuário pode testar com segurança

Todo o percurso de homologação descrito em “Como usar”. Nenhum documento serve para cobrança real. Ver relatório de testes em `ACEITE.md` e instruções de hospedagem em `HOSPEDAGEM_PASSO_A_PASSO.md`.

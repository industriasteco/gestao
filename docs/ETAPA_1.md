# Etapa 1 — base e planejamento seguro

## Fontes inspecionadas

Leitura integral do README inicial, especificação Markdown e DDL conceitual antes de codificar. DDL convertido parcialmente em migrations Django; não foi executado como um ERP pronto. Inspeção estrutural da planilha com openpyxl, sem executar VBA: 21 abas, histórico LANÇAMENTOS sem importação. Módulo `.bas` separado inspecionado para agrupamento, emissão, marcas e IBIS; não presumimos igualdade com o VBA incorporado. Referências visuais consultadas: duas fotos de notinhas e imagens das marcas; nenhum logo redesenhado. CSVs lidos como referências não faturáveis, preservando campos e checksum.

Conferências reais: auditoria 82 linhas, previsão 31, recorrências 101; clientes referência 47, produtos 28. Há conflito de quantidades no legado que precisa de conferência. Empresas sem CNPJ validado e preços em branco são pendências; não os completamos por inferência. CSV usa vírgula, inclusive campos entre aspas com ponto e vírgula: carregamento usa `csv.DictReader` e mantém strings originais.

## Arquivos desta etapa

- `config/`, `manage.py`, `requirements.txt`: aplicação Django/PostgreSQL e autenticação por sessão/CSRF.
- `core/models.py`, `core/migrations/`: empresas, vínculos, cadastros, preços, recorrências, pedidos artificiais, staging e auditoria imutável.
- `core/services.py`: autorização, pré-lançamento transacional, idempotência, quantidades, cancelamento de planejamento, revisão e preços vigentes.
- `core/views.py`, `core/templates/`: login, pedidos, painel Noturno/Diurno/Total/Sem Turno e staging paginado.
- `core/admin.py`: cadastros administrativos e consulta de auditoria.
- `core/management/commands/seed_demo.py`: fixtures artificiais e staging repetível.
- `core/tests.py`: proteção e matriz parcial dos critérios CT-01 a CT-20.
- `Dockerfile`, `compose.yaml`: ambiente local; `README.md`: operação e restrições.

## Riscos e pendências antes de emissão real

Este incremento não é o ERP completo. Recorrência inicial tem um produto por regra; agrupamento de múltiplos itens, suspensões/feriados, exceções e calendário mais completo ainda precisam ser desenvolvidos. Vínculo cliente/empresa inicial é fixo; vigências e múltiplas empresas por cliente precisam de modelo próprio. Produção representa quantidades planejadas, não mede assados/perdas e ainda não exige padeiro. Perfis avançados, MFA, propostas/aprovações de cadastros, máscaras/validação completa de CNPJ e concorrência sob carga permanecem pendentes.

Snapshots de nome/unidade e campo decimal de preço existem; congelamento comercial completo, descontos, documentos e fechamento precisam de implementação e testes reais. Emissão, entrega e fechamento não estão disponíveis. Testes parciais de planejamento não substituem CTs completos que exigem PDFs ou financeiro.

Homologação humana necessária: CNPJ/razão social, preços por vigência, marcas e impressora, aprovação individual das 101 regras, aliases/kits, evidências das notas antigas. Nenhum pedido faturável deve ser gerado por staging. Aprovação da revisão também não autoriza conciliação ou cobrança.

## Tela segura para testar

Pedidos do dia, produção planejada e staging. Use `seed_demo`, crie seu usuário e prepare uma data. Ambas as empresas estão sem CNPJ e sem preços por decisão de segurança. Ajustes, repetição e cancelamentos podem ser exercitados exclusivamente com os clientes identificados como artificiais.

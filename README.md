# ERP Teco + Nona — homologação

Sistema web Django / PostgreSQL em português, com pedidos, produção por turno, staging privado do legado e documentos comerciais **de teste**. Operação real e cobrança permanecem bloqueadas. PDFs não são documentos fiscais.

## Para quem não programa

A instalação na internet está explicada em [Hospedagem: passo a passo](docs/HOSPEDAGEM_PASSO_A_PASSO.md). Depois de criar o primeiro acesso, abra **Como usar** dentro do sistema. O botão **Preparar meus exemplos de teste** dispensa comandos.

Fluxo: **Preparar dia → Conferir produção → Abrir pedido → Gerar documento de teste → Confirmar entrega → Liberar → Fechamento de teste**. Cada etapa é separada e pede a conferência apropriada. Preços ausentes bloqueiam emissão; nenhum preço ou CNPJ é inventado.

Dados antigos só entram na tela autenticada **Dados antigos**. Aprovar uma revisão não cria pedido ou cobrança e não ativa recorrência. As 101 regras legadas são candidatas desativadas. Notas de 01–04/11/2026 são auditoria e 05/11 é previsão.

## Desenvolvimento local

Python 3.12 e PostgreSQL 16. A tarefa de nuvem já é isolada: use o checkout existente, sem criar worktree.

```sh
docker compose up -d db
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver 0.0.0.0:8000
```

`/` pedidos; `/ajuda/` guia; `/staging/` dados antigos; `/cadastros/clientes/` cadastros; `/fechamento/` relatório do mês; `/auditoria/` histórico do administrador. A chave SETUP_KEY habilita a tela de primeiro acesso somente enquanto não existir administrador ativo. Não há senha fixa.

`seed_demo` cria somente cadastros e regras artificiais, sem preços ou CNPJ; é repetível. Na hospedagem, execute pela tela **Como usar**, pelo botão de demonstração. Não carrega dados privados que não estejam presentes localmente.

Alternativa em containers: `docker compose up --build`. Migrations executadas pelo serviço web. No ambiente de nuvem com CA de proxy, construa com `docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t gestao-web .`. Preserve proxy/TLS; nunca desative verificações.

Credenciais padrão `teco / dev-only` são exclusivamente para o banco local. Para hospedagem, configure DATABASE_URL, DJANGO_DEBUG=0, DJANGO_SECRET_KEY, SETUP_KEY e hosts. O Render Blueprint usa PostgreSQL externo com TLS verificado e Gunicorn; não cria banco pago. O Compose publica portas apenas em loopback.

## Testes

```sh
.venv/bin/python manage.py test -v 2
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py check_restore
```

42 testes passaram sem testes ignorados: [matriz de evidências](docs/ACEITE.md). Restauração de teste exige usuário PostgreSQL autorizado a criar um banco separado e efêmero; jamais substitui a origem. Não é configuração de backup durável da hospedagem.

## Organização e limites

`core/models.py` e migrations: entidades e constraints; `services.py`: planejamento/staging; `workflow.py`: transações de homologação; `pdf.py`: PDFs; `backup.py`: verificação de restauração; `forms.py` e templates: operação guiada. Documento armazenado privadamente no PostgreSQL com hash. Auditoria protegida por trigger contra alteração/exclusão, preservado o papel administrativo do DBA.

[Etapa 1](docs/ETAPA_1.md), [Etapa 2 e pendências](docs/ETAPA_2.md). Ainda pendentes: operação real homologada, MFA, backup durável criptografado/agendado, produção assada/perdas, devoluções parciais, correções pós-fechamento, compartilhamento de clientes com vigências, integração fiscal e teste físico da impressora.

Este repositório é público. As fontes privadas (`reference/`, planilhas, CSVs originais e arquivos de credenciais) ficam fora do versionamento. Nesta tarefa estão no ZIP anexado e em `/workspace/erp-reference`; na hospedagem, carregue CSVs pela área protegida do ERP. Macros VBA não são executadas.

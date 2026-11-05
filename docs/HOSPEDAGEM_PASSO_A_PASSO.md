# Colocar a versão de teste na internet — Render + Neon

Você não precisa digitar comandos. As contas devem ser suas. Nunca envie senha, chave de instalação ou conexão do banco no chat. Não contrate plano pago sem conferir o valor.

## 1. Banco no Neon

1. Acesse https://neon.tech e crie sua conta, preferencialmente usando o mesmo GitHub.
2. Crie um projeto PostgreSQL para a **homologação**. Selecione o plano gratuito, quando disponível. Região próxima da aplicação ajuda no desempenho.
3. No projeto, abra **Connect**. A conexão começa por `postgresql://`. Ela contém senha: copie somente para o campo protegido DATABASE_URL do Render. Não envie aqui nem inclua em foto.
4. O teste de restauração local não configura automaticamente backups na sua conta Neon. Verifique retenção e recuperação disponíveis no plano escolhido antes de usar dados reais.

## 2. Aplicação no Render

1. Acesse https://dashboard.render.com.
2. Selecione **New / Novo → Web Service / Serviços Web**.
3. Conecte o GitHub e escolha `industriasteco/gestao`, na branch que contém esta versão do sistema.
4. Escolha **Python 3** como linguagem/runtime. Nome sugerido: `teco-nona-homologacao`. Plano **Free**, se disponível. Não escolha Static Site.
5. A configuração completa está no arquivo `render.yaml`. O caminho que automatiza sua leitura é **New → Blueprint**, selecionando o mesmo repositório. Se usar o formulário de Web Service, estes são os campos para copiar:
   - **Build Command:** `pip install -r requirements.lock && python manage.py collectstatic --noinput`
   - **Start Command:** `python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
6. Em **Environment**, configure DATABASE_URL com a conexão do Neon, DJANGO_DEBUG com `0`, PYTHON_VERSION com `3.12.14`. Gere valores secretos aleatórios para DJANGO_SECRET_KEY e SETUP_KEY no próprio Render. O Blueprint já solicita/genera esses campos. Não publique os valores.
7. Depois de validar os campos, use **Deploy**. A implantação aplica o banco e inicia o sistema. Se falhar, compartilhe somente a mensagem de erro, ocultando credenciais.

Os planos gratuitos podem mudar, suspender a aplicação e limitar uso. Confira o resumo de preços antes de criar os serviços. O arquivo preparado usa plano gratuito para aplicação e não solicita banco pago no Render.

## 3. Seu primeiro acesso

1. Abra o endereço HTTPS fornecido pelo Render.
2. Na tela de login com o logo principal, clique em **Configurar o primeiro acesso da instalação**. Esse link aparece somente enquanto a chave SETUP_KEY estiver configurada e ainda não houver administrador ativo.
3. Use a SETUP_KEY das configurações do Render na própria página do sistema; escolha seu nome de usuário e sua senha.
4. A página só cria o primeiro administrador uma vez. Depois, use o login normal.
5. Abra **Como usar → Preparar meus exemplos de teste**. Esse botão cria somente exemplos artificiais sem preços ou CNPJs inventados.

## 4. O que testar primeiro

Siga a página **Como usar**, dentro do sistema: pedidos do dia, produção, documento de teste, entrega e fechamento de teste. Os preços devem ser preenchidos por você com informação confirmada. CSVs são carregados em **Dados antigos**, ficam no banco protegido e nunca alimentam cobrança automaticamente.

Nenhuma planilha/CSV de clientes deve ser publicada no GitHub. O repositório deste projeto é público; as fontes privadas da tarefa estão excluídas do versionamento.

## 5. Limites desta instalação

A instalação começa em configuração/teste. Para iniciar o uso gerencial, complete e ative cada empresa em **Começar operação**, seguindo [o roteiro do primeiro dia](COMECE_HOJE.md). Pedidos antigos de teste permanecem identificados e separados; novos pedidos de empresa ativada geram comprovantes de entrega não fiscais. Impressão IBIS deve ser medida na impressora real. Antes de depender do ERP diariamente: validar cadastros e regras, configurar recuperação/backup durável, monitoramento e acessos, e homologar a operação real. Não há emissão de nota fiscal oficial.

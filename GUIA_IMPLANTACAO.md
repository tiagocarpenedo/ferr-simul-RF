# Guia de implantação — Simulador NTN-B

Este guia foi escrito para quem não é técnico.

## Parte 1 — Preparar os arquivos

1. Baixe o arquivo ZIP entregue no ChatGPT.
2. Descompacte o ZIP no seu computador.
3. Abra a pasta descompactada.
4. Confirme que os seguintes arquivos aparecem:
   - app.py
   - ntnb_core.py
   - data_sources.py
   - requirements.txt
   - README.md
   - pasta .streamlit

Se esses arquivos aparecerem, você está pronto para publicar.

## Parte 2 — Criar conta no GitHub

1. Acesse github.com.
2. Clique em Sign up, se ainda não tiver conta.
3. Crie sua conta.
4. Confirme o e-mail, se o GitHub pedir.

## Parte 3 — Criar o repositório

1. Com o GitHub aberto, clique no botão + no canto superior direito.
2. Clique em New repository.
3. No campo Repository name, digite: ntnb-simulador
4. Em Public/Private, escolha Public se não se importar que o código fique visível.
5. Não precisa marcar nenhuma opção adicional.
6. Clique em Create repository.

## Parte 4 — Subir os arquivos

1. Dentro do repositório recém-criado, procure o botão Add file.
2. Clique em Add file.
3. Clique em Upload files.
4. Arraste todos os arquivos da pasta descompactada para a tela do GitHub.
5. Atenção: o arquivo app.py precisa ficar na primeira tela do repositório, e não dentro de uma pasta extra.
6. Role a página até o final.
7. Clique em Commit changes.

## Parte 5 — Criar conta no Streamlit Community Cloud

1. Acesse streamlit.io/cloud.
2. Clique em Sign in.
3. Escolha Sign in with GitHub.
4. Autorize o Streamlit a acessar sua conta GitHub.

## Parte 6 — Publicar o app

1. No Streamlit Community Cloud, clique em New app ou Create app.
2. Em Repository, escolha: ntnb-simulador
3. Em Branch, escolha: main
4. Em Main file path, digite: app.py
5. Clique em Deploy.

Aguarde alguns minutos. O Streamlit vai instalar as bibliotecas e publicar o app.

## Parte 7 — Testar

1. Quando o app abrir, clique em Atualizar dados do Tesouro.
2. Escolha um título IPCA+ com Juros Semestrais.
3. Ajuste as premissas de IPCA, choques e horizontes.
4. Veja a matriz de cenários e os gráficos.

## Parte 8 — Compartilhar

Depois do deploy, o Streamlit gera um link do tipo: https://nome-do-app.streamlit.app

Copie esse link e envie para quem quiser acessar o simulador.

## Problemas comuns

### O app não abre

Verifique se o arquivo app.py está na raiz do repositório.

### O Streamlit diz que não encontrou uma biblioteca

Verifique se o arquivo requirements.txt foi enviado.

### A atualização do Tesouro falhou

Pode ser instabilidade temporária do Tesouro Transparente. Tente clicar novamente em Atualizar dados do Tesouro alguns minutos depois.

### Quero alterar alguma coisa

Peça ao ChatGPT para alterar o simulador. Depois substitua os arquivos no GitHub e o Streamlit atualizará o app.

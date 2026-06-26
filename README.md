# Simulador visual de NTN-B / Tesouro IPCA+ com Juros Semestrais

Aplicativo em Streamlit pronto para publicar no Streamlit Community Cloud.

## O que ele faz

- Atualiza automaticamente os dados pelo Tesouro Transparente.
- Filtra títulos Tesouro IPCA+ com Juros Semestrais.
- Usa taxa e PU oficiais da data base mais recente.
- Simula cenários de alta/queda do prêmio real.
- Mostra matriz de retorno por horizonte e choque de taxa.
- Mostra gráficos de preço versus taxa.
- Calcula duration de Macaulay, duration modificada, duration efetiva e convexidade.
- Considera cupons semestrais e reinvestimento dos cupons.
- Permite baixar a tabela de cenários em CSV.

## Como publicar

O caminho recomendado é GitHub + Streamlit Community Cloud.

1. Crie um repositório no GitHub.
2. Suba estes arquivos na raiz do repositório:
   - `app.py`
   - `ntnb_core.py`
   - `data_sources.py`
   - `requirements.txt`
   - `README.md`
   - `.streamlit/config.toml`
3. No Streamlit Community Cloud, crie um novo app.
4. Escolha o repositório.
5. Informe `app.py` como arquivo principal.
6. Clique em Deploy.

## Observação importante

A ferramenta usa dados públicos do Tesouro Transparente. Não exige login, credenciais, ANBIMA ou CALC B3.

Retornos são brutos e simulatórios. Não há recomendação de investimento.

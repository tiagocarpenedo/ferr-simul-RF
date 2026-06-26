from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from data_sources import fetch_tesouro_taxas_csv, latest_ipca_sem_coupon_rows, row_label, format_date_br
from ntnb_core import NTNBParams, cashflows_real, price_quote_from_yield, macaulay_duration, modified_duration, effective_modified_duration, convexity, real_coupon_factor, infer_vna_from_official_pu, simulate_matrix, simulate_sale_scenario

st.set_page_config(page_title="Simulador NTN-B", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_tesouro_data():
    raw, source_url = fetch_tesouro_taxas_csv()
    latest = latest_ipca_sem_coupon_rows(raw)
    return latest, source_url


def pct(x: float, digits: int = 2) -> str:
    return f"{x * 100:,.{digits}f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def br_num(x: float, digits: int = 6) -> str:
    return f"{x:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_horizons(text: str) -> list[float]:
    items = []
    for part in text.split(","):
        part = part.strip().replace(" ", "")
        if not part:
            continue
        try:
            value = float(part)
            if value > 0:
                items.append(value)
        except ValueError:
            pass
    return items or [0.08, 0.25, 0.5, 1, 2, 3, 5]


def build_params_from_selection(row, reference_side: str, coupon_rate: float) -> tuple[NTNBParams, dict]:
    if reference_side == "Venda":
        real_yield_pct = row.taxa_venda_pct
        official_pu = row.pu_venda
    else:
        real_yield_pct = row.taxa_compra_pct
        official_pu = row.pu_compra
    if pd.isna(real_yield_pct) or pd.isna(official_pu):
        raise ValueError(f"A linha selecionada não possui taxa/PU de {reference_side.lower()}.")
    settlement = row.data_base
    maturity = row.vencimento
    real_yield = float(real_yield_pct) / 100
    implied_vna = infer_vna_from_official_pu(settlement=settlement, maturity=maturity, real_yield=real_yield, official_pu=float(official_pu), coupon_rate=coupon_rate)
    params = NTNBParams(settlement=settlement, maturity=maturity, real_yield=real_yield, coupon_rate=coupon_rate, vna=implied_vna)
    meta = {"settlement": settlement, "maturity": maturity, "real_yield_pct": float(real_yield_pct), "official_pu": float(official_pu), "reference_side": reference_side, "implied_vna": implied_vna}
    return params, meta

st.title("Simulador visual de NTN-B / Tesouro IPCA+ com Juros Semestrais")
st.caption("Atualização automática pelo Tesouro Transparente, sem login e sem planilha manual.")

with st.sidebar:
    st.header("1. Dados oficiais")
    if st.button("🔄 Atualizar dados do Tesouro", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    try:
        latest_df, source_url = load_tesouro_data()
        data_error = None
    except Exception as exc:
        latest_df = pd.DataFrame()
        source_url = ""
        data_error = exc
    if data_error:
        st.error(f"Não consegui baixar os dados do Tesouro: {data_error}")
        st.stop()
    if latest_df.empty:
        st.error("A base foi baixada, mas não encontrei títulos IPCA+ com juros semestrais.")
        st.stop()
    st.success(f"Base carregada: {format_date_br(latest_df['data_base'].max())}")
    labels = [row_label(row) for _, row in latest_df.iterrows()]
    selected_idx = st.selectbox("Escolha o título", options=list(range(len(labels))), format_func=lambda i: labels[i])
    selected = latest_df.iloc[selected_idx]
    reference_side = st.radio("Usar qual referência de taxa/PU?", ["Venda", "Compra"], index=0, horizontal=True, help="Escolha a referência que deseja usar. Os nomes Compra/Venda seguem exatamente as colunas do arquivo oficial do Tesouro.")
    st.divider()
    st.header("2. Premissas de simulação")
    coupon_pct = st.number_input("Cupom real do título (% a.a.)", value=6.00, min_value=0.0, step=0.10, format="%.4f", help="Para NTN-B com juros semestrais, o padrão é 6% a.a.")
    inflation_pct = st.number_input("IPCA projetado (% a.a.)", value=5.00, min_value=-10.0, max_value=50.0, step=0.10, format="%.4f")
    reinvest_coupons = st.checkbox("Reinvestir cupons até a venda", value=True)
    reinvest_mode = st.selectbox("Taxa real de reinvestimento dos cupons", ["future_yield", "initial_yield", "zero_real"], index=0, format_func=lambda x: {"future_yield": "taxa real futura do cenário", "initial_yield": "taxa real inicial", "zero_real": "0% real"}[x])
    st.divider()
    st.header("3. Grade de cenários")
    min_shock = st.number_input("Choque mínimo no prêmio (p.p.)", value=-3.0, step=0.25)
    max_shock = st.number_input("Choque máximo no prêmio (p.p.)", value=3.0, step=0.25)
    shock_step = st.number_input("Intervalo dos choques (p.p.)", value=0.50, min_value=0.05, step=0.25)
    horizons_text = st.text_input("Horizontes em anos", value="0.08, 0.25, 0.50, 1, 2, 3, 5", help="Use ponto decimal. Ex.: 0.08 ≈ 1 mês; 0.50 = 6 meses; 1 = 1 ano.")

try:
    params, meta = build_params_from_selection(selected, reference_side, coupon_pct / 100)
except Exception as exc:
    st.error(f"Erro ao montar o título selecionado: {exc}")
    st.stop()

cfs = cashflows_real(params)
quote = price_quote_from_yield(cfs, params.real_yield)
pu_model = quote * params.vna
d_mac = macaulay_duration(cfs, params.real_yield)
d_mod = modified_duration(cfs, params.real_yield)
d_eff = effective_modified_duration(cfs, params.real_yield)
conv = convexity(cfs, params.real_yield)
coupon_sem = real_coupon_factor(params.coupon_rate, params.frequency)

st.info("Esta versão ancora o simulador no PU oficial do Tesouro Transparente e infere um VNA operacional para projetar os cenários. Assim, a simulação parte do preço oficial mais recente, sem você precisar colar planilhas ou buscar o VNA manualmente.")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Data base", format_date_br(meta["settlement"]))
m2.metric("Vencimento", format_date_br(meta["maturity"]))
m3.metric(f"PU oficial ({reference_side})", br_num(meta["official_pu"], 6))
m4.metric(f"Taxa oficial ({reference_side})", f"{meta['real_yield_pct']:.4f}%".replace(".", ","))
m5.metric("Cupom semestral", pct(coupon_sem, 4))

m6, m7, m8, m9, m10 = st.columns(5)
m6.metric("PU usado no modelo", br_num(pu_model, 6))
m7.metric("VNA implícito", br_num(meta["implied_vna"], 6))
m8.metric("Duration modificada", br_num(d_mod, 4))
m9.metric("Duration efetiva", br_num(d_eff, 4))
m10.metric("Convexidade", br_num(conv, 4))

with st.expander("Ver observações importantes de cálculo"):
    st.markdown("""
- A taxa usada é a taxa real anual do Tesouro, em base DU/252.
- O preço de partida é o PU oficial do Tesouro Transparente na data base.
- O simulador infere um VNA operacional para que o preço calculado bata com o PU oficial.
- Os cenários futuros projetam o VNA por IPCA constante informado por você.
- O retorno é bruto: não desconta Imposto de Renda, taxa de custódia, spread operacional ou eventuais custos.
- A simulação é adequada para análise de sensibilidade e marcação a mercado, mas não substitui confirmação oficial em ambiente profissional.
""")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Matriz de cenários", "📈 Preço × taxa", "🔍 Cenário único", "💵 Fluxos", "ℹ️ Fonte e método"])
shocks = np.arange(min_shock, max_shock + 0.000001, shock_step)
horizons = parse_horizons(horizons_text)

with tab1:
    st.subheader("Retorno por horizonte e variação do prêmio real")
    sim_df = simulate_matrix(params=params, annual_inflation=inflation_pct / 100, horizons_years=horizons, shocks_pp=shocks, reinvest_coupons=reinvest_coupons, reinvest_real_rate_mode=reinvest_mode)
    metric = st.radio("Métrica principal", ["retorno_nominal_bruto", "retorno_real_bruto", "pu_venda", "cupons_reinvestidos"], index=0, horizontal=True, format_func=lambda x: {"retorno_nominal_bruto": "Retorno nominal bruto", "retorno_real_bruto": "Retorno real bruto", "pu_venda": "PU projetado de venda", "cupons_reinvestidos": "Cupons acumulados/reinvestidos"}[x])
    pivot = sim_df.pivot_table(index="horizonte_anos", columns="choque_pp", values=metric, aggfunc="first").sort_index().sort_index(axis=1)
    if "retorno" in metric:
        display = pivot * 100
        st.dataframe(display.style.format("{:+.2f}%"), use_container_width=True)
        heat_data = display
        z_label = "Retorno (%)"
    else:
        st.dataframe(pivot.style.format("{:.6f}"), use_container_width=True)
        heat_data = pivot
        z_label = metric
    fig_heat = px.imshow(heat_data, aspect="auto", text_auto=".2f", labels=dict(x="Choque no prêmio real (p.p.)", y="Horizonte em anos", color=z_label), title="Mapa de calor dos cenários")
    st.plotly_chart(fig_heat, use_container_width=True)
    chart_df = sim_df.copy()
    chart_df["Choque"] = chart_df["choque_pp"].map(lambda x: f"{x:+.2f} p.p.")
    if "retorno" in metric:
        chart_df["valor"] = chart_df[metric] * 100
        y_label = "Retorno (%)"
    else:
        chart_df["valor"] = chart_df[metric]
        y_label = metric
    fig_line = px.line(chart_df, x="horizonte_anos", y="valor", color="Choque", markers=True, labels={"horizonte_anos": "Horizonte em anos", "valor": y_label}, title="Evolução do cenário por horizonte")
    st.plotly_chart(fig_line, use_container_width=True)
    csv = sim_df.to_csv(index=False).encode("utf-8")
    st.download_button("Baixar tabela completa de cenários em CSV", data=csv, file_name="cenarios_ntnb_tesouro_transparente.csv", mime="text/csv", use_container_width=True)

with tab2:
    st.subheader("Curva de PU conforme o prêmio real")
    price_rows = []
    for shock in shocks:
        y = params.real_yield + shock / 100
        q = price_quote_from_yield(cfs, y)
        pu = q * params.vna
        approx_change = -d_mod * (shock / 100)
        exact_change = pu / pu_model - 1 if pu_model else 0
        price_rows.append({"choque_pp": shock, "premio_real_pct": y * 100, "pu": pu, "variacao_exata_pct": exact_change * 100, "variacao_por_duration_pct": approx_change * 100, "erro_duration_pct": (exact_change - approx_change) * 100})
    price_df = pd.DataFrame(price_rows)
    fig_price = px.line(price_df, x="premio_real_pct", y="pu", markers=True, labels={"premio_real_pct": "Prêmio real (% a.a.)", "pu": "PU"}, title="PU projetado por taxa real")
    st.plotly_chart(fig_price, use_container_width=True)
    st.markdown("Comparação entre repricing exato e aproximação por duration:")
    st.dataframe(price_df.style.format({"choque_pp": "{:+.2f}", "premio_real_pct": "{:.4f}", "pu": "{:.6f}", "variacao_exata_pct": "{:+.4f}%", "variacao_por_duration_pct": "{:+.4f}%", "erro_duration_pct": "{:+.4f}%"}), use_container_width=True)

with tab3:
    st.subheader("Abrir um cenário específico")
    col_a, col_b = st.columns(2)
    with col_a:
        single_h = st.number_input("Horizonte da venda, em anos", value=1.0, min_value=0.01, step=0.25)
    with col_b:
        single_shock = st.number_input("Choque no prêmio real, em p.p.", value=-1.0, step=0.25)
    res = simulate_sale_scenario(params=params, annual_inflation=inflation_pct / 100, horizon_years=single_h, shock_pp=single_shock, reinvest_coupons=reinvest_coupons, reinvest_real_rate_mode=reinvest_mode)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Data de venda simulada", format_date_br(res["data_venda"]))
    c2.metric("Taxa real futura", f"{res['taxa_real_futura']*100:.4f}%".replace(".", ","))
    c3.metric("Retorno nominal bruto", pct(res["retorno_nominal_bruto"], 2))
    c4.metric("Retorno real bruto", pct(res["retorno_real_bruto"], 2))
    detail = pd.DataFrame([res]).T.reset_index()
    detail.columns = ["Campo", "Valor"]
    st.dataframe(detail, use_container_width=True)

with tab4:
    st.subheader("Fluxos reais remanescentes")
    flow_df = cfs.copy()
    if not flow_df.empty:
        flow_df["vp_fluxo_vna"] = flow_df["fluxo_vna"] / ((1 + params.real_yield) ** flow_df["t_du_252"])
        flow_df["peso_vp"] = flow_df["vp_fluxo_vna"] / flow_df["vp_fluxo_vna"].sum()
        flow_df["fluxo_estimado_em_reais_na_data_base"] = flow_df["fluxo_vna"] * params.vna
    st.dataframe(flow_df.style.format({"t_du_252": "{:.6f}", "fluxo_vna": "{:.8f}", "vp_fluxo_vna": "{:.8f}", "peso_vp": "{:.2%}", "fluxo_estimado_em_reais_na_data_base": "{:.6f}"}), use_container_width=True)

with tab5:
    st.subheader("Fonte dos dados e método")
    st.markdown(f"""
**Fonte automática:** Tesouro Transparente, base pública de preços e taxas dos títulos ofertados pelo Tesouro Direto.

**URL usada pelo app:** `{source_url}`

**Título selecionado:** {selected.tipo}  
**Data base:** {format_date_br(meta['settlement'])}  
**Vencimento:** {format_date_br(meta['maturity'])}  
**Referência escolhida:** {reference_side}

### Método resumido

1. O app baixa automaticamente o CSV público do Tesouro.
2. Filtra apenas títulos **Tesouro IPCA+ com Juros Semestrais**.
3. Seleciona a data base mais recente disponível.
4. Usa a taxa e o PU oficial escolhidos como ponto de partida.
5. Infere um VNA operacional para fazer o preço calculado bater com o PU oficial.
6. Projeta cenários futuros alterando o prêmio real e recalculando o PU pelos fluxos remanescentes.
7. Calcula retorno nominal e real, considerando cupons e reinvestimento, se ativado.

### Limitações transparentes

- Retornos são brutos, antes de IR, taxa de custódia e custos.
- IPCA futuro é uma premissa constante digitada por você.
- O calendário de feriados cobre os principais feriados brasileiros; para uso institucional, valide DUs em fonte oficial.
- A ferramenta é para simulação e análise de sensibilidade. Não é recomendação de investimento.
""")

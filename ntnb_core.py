from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional, List, Tuple, Dict

import pandas as pd


def easter_date(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def brazil_market_holidays(year: int) -> set[date]:
    easter = easter_date(year)
    fixed = {
        date(year, 1, 1), date(year, 4, 21), date(year, 5, 1), date(year, 9, 7),
        date(year, 10, 12), date(year, 11, 2), date(year, 11, 15), date(year, 11, 20),
        date(year, 12, 25),
    }
    movable = {easter - timedelta(days=48), easter - timedelta(days=47), easter - timedelta(days=2), easter + timedelta(days=60)}
    return fixed | movable


def holiday_set_between(start: date, end: date, extra_holidays: Optional[Iterable[date]] = None) -> set[date]:
    years = range(min(start.year, end.year) - 1, max(start.year, end.year) + 2)
    hols: set[date] = set()
    for year in years:
        hols |= brazil_market_holidays(year)
    if extra_holidays:
        hols |= set(extra_holidays)
    return hols


def is_business_day(d: date, extra_holidays: Optional[Iterable[date]] = None) -> bool:
    return d.weekday() < 5 and d not in holiday_set_between(d, d, extra_holidays)


def adjust_business_day(d: date, convention: str = "following", extra_holidays: Optional[Iterable[date]] = None) -> date:
    if convention == "none":
        return d
    if convention not in {"following", "preceding"}:
        raise ValueError("convention deve ser 'following', 'preceding' ou 'none'.")
    step = 1 if convention == "following" else -1
    out = d
    while not is_business_day(out, extra_holidays):
        out = out + timedelta(days=step)
    return out


def business_days_between(start: date, end: date, extra_holidays: Optional[Iterable[date]] = None, include_end: bool = True) -> int:
    if end <= start:
        return 0
    hols = holiday_set_between(start, end, extra_holidays)
    current = start + timedelta(days=1)
    last = end if include_end else end - timedelta(days=1)
    count = 0
    while current <= last:
        if current.weekday() < 5 and current not in hols:
            count += 1
        current += timedelta(days=1)
    return count


@dataclass(frozen=True)
class NTNBParams:
    settlement: date
    maturity: date
    real_yield: float
    coupon_rate: float = 0.06
    vna: float = 1.0
    principal_units: float = 1.0
    frequency: int = 2
    coupon_adjustment: str = "following"
    extra_holidays: Optional[Tuple[date, ...]] = None


def add_months(dt: date, months: int) -> date:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    month_days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(dt.day, month_days[month - 1]))


def real_coupon_factor(coupon_rate: float = 0.06, frequency: int = 2) -> float:
    return (1 + coupon_rate) ** (1 / frequency) - 1


def coupon_schedule(settlement: date, maturity: date, frequency: int = 2, adjustment: str = "following", extra_holidays: Optional[Iterable[date]] = None) -> List[date]:
    if maturity <= settlement:
        return []
    months_step = int(12 / frequency)
    raw_dates: list[date] = []
    d = maturity
    while d > settlement:
        raw_dates.append(d)
        d = add_months(d, -months_step)
    adjusted = []
    for raw in raw_dates:
        adj = adjust_business_day(raw, adjustment, extra_holidays)
        if adj > settlement:
            adjusted.append(adj)
    return sorted(set(adjusted))


def cashflows_real(params: NTNBParams, pricing_date: Optional[date] = None) -> pd.DataFrame:
    pricing_date = pricing_date or params.settlement
    maturity_adj = adjust_business_day(params.maturity, params.coupon_adjustment, params.extra_holidays)
    dates = coupon_schedule(pricing_date, params.maturity, params.frequency, params.coupon_adjustment, params.extra_holidays)
    coupon = real_coupon_factor(params.coupon_rate, params.frequency) * params.principal_units
    rows = []
    for d in dates:
        flow = coupon
        if d == maturity_adj:
            flow += params.principal_units
        du = business_days_between(pricing_date, d, params.extra_holidays)
        rows.append({"data_fluxo": d, "du": du, "t_du_252": du / 252, "fluxo_vna": flow})
    return pd.DataFrame(rows)


def price_quote_from_yield(cfs: pd.DataFrame, real_yield: float) -> float:
    if cfs.empty:
        return 0.0
    return float((cfs["fluxo_vna"] / ((1 + real_yield) ** cfs["t_du_252"])).sum())


def pu_from_yield(params: NTNBParams, real_yield: Optional[float] = None, pricing_date: Optional[date] = None) -> float:
    y = params.real_yield if real_yield is None else real_yield
    cfs = cashflows_real(params, pricing_date or params.settlement)
    return price_quote_from_yield(cfs, y) * params.vna


def macaulay_duration(cfs: pd.DataFrame, real_yield: float) -> float:
    if cfs.empty:
        return 0.0
    pv = cfs["fluxo_vna"] / ((1 + real_yield) ** cfs["t_du_252"])
    price = float(pv.sum())
    if price == 0:
        return 0.0
    return float((cfs["t_du_252"] * pv).sum() / price)


def modified_duration(cfs: pd.DataFrame, real_yield: float) -> float:
    return macaulay_duration(cfs, real_yield) / (1 + real_yield)


def effective_modified_duration(cfs: pd.DataFrame, real_yield: float, bump: float = 0.0001) -> float:
    p_down = price_quote_from_yield(cfs, real_yield - bump)
    p_up = price_quote_from_yield(cfs, real_yield + bump)
    p0 = price_quote_from_yield(cfs, real_yield)
    if p0 == 0:
        return 0.0
    return float((p_down - p_up) / (2 * p0 * bump))


def convexity(cfs: pd.DataFrame, real_yield: float) -> float:
    if cfs.empty:
        return 0.0
    t = cfs["t_du_252"]
    numerator = (cfs["fluxo_vna"] * t * (t + 1) / ((1 + real_yield) ** (t + 2))).sum()
    price = price_quote_from_yield(cfs, real_yield)
    if price == 0:
        return 0.0
    return float(numerator / price)


def projected_vna(vna0: float, annual_inflation: float, start: date, target: date) -> float:
    elapsed = max((target - start).days / 365.0, 0.0)
    return vna0 * ((1 + annual_inflation) ** elapsed)


def nominal_rate(real_rate: float, inflation: float) -> float:
    return (1 + real_rate) * (1 + inflation) - 1


def infer_vna_from_official_pu(settlement: date, maturity: date, real_yield: float, official_pu: float, coupon_rate: float = 0.06) -> float:
    params_unit = NTNBParams(settlement=settlement, maturity=maturity, real_yield=real_yield, coupon_rate=coupon_rate, vna=1.0)
    cfs = cashflows_real(params_unit, settlement)
    quote = price_quote_from_yield(cfs, real_yield)
    if quote <= 0:
        raise ValueError("Não foi possível inferir VNA: cotação por VNA zerada.")
    return official_pu / quote


def simulate_sale_scenario(params: NTNBParams, annual_inflation: float, horizon_years: float, shock_pp: float, reinvest_coupons: bool = True, reinvest_real_rate_mode: str = "future_yield", sale_date_adjustment: str = "following") -> Dict[str, float | date]:
    maturity_adj = adjust_business_day(params.maturity, params.coupon_adjustment, params.extra_holidays)
    raw_sale_date = params.settlement + timedelta(days=int(round(horizon_years * 365)))
    sale_date = min(raw_sale_date, maturity_adj)
    sale_date = adjust_business_day(sale_date, sale_date_adjustment, params.extra_holidays)
    if sale_date > maturity_adj:
        sale_date = maturity_adj
    future_yield = params.real_yield + shock_pp / 100
    cfs_purchase = cashflows_real(params, params.settlement)
    purchase_quote = price_quote_from_yield(cfs_purchase, params.real_yield)
    purchase_pu = purchase_quote * params.vna
    coupon_factor = real_coupon_factor(params.coupon_rate, params.frequency)
    all_coupon_dates = coupon_schedule(params.settlement, params.maturity, params.frequency, params.coupon_adjustment, params.extra_holidays)
    coupons_nominal_accum = 0.0
    coupons_received_count = 0
    for d in all_coupon_dates:
        if params.settlement < d <= sale_date and d < maturity_adj:
            coupons_received_count += 1
            vna_d = projected_vna(params.vna, annual_inflation, params.settlement, d)
            coupon_nominal = vna_d * coupon_factor * params.principal_units
            if reinvest_coupons:
                if reinvest_real_rate_mode == "future_yield":
                    real_reinvest = future_yield
                elif reinvest_real_rate_mode == "initial_yield":
                    real_reinvest = params.real_yield
                elif reinvest_real_rate_mode == "zero_real":
                    real_reinvest = 0.0
                else:
                    raise ValueError("Modo de reinvestimento inválido.")
                reinv_nominal = nominal_rate(real_reinvest, annual_inflation)
                elapsed = max((sale_date - d).days / 365.0, 0.0)
                coupons_nominal_accum += coupon_nominal * ((1 + reinv_nominal) ** elapsed)
            else:
                coupons_nominal_accum += coupon_nominal
    if sale_date >= maturity_adj:
        vna_sale = projected_vna(params.vna, annual_inflation, params.settlement, maturity_adj)
        sale_quote = 1 + coupon_factor
        sale_pu = vna_sale * sale_quote * params.principal_units
    else:
        vna_sale = projected_vna(params.vna, annual_inflation, params.settlement, sale_date)
        remaining_params = NTNBParams(settlement=sale_date, maturity=params.maturity, real_yield=future_yield, coupon_rate=params.coupon_rate, vna=vna_sale, principal_units=params.principal_units, frequency=params.frequency, coupon_adjustment=params.coupon_adjustment, extra_holidays=params.extra_holidays)
        cfs_remaining = cashflows_real(remaining_params, sale_date)
        sale_quote = price_quote_from_yield(cfs_remaining, future_yield)
        sale_pu = sale_quote * vna_sale
    final_nominal = sale_pu + coupons_nominal_accum
    ret_nominal = final_nominal / purchase_pu - 1
    inflation_factor = projected_vna(1.0, annual_inflation, params.settlement, sale_date)
    ret_real = (1 + ret_nominal) / inflation_factor - 1
    return {"data_venda": sale_date, "horizonte_anos": max((sale_date - params.settlement).days / 365.0, 0.0), "choque_pp": shock_pp, "taxa_real_futura": future_yield, "pu_compra": purchase_pu, "cotacao_compra_vna": purchase_quote, "vna_compra_implicito": params.vna, "vna_venda_projetado": vna_sale, "pu_venda": sale_pu, "cotacao_venda_vna": sale_quote, "cupons_recebidos_qtd": coupons_received_count, "cupons_reinvestidos": coupons_nominal_accum, "valor_final_nominal": final_nominal, "retorno_nominal_bruto": ret_nominal, "retorno_real_bruto": ret_real}


def simulate_matrix(params: NTNBParams, annual_inflation: float, horizons_years: Iterable[float], shocks_pp: Iterable[float], reinvest_coupons: bool = True, reinvest_real_rate_mode: str = "future_yield") -> pd.DataFrame:
    rows = []
    for h in horizons_years:
        for s in shocks_pp:
            rows.append(simulate_sale_scenario(params=params, annual_inflation=annual_inflation, horizon_years=h, shock_pp=s, reinvest_coupons=reinvest_coupons, reinvest_real_rate_mode=reinvest_real_rate_mode))
    return pd.DataFrame(rows)

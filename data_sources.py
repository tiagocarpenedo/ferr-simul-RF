from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
import io
import unicodedata

import pandas as pd
import requests

PACKAGE_API_URL = "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id=taxas-dos-titulos-ofertados-pelo-tesouro-direto"
FALLBACK_CSV_URL = "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv"


def normalize_col(s: str) -> str:
    s = str(s).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    for ch in [" ", "-", "/", ".", "(", ")", "%", "+"]:
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def parse_br_number(x):
    if pd.isna(x):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return None
    s = s.replace("\xa0", "").replace(" ", "")
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_date_any(x) -> Optional[date]:
    if pd.isna(x):
        return None
    if isinstance(x, date):
        return x
    s = str(x).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except Exception:
        return None


def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    norm_map = {normalize_col(c): c for c in df.columns}
    for cand in candidates:
        nc = normalize_col(cand)
        if nc in norm_map:
            return norm_map[nc]
    normalized = [(normalize_col(c), c) for c in df.columns]
    for cand in candidates:
        nc = normalize_col(cand)
        for n, original in normalized:
            if nc in n:
                return original
    return None


@dataclass
class TesouroColumns:
    title_type: str
    maturity: str
    base_date: str
    buy_rate: Optional[str]
    sell_rate: Optional[str]
    buy_pu: Optional[str]
    sell_pu: Optional[str]


def get_package_metadata(timeout: int = 30) -> dict:
    r = requests.get(PACKAGE_API_URL, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError("A API CKAN do Tesouro Transparente retornou success=false.")
    return data


def find_csv_url_from_metadata(metadata: dict) -> str:
    resources = metadata.get("result", {}).get("resources", [])
    csv_candidates = []
    for res in resources:
        name = str(res.get("name", ""))
        fmt = str(res.get("format", ""))
        url = res.get("url") or res.get("download_url")
        if not url:
            continue
        looks_csv = "csv" in fmt.lower() or str(url).lower().endswith(".csv")
        looks_price_tax = ("preço" in name.lower() or "preco" in name.lower() or "taxa" in name.lower() or "títulos ofertados" in name.lower() or "titulos ofertados" in name.lower())
        if looks_csv and looks_price_tax:
            csv_candidates.append(str(url))
    return csv_candidates[0] if csv_candidates else FALLBACK_CSV_URL


def fetch_tesouro_taxas_csv(timeout: int = 60) -> tuple[pd.DataFrame, str]:
    try:
        metadata = get_package_metadata(timeout=timeout)
        csv_url = find_csv_url_from_metadata(metadata)
    except Exception:
        csv_url = FALLBACK_CSV_URL
    r = requests.get(csv_url, timeout=timeout)
    r.raise_for_status()
    content = r.content
    try:
        df = pd.read_csv(io.BytesIO(content), sep=";", dtype=str, encoding="latin1", low_memory=False)
    except UnicodeDecodeError:
        df = pd.read_csv(io.BytesIO(content), sep=";", dtype=str, encoding="utf-8", low_memory=False)
    return df, csv_url


def detect_tesouro_columns(df: pd.DataFrame) -> TesouroColumns:
    title_type = _find_col(df, ["Tipo Titulo", "Tipo Título", "Tipo do Titulo", "Titulo"])
    maturity = _find_col(df, ["Data Vencimento", "Vencimento"])
    base_date = _find_col(df, ["Data Base", "Data Referencia", "Data Referência"])
    buy_rate = _find_col(df, ["Taxa Compra Manha", "Taxa Compra Manhã", "Taxa Compra"])
    sell_rate = _find_col(df, ["Taxa Venda Manha", "Taxa Venda Manhã", "Taxa Venda"])
    buy_pu = _find_col(df, ["PU Compra Manha", "PU Compra Manhã", "PU Compra", "Preco Compra", "Preço Compra"])
    sell_pu = _find_col(df, ["PU Venda Manha", "PU Venda Manhã", "PU Venda", "Preco Venda", "Preço Venda"])
    required = {"tipo do título": title_type, "vencimento": maturity, "data base": base_date}
    missing = [k for k, v in required.items() if v is None]
    if missing:
        raise ValueError("Não consegui detectar colunas obrigatórias no CSV do Tesouro. " + f"Colunas ausentes: {missing}. Colunas encontradas: {list(df.columns)}")
    return TesouroColumns(title_type, maturity, base_date, buy_rate, sell_rate, buy_pu, sell_pu)


def prepare_tesouro_dataset(df: pd.DataFrame) -> pd.DataFrame:
    cols = detect_tesouro_columns(df)
    out = df.copy()
    out["tipo"] = out[cols.title_type].astype(str)
    out["vencimento"] = out[cols.maturity].apply(parse_date_any)
    out["data_base"] = out[cols.base_date].apply(parse_date_any)
    out["taxa_compra_pct"] = out[cols.buy_rate].apply(parse_br_number) if cols.buy_rate else None
    out["taxa_venda_pct"] = out[cols.sell_rate].apply(parse_br_number) if cols.sell_rate else None
    out["pu_compra"] = out[cols.buy_pu].apply(parse_br_number) if cols.buy_pu else None
    out["pu_venda"] = out[cols.sell_pu].apply(parse_br_number) if cols.sell_pu else None
    out = out.dropna(subset=["tipo", "vencimento", "data_base"])
    return out[["tipo", "vencimento", "data_base", "taxa_compra_pct", "taxa_venda_pct", "pu_compra", "pu_venda"]].copy()


def latest_ipca_sem_coupon_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = prepare_tesouro_dataset(df)
    mask = out["tipo"].str.contains("IPCA", case=False, na=False) & out["tipo"].str.contains("Juros", case=False, na=False)
    out = out[mask].copy()
    if out.empty:
        return out
    latest = out["data_base"].max()
    out = out[out["data_base"] == latest].copy()
    out = out.sort_values(["vencimento", "tipo"]).reset_index(drop=True)
    return out


def row_label(row) -> str:
    venda = f"{row.taxa_venda_pct:.2f}%" if pd.notna(row.taxa_venda_pct) else "n/d"
    compra = f"{row.taxa_compra_pct:.2f}%" if pd.notna(row.taxa_compra_pct) else "n/d"
    return f"{row.tipo} | venc. {row.vencimento.strftime('%d/%m/%Y')} | venda {venda} | compra {compra}"


def format_date_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")

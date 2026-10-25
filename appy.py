"""
Real Exchange Rate Explorer
===========================

Streamlit app that builds a bilateral real exchange rate (RER) between any two
IMF countries (or the Euro area) from IMF SDMX 3.0 data.

Definitions
-----------
S(t)   = units of Country 2 currency per 1 unit of Country 1 currency
P1(t)  = monthly CPI of Country 1,  P2(t) = monthly CPI of Country 2
RER(t) = S(t) * P1(t) / P2(t)
RER*   = average of RER(t) over valid months in the selected sample
Real Index(t) = 100 * RER(t) / RER*

The IMF publishes exchange rates as local-currency units per US dollar
(XDC_USD).  With E_i(t) = LCU_i per USD, the cross rate is

    S(t) = E_2(t) / E_1(t)        (Country 2 currency per Country 1 currency)

Run with:  streamlit run app.py
"""

from __future__ import annotations

import math
import re
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from defusedxml import ElementTree as SafeET
from plotly.subplots import make_subplots
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# IMF API configuration
# ---------------------------------------------------------------------------
IMF_BASE = "https://api.imf.org/external/sdmx/3.0"
AGENCY = "IMF.STA"
CPI_FLOW = "CPI"
ER_FLOW = "ER"
CPI_KEY = "{iso}.CPI._T.IX.M"        # all-items CPI, index, monthly
ER_KEY = "{iso}.XDC_USD.PA_RT.M"     # LCU per USD, period average, monthly
EURO_AREA = "G163"                    # IMF code for the Euro area
USA = "USA"
START_MONTH = "1976-01"
REQUEST_TIMEOUT = 60
USER_AGENT = "rer-explorer/1.0 (Streamlit; IMF SDMX 3.0)"

# Used only if the IMF metadata endpoints cannot be reached. Countries listed
# here had both CPI and exchange-rate series in the IMF catalogue; actual
# monthly coverage is still checked when data are downloaded.
FALLBACK_COUNTRIES: dict[str, str] = {
    "ABW": "Aruba, Kingdom of the Netherlands",
    "AFG": "Afghanistan, Islamic Republic of",
    "AGO": "Angola",
    "AIA": "Anguilla, United Kingdom-British Overseas Territory",
    "ALB": "Albania",
    "ANT": "Netherlands Antilles",
    "ARE": "United Arab Emirates",
    "ARG": "Argentina",
    "ARM": "Armenia, Republic of",
    "ATG": "Antigua and Barbuda",
    "AUS": "Australia",
    "AUT": "Austria",
    "AZE": "Azerbaijan, Republic of",
    "BDI": "Burundi",
    "BEL": "Belgium",
    "BEN": "Benin",
    "BFA": "Burkina Faso",
    "BGD": "Bangladesh",
    "BGR": "Bulgaria",
    "BHR": "Bahrain, Kingdom of",
    "BHS": "Bahamas, The",
    "BIH": "Bosnia and Herzegovina",
    "BLR": "Belarus, Republic of",
    "BLZ": "Belize",
    "BOL": "Bolivia",
    "BRA": "Brazil",
    "BRB": "Barbados",
    "BRN": "Brunei Darussalam",
    "BTN": "Bhutan",
    "BWA": "Botswana",
    "CAF": "Central African Republic",
    "CAN": "Canada",
    "CHE": "Switzerland",
    "CHL": "Chile",
    "CHN": "China, People's Republic of",
    "CIV": "C\u00f4te d'Ivoire",
    "CMR": "Cameroon",
    "COD": "Congo, Democratic Republic of the",
    "COG": "Congo, Republic of",
    "COL": "Colombia",
    "COM": "Comoros, Union of the",
    "CPV": "Cabo Verde",
    "CRI": "Costa Rica",
    "CUW": "Cura\u00e7ao, Kingdom of the Netherlands",
    "CYM": "Cayman Islands",
    "CYP": "Cyprus",
    "CZE": "Czech Republic",
    "DEU": "Germany",
    "DJI": "Djibouti",
    "DMA": "Dominica",
    "DNK": "Denmark",
    "DOM": "Dominican Republic",
    "DZA": "Algeria",
    "ECU": "Ecuador",
    "EGY": "Egypt, Arab Republic of",
    "ESP": "Spain",
    "EST": "Estonia, Republic of",
    "ETH": "Ethiopia, The Federal Democratic Republic of",
    "FIN": "Finland",
    "FJI": "Fiji, Republic of",
    "FRA": "France",
    "FSM": "Micronesia, Federated States of",
    "GAB": "Gabon",
    "GBR": "United Kingdom",
    "GEO": "Georgia",
    "GHA": "Ghana",
    "GIN": "Guinea",
    "GLP": "Guadeloupe",
    "GMB": "Gambia, The",
    "GNB": "Guinea-Bissau",
    "GNQ": "Equatorial Guinea, Republic of",
    "GRC": "Greece",
    "GRD": "Grenada",
    "GRL": "Greenland",
    "GTM": "Guatemala",
    "GUY": "Guyana",
    "HKG": "Hong Kong Special Administrative Region, People's Republic of China",
    "HND": "Honduras",
    "HRV": "Croatia, Republic of",
    "HTI": "Haiti",
    "HUN": "Hungary",
    "IDN": "Indonesia",
    "IND": "India",
    "IRL": "Ireland",
    "IRN": "Iran, Islamic Republic of",
    "IRQ": "Iraq",
    "ISL": "Iceland",
    "ISR": "Israel",
    "ITA": "Italy",
    "JAM": "Jamaica",
    "JOR": "Jordan",
    "JPN": "Japan",
    "KAZ": "Kazakhstan, Republic of",
    "KEN": "Kenya",
    "KGZ": "Kyrgyz Republic",
    "KHM": "Cambodia",
    "KIR": "Kiribati",
    "KNA": "St. Kitts and Nevis",
    "KOR": "Korea, Republic of",
    "KOS": "Kosovo, Republic of",
    "KWT": "Kuwait",
    "LAO": "Lao People's Democratic Republic",
    "LBN": "Lebanon",
    "LBR": "Liberia",
    "LBY": "Libya",
    "LCA": "St. Lucia",
    "LKA": "Sri Lanka",
    "LSO": "Lesotho, Kingdom of",
    "LTU": "Lithuania, Republic of",
    "LUX": "Luxembourg",
    "LVA": "Latvia, Republic of",
    "MAC": "Macao Special Administrative Region, People's Republic of China",
    "MAR": "Morocco",
    "MDA": "Moldova, Republic of",
    "MDG": "Madagascar, Republic of",
    "MDV": "Maldives",
    "MEX": "Mexico",
    "MKD": "North Macedonia, Republic of",
    "MLI": "Mali",
    "MLT": "Malta",
    "MMR": "Myanmar",
    "MNE": "Montenegro",
    "MNG": "Mongolia",
    "MOZ": "Mozambique, Republic of",
    "MRT": "Mauritania, Islamic Republic of",
    "MSR": "Montserrat, United Kingdom-British Overseas Territory",
    "MTQ": "Martinique",
    "MUS": "Mauritius",
    "MWI": "Malawi",
    "MYS": "Malaysia",
    "NAM": "Namibia",
    "NCL": "New Caledonia",
    "NER": "Niger",
    "NGA": "Nigeria",
    "NIC": "Nicaragua",
    "NLD": "Netherlands, The",
    "NOR": "Norway",
    "NPL": "Nepal",
    "NRU": "Naoero, Republic of",
    "NZL": "New Zealand",
    "OMN": "Oman",
    "PAK": "Pakistan",
    "PAN": "Panama",
    "PER": "Peru",
    "PHL": "Philippines",
    "PLW": "Palau, Republic of",
    "PNG": "Papua New Guinea",
    "POL": "Poland, Republic of",
    "PRT": "Portugal",
    "PRY": "Paraguay",
    "QAT": "Qatar",
    "ROU": "Romania",
    "RUS": "Russian Federation",
    "RWA": "Rwanda",
    "SAU": "Saudi Arabia",
    "SDN": "Sudan",
    "SEN": "Senegal",
    "SGP": "Singapore",
    "SLB": "Solomon Islands",
    "SLE": "Sierra Leone",
    "SLV": "El Salvador",
    "SMR": "San Marino, Republic of",
    "SOM": "Somalia",
    "SRB": "Serbia, Republic of",
    "SSD": "South Sudan, Republic of",
    "STP": "S\u00e3o Tom\u00e9 and Pr\u00edncipe, Democratic Republic of",
    "SUR": "Suriname",
    "SVK": "Slovak Republic",
    "SVN": "Slovenia, Republic of",
    "SWE": "Sweden",
    "SWZ": "Eswatini, Kingdom of",
    "SXM": "Sint Maarten, Kingdom of the Netherlands",
    "SYC": "Seychelles",
    "SYR": "Syrian Arab Republic",
    "TCD": "Chad",
    "TGO": "Togo",
    "THA": "Thailand",
    "TJK": "Tajikistan, Republic of",
    "TLS": "Timor-Leste, Democratic Republic of",
    "TON": "Tonga",
    "TTO": "Trinidad and Tobago",
    "TUN": "Tunisia",
    "TUR": "T\u00fcrkiye, Republic of",
    "TUV": "Tuvalu",
    "TZA": "Tanzania, United Republic of",
    "UGA": "Uganda",
    "UKR": "Ukraine",
    "URY": "Uruguay",
    "USA": "United States",
    "UZB": "Uzbekistan, Republic of",
    "VCT": "St. Vincent and the Grenadines",
    "VEN": "Venezuela, Rep\u00fablica Bolivariana de",
    "VNM": "Vietnam",
    "VUT": "Vanuatu",
    "WSM": "Samoa",
    "YEM": "Yemen, Republic of",
    "ZAF": "South Africa",
    "ZMB": "Zambia",
    "ZWE": "Zimbabwe",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
@st.cache_resource
def _session() -> requests.Session:
    """Shared HTTP session with retries for transient IMF API errors."""
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = USER_AGENT
    return session


class IMFDataError(RuntimeError):
    """Raised when the IMF API returns an unusable response."""


def _local(tag: str) -> str:
    """Strip an XML namespace: '{ns}Obs' -> 'Obs'."""
    return tag.rsplit("}", 1)[-1]


_PERIOD_RE = re.compile(r"^(\d{4})-?M?(\d{1,2})")


def _to_period(time_period: str | None) -> pd.Period | None:
    """Convert IMF monthly periods ('1976-M01', '1976-01', '1976-01-01')."""
    if not time_period:
        return None
    m = _PERIOD_RE.match(time_period.strip())
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return None
    return pd.Period(year=year, month=month, freq="M")


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def parse_sdmx_xml(xml_text: str) -> pd.Series:
    """Parse an SDMX 3.0 data message (structure-specific or generic XML)
    into a float Series indexed by monthly Period."""
    root = SafeET.fromstring(xml_text)
    values: dict[pd.Period, float] = {}
    for el in root.iter():
        if _local(el.tag) != "Obs":
            continue
        # Structure-specific format: <Obs TIME_PERIOD="1976-M01" OBS_VALUE="1.2"/>
        tp = el.attrib.get("TIME_PERIOD")
        val = el.attrib.get("OBS_VALUE")
        # Generic format: <ObsDimension value=".."/><ObsValue value=".."/>
        if tp is None or val is None:
            for child in el:
                name = _local(child.tag)
                if name in ("ObsDimension", "ObsKey") and tp is None:
                    tp = child.attrib.get("value")
                    if tp is None:  # ObsKey/Value nesting
                        for sub in child:
                            if sub.attrib.get("id") == "TIME_PERIOD":
                                tp = sub.attrib.get("value")
                elif name == "ObsValue" and val is None:
                    val = child.attrib.get("value")
        period, number = _to_period(tp), _to_float(val)
        if period is not None and number is not None:
            values[period] = number
    if not values:
        return pd.Series(dtype="float64")
    series = pd.Series(values, dtype="float64").sort_index()
    series.index = pd.PeriodIndex(series.index, freq="M")
    return series


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_series(flow: str, key: str) -> pd.Series:
    """Download one monthly IMF series from START_MONTH onward.

    Returns an empty Series when the IMF has no data for the key (HTTP 404 /
    empty dataset). Raises IMFDataError for other failures.
    """
    url = f"{IMF_BASE}/data/dataflow/{AGENCY}/{flow}/+/{key}"
    common = "dimensionAtObservation=TIME_PERIOD&detail=full&includeHistory=false"
    attempts = [
        f"{url}?c[TIME_PERIOD]=ge:{START_MONTH}-01&{common}",
        f"{url}?{common}",  # retry without the time filter if it is rejected
    ]
    last_error = "unknown error"
    for attempt in attempts:
        try:
            resp = _session().get(
                attempt,
                headers={"Accept": "application/xml"},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            continue
        if resp.status_code == 404:  # SDMX "NoResultsFound"
            return pd.Series(dtype="float64")
        if resp.status_code != 200:
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            continue
        try:
            series = parse_sdmx_xml(resp.text)
        except Exception as exc:  # malformed XML
            last_error = f"could not parse response ({exc})"
            continue
        start = pd.Period(START_MONTH, freq="M")
        return series[series.index >= start]
    raise IMFDataError(f"{flow}/{key}: {last_error}")


def _available_countries(flow: str, wildcard_key: str) -> set[str]:
    """Countries that have data for a wildcard key, via the availability API."""
    url = (
        f"{IMF_BASE}/availability/dataflow/{AGENCY}/{flow}/%2B/"
        f"{wildcard_key}/COUNTRY?mode=available&references=none"
    )
    resp = _session().get(
        url, headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    found: set[str] = set()
    for constraint in resp.json().get("data", {}).get("dataConstraints", []):
        for region in constraint.get("cubeRegions", []):
            for comp in region.get("keyValues", []) + region.get("components", []):
                if comp.get("id") != "COUNTRY":
                    continue
                for v in comp.get("values", []):
                    code = v.get("value") if isinstance(v, dict) else v
                    if code:
                        found.add(str(code))
    return found


def _country_names() -> dict[str, str]:
    """Country names from the IMF CL_COUNTRY codelist."""
    url = f"{IMF_BASE}/structure/codelist/*/CL_COUNTRY/latest?detail=full&references=none"
    resp = _session().get(
        url, headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    names: dict[str, str] = {}
    for codelist in resp.json().get("data", {}).get("codelists", []):
        for code in codelist.get("codes", []):
            cid = code.get("id")
            label = (code.get("names") or {}).get("en") or code.get("name") or cid
            if cid:
                names[cid] = label
    return names


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_countries() -> tuple[dict[str, str], str]:
    """Return ({code: name}, source note). Euro area is always included."""
    note = "IMF metadata API"
    try:
        names = _country_names()
    except Exception:
        names, note = {}, "built-in list (IMF metadata unavailable)"
    try:
        cpi = _available_countries(CPI_FLOW, CPI_KEY.format(iso="*"))
        er = _available_countries(ER_FLOW, ER_KEY.format(iso="*")) | {USA}
        codes = {c for c in cpi & er if re.fullmatch(r"[A-Z]{3}", c)}
    except Exception:
        codes = set()
    if not codes:
        codes = set(FALLBACK_COUNTRIES)
        if note == "IMF metadata API":
            note = "built-in list (IMF availability API unavailable)"
    countries = {
        c: names.get(c) or FALLBACK_COUNTRIES.get(c) or c for c in sorted(codes)
    }
    countries[EURO_AREA] = "Euro Area"
    return countries, note


# ---------------------------------------------------------------------------
# Economics
# ---------------------------------------------------------------------------
def exchange_rate_vs_usd(iso: str) -> pd.Series:
    """LCU per USD. The US dollar is 1 USD per USD by definition."""
    if iso == USA:
        months = pd.period_range(START_MONTH, pd.Period(date.today(), freq="M"), freq="M")
        return pd.Series(1.0, index=months, dtype="float64")
    return fetch_series(ER_FLOW, ER_KEY.format(iso=iso))


def build_dataset(c1: str, c2: str) -> pd.DataFrame:
    """Monthly frame with raw inputs, S(t) and RER(t). Gaps remain NaN."""
    e1 = exchange_rate_vs_usd(c1)
    e2 = exchange_rate_vs_usd(c2)
    p1 = fetch_series(CPI_FLOW, CPI_KEY.format(iso=c1))
    p2 = fetch_series(CPI_FLOW, CPI_KEY.format(iso=c2))

    df = pd.concat({"E1": e1, "E2": e2, "P1": p1, "P2": p2}, axis=1)
    if df.empty:
        return df
    full_index = pd.period_range(df.index.min(), df.index.max(), freq="M")
    df = df.reindex(full_index).astype("float64")
    df = df.where(df > 0)  # non-positive prices / rates are not usable

    df["S"] = df["E2"] / df["E1"]                 # C2 currency per 1 C1 currency
    df["RER"] = df["S"] * df["P1"] / df["P2"]
    df.index.name = "month"
    return df


def redenomination_flags(df: pd.DataFrame, factor: float = 10.0) -> list[str]:
    """Months where a USD rate moves by more than `factor` in one month,
    which usually signals a currency redenomination or unit change."""
    flags: list[str] = []
    for col in ("E1", "E2"):
        s = df[col].dropna()
        if len(s) < 2:
            continue
        ratio = s / s.shift(1)
        jumps = ratio[(ratio > factor) | (ratio < 1 / factor)]
        flags.extend(f"{col} at {p}" for p in jumps.index)
    return flags


def coverage_table(df: pd.DataFrame, labels: dict[str, str]) -> pd.DataFrame:
    rows = []
    for col, label in labels.items():
        s = df[col].dropna() if col in df else pd.Series(dtype="float64")
        if s.empty:
            rows.append({"Series": label, "First": "—", "Last": "—",
                         "Observations": 0, "Missing months inside span": "—"})
            continue
        span = (s.index.max() - s.index.min()).n + 1
        rows.append({
            "Series": label,
            "First": str(s.index.min()),
            "Last": str(s.index.max()),
            "Observations": int(s.size),
            "Missing months inside span": int(span - s.size),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Real Exchange Rate Explorer", layout="wide")
st.title("Real Exchange Rate Explorer")
st.caption(
    "Bilateral real exchange rates from IMF monthly CPI and exchange-rate data "
    f"(SDMX 3.0 API), from {START_MONTH} where available."
)

with st.spinner("Loading IMF country list…"):
    countries, country_source = load_countries()

codes = sorted(countries, key=lambda c: (c != EURO_AREA, countries[c].lower()))


def _fmt(code: str) -> str:
    return f"{countries.get(code, code)} ({code})"


with st.sidebar:
    st.header("Countries")
    default_1 = codes.index(EURO_AREA) if EURO_AREA in codes else 0
    default_2 = codes.index(USA) if USA in codes else min(1, len(codes) - 1)
    c1 = st.selectbox("Country 1", codes, index=default_1, format_func=_fmt)
    c2 = st.selectbox("Country 2", codes, index=default_2, format_func=_fmt)
    st.caption(f"Country list source: {country_source}.")

if c1 == c2:
    st.info("Choose two different countries.")
    st.stop()

name1, name2 = countries.get(c1, c1), countries.get(c2, c2)
s_unit = f"{name2} currency per 1 {name1} currency"

try:
    with st.spinner(f"Downloading IMF data for {name1} and {name2}…"):
        data = build_dataset(c1, c2)
except IMFDataError as exc:
    st.error(f"The IMF API request failed: {exc}. Please try again in a moment.")
    st.stop()
except requests.RequestException as exc:
    st.error(f"Could not reach the IMF API: {exc}")
    st.stop()

series_labels = {
    "E1": f"{name1}: LCU per USD",
    "E2": f"{name2}: LCU per USD",
    "P1": f"{name1}: CPI",
    "P2": f"{name2}: CPI",
}
missing = [series_labels[c] for c in series_labels if c not in data or data[c].dropna().empty]
if missing:
    st.warning("The IMF returned no monthly data for: " + "; ".join(missing) + ".")

valid_any = data.dropna(subset=["S"], how="all") if not data.empty else data
if data.empty or valid_any.empty:
    st.error(
        "There is no overlapping exchange-rate data for this pair, so S(t) cannot "
        "be computed. Try another pair."
    )
    st.stop()

# Sample window: anything with a valid nominal rate (RER may be shorter).
first, last = valid_any.index.min(), valid_any.index.max()
months = [str(p) for p in pd.period_range(first, last, freq="M")]

with st.sidebar:
    st.header("Sample period")
    start_label, end_label = st.select_slider(
        "Start and end month",
        options=months,
        value=(months[0], months[-1]),
        key=f"window_{c1}_{c2}",  # resets the window when countries change
    )
    st.header("Chart")
    view = st.radio("Show", ["Real", "Nominal", "Both"], index=2, horizontal=True)
    log_nominal = st.checkbox("Log scale for nominal S(t)", value=False)

start_p, end_p = pd.Period(start_label, freq="M"), pd.Period(end_label, freq="M")
sample = data.loc[(data.index >= start_p) & (data.index <= end_p)].copy()

valid_rer = sample["RER"].dropna()
rer_star = float(valid_rer.mean()) if not valid_rer.empty else float("nan")
sample["RER_star"] = rer_star
sample["Real_Index"] = 100.0 * sample["RER"] / rer_star if valid_rer.size else float("nan")

# ---- headline numbers -----------------------------------------------------
m1, m2, m3, m4 = st.columns(4)
m1.metric("RER* (sample mean of RER)", f"{rer_star:,.6g}" if valid_rer.size else "n/a")
m2.metric("Valid RER months", f"{valid_rer.size} / {len(sample)}")
last_real = sample["Real_Index"].dropna()
m3.metric(
    "Latest Real Index",
    f"{last_real.iloc[-1]:,.1f}" if not last_real.empty else "n/a",
    help=f"Month: {last_real.index[-1]}" if not last_real.empty else None,
)
last_s = sample["S"].dropna()
m4.metric(
    "Latest S(t)",
    f"{last_s.iloc[-1]:,.6g}" if not last_s.empty else "n/a",
    help=f"{s_unit}; month: {last_s.index[-1]}" if not last_s.empty else s_unit,
)

if valid_rer.empty and view != "Nominal":
    st.warning(
        "No month in the selected sample has CPI data for both countries and an "
        "exchange rate, so the real index cannot be computed. Showing nominal S(t) "
        "only."
    )
    view = "Nominal"

# ---- chart ----------------------------------------------------------------
x = sample.index.to_timestamp()
real_trace = go.Scatter(
    x=x, y=sample["Real_Index"], name="Real Index (RER* = 100)",
    mode="lines", connectgaps=False, line=dict(width=2, color="#1f6fb2"),
    hovertemplate="%{x|%Y-%m}<br>Real Index: %{y:.2f}<extra></extra>",
)
nominal_trace = go.Scatter(
    x=x, y=sample["S"], name=f"S(t): {s_unit}",
    mode="lines", connectgaps=False, line=dict(width=2, color="#d9822b"),
    hovertemplate="%{x|%Y-%m}<br>S: %{y:.6g}<extra></extra>",
)
nominal_axis_type = "log" if log_nominal else "linear"

if view == "Real":
    fig = go.Figure(real_trace)
    fig.add_hline(y=100, line_dash="dash", line_color="gray",
                  annotation_text="RER* = 100", annotation_position="top left")
    fig.update_yaxes(title_text="Real Index (RER* = 100)")
elif view == "Nominal":
    fig = go.Figure(nominal_trace)
    fig.update_yaxes(title_text=s_unit, type=nominal_axis_type)
else:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(real_trace, secondary_y=False)
    fig.add_trace(nominal_trace, secondary_y=True)
    fig.add_hline(y=100, line_dash="dash", line_color="gray", secondary_y=False)
    fig.update_yaxes(title_text="Real Index (RER* = 100)", secondary_y=False)
    fig.update_yaxes(title_text=s_unit, secondary_y=True, type=nominal_axis_type,
                     showgrid=False)

fig.update_layout(
    title=f"{name1} vs {name2}, {start_label} to {end_label}",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    margin=dict(l=10, r=10, t=80, b=10),
    height=520,
)
fig.update_xaxes(title_text="Month", rangeslider_visible=False)
st.plotly_chart(fig)

st.caption(
    f"RER(t) = S(t) × P1(t) / P2(t), with S(t) = {s_unit}. A rise in the Real "
    f"Index means a real appreciation of the {name1} currency against the "
    f"{name2} currency relative to the sample average. Months with a missing "
    "input are left as gaps and excluded from RER*."
)

# ---- CSV download ---------------------------------------------------------
export = pd.DataFrame({
    "month": sample.index.astype(str),
    f"{c1}_LCU_per_USD": sample["E1"].to_numpy(),
    f"{c2}_LCU_per_USD": sample["E2"].to_numpy(),
    f"S_{c2}_per_{c1}": sample["S"].to_numpy(),
    f"CPI_{c1}": sample["P1"].to_numpy(),
    f"CPI_{c2}": sample["P2"].to_numpy(),
    "RER": sample["RER"].to_numpy(),
    "valid_for_RER_star": sample["RER"].notna().to_numpy(),
    "RER_star": sample["RER_star"].to_numpy(),
    "Real_Index": sample["Real_Index"].to_numpy(),
})
st.download_button(
    "Download CSV (selected sample)",
    data=export.to_csv(index=False).encode("utf-8"),
    file_name=f"rer_{c1}_{c2}_{start_label}_{end_label}.csv",
    mime="text/csv",
)

# ---- diagnostics ----------------------------------------------------------
with st.expander("Data coverage and notes"):
    st.dataframe(coverage_table(data, series_labels), hide_index=True)
    flags = redenomination_flags(data)
    if flags:
        st.warning(
            "Possible currency redenomination or unit change (USD rate moved more "
            "than 10× in one month): " + ", ".join(flags) + ". Values across such a "
            "break are not comparable; consider choosing a sample that avoids it."
        )
    st.markdown(
        f"""
- **Source:** IMF SDMX 3.0 API, dataflows `{AGENCY}/{ER_FLOW}` (key
  `ISO3.XDC_USD.PA_RT.M`, period-average LCU per USD) and `{AGENCY}/{CPI_FLOW}`
  (key `ISO3.CPI._T.IX.M`, all-items CPI index).
- **Conversion:** S(t) = E₂(t) / E₁(t), where Eᵢ is local currency per USD.
  The US rate is 1 by definition.
- **Gaps:** months are never interpolated. A month counts toward RER* only
  when both exchange rates and both CPIs are present.
- **CPI base years** differ across countries; they cancel out in the
  normalised Real Index but affect the level of RER(t).
- Data are cached for 6 hours. Downloaded {date.today():%Y-%m-%d}.
"""
    )

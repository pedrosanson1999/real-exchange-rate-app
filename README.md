# real-exchange-rate-app
Real Exchange Rate Explorer

An interactive Streamlit app that builds the bilateral real exchange rate (RER) between any two IMF countries, or a country and the Euro area. It uses monthly CPI and exchange-rate data from the IMF SDMX 3.0 API, starting in January 1976 where data are available.

Features
Choose Country 1 and Country 2 from IMF countries plus the Euro area (IMF code G163).
Downloads monthly IMF CPI and exchange-rate data from 1976-01 onward.
Choose the start and end months of the sample. RER* and the Real Index are recalculated automatically whenever the dates change.
Interactive Plotly charts that show Real, Nominal, or Both. Both uses separate left and right y-axes.
Nominal S(t) is plotted in actual currency units and is never normalised. A log-scale option helps for high-inflation currencies.
CSV download with every monthly observation and calculation in the selected sample.
A data-coverage table showing first and last observations and missing months for each series. The app also flags likely currency redenominations.
Economics
Symbol	Definition
E₁(t), E₂(t)	IMF exchange rate, local currency units (LCU) per USD, monthly period average
S(t)	Units of Country 2 currency per 1 unit of Country 1 currency = E₂(t) / E₁(t)
P₁(t), P₂(t)	Monthly all-items CPI of Country 1 and Country 2
RER(t)	S(t) × P₁(t) / P₂(t)
RER*	Average of RER(t) over valid months in the selected sample
Real Index(t)	100 × RER(t) / RER*

The IMF publishes rates as LCU per USD, so the app converts them to the S(t) direction. For example, with Country 1 = Euro area and Country 2 = United States, S(t) = 1 / (EUR per USD) = USD per EUR. The US rate is set to 1 by definition.

A month is valid only when E₁, E₂, P₁ and P₂ are all available and positive. Missing months are never interpolated. They appear as gaps in the chart and are excluded from RER*.

Interpretation: a Real Index above 100 means Country 1's currency is really stronger against Country 2's than its sample average. In that case Country 1's goods are relatively more expensive.

IMF API

Base URL: https://api.imf.org/external/sdmx/3.0

Data	Dataflow	Series key
CPI (index, all items, monthly)	IMF.STA/CPI	{ISO3}.CPI._T.IX.M
Exchange rate (LCU per USD, period average, monthly)	IMF.STA/ER	{ISO3}.XDC_USD.PA_RT.M

Example request:

https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/+/USA.CPI._T.IX.M?c[TIME_PERIOD]=ge:1976-01-01&dimensionAtObservation=TIME_PERIOD

The country list comes from the IMF CL_COUNTRY codelist. It is filtered by the availability endpoint to countries that have both series. If the metadata endpoints are unreachable, the app falls back to a built-in list.

Run locally

Requires Python 3.12.

bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py

The app opens at http://localhost:8501.

Deploy from GitHub (Streamlit Community Cloud)
Push app.py, requirements.txt and README.md to a GitHub repository.
Go to https://share.streamlit.io, choose Create app, and pick your repo and branch. Set the main file to app.py.
Under Advanced settings, select Python 3.12, then deploy.
Data caveats
Coverage varies. Many countries have monthly CPI or exchange-rate data only for recent decades, and some series have gaps. The app uses whatever overlap exists. Check the coverage table under Data coverage and notes.
Euro area (G163) exchange-rate data generally begin in 1999. Earlier months are therefore not valid for pairs involving the Euro area.
Euro-area member countries may report pre-1999 rates in legacy national currency or converted to euros. A level break in January 1999 signals legacy units.
Redenominations. For example, a currency that removed zeros may show a jump if the IMF did not back-convert the series. The app flags USD-rate moves of more than 10× in one month. Choose a sample that avoids such breaks.
CPI base years differ across countries. This affects the level of RER(t) but cancels out in the Real Index.
API responses are cached for 6 hours and the country list for 24 hours.
Files
app.py            Streamlit app: data download, calculations, charts, CSV export
requirements.txt  Python dependencies
README.md         This file

"""Gemensamt analysfönster, as-of och standardhorisonter för fond-rapporten.

Fönstret startar vid EGEN:s inception – den första dagen EGEN:s verkliga (REAL)
portfölj har en värderad position. Före dess ligger EGEN-serien platt på bas 100
(inget innehav), och en jämförelse mot referensportföljen PA vore missvisande.
Alla serier rebaseras till 100 vid detta datum och skärs av tidigare, så att EGEN
mäts mot PA (referensen som ska slås) och externa benchmarks över exakt EGEN:s
livslängd.

Inceptionen härleds ur datan – aldrig hårdkodad. As-of styr fönstrets slut
(default = senaste datat i BI-filen); alla horisonter räknas relativt as-of och
serierna skärs till [inception, as_of].
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .data import BIData

INCEPTION_SERIES = "PORT_EGEN_REAL"
BASE_INDEX = 100.0
RETURN_TOLERANCE = 1e-9  # daglig RET under detta räknas som noll (platt förhistoria)
ONE_YEAR_DAYS = 365.25


def derive_inception(data: BIData) -> pd.Timestamp:
    """EGEN:s inception = ankardagen (bas 100) före första värderade REAL-avkastningen.

    Före inception saknar EGEN innehav och REAL-indexet ligger platt på bas 100.
    Den första dagen med en icke-noll avkastning är dagen då positionen först
    värderas mot föregående stängning; ankardagen (den sista platta bas-100-dagen)
    är dagen innan. Härleds ur ``PORT_EGEN_REAL`` – ingen hårdkodning.
    """
    sub = data.fact_daily[data.fact_daily["Series_ID"] == INCEPTION_SERIES]
    if sub.empty:
        raise KeyError(f"Inceptionserien saknas i Fact_Series_Daily: {INCEPTION_SERIES}")
    sub = sub.sort_values("Date")
    moved = sub[sub["RET"].abs() > RETURN_TOLERANCE]
    if moved.empty:
        raise ValueError(
            f"{INCEPTION_SERIES} har ingen avkastning – inception kan inte härledas."
        )
    first_move = moved["Date"].iloc[0]
    before = sub[sub["Date"] < first_move]
    if before.empty:
        # Ingen platt förhistoria: seriens första dag är inceptionen.
        return pd.Timestamp(sub["Date"].iloc[0])
    return pd.Timestamp(before["Date"].iloc[-1])


def resolve_as_of(data: BIData, as_of: str | pd.Timestamp | None) -> pd.Timestamp:
    """As-of-datum. Default = senaste datat i BI-filen. Får inte ligga efter det."""
    latest = pd.Timestamp(data.fact_daily["Date"].max())
    if as_of is None:
        return latest
    ts = pd.Timestamp(as_of).normalize()
    if ts > latest:
        raise ValueError(
            f"--as-of {ts.date()} ligger efter senaste datat i BI-filen ({latest.date()})."
        )
    return ts


@dataclass(frozen=True)
class Horizon:
    """En rapporthorisont relativt as-of, med tillgänglighet och rätt avkastningsmått."""

    key: str  # 'YTD' | '1Y' | '3Y' | 'Since_Start'
    label: str  # kort namn för kolumnrubrik
    start: pd.Timestamp
    end: pd.Timestamp  # = as_of
    available: bool
    measure: str  # 'cumulative' (<1 år) | 'cagr' (>=1 år)
    span_years: float
    note: str  # tomt om tillgänglig; annars orsak till utelämnandet

    def date_range(self) -> str:
        return f"{self.start.date()} – {self.end.date()}"


def build_horizons(inception: pd.Timestamp, as_of: pd.Timestamp) -> list[Horizon]:
    """Standardhorisonterna YTD · 1Y · 3Y · Sedan start relativt as-of.

    En horisont är tillgänglig endast om dess startdatum ligger på eller efter
    inceptionen – annars skulle fönstret inte rymma hela horisonten. 3Y faller ut
    på exakt samma villkor (fönstret måste rymma tre år), och gate:as därmed
    automatiskt tills det finns tre års historik. Måttet är kumulativ avkastning
    för horisonter under ett år (YTD) och CAGR för ett år och längre.
    """
    specs = [
        ("YTD", "YTD", pd.Timestamp(year=as_of.year, month=1, day=1)),
        ("1Y", "1 år", as_of - pd.DateOffset(years=1)),
        ("3Y", "3 år", as_of - pd.DateOffset(years=3)),
        ("Since_Start", "Sedan start", inception),
    ]
    one_year_ago = as_of - pd.DateOffset(years=1)
    horizons: list[Horizon] = []
    for key, label, start in specs:
        span_years = (as_of - start).days / ONE_YEAR_DAYS
        available = start >= inception
        # Måttet avgörs av kalenderdefinitionen, inte av bråkdelar av dagar: en
        # horisont som spänner minst ett kalenderår (start <= as_of − 1 år)
        # annualiseras (CAGR); kortare horisonter (YTD, eller "sedan start" innan
        # EGEN fyllt ett år) redovisas kumulativt och annualiseras aldrig.
        measure = "cagr" if start <= one_year_ago else "cumulative"
        if available:
            note = ""
        elif key == "3Y":
            note = (
                f"Kräver 3 års data (fönstret är {(as_of - inception).days / ONE_YEAR_DAYS:.1f} år)."
            )
        else:
            note = f"Kräver historik från {start.date()}; fönstret startar {inception.date()}."
        horizons.append(
            Horizon(
                key=key,
                label=label,
                start=pd.Timestamp(start),
                end=pd.Timestamp(as_of),
                available=available,
                measure=measure,
                span_years=span_years,
                note=note,
            )
        )
    return horizons


def rebase_series(
    idx: pd.Series, inception: pd.Timestamp, as_of: pd.Timestamp, base: float = BASE_INDEX
) -> pd.Series:
    """Rebasera en datumindexerad IDX-serie till ``base`` vid inceptionen.

    Nivån vid inceptionen tas som senast kända värde på eller före inceptionen
    (``asof``). När inceptionen är en handelsdag i serien – vilket den är för
    samtliga rapportserier – blir första punkten exakt ``base``. Serien skärs till
    [inception, as_of].
    """
    idx = idx.sort_index()
    anchor_level = idx.asof(inception)
    if pd.isna(anchor_level) or anchor_level == 0:
        raise ValueError(
            f"Kan inte rebasera: ingen giltig nivå vid inceptionen {inception.date()}."
        )
    window = idx[(idx.index >= inception) & (idx.index <= as_of)]
    return window / float(anchor_level) * base

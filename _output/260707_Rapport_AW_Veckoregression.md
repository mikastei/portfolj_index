# Slutrapport: Veckoregression för Beta/Alfa/R² mot policyreferenserna

**Datum:** 2026-07-07
**Branch:** `feat/veckoregression` → mergad till `main`
**Commits:** `9032df6` (feature), `5f45a02` (merge)

## Vad som gjorts

Regressionsbasen för Beta/Alfa/R² mot policyreferenserna (POLICY_EGEN, POLICY_PA)
är bytt från dags- till veckodata i fond-rapporten, enligt beslutet efter att
dagsdatans R² 0,54–0,58 visats vara en mätartefakt av strukturell NAV-lagg.

- **Veckoaggregering** (`weekly_returns` i `tools/fond_rapport/policy.py`):
  dagsavkastningar kapitaliseras per vecka som slutar fredag (W-FRI-buckets);
  infaller helgdag slutar veckan på närmast föregående handelsdag. REAL- och
  policyserien alignas dagligen (inner join) före aggregeringen så att båda
  veckoserier bygger på exakt samma handelsdagar.
- **Alfa annualiseras** nu som (1 + alfa_vecka)^52 − 1 (tidigare ^252 på dagsbas).
- **R²-spärren 0,70** och den **datumstyrda preliminär-markeringen**
  (inception + 3 år) är oförändrade.
- **Dagsserierna behålls oförändrade** för grafer och övriga KPI:er – bytet
  gäller enbart regressionen.
- **Rapportblocket** redovisar veckobasen och skälet (NAV-lagg → felalignade
  dagsavkastningar → R² nedtryckt, beta biasad mot noll) i metodtexten och
  fotnoten, samt att ~52 obs/år ger breda konfidensintervall tills historiken
  växer. Obs-kolumnen är omdöpt till "Obs (veckor)".

## Nya resultat (fönster 2024-08-21 – 2026-07-06, 99 veckoobservationer)

| Regression | R² | Beta | Alfa (ann.) | Obs (veckor) |
|---|---|---|---|---|
| EGEN REAL vs POLICY_EGEN (90/10) | **0,745** | **0,662** | **+0,90 %/år** | 99 |
| PA REAL vs POLICY_PA (85/15) | **0,753** | **0,689** | **−1,25 %/år** | 99 |

Jämfört med dagsbasen (R² 0,54–0,58, beta ~0,50, allt undertryckt av spärren):
båda regressionerna passerar nu 0,70-spärren och Beta/Alfa visas i rapporten,
med preliminär-markering till 2027-08-21 (datumstyrd). Beta ligger fortfarande
under naiv förväntan för 90/85 % aktieandel – kvarvarande utjämning i vecko-
NAV:er och portföljens geografi-/temaavvikelser mot ACWI ligger kvar i beta-
nivån, men mätartefakten från dagslaggen är neutraliserad.

## Tester

Nya/uppdaterade tester i `tests/test_fond_rapport_policy.py` (13 st, alla gröna;
hela sviten 60/60):

- Veckoaggregering med analytiskt facit på två hela handelsveckor.
- Fre–fre-logik kring helgdag (långfredag → veckoslut torsdag; annandag påsk →
  veckostart tisdag), kantveckor och helt tomma veckor.
- DataFrame-aggregering kolumnvis på samma buckets.
- Regression med känt beta/alfa på veckobas (exakt återvinning, n ≈ 100).
- Annualisering ^52 samt oförändrade spärr-/preliminär-tester.

## Verifiering av bygget

`python -m tools.fond_rapport.build_report` körd mot produktions-BI-filen:
KPI-verifiering 546 värden, 0 utanför tolerans; rapport skriven till
`Fondanalys-Data/04_Analyser/Portföljanalyser/fond_rapport_2026-07-06.html`.
Övriga block (attribution, risk, avgifter) oförändrade mot föregående bygge.

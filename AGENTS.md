# AGENTS.md

## Syfte

Detta repository utvecklas med hjalp av Codex-agenter.
Den har filen beskriver hur agenter bor arbeta i projektet.

Malet ar att arbetet ska vara:

- tydligt
- stabilt
- konsekvent
- latt att forsta och underhalla

Om flera losningar ar mojliga ska agenten normalt valja **den enklaste korrekta losningen**.

---

# Projektets dokumentation

Agenter ska lasa projektets dokumentation innan storre andringar gors.

Relevanta dokument finns i:

```
docs/

```

# Utvecklingsprinciper

Foredra:

- enkla losningar
- lasbar kod
- fa beroenden
- stegvisa forbattringar

Undvik:

- stora omskrivningar utan tydlig anledning
- onodiga ramverk eller bibliotek
- abstraktioner som inte behovs

Nar kod andras:

- andra sa lite som mojligt
- behall befintlig struktur dar det ar rimligt
- hall logiken latt att forsta

---

# Codex-tradar i projektet

Projektet anvander tva huvudtyper av tradar.

## Huvudtradar

Huvudtradar anvands for:

- projektplanering
- arkitekturdiskussion
- definiera uppgifter
- sammanfatta framsteg

De ska framst fokusera pa **analys och planering**, inte implementation.

---

## Arbetstradar

Arbetstradar anvands for:

- implementera funktioner
- atgarda buggar
- refaktorera kod
- gora forbattringar

Varje arbetstrad bor fokusera pa **en tydlig uppgift**.

---

# Nar kontext klistras in fran andra tradar

Om anvandaren klistrar in sammanfattningar eller innehall fran tidigare tradar ska agenten:

1. sammanfatta nulaget
2. identifiera malet
3. peka ut antaganden eller risker
4. foresla ett rimligt nasta steg

Sammanfattningar ska vara **kompakta och tydliga**.

---

# Kodandringar

Nar kod foreslas eller andras:

- foredra sma och fokuserade andringar
- undvik att andra filer som inte ar relevanta
- folj befintliga namn- och kodkonventioner
- behall projektets struktur

Om en andring ar komplex ska den delas upp i **flera mindre steg**.

---

# Git-arbetsflode

Projektet anvander ett enkelt Git-flode.

Typisk arbetssekvens:

```
git pull
gor andringar
git add .
git commit
git push
```

Principer:

- sma commits
- tydliga commit-meddelanden
- en logisk andring per commit

Genererade filer ska normalt **inte commitas**.

---

# Pull Requests

Nar en andring foreslas ska agenten ge en kort sammanfattning:

- vad som andrats
- varfor andringen gjordes
- vad som bor testas

---

# Testning och validering

Nar beteende andras bor agenten:

- tanka pa edge cases
- kontrollera att befintlig funktionalitet inte bryts
- foresla tester om det ar relevant

Om agenten inte kan kora Python, pytest eller andra verifieringskommandon i sin miljo ska agenten:

- behandla detta som en miljobegransning, inte automatiskt som ett projektfel
- anda genomfora relevanta kodandringar om uppgiften i ovrigt ar tydlig
- tydligt redovisa vilka verifieringssteg som inte kunde koras
- ange exakta kommandon som anvandaren kan kora lokalt
- undvika att foresla stora andringar i projektets setup enbart for att agentmiljon saknar atkomst

Om lokal verifiering inte kunde koras ska agentens slutrapport uttryckligen skilja mellan:

- vad som har implementerats
- vad som har kontrollerats genom kodlasning eller annan indirekt validering
- vad som aterstar att verifiera genom faktisk korning

---

# Agentmiljo och filskrivning

Detta projekt har haft viss friktion med Codex-agenters filskrivning och patchning i Windows-miljo.

Agenter bor darfor utga fran foljande:

- workspace-write racker normalt for filer i repot, men enstaka verktyg kan anda fallera
- om `apply_patch` misslyckas tidigt pa en liten andring ska agenten snabbt byta till ett stabilt fallback-satt i stallet for att fastna i patchfelsokning
- nya filer bor i detta repo normalt skapas med ett enkelt shell-baserat skrivsatt direkt, eftersom `apply_patch` har visat sig vara opalitligt just for filskapande i denna Windows-miljo
- hall alla textfiler i UTF-8 och konsekventa radslut for att minska patch- och diff-problem
- undvik att lagga energi pa `.pytest_cache` eller andra mappar som visar behorighetsfel om de inte ar direkt relevanta for uppgiften
- andra inte sokvagar eller OneDrive-relaterad runtime-konfiguration utan tydligt behov
- om en miljobegransning misstanks ska agenten skilja pa verktygsfel, filbehorighet och faktisk projektbugg
- den inbyggda delade terminalen kan ha striktare PowerShell- eller Python-policy an en vanlig extern terminal; blockerad `Activate.ps1`, `python` eller `py` i den delade terminalen ska inte automatiskt tolkas som projektfel
- om exekverbar verifiering blockeras i den delade terminalen ska agenten redovisa det som en miljobegransning och ge exakta kommandon for lokal korning i extern terminal

Standardarbetssatt i arbetstradar:

1. lasa relevanta filer och kontrollera snabbt att skrivning i repot fungerar
2. gora sma, fokuserade andringar i fa filer at gangen
3. om patchverktyg strular, anvanda ett enklare och mer robust skrivsatt
4. behalla textfiler som UTF-8 med konsekventa radslut
5. redovisa tydligt vad som ar implementerat, indirekt verifierat och kvar att testa

---

# Projektstruktur

Normal struktur i repositoryt:

```
project/
   src/
   tests/
   docs/

```

Agenter ska respektera denna struktur.

---

# Kommunikationsstil

Svar bor vara:

- tydliga
- kortfattade
- strukturerade nar det hjalper

Anvand garna:

- punktlistor
- steg-for-steg-beskrivningar

Undvik onodigt langa forklaringar.

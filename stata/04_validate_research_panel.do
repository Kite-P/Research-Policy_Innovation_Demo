version 18.0
clear all
set more off

capture mkdir "results"
capture mkdir "logs"
log using "logs/04_validate_research_panel.log", text replace

use "data/processed/research_panel_base.dta", clear

count
assert r(N) == 240
isid stock_code year
egen firm_id = group(stock_code)
quietly levelsof firm_id, local(firms)
assert r(r) == 40
summarize year
assert r(min) == 2020
assert r(max) == 2025
contract year
assert _freq == 40
drop _freq

use "data/processed/research_panel_base.dta", clear
tabulate patent_record_present
count if patent_record_present == 1
assert r(N) == 220
count if patent_record_present == 0
assert r(N) == 20
count if patent_record_present == 0 & !missing(invention_patents)
assert r(N) == 0
count if patent_record_present == 0 & !missing(utility_patents)
assert r(N) == 0
count if patent_record_present == 0 & !missing(patent_citations)
assert r(N) == 0
count if missing(province)
assert r(N) == 0

display "Research panel validation completed"
log close
exit, clear

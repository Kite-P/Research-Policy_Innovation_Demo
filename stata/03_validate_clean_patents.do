version 18.0
clear all
set more off

capture mkdir "results"
capture mkdir "results/stata"
log using "results/stata/03_validate_clean_patents.log", text replace

use "data/processed/patents_clean.dta", clear
describe
count
assert r(N) == 220
isid stock_code year
assert strlen(stock_code) == 6
assert regexm(stock_code, "^[0-9]+$")
summarize year
assert r(min) == 2020
assert r(max) == 2025
tabulate year
misstable summarize invention_patents utility_patents patent_citations
summarize invention_patents utility_patents patent_citations
assert invention_patents >= 0 if !missing(invention_patents)
assert utility_patents >= 0 if !missing(utility_patents)
assert patent_citations >= 0 if !missing(patent_citations)

display "Patent validation completed"
log close
exit, clear

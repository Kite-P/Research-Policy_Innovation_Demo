version 18.0
clear all
set more off

capture mkdir "results"
capture mkdir "results/stata"
log using "results/stata/05_validate_research_variables.log", text replace

use "data/processed/research_panel_variables.dta", clear

count
assert r(N) == 240
isid stock_code year

foreach variable in size_ln leverage roa rd_intensity cash_ratio employee_ln firm_age patent_total patent_total_ln invention_ln citation_ln invention_share citations_per_invention {
    confirm variable `variable'
    count if missing(`variable')
    summarize `variable'
}

count if patent_record_present == 0 & !missing(patent_total)
assert r(N) == 0
count if patent_record_present == 0 & !missing(patent_total_ln)
assert r(N) == 0
count if patent_record_present == 0 & !missing(invention_ln)
assert r(N) == 0
count if patent_record_present == 0 & !missing(citation_ln)
assert r(N) == 0
count if patent_record_present == 0 & !missing(invention_share)
assert r(N) == 0
count if patent_record_present == 0 & !missing(citations_per_invention)
assert r(N) == 0

assert abs(size_ln) < 1e100 if !missing(size_ln)
assert abs(leverage) < 1e100 if !missing(leverage)
assert abs(roa) < 1e100 if !missing(roa)
assert abs(rd_intensity) < 1e100 if !missing(rd_intensity)
assert abs(cash_ratio) < 1e100 if !missing(cash_ratio)
assert abs(employee_ln) < 1e100 if !missing(employee_ln)
assert abs(firm_age) < 1e100 if !missing(firm_age)

display "Research variable validation completed"
log close
exit, clear

version 18
clear all
set more off
capture log close _all
log using "logs/15_validate_financial_canary.log", replace text

use "results/real_financial_full/canary_200.dta", clear
isid firm_key year
assert inrange(year, 2020, 2025)
assert inlist(exchange, "SSE", "SZSE")

foreach variable in size_ln leverage roa cash_ratio employee_ln rd_intensity {
    count if missing(`variable')
    assert missing(`variable') | abs(`variable') < 1e100
}

count if size_ln < .
count if leverage < .
count if roa < .
count if cash_ratio < .
count if employee_ln < .
count if rd_intensity < .
display "FINANCIAL_FULL_CANARY_VALIDATION_PASS"
log close

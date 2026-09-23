version 18
clear all
set more off
capture log close _all
log using "logs/14_validate_financial_pilot.log", replace text

use "results/real_financial_pilot/financial_pilot.dta", clear

isid firm_key year
assert inrange(year, 2020, 2025)

local core total_assets total_liabilities cash revenue net_profit employees
foreach variable of local core {
    count if missing(`variable')
    display "MISSING `variable' = " r(N)
}

local derived size_ln leverage roa cash_ratio employee_ln rd_intensity
foreach variable of local derived {
    count if missing(`variable')
    display "MISSING `variable' = " r(N)
    count if `variable' < . & abs(`variable') > 1e100
    assert r(N) == 0
}

describe firm_key year exchange total_assets total_liabilities cash revenue net_profit employees rd_expense
display "FINANCIAL_PILOT_VALIDATION_PASS"
log close

version 18
clear all
set more off
capture log close _all
log using "logs/16_validate_financial_sse_szse_full_20260928.log", text replace

tempfile target_keys
use "data/processed/real_company_universe_enriched.dta", clear
keep if inlist(exchange, "SSE", "SZSE") & industry_known == 1 & is_financial_industry == 0
keep firm_key year
isid firm_key year
assert _N == 28537
egen tag_firm = tag(firm_key)
count if tag_firm
assert r(N) == 5269
drop tag_firm
save `target_keys'

use "data/processed/real_financials_sse_szse_nonfinancial.dta", clear
isid firm_key year
assert _N == 28537
egen tag_firm = tag(firm_key)
count if tag_firm
assert r(N) == 5269
drop tag_firm
assert inrange(year, 2020, 2025)
assert inlist(exchange, "SSE", "SZSE")
assert industry_known == 1
assert is_financial_industry == 0
assert year >= year(dofc(market_listing_date))
assert missing(delisting_date) | year <= year(dofc(delisting_date))
foreach v in total_assets total_liabilities cash revenue net_profit employees rd_expense size_ln leverage roa cash_ratio employee_ln rd_intensity {
    capture confirm numeric variable `v'
    if _rc != 0 exit 459
}
foreach v in size_ln leverage roa cash_ratio employee_ln rd_intensity {
    assert missing(`v') | abs(`v') < 1e100
}
foreach v in total_assets total_liabilities cash revenue net_profit employees {
    quietly count if missing(`v')
    display "CORE_MISSING_`v'=" r(N)
}
merge 1:1 firm_key year using `target_keys'
assert _merge == 3
drop _merge
foreach ex in SSE SZSE {
    quietly count if exchange == "`ex'" & missing(delisting_date)
    local denominator = r(N)
    quietly count if exchange == "`ex'" & missing(delisting_date) & !missing(total_assets, total_liabilities, cash, revenue, net_profit, employees)
    local numerator = r(N)
    local coverage = `numerator' / `denominator'
    display "`ex'_CURRENT_CORE_COVERAGE=" %8.6f `coverage'
    if `coverage' < 0.90 exit 459
}
quietly count
local firm_years = r(N)
quietly egen tag_firm = tag(firm_key)
quietly count if tag_firm
local firms = r(N)
quietly count if exchange == "SSE"
local sse_rows = r(N)
quietly count if exchange == "SZSE"
local szse_rows = r(N)
display "firms=`firms' firm_years=`firm_years' SSE_rows=`sse_rows' SZSE_rows=`szse_rows'"
display "FINANCIAL_SSE_SZSE_FULL_VALIDATION_PASS"
log close

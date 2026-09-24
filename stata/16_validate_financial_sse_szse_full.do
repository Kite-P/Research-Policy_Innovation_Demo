version 18
clear all
set more off

use "data/processed/real_financials_sse_szse_nonfinancial.dta", clear
isid firm_key year
assert inrange(year, 2020, 2025)
assert inlist(exchange, "SSE", "SZSE")
foreach v in total_assets total_liabilities cash revenue net_profit employees rd_expense size_ln leverage roa cash_ratio employee_ln rd_intensity {
    capture confirm numeric variable `v'
    if _rc != 0 exit 459
}
foreach v in size_ln leverage roa cash_ratio employee_ln rd_intensity {
    assert missing(`v') | abs(`v') < 1e100
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

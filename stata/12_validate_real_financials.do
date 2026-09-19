version 18
clear all
set more off

use "data/processed/real_financials_clean.dta", clear
isid exchange stock_code_current year
assert inrange(year, 2020, 2025)
assert total_assets > 0 if !missing(total_assets)
assert employees > 0 if !missing(employees)
assert !missing(size_ln) if !missing(total_assets)
assert !missing(employee_ln) if !missing(employees)
summarize total_assets total_liabilities cash revenue net_profit employees

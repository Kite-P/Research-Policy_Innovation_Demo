version 18
clear all
set more off

use "data/processed/real_company_universe.dta", clear
isid firm_key year
assert inrange(year, 2020, 2025)
assert !missing(firm_key)
assert !missing(exchange)
assert !(exchange == "BSE" & year == 2020)
contract exchange year
list, noobs

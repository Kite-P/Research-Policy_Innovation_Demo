version 18
clear all
set more off
capture log close _all
log using "logs/11_validate_real_company_universe.log", text replace

use "data/processed/real_company_universe.dta", clear
isid firm_key year
assert inrange(year, 2020, 2025)
assert !missing(firm_key)
assert !missing(exchange)
assert !(exchange == "BSE" & year == 2020)
count
assert r(N) == 30317
egen tag_firm = tag(firm_key)
count if tag_firm
assert r(N) == 5687
drop tag_firm
count if exchange == "BSE" & year == 2020
assert r(N) == 0
contract exchange year
list, noobs
display "REAL_COMPANY_UNIVERSE_VALIDATION_PASS"
log close

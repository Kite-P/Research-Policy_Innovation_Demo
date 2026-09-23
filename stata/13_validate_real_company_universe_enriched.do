version 18.0
clear all
set more off

use "data/processed/real_company_universe_enriched.dta", clear

isid firm_key year
assert inrange(year, 2020, 2025)
assert !missing(firm_key)
assert !missing(exchange)
assert market_listing_date <= mdy(12, 31, year)
assert missing(delisting_date) | delisting_date > mdy(1, 1, year)
count if exchange == "BSE" & year == 2020
assert r(N) == 0
duplicates report firm_key year
tab exchange, missing
tab year, missing
summ year, detail

capture confirm variable profile_status_profile
if !_rc {
    tab profile_status_profile, missing
}

display "ENRICHED_UNIVERSE_VALIDATION_PASS"

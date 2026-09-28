version 18.0
clear all
set more off
capture log close _all
log using "logs/13_validate_real_company_universe_enriched.log", text replace

tempfile target_keys
use "data/processed/real_company_universe.dta", clear
keep firm_key year
isid firm_key year
save `target_keys'

use "data/processed/real_company_universe_enriched.dta", clear

isid firm_key year
assert _N == 30317
egen tag_firm = tag(firm_key)
count if tag_firm
assert r(N) == 5687
drop tag_firm
assert inrange(year, 2020, 2025)
assert !missing(firm_key)
assert !missing(exchange)
assert year >= year(dofc(market_listing_date))
assert missing(delisting_date) | year <= year(dofc(delisting_date))
merge 1:1 firm_key year using `target_keys'
assert _merge == 3
drop _merge
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
assert !missing(company_name_legal_profile)
assert !missing(province_profile)
assert !missing(industry_csrc)
assert !missing(source_org_code)
assert profile_status_profile == "PASS"

display "ENRICHED_UNIVERSE_VALIDATION_PASS"
log close

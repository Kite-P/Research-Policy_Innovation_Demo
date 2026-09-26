version 18
clear all
set more off

capture log close _all
log using "logs/17_validate_historical_province.log", text replace

use "data/processed/real_company_universe_enriched.dta", clear
keep if inlist(exchange, "SSE", "SZSE") & inrange(year, 2020, 2025)
keep if industry_known == 1 & is_financial_industry == 0
assert !missing(market_listing_date)
assert year >= year(dofc(market_listing_date))
assert missing(delisting_date) | year <= year(dofc(delisting_date))
keep firm_key year
isid firm_key year
quietly count
assert r(N) == 28548
tempfile target_keys
save `target_keys'

use "data/processed/firm_year_historical_province.dta", clear
isid firm_key year
assert _N == 28548
assert inrange(year, 2020, 2025)
assert inlist(exchange, "SSE", "SZSE")
assert inlist(province_status, "historical_confirmed", "historical_inferred", ///
    "static_fallback_only", "missing")
assert !missing(province_historical) if inlist(province_status, ///
    "historical_confirmed", "historical_inferred")
assert missing(province_historical) if inlist(province_status, ///
    "static_fallback_only", "missing")
assert inlist(province_conflict, 0, 1)
assert missing(province_historical) if province_conflict == 1

merge 1:1 firm_key year using `target_keys'
assert _merge == 3
drop _merge

quietly count if province_status == "historical_confirmed"
display "HISTORICAL_CONFIRMED=" r(N)
quietly count if province_status == "historical_inferred"
display "HISTORICAL_INFERRED=" r(N)
quietly count if province_status == "static_fallback_only"
display "STATIC_FALLBACK_ONLY=" r(N)
quietly count if province_status == "missing"
display "HISTORICAL_MISSING=" r(N)
quietly count if province_conflict == 1
display "UNRESOLVED_CONFLICTS=" r(N)
quietly count if inlist(province_status, "historical_confirmed", ///
    "historical_inferred") & province_static_current != province_historical
display "STATIC_HISTORICAL_DISAGREEMENTS=" r(N)

display "HISTORICAL_PROVINCE_VALIDATION_PASS"
log close

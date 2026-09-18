version 18.0
clear all
set more off

capture mkdir "results"
capture mkdir "logs"

log using "logs/02_validate_clean_profile.log", text replace

display "========================================"
display "Processed firm profile validation"
display "========================================"

use "data/processed/firm_profile_clean.dta", clear

describe

count
assert r(N) == 42

isid stock_code

assert strlen(stock_code) == 6

count if missing(ownership)
assert r(N) == 3

count if missing(listing_date)
assert r(N) == 10

count if inlist(stock_code, "900001", "900002")
assert r(N) == 2

tabulate province

tabulate ownership, missing

summarize listing_date

display "========================================"
display "Profile validation completed"
display "========================================"

log close
exit, clear

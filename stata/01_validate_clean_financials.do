version 18.0
clear all
set more off

capture mkdir "results"
capture mkdir "logs"

log using "logs/01_validate_clean_financials.log", text replace

display "========================================"
display "Processed financial panel validation"
display "========================================"

use "data/processed/firm_financials_clean.dta", clear

describe

count
assert r(N) == 240

isid stock_code year

assert strlen(stock_code) == 6

tabulate year

misstable summarize

display "========================================"
display "Stata validation completed"
display "========================================"

log close
exit, clear

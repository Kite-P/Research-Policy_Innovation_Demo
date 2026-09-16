version 18.0
clear all
set more off

capture mkdir "results"
capture mkdir "results/stata"

log using "results/stata/00_environment_check.log", text replace

display "========================================"
display "Stata environment check"
display "========================================"

display "========================================"
display "Basic arithmetic test"
display "========================================"

display 1 + 1

display "========================================"
display "Built-in dataset test"
display "========================================"

sysuse auto, clear

describe

summarize price mpg weight

display "========================================"
display "Environment check completed"
display "========================================"

log close
exit, clear
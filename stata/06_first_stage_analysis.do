version 18.0
clear all
set more off

capture mkdir "results"
capture mkdir "results/first_stage"
capture mkdir "results/stata"
log using "results/stata/06_first_stage_analysis.log", text replace

use "data/processed/research_panel_variables.dta", clear
egen firm_id = group(stock_code)
xtset firm_id year

preserve
postfile results str1 model str32 outcome double rd_coefficient standard_error p_value N firms within_r2 using "results/first_stage/regression_results.dta", replace

quietly xtreg patent_total_ln rd_intensity size_ln leverage roa cash_ratio i.year, fe vce(cluster firm_id)
local b = _b[rd_intensity]
local se = _se[rd_intensity]
local p = 2 * ttail(e(df_r), abs(`b' / `se'))
post results ("A") ("patent_total_ln") (`b') (`se') (`p') (e(N)) (e(N_g)) (e(r2_w))

quietly xtreg invention_ln rd_intensity size_ln leverage roa cash_ratio i.year, fe vce(cluster firm_id)
local b = _b[rd_intensity]
local se = _se[rd_intensity]
local p = 2 * ttail(e(df_r), abs(`b' / `se'))
post results ("B") ("invention_ln") (`b') (`se') (`p') (e(N)) (e(N_g)) (e(r2_w))

quietly xtreg citation_ln rd_intensity size_ln leverage roa cash_ratio i.year, fe vce(cluster firm_id)
local b = _b[rd_intensity]
local se = _se[rd_intensity]
local p = 2 * ttail(e(df_r), abs(`b' / `se'))
post results ("C") ("citation_ln") (`b') (`se') (`p') (e(N)) (e(N_g)) (e(r2_w))

postclose results
restore

use "results/first_stage/regression_results.dta", clear
export delimited using "results/first_stage/regression_results.csv", replace

display "First-stage fixed-effects diagnostics completed"
log close
exit, clear

version 18.0
clear all
set more off
use "data/processed/research_panel_policy.dta", clear
isid stock_code year
egen firm_id = group(stock_code)
egen province_id = group(province)
xtset firm_id year
gen policy_lag = L.policy_continuity_tfidf
xtreg patent_total_ln policy_lag size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
xtreg patent_total_ln policy_cont_tfidf_exp size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
xtreg patent_total_ln policy_continuity_full_tfidf size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
xtreg patent_total_ln policy_continuity_theme size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
xtreg invention_ln policy_lag size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
xtreg citation_ln policy_lag size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
xtreg invention_ln policy_cont_tfidf_exp size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
xtreg citation_ln policy_cont_tfidf_exp size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)

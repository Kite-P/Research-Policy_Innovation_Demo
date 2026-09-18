version 18.0
clear all
set more off

capture mkdir "results"
capture mkdir "results/chapter3"
use "data/processed/research_panel_policy.dta", clear
isid stock_code year
egen firm_id = group(stock_code)
egen province_id = group(province)
xtset firm_id year
assert policy_metric_present == 1
assert policy_cont_tfidf_exp >= 0 & policy_cont_tfidf_exp <= 1

* Primary and secondary specifications. Province clustering is primary cluster.
xtreg patent_total_ln policy_continuity_tfidf, fe vce(cluster province_id)
estimates store model0
xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
estimates store base_primary
xtreg invention_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
estimates store base_secondary_inv
xtreg citation_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
estimates store base_secondary_cit

* Complementary HC2 and firm-cluster estimates for the primary model.
xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln, fe vce(hc2 province_id, dfadjust)
estimates store base_primary_hc2
xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln, fe vce(cluster firm_id)
estimates store base_primary_firm

* Primary small-cluster inference: Stata 18 official wildbootstrap.
wildbootstrap xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln, fe cluster(province_id) coefficients(policy_continuity_tfidf) errorweight(webb) reps(10000) rseed(20260918) ptype(equal)

version 18.0
clear all
set more off
use "data/processed/research_panel_policy.dta", clear
isid stock_code year
egen firm_id = group(stock_code)
egen province_id = group(province)
xtset firm_id year

xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln pair_mean_log_industry_chars abs_log_industry_length_change, fe vce(cluster province_id)
xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln pair_mean_log_full_chars abs_log_full_length_change, fe vce(cluster province_id)
xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln both_direct_official, fe vce(cluster province_id)

preserve
keep if both_direct_official == 1
xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
restore

* Leave-one-province-out estimates are intentionally all reported.
levelsof province, local(provinces)
foreach excluded of local provinces {
    preserve
    drop if province == "`excluded'"
    xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln, fe vce(cluster province_id)
    restore
}

* Missing patent observations remain missing; this is only a diagnostic.
tabulate year if patent_record_present == 0
tabulate province if patent_record_present == 0

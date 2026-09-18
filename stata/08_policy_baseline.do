version 18.0
clear all
set more off

capture mkdir "results"
capture mkdir "results/chapter3"
capture mkdir "logs"
capture log close _all
log using "logs/08_policy_baseline.log", text replace

use "data/processed/research_panel_policy.dta", clear
isid stock_code year
egen firm_id = group(stock_code)
egen province_id = group(province)
xtset firm_id year
assert _N == 240
quietly levelsof year, local(years)
local year_count : word count `years'
assert `year_count' == 6
quietly levelsof province_id, local(all_provinces)
local province_count : word count `all_provinces'
assert `province_count' == 7
bysort firm_id: egen __pmin = min(province_id)
bysort firm_id: egen __pmax = max(province_id)
assert __pmin == __pmax
drop __pmin __pmax
assert policy_metric_present == 1
assert policy_cont_tfidf_exp >= 0 & policy_cont_tfidf_exp <= 1

tempfile baseline_post
postfile BASE str24 model str24 outcome double(beta province_cluster_se province_cluster_p province_cluster_ci_low province_cluster_ci_high hc2_se hc2_p hc2_ci_low hc2_ci_high wcb_p wcb_ci_low wcb_ci_high firm_cluster_se firm_cluster_p N firms province_clusters within_r2) str20 wcb_weight double(wcb_reps wcb_seed) str20 wcb_ptype str20 clustvar using `baseline_post', replace

quietly xtreg patent_total_ln policy_continuity_tfidf i.year, fe vce(cluster province_id)
scalar __beta = _b[policy_continuity_tfidf]
scalar __se = _se[policy_continuity_tfidf]
scalar __p = 2 * ttail(e(df_r), abs(__beta / __se))
scalar __ll = __beta - invttail(e(df_r), .025) * __se
scalar __ul = __beta + invttail(e(df_r), .025) * __se
scalar __N = e(N)
scalar __firms = e(N_g)
scalar __r2w = e(r2_w)
quietly levelsof province_id if e(sample), local(__cl)
local __clusters : word count `__cl'
scalar __hc2se = .
scalar __hc2p = .
scalar __hc2ll = .
scalar __hc2ul = .
scalar __firmse = .
scalar __firmp = .
quietly wildbootstrap xtreg patent_total_ln policy_continuity_tfidf i.year, fe cluster(province_id) coefficients(policy_continuity_tfidf) errorweight(webb) reps(10000) rseed(20260918) ptype(equal)
matrix __W = r(table)
local __rows : rownames __W
local __prow : list posof "pvalue" in __rows
local __llrow : list posof "ll" in __rows
local __ulrow : list posof "ul" in __rows
assert `__prow' > 0 & `__llrow' > 0 & `__ulrow' > 0
assert colsof(__W) == 1
scalar __wbp = __W[`__prow',1]
scalar __wbll = __W[`__llrow',1]
scalar __wbul = __W[`__ulrow',1]
post BASE ("MODEL_0") ("patent_total_ln") (__beta) (__se) (__p) (__ll) (__ul) (__hc2se) (__hc2p) (__hc2ll) (__hc2ul) (__wbp) (__wbll) (__wbul) (__firmse) (__firmp) (__N) (__firms) (`__clusters') (__r2w) ("Webb") (10000) (20260918) ("equal-tailed") ("province_id")

quietly xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln i.year, fe vce(cluster province_id)
scalar __beta = _b[policy_continuity_tfidf]
scalar __se = _se[policy_continuity_tfidf]
scalar __p = 2 * ttail(e(df_r), abs(__beta / __se))
scalar __ll = __beta - invttail(e(df_r), .025) * __se
scalar __ul = __beta + invttail(e(df_r), .025) * __se
scalar __N = e(N)
scalar __firms = e(N_g)
scalar __r2w = e(r2_w)
quietly levelsof province_id if e(sample), local(__cl)
local __clusters : word count `__cl'
quietly xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln i.year, fe vce(hc2 province_id, dfadjust)
scalar __hc2se = _se[policy_continuity_tfidf]
scalar __hc2p = 2 * ttail(e(df_r), abs(_b[policy_continuity_tfidf] / __hc2se))
scalar __hc2ll = _b[policy_continuity_tfidf] - invttail(e(df_r), .025) * __hc2se
scalar __hc2ul = _b[policy_continuity_tfidf] + invttail(e(df_r), .025) * __hc2se
quietly xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln i.year, fe vce(cluster firm_id)
scalar __firmse = _se[policy_continuity_tfidf]
scalar __firmp = 2 * ttail(e(df_r), abs(_b[policy_continuity_tfidf] / __firmse))
quietly wildbootstrap xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln i.year, fe cluster(province_id) coefficients(policy_continuity_tfidf) errorweight(webb) reps(10000) rseed(20260918) ptype(equal)
matrix __W = r(table)
local __rows : rownames __W
local __prow : list posof "pvalue" in __rows
local __llrow : list posof "ll" in __rows
local __ulrow : list posof "ul" in __rows
assert `__prow' > 0 & `__llrow' > 0 & `__ulrow' > 0
assert colsof(__W) == 1
scalar __wbp = __W[`__prow',1]
scalar __wbll = __W[`__llrow',1]
scalar __wbul = __W[`__ulrow',1]
post BASE ("BASE_PRIMARY") ("patent_total_ln") (__beta) (__se) (__p) (__ll) (__ul) (__hc2se) (__hc2p) (__hc2ll) (__hc2ul) (__wbp) (__wbll) (__wbul) (__firmse) (__firmp) (__N) (__firms) (`__clusters') (__r2w) ("Webb") (10000) (20260918) ("equal-tailed") ("province_id")

foreach spec in "BASE_SECONDARY_INV invention_ln" "BASE_SECONDARY_CIT citation_ln" {
    tokenize `spec'
    quietly xtreg `2' policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln i.year, fe vce(cluster province_id)
    scalar __beta = _b[policy_continuity_tfidf]
    scalar __se = _se[policy_continuity_tfidf]
    scalar __p = 2 * ttail(e(df_r), abs(__beta / __se))
    scalar __ll = __beta - invttail(e(df_r), .025) * __se
    scalar __ul = __beta + invttail(e(df_r), .025) * __se
    scalar __N = e(N)
    scalar __firms = e(N_g)
    scalar __r2w = e(r2_w)
    quietly levelsof province_id if e(sample), local(__cl)
    local __clusters : word count `__cl'
    scalar __hc2se = .
    scalar __hc2p = .
    scalar __hc2ll = .
    scalar __hc2ul = .
    scalar __firmse = .
    scalar __firmp = .
    quietly wildbootstrap xtreg `2' policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln i.year, fe cluster(province_id) coefficients(policy_continuity_tfidf) errorweight(webb) reps(10000) rseed(20260918) ptype(equal)
    matrix __W = r(table)
    local __rows : rownames __W
    local __prow : list posof "pvalue" in __rows
    local __llrow : list posof "ll" in __rows
    local __ulrow : list posof "ul" in __rows
    assert `__prow' > 0 & `__llrow' > 0 & `__ulrow' > 0
    assert colsof(__W) == 1
    scalar __wbp = __W[`__prow',1]
    scalar __wbll = __W[`__llrow',1]
    scalar __wbul = __W[`__ulrow',1]
    post BASE ("`1'") ("`2'") (__beta) (__se) (__p) (__ll) (__ul) (__hc2se) (__hc2p) (__hc2ll) (__hc2ul) (__wbp) (__wbll) (__wbul) (__firmse) (__firmp) (__N) (__firms) (`__clusters') (__r2w) ("Webb") (10000) (20260918) ("equal-tailed") ("province_id")
}
postclose BASE

use `baseline_post', clear
export delimited using "results/chapter3/stata_baseline_inference.csv", replace
display "CHAPTER3_08_OK"
log close

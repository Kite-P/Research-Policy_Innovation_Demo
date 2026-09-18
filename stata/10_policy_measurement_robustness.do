version 18.0
clear all
set more off
capture mkdir "results"
capture mkdir "results/chapter3"
capture mkdir "results/stata"
capture log close _all
log using "results/stata/10_policy_measurement_robustness.log", text replace

use "data/processed/research_panel_policy.dta", clear
isid stock_code year
egen firm_id = group(stock_code)
egen province_id = group(province)
xtset firm_id year
assert _N == 240
quietly levelsof province_id, local(all_provinces)
local province_count : word count `all_provinces'
assert `province_count' == 7
bysort firm_id: egen __pmin = min(province_id)
bysort firm_id: egen __pmax = max(province_id)
assert __pmin == __pmax
drop __pmin __pmax

tempfile measurement_post leaveout_post weight_post
postfile MEASURE str32 model str24 outcome str40 policy_variable double(beta province_cluster_se province_cluster_p province_cluster_ci_low province_cluster_ci_high wcb_p wcb_ci_low wcb_ci_high N firms province_clusters within_r2) str20 wcb_weight double(wcb_reps wcb_seed) str20 wcb_ptype str20 clustvar using `measurement_post', replace
postfile LEAVEOUT str32 model str24 outcome str40 policy_variable double(beta province_cluster_se province_cluster_p province_cluster_ci_low province_cluster_ci_high wcb_p wcb_ci_low wcb_ci_high N firms province_clusters within_r2) str20 wcb_weight double(wcb_reps wcb_seed) str20 wcb_ptype str20 clustvar using `leaveout_post', replace
postfile WEIGHTS str20 weight str24 outcome str40 policy_variable double(beta wcb_p wcb_ci_low wcb_ci_high N firms province_clusters) double(wcb_reps wcb_seed) str20 wcb_ptype str20 clustvar using `weight_post', replace

program drop _all
program define post_measure
    args target model outcome policy extras
    quietly xtreg `outcome' `policy' size_ln leverage roa cash_ratio employee_ln `extras' i.year, fe vce(cluster province_id)
    scalar __beta = _b[`policy']
    scalar __se = _se[`policy']
    scalar __p = 2 * ttail(e(df_r), abs(__beta / __se))
    scalar __ll = __beta - invttail(e(df_r), .025) * __se
    scalar __ul = __beta + invttail(e(df_r), .025) * __se
    scalar __N = e(N)
    scalar __firms = e(N_g)
    scalar __r2w = e(r2_w)
    quietly levelsof province_id if e(sample), local(__cl)
    local __clusters : word count `__cl'
    quietly wildbootstrap xtreg `outcome' `policy' size_ln leverage roa cash_ratio employee_ln `extras' i.year, fe cluster(province_id) coefficients(`policy') errorweight(webb) reps(10000) rseed(20260918) ptype(equal)
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
    post `target' ("`model'") ("`outcome'") ("`policy'") (__beta) (__se) (__p) (__ll) (__ul) (__wbp) (__wbll) (__wbul) (__N) (__firms) (`__clusters') (__r2w) ("Webb") (10000) (20260918) ("equal-tailed") ("province_id")
end

post_measure MEASURE "industry_volume" "patent_total_ln" "policy_continuity_tfidf" "pair_mean_log_industry_chars abs_log_industry_length_change"
post_measure MEASURE "full_volume" "patent_total_ln" "policy_continuity_tfidf" "pair_mean_log_full_chars abs_log_full_length_change"
post_measure MEASURE "source_quality" "patent_total_ln" "policy_continuity_tfidf" "both_direct_official"

preserve
keep if both_direct_official == 1
post_measure MEASURE "direct_source_restricted" "patent_total_ln" "policy_continuity_tfidf" ""
restore

quietly levelsof province, local(provinces)
foreach excluded of local provinces {
    preserve
    drop if province == "`excluded'"
    post_measure LEAVEOUT "leave_out_`excluded'" "patent_total_ln" "policy_continuity_tfidf" ""
    restore
}

quietly xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln i.year, fe vce(cluster province_id)
scalar __beta = _b[policy_continuity_tfidf]
scalar __N = e(N)
scalar __firms = e(N_g)
quietly levelsof province_id if e(sample), local(__cl)
local __clusters : word count `__cl'
foreach weight in "webb" "rademacher" {
    quietly wildbootstrap xtreg patent_total_ln policy_continuity_tfidf size_ln leverage roa cash_ratio employee_ln i.year, fe cluster(province_id) coefficients(policy_continuity_tfidf) errorweight(`weight') reps(10000) rseed(20260918) ptype(equal)
    matrix __W = r(table)
    local __rows : rownames __W
    local __prow : list posof "pvalue" in __rows
    local __llrow : list posof "ll" in __rows
    local __ulrow : list posof "ul" in __rows
    assert `__prow' > 0 & `__llrow' > 0 & `__ulrow' > 0
    scalar __wbp = __W[`__prow',1]
    scalar __wbll = __W[`__llrow',1]
    scalar __wbul = __W[`__ulrow',1]
    post WEIGHTS ("`weight'") ("patent_total_ln") ("policy_continuity_tfidf") (__beta) (__wbp) (__wbll) (__wbul) (__N) (__firms) (`__clusters') (10000) (20260918) ("equal-tailed") ("province_id")
}

postclose MEASURE
postclose LEAVEOUT
postclose WEIGHTS
use `measurement_post', clear
export delimited using "results/chapter3/stata_measurement_robustness.csv", replace
use `leaveout_post', clear
export delimited using "results/chapter3/stata_leave_one_province_out.csv", replace
use `weight_post', clear
export delimited using "results/chapter3/stata_weight_sensitivity.csv", replace
display "CHAPTER3_10_OK"
log close

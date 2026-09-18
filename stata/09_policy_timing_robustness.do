version 18.0
clear all
set more off
capture mkdir "results"
capture mkdir "results/chapter3"
capture mkdir "logs"
capture log close _all
log using "logs/09_policy_timing_robustness.log", text replace

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

tempfile policy_year
preserve
keep province year policy_continuity_tfidf
duplicates drop
isid province year
sort province year
by province: gen policy_lag = policy_continuity_tfidf[_n-1]
keep province year policy_lag
save `policy_year', replace
restore
merge m:1 province year using `policy_year'
assert _merge == 3
drop _merge
count if year == 2020 & missing(policy_lag)
assert r(N) == 40
count if inrange(year, 2021, 2025) & !missing(policy_lag)
assert r(N) == 200
count if !missing(policy_lag)
assert r(N) == 200

tempfile timing_post
postfile TIMING str28 model str24 outcome str40 policy_variable double(beta province_cluster_se province_cluster_p province_cluster_ci_low province_cluster_ci_high wcb_p wcb_ci_low wcb_ci_high N firms province_clusters within_r2) str20 wcb_weight double(wcb_reps wcb_seed) str20 wcb_ptype str20 clustvar using `timing_post', replace

program drop _all
program define post_timing
    args model outcome policy
    quietly xtreg `outcome' `policy' size_ln leverage roa cash_ratio employee_ln i.year, fe vce(cluster province_id)
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
    quietly wildbootstrap xtreg `outcome' `policy' size_ln leverage roa cash_ratio employee_ln i.year, fe cluster(province_id) coefficients(`policy') errorweight(webb) reps(10000) rseed(20260918) ptype(equal)
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
    post TIMING ("`model'") ("`outcome'") ("`policy'") (__beta) (__se) (__p) (__ll) (__ul) (__wbp) (__wbll) (__wbul) (__N) (__firms) (`__clusters') (__r2w) ("Webb") (10000) (20260918) ("equal-tailed") ("province_id")
end

post_timing "lagged_primary" "patent_total_ln" "policy_lag"
post_timing "lagged_primary" "invention_ln" "policy_lag"
post_timing "lagged_primary" "citation_ln" "policy_lag"
post_timing "expanding" "patent_total_ln" "policy_cont_tfidf_exp"
post_timing "expanding" "invention_ln" "policy_cont_tfidf_exp"
post_timing "expanding" "citation_ln" "policy_cont_tfidf_exp"
post_timing "full_report" "patent_total_ln" "policy_continuity_full_tfidf"
post_timing "theme" "patent_total_ln" "policy_continuity_theme"

postclose TIMING
use `timing_post', clear
export delimited using "results/chapter3/stata_timing_robustness.csv", replace
display "CHAPTER3_09_OK"
log close

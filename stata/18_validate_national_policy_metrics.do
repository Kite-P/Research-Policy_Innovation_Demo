version 18.0
clear all
set more off

capture mkdir "logs"
log using "logs/18_validate_national_policy_metrics.log", text replace

display "Stata version: " c(stata_version) " | MP: " c(MP) " | processors: " c(processors)
if c(stata_version) != 18 | c(MP) != 1 {
    display as error "Required runtime is Stata/MP 18; validation stopped."
    exit 9
}
use "data/processed/province_year_policy_metrics.dta", clear

count
assert r(N) == 217
isid province year
isid province_key year
assert inrange(year, 2019, 2025)
assert province != "香港特别行政区"
egen province_tag = tag(province)
quietly count if province_tag
assert r(N) == 31
drop province_tag
bysort province_key: assert _N == 7

quietly count if year == 2019
assert r(N) == 31
quietly count if year == 2019 & missing(policy_continuity_tfidf)
assert r(N) == 31
quietly count if inrange(year, 2020, 2025) & !missing(policy_continuity_tfidf)
assert r(N) == 186
quietly count if inrange(year, 2020, 2025) & missing(policy_continuity_tfidf)
assert r(N) == 0
quietly count if inrange(year, 2020, 2025) & !missing(policy_cont_tfidf_exp)
assert r(N) == 186

assert missing(policy_continuity_tfidf) | (policy_continuity_tfidf >= 0 & policy_continuity_tfidf <= 1 & abs(policy_continuity_tfidf) < 1e100)
assert missing(policy_cont_tfidf_exp) | (policy_cont_tfidf_exp >= 0 & policy_cont_tfidf_exp <= 1 & abs(policy_cont_tfidf_exp) < 1e100)
assert missing(policy_continuity_full_tfidf) | (policy_continuity_full_tfidf >= 0 & policy_continuity_full_tfidf <= 1 & abs(policy_continuity_full_tfidf) < 1e100)
assert missing(policy_continuity_theme) | (policy_continuity_theme >= 0 & policy_continuity_theme <= 1 & abs(policy_continuity_theme) < 1e100)

assert inrange(source_tier_current, 1, 4)
assert missing(source_tier_previous) if year == 2019
assert inrange(source_tier_previous, 1, 4) if year > 2019
assert missing(source_tier_max) if year == 2019
assert inrange(source_tier_max, 1, 4) if year > 2019
assert missing(source_tier_changed) if year == 2019
assert inlist(source_tier_changed, 0, 1) if year > 2019
assert missing(both_direct_official) if year == 2019
assert inlist(both_direct_official, 0, 1) if year > 2019

describe
summarize policy_continuity_tfidf policy_cont_tfidf_exp policy_continuity_full_tfidf policy_continuity_theme
summarize source_tier_current source_tier_previous source_tier_max source_tier_changed both_direct_official
display "NATIONAL_POLICY_METRICS_VALIDATION_PASS"
log close
exit, clear

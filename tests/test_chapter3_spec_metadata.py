import pandas as pd


def test_chapter3_specifications_are_frozen():
    specs = pd.read_csv("metadata/chapter3_model_specifications.csv")
    assert specs.spec_id.tolist() == ["BASE_PRIMARY", "BASE_SECONDARY_INV", "BASE_SECONDARY_CIT"]
    assert specs.loc[0, "outcome"] == "patent_total_ln"
    assert specs.policy_variable.eq("policy_continuity_tfidf").all()
    assert specs.cluster_level.eq("province").all()
    assert specs.primary_inference.eq("webb_wild_cluster_bootstrap").all()
    assert specs.firm_fe.eq(1).all() and specs.year_fe.eq(1).all()

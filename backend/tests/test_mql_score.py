"""Unit tests for compute_mql_score() — all metrics are deterministic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.lsq_client import compute_mql_score


def _lead(**kwargs):
    """Build a minimal lead dict with nulls for everything not specified."""
    return {
        "mx_Age_Group": None,
        "mx_City": None,
        "mx_utm_disease": None,
        "mx_Do_you_remember_your_HbA1c_levels": None,
        "mx_Are_you_open_to_investing_in_this_paid_program_of": None,
        **kwargs,
    }


# --- All-null → score 0 ------------------------------------------------

def test_all_null_gives_zero():
    score, signals = compute_mql_score(_lead())
    assert score == 0
    assert signals == {"age": False, "city": False, "condition": False, "hba1c": False, "intent": False}


# --- Age signal -----------------------------------------------------------

def test_age_31_40_in_range():
    score, s = compute_mql_score(_lead(**{"mx_Age_Group": "31–40"}))
    assert s["age"] is True

def test_age_41_50_in_range():
    _, s = compute_mql_score(_lead(**{"mx_Age_Group": "41–50"}))
    assert s["age"] is True

def test_age_51_60_in_range():
    _, s = compute_mql_score(_lead(**{"mx_Age_Group": "51–60"}))
    assert s["age"] is True

def test_age_61_70_in_range():
    # Straddles upper bound — conservative inclusion per spec
    _, s = compute_mql_score(_lead(**{"mx_Age_Group": "61–70"}))
    assert s["age"] is True

def test_age_under_30_out_of_range():
    _, s = compute_mql_score(_lead(**{"mx_Age_Group": "18–30"}))
    assert s["age"] is False

def test_age_above_70_out_of_range():
    _, s = compute_mql_score(_lead(**{"mx_Age_Group": "71+"}))
    assert s["age"] is False

def test_age_blank_is_false():
    _, s = compute_mql_score(_lead(**{"mx_Age_Group": ""}))
    assert s["age"] is False


# --- City signal ----------------------------------------------------------

def test_city_hyderabad_matches():
    _, s = compute_mql_score(_lead(**{"mx_City": "Hyderabad"}))
    assert s["city"] is True

def test_city_mumbai_matches():
    _, s = compute_mql_score(_lead(**{"mx_City": "Mumbai"}))
    assert s["city"] is True

def test_city_bangalore_alternate_spelling():
    _, s = compute_mql_score(_lead(**{"mx_City": "Bengaluru"}))
    assert s["city"] is True

def test_city_tumkur_no_match():
    _, s = compute_mql_score(_lead(**{"mx_City": "Tumkur"}))
    assert s["city"] is False

def test_city_case_insensitive():
    _, s = compute_mql_score(_lead(**{"mx_City": "PUNE"}))
    assert s["city"] is True


# --- Condition signal -----------------------------------------------------

def test_condition_diabetes_matches():
    _, s = compute_mql_score(_lead(**{"mx_utm_disease": "Diabetes"}))
    assert s["condition"] is True

def test_condition_pcos_matches():
    _, s = compute_mql_score(_lead(**{"mx_utm_disease": "PCOS"}))
    assert s["condition"] is True

def test_condition_unknown_no_match():
    _, s = compute_mql_score(_lead(**{"mx_utm_disease": "Back Pain"}))
    assert s["condition"] is False


# --- HbA1c signal ---------------------------------------------------------

def test_hba1c_57_to_64_prediabetes_matches():
    _, s = compute_mql_score(_lead(**{"mx_Do_you_remember_your_HbA1c_levels": "5.7 – 6.4 (pre-diabetes range)"}))
    assert s["hba1c"] is True

def test_hba1c_65_to_8_matches():
    _, s = compute_mql_score(_lead(**{"mx_Do_you_remember_your_HbA1c_levels": "6.5 – 8.0"}))
    assert s["hba1c"] is True

def test_hba1c_above_8_matches():
    _, s = compute_mql_score(_lead(**{"mx_Do_you_remember_your_HbA1c_levels": "above_8"}))
    assert s["hba1c"] is True

def test_hba1c_normal_below_57_no_match():
    # Normal range < 5.7
    _, s = compute_mql_score(_lead(**{"mx_Do_you_remember_your_HbA1c_levels": "5.0 – 5.6 (normal)"}))
    assert s["hba1c"] is False

def test_hba1c_null_is_false():
    _, s = compute_mql_score(_lead(**{"mx_Do_you_remember_your_HbA1c_levels": None}))
    assert s["hba1c"] is False


# --- Intent signal --------------------------------------------------------

def test_intent_yes_matches():
    _, s = compute_mql_score(_lead(**{"mx_Are_you_open_to_investing_in_this_paid_program_of": "yes"}))
    assert s["intent"] is True

def test_intent_maybe_matches():
    _, s = compute_mql_score(_lead(**{
        "mx_Are_you_open_to_investing_in_this_paid_program_of":
            "maybe,_i'd_like_to_understand_the_program_first"
    }))
    assert s["intent"] is True

def test_intent_no_is_false():
    _, s = compute_mql_score(_lead(**{"mx_Are_you_open_to_investing_in_this_paid_program_of": "no"}))
    assert s["intent"] is False

def test_intent_null_is_false():
    _, s = compute_mql_score(_lead(**{"mx_Are_you_open_to_investing_in_this_paid_program_of": None}))
    assert s["intent"] is False


# --- Full MQL (score = 5) -------------------------------------------------

def test_full_mql_score_is_5():
    lead = _lead(**{
        "mx_Age_Group": "41–50",
        "mx_City": "Hyderabad",
        "mx_utm_disease": "Diabetes",
        "mx_Do_you_remember_your_HbA1c_levels": "5.7 – 6.4 (pre-diabetes range)",
        "mx_Are_you_open_to_investing_in_this_paid_program_of": "yes",
    })
    score, signals = compute_mql_score(lead)
    assert score == 5
    assert all(signals.values())


# --- Near-MQL (score = 4) -------------------------------------------------

def test_near_mql_missing_intent():
    lead = _lead(**{
        "mx_Age_Group": "41–50",
        "mx_City": "Mumbai",
        "mx_utm_disease": "Diabetes",
        "mx_Do_you_remember_your_HbA1c_levels": "6.5 – 8.0",
        "mx_Are_you_open_to_investing_in_this_paid_program_of": None,
    })
    score, signals = compute_mql_score(lead)
    assert score == 4
    assert signals["intent"] is False

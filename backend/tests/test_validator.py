from app.genai.validator import check_ids, check_numbers, facts_numbers, numbers_in


def test_extracts_indian_grouping_and_decimals():
    assert numbers_in("₹1,23,456 and 9.5 kWh") == [123456.0, 9.5]


def test_ignores_numbers_inside_ids():
    assert numbers_in("Fix WO-17 at A-202 and BIN-05") == []


def test_native_digits_are_normalised():
    assert numbers_in("ನಷ್ಟ ₹೪೨/ಗಂಟೆ") == [42.0]
    assert numbers_in("नुकसान ₹४२") == [42.0]


def test_rejects_invented_numbers():
    facts = {"loss": 42.0, "nested": {"kwh": 13841}}
    allowed = facts_numbers(facts)
    assert check_numbers("Loss ₹42/hour, 13,841 kWh used", allowed) == []
    assert check_numbers("Loss ₹42/hour, saving ₹5,000", allowed) == [5000.0]


def test_small_integers_always_allowed():
    assert check_numbers("1. Go there 2. Switch off", set()) == []


def test_tolerates_rounding():
    assert check_numbers("about 13,800 kWh", {13841.0}) == []  # within 1%
    assert check_numbers("about 13,000 kWh", {13841.0}) == [13000.0]


def test_dsu_room_ids_are_recognised():
    assert numbers_in("Fix B1-1WR and E-201 for WO-3") == []
    assert check_ids("Go to B1-1WR and E-201", "B1-1WR ಮತ್ತು E-201") == set()


def test_ids_must_survive_translation():
    en = "Reply DONE WO-5 for A-202"
    assert check_ids(en, "A-202 ಗಾಗಿ DONE WO-5 ಕಳುಹಿಸಿ") == set()
    assert check_ids(en, "DONE ಕಳುಹಿಸಿ") == {"WO-5", "A-202"}

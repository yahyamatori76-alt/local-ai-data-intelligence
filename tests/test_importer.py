from app.ingestion.importer import safe_filename


def test_safe_filename_discards_paths_and_control_characters():
    assert safe_filename("../../transactions.csv") == "transactions.csv"
    assert safe_filename("folder\\events.log") == "events.log"

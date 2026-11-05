import csv

from complaints_agent import classifier, dataset


def test_rule_classification_has_explainable_evidence():
    result = classifier.classify("I was charged twice for my monthly bill.")
    assert result["key"] == "billing_duplicate"
    assert result["method"] == "rules"
    assert result["similarity"] == 1.0
    assert result["matchedWord"]


def test_low_information_text_is_not_forced_into_a_cluster():
    result = classifier.classify("I need help with something.")
    assert result["key"] == "other"
    assert result["method"] == "unclassified"
    assert result["similarity"] == 0.0


def test_external_csv_is_read_only_and_summarised(tmp_path, monkeypatch):
    source = tmp_path / "complaints.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "Ticket #", "Customer Complaint", "Date", "Received Via", "City", "State", "Status",
        ])
        writer.writeheader()
        writer.writerow({
            "Ticket #": "1", "Customer Complaint": "Charged twice for my bill", "Date": "22-04-15",
            "Received Via": "Customer Care Call", "City": "Tunis", "State": "TN", "Status": "Open",
        })
        writer.writerow({
            "Ticket #": "2", "Customer Complaint": "No signal at home", "Date": "22-04-15",
            "Received Via": "Internet", "City": "Sfax", "State": "TN", "Status": "Closed",
        })
    monkeypatch.setenv("COMPLAINTS_CSV", str(source))
    result = dataset.overview()
    assert result["records"] == 2
    assert result["open"] == 1
    assert result["enabled"] is True
    assert result["methods"]["rules"] == 2

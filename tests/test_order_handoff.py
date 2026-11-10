from marketplace_documents import BuyerQuestion, SellerAsset, handoff_for_match


def test_confident_document_match_releases_order_handoff() -> None:
    asset = SellerAsset("listing-42", "condition-report.pdf", "https://example.test/report.pdf")
    buyer = BuyerQuestion("buyer-9", "Does the report mention a repaired corner?")
    result = handoff_for_match(asset, buyer, [{"score": 0.92, "metadata": {"caption": "Condition: repaired corner noted."}}])

    assert result.order_status == "ready_for_order_handoff"
    assert "repaired corner" in result.answer


def test_ingest_and_answer_never_persist_vectors() -> None:
    from marketplace_documents import MarketplaceArchive

    archive = MarketplaceArchive.__new__(MarketplaceArchive)
    archive.captions = {}
    calls = []

    def request(method, path, body):
        calls.append(path)
        assert path == "/v1/pdf/ocr"
        assert body["quality"] == "balanced"
        return {"text": "Condition: repaired corner noted."}

    archive.request = request
    archive.embed = lambda text: [1.0, 0.0]
    asset = SellerAsset("listing-42", "condition-report.pdf", "test.pdf")
    buyer = BuyerQuestion("buyer-9", "Is there a repaired corner?")
    archive.ingest(asset)
    assert archive.answer(asset, buyer).order_status == "ready_for_order_handoff"
    assert calls == ["/v1/pdf/ocr"]
    assert archive.captions == {}

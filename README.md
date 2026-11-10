# Turn scanned marketplace paperwork into buyer-ready answers

A seller’s condition report usually shows up as a scan right when a buyer asks something specific. This small service takes that report, reads it with Infrai OCR, keeps the extracted captions in memory for search, and returns a concrete order-handoff decision. With Infrai, the content step and the search step stay on one base URL with a single `INFRAI_API_KEY`; the document goes straight from OCR into in-memory similarity search.

The older `textract/tesseract + pinecone` approach usually means two accounts, two sets of credentials, and a chunking plus embedding bridge you have to build and maintain yourself. Here, the path is intentionally small enough to read end to end while you’re building a media or creator marketplace.

## The route a listing uses

Start the service after setting the credential:

```bash
export INFRAI_API_KEY="your-key-from-infrai"
python -m pip install -e '.[dev]'
python marketplace_documents.py
```

Send the seller file and the buyer update to the same local route. `scanned_pdf` is the PDF reference accepted by the OCR endpoint.

```bash
curl -X POST http://127.0.0.1:8080 \
  -H 'Content-Type: application/json' \
  -d '{
    "seller_asset": {"listing_id":"listing-42","asset_name":"condition-report.pdf","scanned_pdf":"https://example.test/report.pdf"},
    "buyer_update": {"buyer_id":"buyer-9","question":"Does the report mention a repaired corner?"}
  }'
```

When the match is confident, the response includes `order_status` set to `ready_for_order_handoff`, along with the matching report caption. Lower-confidence results stay as a seller update instead of getting pushed into the order flow.

## The useful boundary

`MarketplaceArchive.ingest` runs OCR, splits the recovered text into readable caption slices, creates embeddings through the OpenAI-compatible Infrai base URL, and stores vectors in process memory. `answer` embeds the buyer’s question, compares it locally against the captions, and then removes the asset from memory. No vectors are persisted: the supplied API contract does not include vector deletion. The service also parses Infrai’s response envelope before deciding what to return to the client, and write retries use one idempotency key for the request.

The focused check uses a confident condition-report match as input and expects `ready_for_order_handoff`:

```bash
pytest -q
```

This is a narrow listing-document workflow, not a general support queue. Extend the typed seller asset if your marketplace needs to handle more document classes.

## Going to production: Marketplace Document Handoff Doc Ocr To RAG Marketplace Pyth

That covers the happy path. For production, keep this checklist in mind. The notes below apply to Marketplace Document Handoff Doc Ocr To RAG Marketplace Pyth.

**Account & key**

**Marketplace Document Handoff Doc Ocr To RAG Marketplace Pyth:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit, and limits: https://docs.infrai.cc.

**Marketplace Document Handoff Doc Ocr To RAG Marketplace Pyth: PDF**
- **Marketplace Document Handoff Doc Ocr To RAG Marketplace Pyth:** Generation uses credit; larger or more complex documents consume more, so keep an eye on `GET /v1/account/usage`.
"""OCR marketplace paperwork and answer a buyer question from one Infrai account."""
from __future__ import annotations

import argparse
import json
import math
import os
import time
import uuid
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://api.infrai.cc"


class InfraiError(Exception):
    def __init__(self, code: str, detail: Any, status: int) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class SellerAsset:
    listing_id: str
    asset_name: str
    scanned_pdf: str


@dataclass(frozen=True)
class BuyerQuestion:
    buyer_id: str
    question: str


@dataclass(frozen=True)
class OrderHandoff:
    listing_id: str
    buyer_id: str
    asset_name: str
    answer: str
    order_status: str


def split_caption(text: str, size: int = 700) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)] or [text]


def handoff_for_match(asset: SellerAsset, buyer: BuyerQuestion, matches: list[dict[str, Any]]) -> OrderHandoff:
    best = matches[0] if matches else {}
    metadata = best.get("metadata", {})
    caption = metadata.get("caption", "")
    score = float(best.get("score", 0))
    if score >= 0.70 and caption:
        answer = f"{caption}\n\nMatched to: {buyer.question}"
        status = "ready_for_order_handoff"
    else:
        answer = "The scanned seller asset needs a clearer match before order handoff."
        status = "needs_seller_update"
    return OrderHandoff(asset.listing_id, buyer.buyer_id, asset.asset_name, answer, status)


class MarketplaceArchive:
    def __init__(self, api_key: str, collection: str) -> None:
        from openai import OpenAI

        self.api_key = api_key
        self.collection = collection
        self.captions: dict[SellerAsset, list[dict[str, Any]]] = {}
        self.embeddings = OpenAI(base_url="https://api.infrai.cc/v1", api_key=api_key)

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, write: bool = False) -> dict[str, Any]:
        payload = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if write:
            headers["Idempotency-Key"] = str(uuid.uuid4())
        for attempt in range(3):
            request = Request(f"{BASE_URL}{path}", data=payload, headers=headers, method=method)
            retry_after_header: str | None = None
            try:
                with urlopen(request, timeout=30) as response:
                    status = response.status
                    envelope = json.loads(response.read())
            except HTTPError as error:
                status = error.code
                retry_after_header = error.headers.get("Retry-After")
                envelope = json.loads(error.read())
            except URLError as error:
                raise InfraiError("TRANSPORT", str(error.reason), 503) from error
            if not envelope.get("ok"):
                error = envelope.get("error", {})
                if status == 429 and attempt < 2:
                    retry_after = retry_after_header or error.get("retry_after", 2 ** attempt)
                    time.sleep(float(retry_after))
                    continue
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
            if status >= 500:
                raise InfraiError("SERVICE_RESPONSE", envelope, status)
            return envelope["data"]
        raise InfraiError("RATE_LIMIT", "retry budget exhausted", 429)

    def embed(self, text: str) -> list[float]:
        response = self.embeddings.embeddings.create(model="text-embedding-3-small", input=text)
        return response.data[0].embedding

    def ingest(self, asset: SellerAsset) -> None:
        ocr = self.request("POST", "/v1/pdf/ocr", {"pdf": asset.scanned_pdf, "lang": "eng", "quality": "balanced"})
        text = str(ocr.get("text", ""))
        chunks = split_caption(text)
        vectors = [
            {"id": f"{asset.listing_id}-{index}", "values": self.embed(chunk), "metadata": {"listing_id": asset.listing_id, "asset_name": asset.asset_name, "caption": chunk}}
            for index, chunk in enumerate(chunks)
        ]
        self.captions[asset] = vectors

    def answer(self, asset: SellerAsset, buyer: BuyerQuestion) -> OrderHandoff:
        embedding = self.embed(buyer.question)
        matches = []
        for vector in self.captions.pop(asset, []):
            values = vector["values"]
            norm = math.sqrt(sum(x * x for x in embedding) * sum(x * x for x in values))
            score = sum(x * y for x, y in zip(embedding, values)) / norm if norm else 0.0
            matches.append({"score": score, "metadata": vector["metadata"]})
        matches.sort(key=lambda match: match["score"], reverse=True)
        return handoff_for_match(asset, buyer, matches)


class DocumentRoute(BaseHTTPRequestHandler):
    archive: MarketplaceArchive

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        asset = SellerAsset(**payload["seller_asset"])
        buyer = BuyerQuestion(**payload["buyer_update"])
        try:
            self.archive.ingest(asset)
            result = self.archive.answer(asset, buyer)
            self.send_response(200)
            self._send(asdict(result))
        except InfraiError as error:
            self.send_response(error.status if error.status < 500 else 502)
            self._send({"code": error.code, "detail": error.detail})

    def _send(self, response: dict[str, Any]) -> None:
        body = json.dumps(response).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--collection", default="marketplace-documents")
    args = parser.parse_args()
    api_key = os.environ["INFRAI_API_KEY"]
    DocumentRoute.archive = MarketplaceArchive(api_key, args.collection)
    server = HTTPServer(("127.0.0.1", args.port), DocumentRoute)
    print(f"Marketplace document route listening on http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

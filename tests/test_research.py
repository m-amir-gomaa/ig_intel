import asyncio, unittest
import httpx
from sonaweft_web.research import candidates
from sonaweft_web.errors import DomainError


class ResearchTests(unittest.TestCase):
    def test_only_provider_dois_are_linked_and_no_verdict_is_fabricated(self):
        def response(req):
            self.assertEqual(req.url.host, "api.crossref.org")
            return httpx.Response(
                200,
                json={
                    "message": {
                        "items": [
                            {"DOI": "10.1234/fixture", "title": ["A source candidate"]},
                            {"DOI": "javascript:alert(1)", "title": ["Injected"]},
                        ]
                    }
                },
            )

        r = asyncio.run(candidates("A claim", httpx.MockTransport(response)))
        self.assertEqual(len(r["sources"]), 1)
        self.assertEqual(r["sources"][0]["status"], "candidate-not-reviewed")
        self.assertEqual(r["sources"][0]["url"], "https://doi.org/10.1234/fixture")

    def test_lookup_failure_does_not_invent_sources(self):
        with self.assertRaises(DomainError):
            asyncio.run(
                candidates(
                    "A claim", httpx.MockTransport(lambda req: httpx.Response(503))
                )
            )

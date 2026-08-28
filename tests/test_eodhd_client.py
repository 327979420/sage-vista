import urllib.error
import unittest
from unittest.mock import patch

from services.scanner.eodhd import get


class EodhdClientSecurityTests(unittest.TestCase):
    @patch.dict("os.environ", {"EODHD_API_TOKEN": "private-eodhd-token"})
    def test_request_error_does_not_expose_api_token(self):
        secret = "private-eodhd-token"
        error = urllib.error.HTTPError(
            f"https://eodhd.com/api/eod/SPY.US?api_token={secret}",
            401,
            "Unauthorized",
            None,
            None,
        )
        self.addCleanup(error.close)

        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                get("eod/SPY.US", _attempts=1)

        message = str(caught.exception)
        self.assertNotIn(secret, message)
        self.assertNotIn("https://", message)
        self.assertEqual(message, "EODHD request failed for eod/SPY.US (HTTP 401)")


if __name__ == "__main__":
    unittest.main()

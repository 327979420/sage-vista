import json,os,time,urllib.error,urllib.parse,urllib.request
from datetime import date,timedelta,datetime,timezone
from dataclasses import dataclass
from http.client import HTTPException, IncompleteRead
from pathlib import Path

BASE="https://eodhd.com/api";HEAD={"User-Agent":"SageVistaResearch/0.1","Accept":"application/json"}
def token():
    value=os.environ.get("EODHD_API_TOKEN","")
    if not value:
        env=Path(__file__).resolve().parents[2]/".env.local"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("EODHD_API_TOKEN="):value=line.split("=",1)[1].strip().strip('"').strip("'")
    if not value:raise RuntimeError("EODHD_API_TOKEN is not configured")
    return value
def get(path,**params):
    timeout=params.pop("_timeout",60);attempts=params.pop("_attempts",1)
    params={**params,"api_token":token(),"fmt":"json"};url=f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=HEAD),timeout=timeout) as response:return json.load(response)
        except (TimeoutError,urllib.error.URLError) as error:
            if attempt+1>=attempts:
                status=getattr(error,"code",None)
                detail=f" (HTTP {status})" if status is not None else ""
                # Never expose the request URL: it contains EODHD_API_TOKEN.
                raise RuntimeError(f"EODHD request failed for {path}{detail}") from None
            time.sleep(2**attempt)
def symbols(delisted=False):return get("exchange-symbol-list/US",delisted=int(delisted))
def prices(code,start="2000-01-01",end=None):
    params={"from":start,"period":"d"}
    if end:params["to"]=end
    return get(f"eod/{code}.US",**params)
def latest_reference_day(code="SPY",lookback_days=14,today=None):
    """Return the provider's latest completed US daily bar using a small query."""
    end=today or date.today();start=end-timedelta(days=lookback_days)
    rows=prices(code,start.isoformat(),end.isoformat())
    days=[row.get("date") for row in rows if row.get("date") and row.get("close") is not None]
    if not days:raise RuntimeError(f"No completed {code} daily bar is available")
    return max(days)
def actions(kind,code,start="2000-01-01"):return get(f"{kind}/{code}.US",**{"from":start})
def news(code,limit=3):return get("news",s=f"{code}.US",limit=limit,offset=0)


# M12 opt-in byte observation. Legacy get()/symbols() behavior is unchanged.
# No arbitrary endpoint, query, proxy, redirect or retry is accepted here.
MEMBERSHIP_URL = 'https://eodhd.com/api/exchange-symbol-list/US?delisted=0&fmt=json'
MEMBERSHIP_MAX_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class MembershipHttpObservation:
    started_at: datetime
    completed_at: datetime
    status: int | None
    content_length: int | None
    eof: bool
    failure: str | None
    raw: bytes


class _NoMembershipRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _membership_open(request):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoMembershipRedirect())
    return opener.open(request, timeout=30)


def observe_active_us_symbols():
    """One fixed request. Retain received error/partial bytes, never raw URLs.

    Socket timeout is per operation; the elapsed budget is checked between
    reads, not a hard process deadline. The future runner owns cancellation.
    This low-level transport grants no acquisition or publication authority.
    """
    start = datetime.now(timezone.utc)
    status, length, eof, failure, response = None, None, False, None, None
    captured = bytearray()
    deadline = time.monotonic() + 120
    try:
        url = MEMBERSHIP_URL + '&' + urllib.parse.urlencode({'api_token': token()})
        request = urllib.request.Request(url, headers={**HEAD, 'Accept-Encoding': 'identity'})
        try:
            response = _membership_open(request)
        except urllib.error.HTTPError as error:
            response = error  # Includes rejected redirects; preserve their body.
        with response:
            status = response.status
            if type(status) is not int or not 100 <= status <= 599:
                status, failure = None, 'http_status_invalid'
            elif status != 200:
                failure = 'http_status_rejected'
            if response.geturl() != url:
                failure = 'http_target_mismatch'
            headers = response.headers
            lengths = headers.get_all('Content-Length', [])
            encodings = headers.get_all('Content-Encoding', [])
            transfers = headers.get_all('Transfer-Encoding', [])
            if lengths:
                if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 12:
                    failure = 'http_length_invalid'
                else:
                    length = int(lengths[0])
            if (encodings and encodings != ['identity']) or (transfers and transfers != ['chunked']) or (transfers and lengths):
                failure = 'http_encoding_invalid'
            # Read even rejected statuses/headers, preserving all received bytes
            # up to the explicit cap+1. Beyond this, completeness stays false.
            while True:
                if time.monotonic() >= deadline:
                    failure = 'http_read_budget_exhausted'
                    break
                chunk = response.read(min(65536, MEMBERSHIP_MAX_BYTES + 1 - len(captured)))
                if not chunk:
                    eof = True
                    break
                captured.extend(chunk)
                if len(captured) > MEMBERSHIP_MAX_BYTES:
                    failure = 'http_body_too_large'
                    break
            if eof and length is not None and length != len(captured):
                failure = 'http_length_mismatch'
    except IncompleteRead as error:
        # http.client may return the last incomplete chunk on the exception.
        captured.extend(error.partial[:MEMBERSHIP_MAX_BYTES + 1 - len(captured)])
        failure = 'http_incomplete_read'
    except (OSError, urllib.error.URLError, HTTPException):
        failure = 'http_transport_failed'
    except RuntimeError:
        failure = 'http_credentials_unavailable'
    return MembershipHttpObservation(start, datetime.now(timezone.utc), status, length, eof, failure, bytes(captured))

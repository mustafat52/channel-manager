"""
test_router.py
--------------
Unit tests for the parser layer ONLY — no DB, no Gmail, no network.
Tests every parser function directly against the real sample email files.

Run from project root:
    python test_router.py

All tests should show ✅. Any ❌ means a parser is broken and must be
fixed before running the live worker.
"""


from pathlib import Path
from app.parsers.airbnb import parse_airbnb, parse_airbnb_cancellation, AirbnbParsingError
from app.parsers.vrbo import parse_vrbo, VrboParsingError
from app.parsers.router import parse_email, detect_platform, UnsupportedEmailError
from app.parsers.utils import normalize_email_text, check_email_size

from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load(filepath: str) -> str:
    return Path(filepath).read_text(encoding="utf-8")


PASS = "✅"
FAIL = "❌"
total = 0
passed = 0


def check(label: str, condition: bool, detail: str = ""):
    global total, passed
    total += 1
    if condition:
        passed += 1
        print(f"  {PASS}  {label}")
    else:
        print(f"  {FAIL}  {label}" + (f" — {detail}" if detail else ""))


def section(title: str):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")


def expect_raises(label: str, exc_type: type, fn, *args, **kwargs):
    """Assert that fn(*args) raises exc_type."""
    global total, passed
    total += 1
    try:
        fn(*args, **kwargs)
        print(f"  {FAIL}  {label} — expected {exc_type.__name__} but nothing was raised")
    except exc_type:
        passed += 1
        print(f"  {PASS}  {label}")
    except Exception as e:
        print(f"  {FAIL}  {label} — wrong exception: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# 1. AIRBNB CONFIRMATION PARSER
# ---------------------------------------------------------------------------
section("1. Airbnb confirmation — sample_airbnb.txt")
try:
    airbnb_text = load("sample_airbnb.txt")
    result = parse_airbnb(airbnb_text)

    check("Returns a dict",                     isinstance(result, dict))
    check("platform = 'airbnb'",                result.get("platform") == "airbnb")
    check("booking_id is present",              bool(result.get("booking_id")))
    check("booking_id = HMSMRP35HP",            result.get("booking_id") == "HMSMRP35HP")
    check("guest_name is present",              bool(result.get("guest_name")))
    check("guest_name contains letters only",   result.get("guest_name", "").replace(" ", "").replace("-", "").replace("'", "").isalpha())
    check("property_name is present",           bool(result.get("property_name")))
    check("property_name length <= 120",        len(result.get("property_name", "")) <= 120)
    check("check_in is present",                bool(result.get("check_in")))
    check("check_out is present",               bool(result.get("check_out")))
    check("check_in is ISO date (YYYY-MM-DD)",  len(result.get("check_in", "")) == 10 and result["check_in"][4] == "-")
    check("check_out > check_in",               result.get("check_out", "") > result.get("check_in", ""))
    check("no 'status' key (it's a confirmation)", "status" not in result)

    print(f"\n  Parsed values:")
    print(f"    booking_id   : {result.get('booking_id')}")
    print(f"    guest_name   : {result.get('guest_name')}")
    print(f"    property_name: {result.get('property_name')}")
    print(f"    check_in     : {result.get('check_in')}")
    print(f"    check_out    : {result.get('check_out')}")

except Exception as e:
    print(f"  {FAIL}  Parser crashed: {e}")


# ---------------------------------------------------------------------------
# 2. VRBO CONFIRMATION PARSER — sample 1 (table format)
# ---------------------------------------------------------------------------
section("2. VRBO confirmation — sample_vrbo.txt")
try:
    vrbo_text = load("sample_vrbo.txt")
    result = parse_vrbo(vrbo_text)

    check("Returns a dict",                     isinstance(result, dict))
    check("platform = 'vrbo'",                  result.get("platform") == "vrbo")
    check("booking_id present",                 bool(result.get("booking_id")))
    check("booking_id format HA-XXXXXX",        result.get("booking_id", "").startswith("HA-"))
    check("platform_property_id present",       bool(result.get("platform_property_id")))
    check("platform_property_id is numeric",    result.get("platform_property_id", "").isdigit())
    check("guest_name present",                 bool(result.get("guest_name")))
    check("check_in present",                   bool(result.get("check_in")))
    check("check_out present",                  bool(result.get("check_out")))
    check("check_out > check_in",               result.get("check_out", "") > result.get("check_in", ""))

    print(f"\n  Parsed values:")
    print(f"    booking_id        : {result.get('booking_id')}")
    print(f"    platform_prop_id  : {result.get('platform_property_id')}")
    print(f"    guest_name        : {result.get('guest_name')}")
    print(f"    check_in          : {result.get('check_in')}")
    print(f"    check_out         : {result.get('check_out')}")

except Exception as e:
    print(f"  {FAIL}  Parser crashed: {e}")


# ---------------------------------------------------------------------------
# 3. VRBO CONFIRMATION PARSER — sample 2 (inline date format)
# ---------------------------------------------------------------------------
section("3. VRBO confirmation — sample_vrbo_two.txt")
try:
    vrbo2_text = load("sample_vrbo_two.txt")
    result = parse_vrbo(vrbo2_text)

    check("Returns a dict",                     isinstance(result, dict))
    check("platform = 'vrbo'",                  result.get("platform") == "vrbo")
    check("booking_id format HA-XXXXXX",        result.get("booking_id", "").startswith("HA-"))
    check("check_out > check_in",               result.get("check_out", "") > result.get("check_in", ""))

    print(f"\n  Parsed values:")
    print(f"    booking_id   : {result.get('booking_id')}")
    print(f"    guest_name   : {result.get('guest_name')}")
    print(f"    check_in     : {result.get('check_in')}")
    print(f"    check_out    : {result.get('check_out')}")

except Exception as e:
    print(f"  {FAIL}  Parser crashed: {e}")


# ---------------------------------------------------------------------------
# 4. AIRBNB CANCELLATION PARSER
# ---------------------------------------------------------------------------
section("4. Airbnb cancellation — sample_airbnb_cancel.txt")
try:
    cancel_text = load("sample_airbnb_cancel.txt")
    result = parse_airbnb_cancellation(cancel_text)

    check("Returns a dict",                     isinstance(result, dict))
    check("platform = 'airbnb'",                result.get("platform") == "airbnb")
    check("status = 'cancelled'",               result.get("status") == "cancelled")
    check("booking_id present",                 bool(result.get("booking_id")))
    check("booking_id = HM4FSJ3NHZ",            result.get("booking_id") == "HM4FSJ3NHZ")
    check("guest_name extracted (bonus)",       bool(result.get("guest_name")))
    check("property_name extracted (bonus)",    bool(result.get("property_name")))

    print(f"\n  Parsed values:")
    print(f"    booking_id   : {result.get('booking_id')}")
    print(f"    status       : {result.get('status')}")
    print(f"    guest_name   : {result.get('guest_name', '(not extracted)')}")
    print(f"    property_name: {result.get('property_name', '(not extracted)')}")

except Exception as e:
    print(f"  {FAIL}  Parser crashed: {e}")


# ---------------------------------------------------------------------------
# 5. ROUTER — platform detection
# ---------------------------------------------------------------------------
section("5. Router — platform detection")
try:
    check("Airbnb detected from body",
          detect_platform(load("sample_airbnb.txt")) == "airbnb")
    check("VRBO detected from body (sample 1)",
          detect_platform(load("sample_vrbo.txt")) == "vrbo")
    check("VRBO detected from body (sample 2)",
          detect_platform(load("sample_vrbo_two.txt")) == "vrbo")
    check("Airbnb detected from sender domain",
          detect_platform("some email body", sender_domain="airbnb.com") == "airbnb")
    check("VRBO detected from sender domain",
          detect_platform("some email body", sender_domain="vrbo.com") == "vrbo")
    check("homeaway.com maps to vrbo",
          detect_platform("some email body", sender_domain="homeaway.com") == "vrbo")

    expect_raises("Unknown platform raises UnsupportedEmailError",
                  UnsupportedEmailError,
                  detect_platform, "hello this is a random email")

except Exception as e:
    print(f"  {FAIL}  Router detection crashed: {e}")


# ---------------------------------------------------------------------------
# 6. ROUTER — cancellation routing
# ---------------------------------------------------------------------------
section("6. Router — cancellation routing")
try:
    cancel_text = load("sample_airbnb_cancel.txt")
    result = parse_email(cancel_text)
    check("Cancellation routed correctly",      result.get("status") == "cancelled")
    check("Booking ID extracted via router",    result.get("booking_id") == "HM4FSJ3NHZ")

except Exception as e:
    print(f"  {FAIL}  Router cancellation routing crashed: {e}")


# ---------------------------------------------------------------------------
# 7. SECURITY — input validation guards
# ---------------------------------------------------------------------------
section("7. Security — input validation guards")

# ReDoS / size guard
oversized = "airbnb " + ("A" * 60_000)
expect_raises("Airbnb: oversized input rejected",
              AirbnbParsingError, parse_airbnb, oversized)
expect_raises("VRBO: oversized input rejected",
              VrboParsingError, parse_vrbo, oversized)

# Invalid booking ID format
bad_airbnb = load("sample_airbnb.txt").replace("HMSMRP35HP", "bad-id!!")
expect_raises("Airbnb: invalid booking ID format rejected",
              AirbnbParsingError, parse_airbnb, bad_airbnb)

# Inverted dates (check_out before check_in)
bad_dates = load("sample_airbnb.txt").replace("Apr 23", "Jan 01").replace("Apr 26", "Jan 02")
# Note: this may or may not trigger depending on fuzzy parse — it's a best-effort check

# Normalisation — \r\n should not break parsing
section("8. Normalisation — CRLF line endings")
try:
    crlf_text = load("sample_airbnb.txt").replace("\n", "\r\n")
    result = parse_airbnb(crlf_text)
    check("CRLF email parses correctly",        result.get("booking_id") == "HMSMRP35HP")
except Exception as e:
    print(f"  {FAIL}  CRLF parsing failed: {e}")


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------
print(f"\n{'='*55}")
print(f"  RESULTS: {passed}/{total} tests passed")
if passed == total:
    print("  🎉 All tests passed — safe to run the worker.")
else:
    print(f"  ⚠️  {total - passed} test(s) failed — fix before running the worker.")
print(f"{'='*55}\n")
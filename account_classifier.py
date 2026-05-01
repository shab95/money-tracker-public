import re


CASH = "Cash"
TAXABLE_INVESTMENTS = "Taxable Investments"
RETIREMENT_RESTRICTED = "Retirement / Restricted"
LIABILITY = "Liability"

# Backwards-compatible aliases for older code/tests.
LIQUID = CASH
INVESTED_LOCKED = RETIREMENT_RESTRICTED


RETIREMENT_KEYWORDS = [
    "401k",
    "401 k",
    "ira",
    "roth",
    "hsa",
    "health savings",
    "retirement",
]

TAXABLE_INVESTMENT_KEYWORDS = [
    "brokerage",
    "investment",
    "stock plan",
    "crypto",
    "robinhood",
    "e*trade",
    "fidelity",
]

LIABILITY_KEYWORDS = [
    "credit card",
    "card",
    "amex",
    "american express",
    "quicksilver",
    "discover",
]

LIQUID_KEYWORDS = [
    "checking",
    "cash",
    "savings",
]


def normalize_account_name(value):
    value = value or ""
    value = re.sub(r"\s*\(\d+\)\s*$", "", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def classify_account(bank, account, balance=0.0):
    text = f"{bank or ''} {account or ''}".lower()
    normalized = normalize_account_name(account)
    bank_text = (bank or "").lower()

    if "fidelity" in bank_text and normalized == "self-directed brokerage":
        return RETIREMENT_RESTRICTED

    if any(keyword in text for keyword in RETIREMENT_KEYWORDS):
        return RETIREMENT_RESTRICTED

    if any(keyword in text for keyword in TAXABLE_INVESTMENT_KEYWORDS):
        return TAXABLE_INVESTMENTS

    if any(keyword in text for keyword in LIABILITY_KEYWORDS) or float(balance or 0) < 0:
        return LIABILITY

    if any(keyword in normalized for keyword in LIQUID_KEYWORDS):
        return CASH

    return CASH


def should_sync_transactions(bank, account):
    text = f"{bank or ''} {account or ''}".lower()
    normalized = normalize_account_name(account)
    bank_text = (bank or "").lower()
    if "fidelity" in bank_text and normalized == "self-directed brokerage":
        return False, "retirement_or_restricted_account"
    if any(keyword in text for keyword in RETIREMENT_KEYWORDS):
        return False, "retirement_or_restricted_account"
    if any(keyword in text for keyword in TAXABLE_INVESTMENT_KEYWORDS):
        return False, "taxable_investment_account"
    if "savings" in text:
        return False, "savings_account"
    return True, ""

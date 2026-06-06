import re


CASH = "Cash"
TAXABLE_INVESTMENTS = "Taxable Investments"
RETIREMENT_RESTRICTED = "Retirement / Restricted"
LIABILITY = "Liability"
ACCOUNT_CLASSIFICATIONS = [CASH, TAXABLE_INVESTMENTS, RETIREMENT_RESTRICTED, LIABILITY]

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


def normalize_bank_name(value):
    return re.sub(r"\s+", " ", (value or "")).strip().lower()


def account_rule_key(bank, account):
    return (normalize_bank_name(bank), normalize_account_name(account))


def rules_to_map(rules):
    if rules is None:
        return {}
    if hasattr(rules, "to_dict"):
        records = rules.to_dict("records")
    else:
        records = rules
    return {
        account_rule_key(item.get("bank"), item.get("account")): item
        for item in records
        if item.get("bank") and item.get("account")
    }


def get_account_rule(rules_map, bank, account):
    return (rules_map or {}).get(account_rule_key(bank, account), {})


def optional_bool(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "include", "1"}:
            return True
        if lowered in {"false", "no", "exclude", "0"}:
            return False
        return None
    return bool(value)


_optional_bool = optional_bool


def classify_account(bank, account, balance=0.0, rule=None):
    rule = rule or {}
    rule_classification = rule.get("classification")
    if rule_classification in ACCOUNT_CLASSIFICATIONS:
        return rule_classification

    text = f"{bank or ''} {account or ''}".lower()
    normalized = normalize_account_name(account)
    bank_text = (bank or "").lower()

    if "fidelity" in bank_text and normalized == "self-directed brokerage":
        return RETIREMENT_RESTRICTED

    if any(keyword in text for keyword in LIABILITY_KEYWORDS) or float(balance or 0) < 0:
        return LIABILITY

    if any(keyword in text for keyword in RETIREMENT_KEYWORDS):
        return RETIREMENT_RESTRICTED

    if any(keyword in text for keyword in TAXABLE_INVESTMENT_KEYWORDS):
        return TAXABLE_INVESTMENTS

    if any(keyword in normalized for keyword in LIQUID_KEYWORDS):
        return CASH

    return CASH


def should_sync_transactions(bank, account, rule=None):
    rule = rule or {}
    include_override = optional_bool(rule.get("include_in_inbox"))
    if include_override is not None:
        return (True, "") if include_override else (False, "account_rule_excluded_from_inbox")

    text = f"{bank or ''} {account or ''}".lower()
    normalized = normalize_account_name(account)
    bank_text = (bank or "").lower()
    if any(keyword in text for keyword in LIABILITY_KEYWORDS):
        return True, ""
    if "fidelity" in bank_text and normalized == "self-directed brokerage":
        return False, "retirement_or_restricted_account"
    if any(keyword in text for keyword in RETIREMENT_KEYWORDS):
        return False, "retirement_or_restricted_account"
    if any(keyword in text for keyword in TAXABLE_INVESTMENT_KEYWORDS):
        return False, "taxable_investment_account"
    if "savings" in text:
        return False, "savings_account"
    return True, ""

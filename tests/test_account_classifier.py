import account_classifier as ac


def test_retirement_restricted_accounts():
    cases = [
        ("Fidelity Investments", "CAPITAL ONE 401K ASP (0072)"),
        ("Robinhood", "Robinhood Roth IRA (0799)"),
        ("Fidelity Investments", "Brokerage Health Savings (6355)"),
        ("Fidelity Investments", "Self-Directed Brokerage (3743)"),
    ]
    for bank, account in cases:
        assert ac.classify_account(bank, account, 100) == ac.RETIREMENT_RESTRICTED


def test_taxable_investment_accounts():
    cases = [
        ("E*Trade", "Individual Brokerage (1934)"),
        ("E*Trade", "Stock Plan (1934)"),
        ("Robinhood", "Robinhood individual (0052)"),
        ("Robinhood", "Crypto (4414)"),
    ]
    for bank, account in cases:
        assert ac.classify_account(bank, account, 100) == ac.TAXABLE_INVESTMENTS


def test_liability_and_liquid_accounts():
    assert ac.classify_account("Capital One", "360 Checking (3285)", 100) == ac.CASH
    assert ac.classify_account("American Express", "American Express Gold Card (1006)", -121) == ac.LIABILITY


def test_fidelity_self_directed_brokerage_skips_inbox_sync_as_retirement():
    included, reason = ac.should_sync_transactions("Fidelity Investments", "Self-Directed Brokerage (3743)")
    assert included is False
    assert reason == "retirement_or_restricted_account"

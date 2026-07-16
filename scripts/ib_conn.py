"""Shared IB Gateway connection helper (S73).

Default target = PAPER Gateway on port 4002 (S69 decision). LIVE (4001) must be
requested explicitly — never fall back to live silently. Override with env
IB_HOST / IB_PORT / IB_CLIENT_ID or the function arguments.

Market data types (ib.reqMarketDataType): 1=realtime, 2=frozen, 3=delayed,
4=delayed-frozen. OPRA option NBBO is realtime (subscribed, ~$1.50/mo);
SPX/VIX/ES index realtime is NOT subscribed (Error 354) — use delayed for those.
"""
import os

from ib_async import IB

HOST = os.environ.get("IB_HOST", "127.0.0.1")
PAPER_PORT, LIVE_PORT = 4002, 4001


def connect(port=None, client_id=None, timeout=15, market_data_type=None, allow_live=False):
    """Connect to IB Gateway; verifies the account really is PAPER (DU…).

    Live (4001) is refused unless allow_live=True — S70/S73 rule: everything
    runs against the paper account now that one exists.
    """
    port = int(port or os.environ.get("IB_PORT", PAPER_PORT))
    cid = int(client_id or os.environ.get("IB_CLIENT_ID", 0) or (os.getpid() % 900 + 100))
    if port == LIVE_PORT and not allow_live:
        raise SystemExit("Refusing LIVE port 4001 — pass allow_live=True if you really mean it.")
    ib = IB()
    try:
        ib.connect(HOST, port, clientId=cid, timeout=timeout)
    except Exception as e:
        # S75 auto-recovery: a "logged-in" Gateway whose API port never came up
        # (the 2026-07-16 silent-morning failure) — bring it up and retry ONCE.
        # Paper port only; never auto-launch anything for live.
        if port != PAPER_PORT:
            raise
        print(f"IB connect failed ({type(e).__name__}: {e}) — running gateway_ensure "
              f"to bring paper {PAPER_PORT} up, then retrying once...")
        try:
            import gateway_ensure
            gateway_ensure.main()
        except Exception as ge:
            print(f"gateway_ensure could not run: {type(ge).__name__}: {ge}")
        ib.connect(HOST, port, clientId=cid, timeout=timeout)  # retry; let it raise if still down
    accts = ib.managedAccounts()
    paper = all(a.startswith("D") for a in accts) if accts else False
    mode = {PAPER_PORT: "PAPER", LIVE_PORT: "LIVE"}.get(port, f"port {port}")
    print(f"IB connected {HOST}:{port} ({mode})  accounts={accts}  serverVersion={ib.client.serverVersion()}")
    if port == PAPER_PORT and not paper:
        ib.disconnect()
        raise SystemExit(f"Port 4002 answered but account(s) {accts} are NOT paper (no DU prefix) — "
                         "Gateway is logged in with the wrong credentials/mode. Aborting.")
    if not paper and not allow_live:
        ib.disconnect()
        raise SystemExit(f"Connected account(s) {accts} are LIVE — refusing without allow_live=True.")
    return ib

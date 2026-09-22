# Setup — ThetaData Terminal + IB Flex (August fill times)

Two one-time setups the USER does (creds/login). After each, tell me it's done and I run the pull.
Secrets never go in the repo or in chat. Related: [[thetadata_fill_validation]].

---

## A. ThetaData API key + Theta Terminal (Windows)

1. **Get the API key** — log in at <https://www.thetadata.net/portal/api_key> and copy it.
   (Prefer the key over email/password: it's revocable from the dashboard.)
2. **Install Java 21+** — Adoptium Temurin 21. Easiest via winget:
   ```powershell
   winget install --id EclipseAdoptium.Temurin.21.JDK -e --accept-package-agreements --accept-source-agreements
   ```
   Then **open a NEW PowerShell** (PATH refresh) and verify: `java -version` → must show 21+.
   (Fallback: Windows x64 MSI from <https://adoptium.net/temurin/releases/?version=21>, and tick
   "Add to PATH" in the installer's Custom Setup.)
3. **Download the terminal jar** — <https://downloads.thetadata.us/ThetaTerminalv3.jar> →
   put it in a folder **OUTSIDE this repo**, e.g. `C:\ThetaTerminal\`.
4. **Store the key as a user env var** (nothing lands in the repo). In PowerShell — replace the
   placeholder; **do NOT paste the real key into chat**:
   ```powershell
   [Environment]::SetEnvironmentVariable("THETADATA_API_KEY", "<your-key>", "User")
   ```
5. **Launch the terminal in a NEW PowerShell** (so it sees the new env var):
   ```powershell
   cd C:\ThetaTerminal
   java -jar ThetaTerminalv3.jar
   ```
   It authenticates with the env-var key and starts serving REST on localhost. **Leave it running.**
6. **Note the REST port** it prints on startup. Our scripts use **25503** (what ThetaData used when
   they ran our calls). If it reports a different port, tell me — it's a one-line change.
7. Tell me it's up → I run `scripts/thetadata_fetch.py --limit 1` (smoke), then the full pull.

**Don't:** pass `--api-key <key>` on the command line (visible in task managers); commit `.env`/
`creds.txt` (already git-ignored); paste the key into chat.

---

## B. August fill times from IB — PAPER account (manual route, simplest, no token)

Goal: recover IB's REAL execution timestamps + commissions (our `orders.csv` only has our
machine-clock time). Date range to request = **2026-08-01 → 2026-09-05** (covers every sim fill).

1. **Log into the PAPER account's Client Portal** — your paper trading account has its own
   username/password (set when the paper account was created), separate from live.
2. **Performance & Reports → Flex Queries.**
3. Under **Trade Confirmation Flex Query**, click **＋ (Create New)**. Name it e.g. `Aug fills`.
4. Expand the **Executions** section and tick these fields:
   Date/Time, Underlying Symbol, Symbol, Expiry, Strike, Put/Call, Buy/Sell, Quantity, Price,
   IB Commission, Order ID, Exec ID, Exchange.
5. Set **Format = XML**. Save.
6. **Run it** (the run/▶ icon) → Period = **Custom** → **2026-08-01 to 2026-09-05** → Run →
   **Download the XML** (save to e.g. `Downloads`).
7. Tell me the file path → I run:
   `.venv/Scripts/python.exe scripts/ib_flex_executions.py --file <path-to-downloaded.xml>`
   → parses it to `data/options_log/ib_flex_executions_<date>.csv`, joinable to our fills on `order_id`.

**Optional automated route** (only if we'll pull repeatedly): Settings → enable **Flex Web
Service** (copy the TOKEN); note the query's **Query ID**; set env `IBKR_FLEX_TOKEN` /
`IBKR_FLEX_QUERY`; then `ib_flex_executions.py` pulls it directly. For a one-time August pull the
manual XML route above is simpler.

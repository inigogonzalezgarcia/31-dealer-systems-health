# Weekly dealer systems review runbook

A 40-minute weekly review of the systems the dealer network depends on, with the integration team, the warranty team, the parts team, dealer IT and (for the red dealers) the area managers. The tool only reads exports; the fixes happen in the DMS, the integration platform, the warranty system and the parts distribution, each through its own process.

## Monday morning (20 minutes)

1. Export the interface log, the warranty claims and the catalogue status (read-only queries, adapted once to your schema):
   ```powershell
   .\scripts\Export-DealerData.ps1 -ServerInstance sql-dealer01\INTEGRATION -Database DealerHub -OutputFolder .\data
   ```
2. Copy the current `dealers.csv` and `onboarding.csv` from the network register, and check `settings.json`: the current catalogue and price file, certified DMS versions, the limits agreed with the warranty team.
3. Build the outputs and send `dealer-review.md` as the agenda:
   ```bash
   python -m dealerhealth review data/ --title "Dealer systems review · week 44"
   ```
4. Send each red dealer's area manager its line from `dealers.csv` and the claims from `claims-at-risk.csv` before the meeting.

## Agenda

| Minutes | Topic | Output |
|---|---|---|
| 5 | Fix first: critical feeds stopped, price files not applied, terminated dealers still connected, openings at risk | `report.html` → Fix first |
| 10 | Interfaces: failing, rejecting and empty feeds, with the DMS vendor if needed | `interfaces.csv` |
| 10 | Warranty: drafts at the limit, the brand's own queue, unanswered information requests, rejection reasons, unpaid claims | `claims-at-risk.csv`, `rejections.csv` |
| 5 | Parts: catalogue and price file per dealer | `catalogue.csv` |
| 10 | Network: DMS versions, dealers opening, dealers leaving | `report.html` → Dealers onboarding, `findings.csv` |

## How to read it

- **A feed that fails one night is already red** for repair orders and warranty claims: the next morning the brand is a day behind and the dealer does not know it. Parts stock and vehicle sales get longer limits.
- **An empty feed is worse than a failing one**, because nothing alerts. Runs that succeed with zero records for several days usually mean a changed filter or an export switched off in the DMS.
- **Rejected records point to master data.** Group the rejections by error code before calling the dealer: most are labour operations or part numbers the dealer's catalogue does not have yet.
- **The brand's queue is ours.** Claims waiting for a decision beyond the target are not the dealer's fault, and dealers measure the brand by them.
- **A high rejection rate with one dominant reason** is a training or catalogue problem. Look at the dealer's catalogue version before talking about the claims.

## After the meeting

- Put each action from `actions.csv` in the tracker with its owner and a date.
- Raise a change for anything that touches the integration platform or the warranty rules.
- Keep each week's output folder; the next review starts by checking last week's red dealers.

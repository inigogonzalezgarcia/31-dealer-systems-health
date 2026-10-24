-- One row per warranty claim whose repair date is in the last $(Days) days, plus every claim still open.
SELECT  c.ClaimNumber           AS [Claim number],
        c.DealerCode            AS [Dealer code],
        c.Vin                   AS [VIN],
        c.RepairDate            AS [Repair date],
        c.SubmittedAt           AS [Submitted],
        c.Status                AS [Status],         -- draft / submitted / info requested / accepted / rejected / paid
        c.StatusChangedAt       AS [Status date],
        c.MainLabourOp          AS [Labour op],
        c.TotalClaimed          AS [Amount],
        c.ReasonText            AS [Reason],         -- rejection reason or information requested
        c.PaidAt                AS [Paid date]
FROM    warranty.Claim AS c
WHERE   c.RepairDate >= DATEADD(day, -$(Days), SYSDATETIME())
   OR   c.Status IN ('draft', 'submitted', 'info requested', 'accepted')

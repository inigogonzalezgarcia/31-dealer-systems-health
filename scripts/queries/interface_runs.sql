-- One row per interface run in the last $(Days) days. Adapt table and column names to your integration platform's job log.
SELECT  j.DealerCode            AS [Dealer code],
        j.InterfaceName         AS [Interface],      -- repair_orders, warranty_claims, parts_orders, vehicle_sales, stock (or close)
        j.StartedAt             AS [Run at],
        j.Result                AS [Status],         -- ok / partial / failed (success, warning, error also accepted)
        j.RecordsProcessed      AS [Records],
        j.RecordsRejected       AS [Errors]
FROM    integration.JobRun AS j
WHERE   j.StartedAt >= DATEADD(day, -$(Days), SYSDATETIME())

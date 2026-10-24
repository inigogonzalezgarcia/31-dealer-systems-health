-- One row per dealer: what parts catalogue and price file its DMS last confirmed.
SELECT  d.DealerCode            AS [Dealer code],
        d.CatalogueVersion      AS [Catalogue version],
        d.CatalogueConfirmedAt  AS [Catalogue date],
        d.PriceFileVersion      AS [Price file version],
        d.PriceFileConfirmedAt  AS [Price file date]
FROM    parts.DealerDistributionStatus AS d

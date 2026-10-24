<#
.SYNOPSIS
    Read-only export of the dealer interface log, warranty claims and catalogue status to the CSV files used by dealerhealth.

.DESCRIPTION
    Every brand stores this data in its own systems, so the queries live in a .sql file per output that you adapt once to your schema:

      queries\interface_runs.sql      one row per interface run: dealer code, interface, run time, status, records, errors
      queries\warranty_claims.sql     one row per claim: number, dealer code, VIN, repair date, submitted, status, status date,
                                      labour op, amount, reason, paid date
      queries\catalogue_status.sql    one row per dealer: catalogue version and date, price file version and date

    The column names in the CSVs only need to be close: dealerhealth accepts common alternatives (see docs/data-format.md).
    dealers.csv and onboarding.csv usually come from the network team's register and are not exported here.

    Safety: the script refuses any query that is not a single SELECT (or WITH ... SELECT) statement, connects with Windows
    authentication or a credential you type in, and stores nothing. Use an account with read access only.

.PARAMETER ServerInstance
    SQL Server instance that holds the integration log and the warranty data (for example sql-dealer01\INTEGRATION).

.PARAMETER Database
    Database name. If the outputs live in different databases, run the script once per database with -Only.

.PARAMETER QueryFolder
    Folder with the .sql files (default .\scripts\queries).

.PARAMETER Only
    Export only some of the outputs: interface_runs, warranty_claims, catalogue_status.

.PARAMETER Days
    Look-back window passed to the queries as the sqlcmd variable $(Days) (default 150).

.PARAMETER Credential
    SQL login to use instead of Windows authentication.

.EXAMPLE
    .\scripts\Export-DealerData.ps1 -ServerInstance sql-dealer01\INTEGRATION -Database DealerHub -OutputFolder .\data
    python -m dealerhealth review .\data
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ServerInstance,
    [Parameter(Mandatory)] [string] $Database,
    [string] $OutputFolder = '.\data',
    [string] $QueryFolder = (Join-Path $PSScriptRoot 'queries'),
    [ValidateSet('interface_runs', 'warranty_claims', 'catalogue_status')] [string[]] $Only = @('interface_runs', 'warranty_claims', 'catalogue_status'),
    [int] $Days = 150,
    [pscredential] $Credential
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Module -ListAvailable -Name SqlServer)) {
    throw 'The SqlServer module is required: Install-Module SqlServer -Scope CurrentUser'
}
Import-Module SqlServer
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null

function Assert-ReadOnly([string] $Sql, [string] $Name) {
    # strip comments, then allow exactly one statement that starts with SELECT or WITH and contains no write keywords
    $clean = ($Sql -replace '(?s)/\*.*?\*/', '' -replace '--[^\r\n]*', '').Trim().TrimEnd(';')
    if ($clean -notmatch '^(?i)(select|with)\b') { throw "$Name is not a SELECT statement" }
    if ($clean -match ';') { throw "$Name contains more than one statement" }
    if ($clean -match '(?i)\b(insert|update|delete|merge|drop|alter|create|truncate|exec|execute|grant|revoke|into)\b') {
        throw "$Name contains a keyword that is not allowed in a read-only export"
    }
}

foreach ($name in $Only) {
    $file = Join-Path $QueryFolder "$name.sql"
    if (-not (Test-Path $file)) { Write-Warning "$file not found, skipping $name"; continue }
    $sql = Get-Content -Raw -Path $file
    Assert-ReadOnly $sql $name
    $params = @{ ServerInstance = $ServerInstance; Database = $Database; Query = $sql; Variable = @("Days=$Days"); QueryTimeout = 600 }
    if ($Credential) { $params.Credential = $Credential }
    Write-Host "Exporting $name..."
    $rows = Invoke-Sqlcmd @params
    $rows | Select-Object -Property * -ExcludeProperty RowError, RowState, Table, ItemArray, HasErrors |
        Export-Csv -Path (Join-Path $OutputFolder "$name.csv") -NoTypeInformation -Encoding UTF8
    Write-Host ("  {0} rows" -f @($rows).Count)
}
Write-Host "Done. Add dealers.csv, onboarding.csv and settings.json, then: python -m dealerhealth review $OutputFolder"

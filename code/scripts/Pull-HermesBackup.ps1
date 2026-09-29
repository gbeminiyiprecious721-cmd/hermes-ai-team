# Pull-HermesBackup.ps1
# Copies the newest Hermes VPS backups to this PC and brings new agent drafts into the Obsidian inbox.
#  - custom + data archives -> C:\path\to\Hermes-VPS-Backups\{custom,data}\   (local disk, NOT OneDrive)
#  - secrets archive is deliberately NOT copied (see SECRETS-INVENTORY.md)
#  - vault drafts: server 00-Inbox\Agent-Outputs -> PC vault 00-Inbox\Agent-Outputs (new files only, never overwrites)
# Uses the same SSH key as the assistant. If that key is ever revoked, generate a new key and edit $Key below.
$ErrorActionPreference = "Stop"
$Key      = "C:\path\to\your\ssh_key"
$Server   = "root@<server-ip-or-tailnet-name>"
$Root     = "C:\path\to\Hermes-VPS-Backups"
$Vault    = "C:\path\to\Your-Obsidian-Vault"
$VaultSrc = "/srv/hermes/obsidian/Precious-AI-Vault/00-Inbox"
$Keep     = 7
$Log      = Join-Path $Root "pull.log"
$SshOpts  = @("-i", $Key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "StrictHostKeyChecking=accept-new")

function Log($m) { $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m; Add-Content -Path $Log -Value $line; Write-Host $line }

try {
    Log "start"
    foreach ($tier in @("custom", "data")) {
        $dir = Join-Path $Root $tier
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $latest = (& ssh @SshOpts $Server "ls -t /root/backups/$tier/$tier-*.tar.gz | head -1").Trim()
        if (-not $latest) { throw "no $tier archive found on the server" }
        $name = Split-Path $latest -Leaf
        $dest = Join-Path $dir $name
        if (Test-Path $dest) { Log "$tier already have $name" }
        else {
            & scp @SshOpts "${Server}:$latest" $dest
            if ($LASTEXITCODE -ne 0) { throw "scp failed for $name" }
            $sums = & ssh @SshOpts $Server "cat /root/backups/$tier/SHA256SUMS"
            $want = ($sums | Where-Object { $_ -match [regex]::Escape($name) } | Select-Object -First 1)
            if (-not $want) { throw "no checksum listed for $name" }
            $expected = ($want -split "\s+")[0].ToLower()
            $actual = (Get-FileHash -Algorithm SHA256 $dest).Hash.ToLower()
            if ($expected -ne $actual) { Remove-Item $dest -Force; throw "checksum mismatch for $name" }
            Log "$tier copied and verified: $name ($([math]::Round((Get-Item $dest).Length/1MB,1)) MB)"
        }
        Get-ChildItem $dir -Filter "$tier-*.tar.gz" | Sort-Object Name -Descending | Select-Object -Skip $Keep | ForEach-Object { Remove-Item $_.FullName -Force; Log "pruned $($_.Name)" }
    }

    # agent drafts -> Obsidian inbox, new files only
    if (Test-Path $Vault) {
        $target = Join-Path $Vault "00-Inbox"
        $before = (Get-ChildItem (Join-Path $target "Agent-Outputs") -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
        $cmd = "tar -C '$VaultSrc' -cf - Agent-Outputs"
        & cmd.exe /c "ssh -i `"$Key`" -o BatchMode=yes -o ConnectTimeout=20 $Server `"$cmd`" | tar -xkf - -C `"$target`" 2>nul"
        $after = (Get-ChildItem (Join-Path $target "Agent-Outputs") -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
        Log "vault drafts: $before -> $after files in 00-Inbox\Agent-Outputs (existing files never overwritten)"
    } else { Log "vault path not found, drafts skipped" }
    Log "done"
} catch { Log "ERROR: $($_.Exception.Message)"; exit 1 }

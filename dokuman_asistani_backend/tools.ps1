function Get-Token {
  param([string]$User="cemre2",[string]$Pass="12345678")
  $apiBase = if ($env:DJANGO_API_BASE_URL) { $env:DJANGO_API_BASE_URL.TrimEnd("/") } else { "http://127.0.0.1:8001" }
  $authBody = @{ username=$User; password=$Pass } | ConvertTo-Json -Compress

  $TOK = Invoke-RestMethod -Proxy $null -Method Post `
    -Uri "$apiBase/api/kimlik/token/" `
    -ContentType "application/json" `
    -Body $authBody

  $script:TOKEN  = $TOK.access
  $script:H      = @{ Authorization = ("Bearer {0}" -f $script:TOKEN) }
  $script:H_CURL = "Authorization: Bearer $script:TOKEN"

  "TOKEN ready. len=$($script:TOKEN.Length)"
}

function Post-JsonUtf8 {
  param([string]$Url, [hashtable]$Obj)

  if (-not $script:H) { throw "Önce Get-Token çalıştır." }

  $json  = $Obj | ConvertTo-Json -Compress
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)

  Invoke-RestMethod -Proxy $null -Method Post `
    -Uri $Url `
    -Headers $script:H `
    -ContentType "application/json; charset=utf-8" `
    -Body $bytes
}

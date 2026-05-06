function Get-Token {
  $apiBase = if ($env:DJANGO_API_BASE_URL) { $env:DJANGO_API_BASE_URL.TrimEnd("/") } else { "http://127.0.0.1:8001" }
  $authBody = @{ username="cemre2"; password="12345678" } | ConvertTo-Json -Compress
  $TOK = Invoke-RestMethod -Proxy $null -Method Post `
    -Uri "$apiBase/api/kimlik/token/" `
    -ContentType "application/json" `
    -Body $authBody

  $script:TOKEN = $TOK.access

  # curl için string header
  $script:H_CURL = "Authorization: Bearer $script:TOKEN"

  # Invoke-RestMethod için hashtable header
  $script:H = @{ Authorization = ("Bearer {0}" -f $script:TOKEN) }

  "TOKEN ready. len=$($script:TOKEN.Length)"
}

function Post-JsonUtf8($url, $obj) {
  $json = $obj | ConvertTo-Json -Compress
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)

  Invoke-RestMethod -Proxy $null -Method Post `
    -Uri $url `
    -Headers $script:H `
    -ContentType "application/json; charset=utf-8" `
    -Body $bytes
}

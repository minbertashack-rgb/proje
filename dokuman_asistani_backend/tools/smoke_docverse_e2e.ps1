param(
    [Parameter(Mandatory = $true)]
    [string]$Username,

    [Parameter(Mandatory = $true)]
    [string]$Password,

    [Parameter(Mandatory = $true)]
    [string]$FilePath,

    [string]$BaseUrl = $(if ($env:DJANGO_API_BASE_URL) { $env:DJANGO_API_BASE_URL } else { "http://127.0.0.1:8001" }),
    [string]$Mesaj = "Bu parcayi sade anlat.",
    [string]$EvidenceQuestion = "Bu dokumanda hangi kanit kullaniliyor?",
    [int]$MaxTokens = 96,
    [int]$AuthTimeoutSec = 20,
    [int]$UploadTimeoutSec = 90,
    [int]$ListTimeoutSec = 30,
    [int]$ExplainTimeoutSec = 180,
    [int]$EvidenceTimeoutSec = 180,
    [int]$NotesTimeoutSec = 60,
    [int]$ThrottleAttempts = 6,
    [string]$SecondaryUsername = "",
    [string]$SecondaryPassword = "",
    [switch]$SkipExplain,
    [switch]$ExpectOcrSignal,
    [switch]$ProbeEvidence,
    [switch]$ProbeNotes,
    [switch]$ProbeForeignAccess,
    [switch]$ProbeThrottle,
    [switch]$RequireThrottleHit,
    [switch]$PlanOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Net.Http

function ConvertFrom-JsonSafe {
    param([string]$Text)

    $raw = if ($null -eq $Text) { "" } else { [string]$Text }
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }

    try {
        return $raw | ConvertFrom-Json -Depth 16
    }
    catch {
        try {
            return $raw | ConvertFrom-Json
        }
        catch {
            return $null
        }
    }
}

function Get-JsonFieldNames {
    param([object]$Payload)

    if ($null -eq $Payload) {
        return @()
    }

    return @($Payload.PSObject.Properties | ForEach-Object { [string]$_.Name })
}

function Get-JsonStringValue {
    param(
        [object]$Payload,
        [string]$Name
    )

    $value = Get-JsonPropertyValue -Payload $Payload -Name $Name
    if ($null -eq $value) {
        return ""
    }

    return [string]$value
}

function Get-JsonPropertyValue {
    param(
        [object]$Payload,
        [string]$Name
    )

    if ($null -eq $Payload -or [string]::IsNullOrWhiteSpace($Name)) {
        return $null
    }

    if ($Payload -is [System.Collections.IDictionary]) {
        if ($Payload.Contains($Name)) {
            return $Payload[$Name]
        }
        return $null
    }

    $prop = $Payload.PSObject.Properties[$Name]
    if ($null -eq $prop) {
        return $null
    }

    return $prop.Value
}

function ConvertTo-CompactText {
    param([object]$Value)

    if ($null -eq $Value) {
        return ""
    }

    if ($Value -is [string]) {
        return [string]$Value
    }

    try {
        return ($Value | ConvertTo-Json -Depth 8 -Compress)
    }
    catch {
        return [string]$Value
    }
}

function Get-ContentTypeForFile {
    param([string]$Path)

    switch ([System.IO.Path]::GetExtension($Path).ToLowerInvariant()) {
        ".pdf" { return "application/pdf" }
        ".docx" { return "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }
        ".xlsx" { return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }
        ".pptx" { return "application/vnd.openxmlformats-officedocument.presentationml.presentation" }
        ".txt" { return "text/plain" }
        ".md" { return "text/markdown" }
        ".py" { return "text/x-python" }
        ".js" { return "application/javascript" }
        ".ts" { return "text/plain" }
        ".png" { return "image/png" }
        ".jpg" { return "image/jpeg" }
        ".jpeg" { return "image/jpeg" }
        default { return "application/octet-stream" }
    }
}

function Get-BodySummary {
    param([string]$BodyText)

    $summary = if ($null -eq $BodyText) { "" } else { [string]$BodyText }
    $summary = $summary.Trim()
    if ([string]::IsNullOrWhiteSpace($summary)) {
        return ""
    }

    $summary = [System.Text.RegularExpressions.Regex]::Replace($summary, "\s+", " ")
    if ($summary.Length -gt 240) {
        $summary = $summary.Substring(0, 240) + "..."
    }

    return $summary
}

function New-StepFailureMessage {
    param(
        [string]$Step,
        [int]$TimeoutSec,
        [string]$Url,
        [string]$Reason,
        [string]$BodyText = ""
    )

    $parts = @(
        ("{0} FAILED: {1}" -f $Step, $Reason),
        ("timeout={0}s" -f $TimeoutSec),
        ("url={0}" -f $Url)
    )

    $bodySummary = Get-BodySummary -BodyText $BodyText
    if (-not [string]::IsNullOrWhiteSpace($bodySummary)) {
        $parts += ("body={0}" -f $bodySummary)
    }

    return ($parts -join " ")
}

function Invoke-ApiRequest {
    param(
        [System.Net.Http.HttpClient]$Client,
        [string]$StepName,
        [int]$TimeoutSec,
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers = $null,
        [object]$Body = $null,
        [System.Net.Http.HttpContent]$Content = $null
    )

    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), $Url)
    $response = $null
    $cancellationSource = [System.Threading.CancellationTokenSource]::new()
    try {
        $cancellationSource.CancelAfter([TimeSpan]::FromSeconds($TimeoutSec))

        if ($Headers) {
            foreach ($entry in $Headers.GetEnumerator()) {
                [void]$request.Headers.TryAddWithoutValidation([string]$entry.Key, [string]$entry.Value)
            }
        }

        if ($null -ne $Content) {
            $request.Content = $Content
        }
        elseif ($null -ne $Body) {
            $json = $Body | ConvertTo-Json -Depth 16 -Compress
            $request.Content = [System.Net.Http.StringContent]::new(
                $json,
                [System.Text.Encoding]::UTF8,
                "application/json"
            )
        }

        $response = $Client.SendAsync($request, $cancellationSource.Token).GetAwaiter().GetResult()
        $bodyText = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        return [pscustomobject]@{
            StatusCode        = [int]$response.StatusCode
            IsSuccessStatusCode = [bool]$response.IsSuccessStatusCode
            BodyText          = $bodyText
            Json              = ConvertFrom-JsonSafe $bodyText
        }
    }
    catch [System.Threading.Tasks.TaskCanceledException] {
        throw (New-StepFailureMessage -Step $StepName -TimeoutSec $TimeoutSec -Url $Url -Reason "timeout/cancelled")
    }
    finally {
        if ($null -ne $response) { $response.Dispose() }
        $cancellationSource.Dispose()
        $request.Dispose()
    }
}

function Resolve-DocId {
    param([object]$Payload)

    if ($null -eq $Payload) {
        return $null
    }
    $docId = Get-JsonPropertyValue -Payload $Payload -Name "doc_id"
    if ($null -ne $docId) {
        return [int]$docId
    }
    $id = Get-JsonPropertyValue -Payload $Payload -Name "id"
    if ($null -ne $id) {
        return [int]$id
    }
    return $null
}

function New-AuthHeaders {
    param(
        [System.Net.Http.HttpClient]$Client,
        [string]$ResolvedBaseUrl,
        [string]$StepPrefix,
        [string]$UserName,
        [string]$UserPassword,
        [int]$TimeoutSec
    )

    $authUrl = "$ResolvedBaseUrl/api/kimlik/token/"
    Write-Host "$StepPrefix AUTH START timeout=${TimeoutSec}s url=$authUrl"
    $authResponse = Invoke-ApiRequest `
        -Client $Client `
        -StepName "$StepPrefix AUTH" `
        -TimeoutSec $TimeoutSec `
        -Method "POST" `
        -Url $authUrl `
        -Body @{ username = $UserName; password = $UserPassword }

    $accessToken = Get-JsonStringValue -Payload $authResponse.Json -Name "access"
    if (-not $authResponse.IsSuccessStatusCode -or [string]::IsNullOrWhiteSpace($accessToken)) {
        throw (New-StepFailureMessage `
            -Step "$StepPrefix AUTH" `
            -TimeoutSec $TimeoutSec `
            -Url $authUrl `
            -Reason ("http={0} access_missing={1}" -f $authResponse.StatusCode, [string]::IsNullOrWhiteSpace($accessToken)) `
            -BodyText (Get-ErrorDetail -Prefix "" -Payload $authResponse.Json -BodyText $authResponse.BodyText))
    }

    Write-Host "$StepPrefix AUTH OK status=$($authResponse.StatusCode)"
    return @{
        Authorization = "Bearer $accessToken"
    }
}

function Select-FirstSuitablePart {
    param([object[]]$Parcalar)

    foreach ($parca in @($Parcalar)) {
        $metin = if ($null -eq $parca.metin) { "" } else { [string]$parca.metin }
        if ($parca.id -and -not [string]::IsNullOrWhiteSpace($metin)) {
            return $parca
        }
    }

    foreach ($parca in @($Parcalar)) {
        if ($parca.id) {
            return $parca
        }
    }

    return $null
}

function Get-ErrorDetail {
    param(
        [string]$Prefix,
        [object]$Payload,
        [string]$BodyText
    )

    $detail = ""
    if ($Payload) {
        $detailValue = Get-JsonPropertyValue -Payload $Payload -Name "detail"
        if ($null -ne $detailValue) {
            $detail = [string]$detailValue
        }
        else {
            $mesajValue = Get-JsonPropertyValue -Payload $Payload -Name "mesaj"
            if ($null -ne $mesajValue) {
                $detail = [string]$mesajValue
            }
        }
        if ([string]::IsNullOrWhiteSpace($detail)) {
            $hataValue = Get-JsonPropertyValue -Payload $Payload -Name "hata"
            if ($null -ne $hataValue) {
                $detail = [string]$hataValue
            }
        }
        if ([string]::IsNullOrWhiteSpace($detail)) {
            $detail = ConvertTo-CompactText -Value $Payload
        }
    }

    if ([string]::IsNullOrWhiteSpace($detail)) {
        $detail = if ($null -eq $BodyText) { "" } else { [string]$BodyText }
    }

    $detail = $detail.Trim()
    if ($detail.Length -gt 240) {
        $detail = $detail.Substring(0, 240) + "..."
    }

    return "$Prefix$detail"
}

$resolvedBaseUrl = $BaseUrl.TrimEnd("/")
$client = [System.Net.Http.HttpClient]::new()
$client.Timeout = [System.Threading.Timeout]::InfiniteTimeSpan

try {
    try {
        $resolvedFile = (Resolve-Path -LiteralPath $FilePath -ErrorAction Stop).ProviderPath
    }
    catch {
        throw "INPUT FAILED: dosya bulunamadi. file_path=$FilePath"
    }

    Write-Host "=== Smoke Plan ==="
    Write-Host "base_url=$resolvedBaseUrl file=$resolvedFile"
    Write-Host "expect_ocr_signal=$ExpectOcrSignal probe_evidence=$ProbeEvidence probe_notes=$ProbeNotes probe_foreign_access=$ProbeForeignAccess probe_throttle=$ProbeThrottle"
    if ($PlanOnly) {
        exit 0
    }

    $headers = New-AuthHeaders `
        -Client $client `
        -ResolvedBaseUrl $resolvedBaseUrl `
        -StepPrefix "PRIMARY" `
        -UserName $Username `
        -UserPassword $Password `
        -TimeoutSec $AuthTimeoutSec

    $fileStream = [System.IO.File]::OpenRead($resolvedFile)
    $multipart = $null
    $fileContent = $null
    $uploadUrl = "$resolvedBaseUrl/api/dokuman-asistani/dokumanlar/yukle/"
    try {
        Write-Host "UPLOAD START timeout=${UploadTimeoutSec}s url=$uploadUrl"
        $multipart = [System.Net.Http.MultipartFormDataContent]::new()
        $fileContent = [System.Net.Http.StreamContent]::new($fileStream)
        $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse((Get-ContentTypeForFile -Path $resolvedFile))
        [void]$multipart.Add($fileContent, "dosya", [System.IO.Path]::GetFileName($resolvedFile))
        [void]$multipart.Add(
            [System.Net.Http.StringContent]::new(
                [System.IO.Path]::GetFileNameWithoutExtension($resolvedFile),
                [System.Text.Encoding]::UTF8
            ),
            "baslik"
        )

        $uploadResponse = Invoke-ApiRequest `
            -Client $client `
            -StepName "UPLOAD" `
            -TimeoutSec $UploadTimeoutSec `
            -Method "POST" `
            -Url $uploadUrl `
            -Headers $headers `
            -Content $multipart
    }
    finally {
        if ($null -ne $multipart) { $multipart.Dispose() }
        if ($null -ne $fileContent) { $fileContent.Dispose() }
        $fileStream.Dispose()
    }

    if ($uploadResponse.StatusCode -ne 201) {
        throw (New-StepFailureMessage `
            -Step "UPLOAD" `
            -TimeoutSec $UploadTimeoutSec `
            -Url $uploadUrl `
            -Reason ("http={0}" -f $uploadResponse.StatusCode) `
            -BodyText (Get-ErrorDetail -Prefix "" -Payload $uploadResponse.Json -BodyText $uploadResponse.BodyText))
    }

    $docId = Resolve-DocId -Payload $uploadResponse.Json
    if ($null -eq $docId) {
        throw (New-StepFailureMessage `
            -Step "UPLOAD" `
            -TimeoutSec $UploadTimeoutSec `
            -Url $uploadUrl `
            -Reason "doc_id bulunamadi" `
            -BodyText $uploadResponse.BodyText)
    }
    $uploadDurum = Get-JsonStringValue -Payload $uploadResponse.Json -Name "durum"
    $uploadParcaSayisi = Get-JsonStringValue -Payload $uploadResponse.Json -Name "parca_sayisi"
    if ([string]::IsNullOrWhiteSpace($uploadDurum)) { $uploadDurum = "-" }
    if ([string]::IsNullOrWhiteSpace($uploadParcaSayisi)) { $uploadParcaSayisi = "-" }
    if ($ExpectOcrSignal) {
        $ocrValue = Get-JsonPropertyValue -Payload $uploadResponse.Json -Name "ocr"
        if ($ocrValue -ne $true) {
            throw (New-StepFailureMessage `
                -Step "UPLOAD" `
                -TimeoutSec $UploadTimeoutSec `
                -Url $uploadUrl `
                -Reason "ocr signal bekleniyordu ama response icinde true degildi" `
                -BodyText $uploadResponse.BodyText)
        }
    }
    Write-Host "UPLOAD OK status=$($uploadResponse.StatusCode) id=$docId durum=$uploadDurum parca_sayisi=$uploadParcaSayisi"

    $parcalarUrl = "$resolvedBaseUrl/api/dokuman-asistani/dokumanlar/$docId/parcalar/"
    Write-Host "PARCALAR START timeout=${ListTimeoutSec}s url=$parcalarUrl"
    $parcalarResponse = Invoke-ApiRequest `
        -Client $client `
        -StepName "PARCALAR" `
        -TimeoutSec $ListTimeoutSec `
        -Method "GET" `
        -Url $parcalarUrl `
        -Headers $headers

    if (-not $parcalarResponse.IsSuccessStatusCode) {
        throw (New-StepFailureMessage `
            -Step "PARCALAR" `
            -TimeoutSec $ListTimeoutSec `
            -Url $parcalarUrl `
            -Reason ("http={0}" -f $parcalarResponse.StatusCode) `
            -BodyText (Get-ErrorDetail -Prefix "" -Payload $parcalarResponse.Json -BodyText $parcalarResponse.BodyText))
    }

    $parcalar = @()
    $parcalarValue = Get-JsonPropertyValue -Payload $parcalarResponse.Json -Name "parcalar"
    if ($parcalarResponse.Json -and $null -ne $parcalarValue) {
        $parcalar = @($parcalarValue)
    }

    if ($parcalar.Count -eq 0) {
        throw (New-StepFailureMessage `
            -Step "PARCALAR" `
            -TimeoutSec $ListTimeoutSec `
            -Url $parcalarUrl `
            -Reason ("parca listesi bos doc_id={0}" -f $docId) `
            -BodyText $parcalarResponse.BodyText)
    }

    $seciliParca = Select-FirstSuitablePart -Parcalar $parcalar
    if ($null -eq $seciliParca) {
        throw (New-StepFailureMessage `
            -Step "PARCALAR" `
            -TimeoutSec $ListTimeoutSec `
            -Url $parcalarUrl `
            -Reason ("uygun ilk parca secilemedi doc_id={0}" -f $docId) `
            -BodyText $parcalarResponse.BodyText)
    }
    Write-Host "PARCALAR OK status=$($parcalarResponse.StatusCode) parca_sayisi=$($parcalar.Count)"

    $anlamadimResponse = $null
    $fallbackNedeni = ""
    $oneLiner = ""
    if (-not $SkipExplain) {
        $anlamadimUrl = "$resolvedBaseUrl/api/dokuman-asistani/parcalar/$($seciliParca.id)/anlamadim-v2/"
        Write-Host "ANLAMADIM START timeout=${ExplainTimeoutSec}s url=$anlamadimUrl"
        $anlamadimResponse = Invoke-ApiRequest `
            -Client $client `
            -StepName "ANLAMADIM" `
            -TimeoutSec $ExplainTimeoutSec `
            -Method "POST" `
            -Url $anlamadimUrl `
            -Headers $headers `
            -Body @{
                mesaj = $Mesaj
                max_tokens = $MaxTokens
                debug_ai2 = $true
            }

        if (-not $anlamadimResponse.IsSuccessStatusCode) {
            throw (New-StepFailureMessage `
                -Step "ANLAMADIM" `
                -TimeoutSec $ExplainTimeoutSec `
                -Url $anlamadimUrl `
                -Reason ("http={0}" -f $anlamadimResponse.StatusCode) `
                -BodyText (Get-ErrorDetail -Prefix "" -Payload $anlamadimResponse.Json -BodyText $anlamadimResponse.BodyText))
        }

        $debugAi2 = Get-JsonPropertyValue -Payload $anlamadimResponse.Json -Name "debug_ai2"
        $fallbackNedeniValue = Get-JsonPropertyValue -Payload $debugAi2 -Name "fallback_nedeni"
        if ($null -ne $fallbackNedeniValue) {
            $fallbackNedeni = [string]$fallbackNedeniValue
        }

        $oneLinerValue = Get-JsonPropertyValue -Payload $anlamadimResponse.Json -Name "one_liner"
        if ($null -ne $oneLinerValue) {
            $oneLiner = [string]$oneLinerValue
        }

        Write-Host "ANLAMADIM OK status=$($anlamadimResponse.StatusCode) parca_id=$($seciliParca.id)"
    }
    else {
        Write-Host "ANLAMADIM SKIP"
    }

    if ($ProbeEvidence) {
        $evidenceUrl = "$resolvedBaseUrl/api/dokuman-asistani/ai2/kanitli-cevap/"
        Write-Host "EVIDENCE START timeout=${EvidenceTimeoutSec}s url=$evidenceUrl"
        $evidenceResponse = Invoke-ApiRequest `
            -Client $client `
            -StepName "EVIDENCE" `
            -TimeoutSec $EvidenceTimeoutSec `
            -Method "POST" `
            -Url $evidenceUrl `
            -Headers $headers `
            -Body @{
                question = $EvidenceQuestion
                doc_id = $docId
                top_k = 2
            }

        if (-not $evidenceResponse.IsSuccessStatusCode) {
            throw (New-StepFailureMessage `
                -Step "EVIDENCE" `
                -TimeoutSec $EvidenceTimeoutSec `
                -Url $evidenceUrl `
                -Reason ("http={0}" -f $evidenceResponse.StatusCode) `
                -BodyText (Get-ErrorDetail -Prefix "" -Payload $evidenceResponse.Json -BodyText $evidenceResponse.BodyText))
        }

        $supported = Get-JsonStringValue -Payload $evidenceResponse.Json -Name "supported"
        $evidenceStrength = Get-JsonStringValue -Payload $evidenceResponse.Json -Name "evidence_strength"
        $weakEvidence = Get-JsonStringValue -Payload $evidenceResponse.Json -Name "weak_evidence"
        Write-Host "EVIDENCE OK status=$($evidenceResponse.StatusCode) supported=$supported evidence_strength=$evidenceStrength weak_evidence=$weakEvidence"
    }

    if ($ProbeNotes) {
        $notesUrl = "$resolvedBaseUrl/api/dokuman-asistani/notlar/"
        Write-Host "NOTES CREATE START timeout=${NotesTimeoutSec}s url=$notesUrl"
        $noteCreate = Invoke-ApiRequest `
            -Client $client `
            -StepName "NOT CREATE" `
            -TimeoutSec $NotesTimeoutSec `
            -Method "POST" `
            -Url $notesUrl `
            -Headers $headers `
            -Body @{
                dokuman = $docId
                parca = [int]$seciliParca.id
                baslik = "Smoke note"
                metin = "Acceptance smoke note."
            }

        if ($noteCreate.StatusCode -ne 201) {
            throw (New-StepFailureMessage `
                -Step "NOT CREATE" `
                -TimeoutSec $NotesTimeoutSec `
                -Url $notesUrl `
                -Reason ("http={0}" -f $noteCreate.StatusCode) `
                -BodyText (Get-ErrorDetail -Prefix "" -Payload $noteCreate.Json -BodyText $noteCreate.BodyText))
        }

        $noteId = Resolve-DocId -Payload $noteCreate.Json
        $noteUpdateUrl = "$resolvedBaseUrl/api/dokuman-asistani/notlar/$noteId/"
        Write-Host "NOTES UPDATE START timeout=${NotesTimeoutSec}s url=$noteUpdateUrl"
        $noteUpdate = Invoke-ApiRequest `
            -Client $client `
            -StepName "NOT UPDATE" `
            -TimeoutSec $NotesTimeoutSec `
            -Method "PATCH" `
            -Url $noteUpdateUrl `
            -Headers $headers `
            -Body @{
                metin = "Acceptance smoke note updated."
            }

        if (-not $noteUpdate.IsSuccessStatusCode) {
            throw (New-StepFailureMessage `
                -Step "NOT UPDATE" `
                -TimeoutSec $NotesTimeoutSec `
                -Url $noteUpdateUrl `
                -Reason ("http={0}" -f $noteUpdate.StatusCode) `
                -BodyText (Get-ErrorDetail -Prefix "" -Payload $noteUpdate.Json -BodyText $noteUpdate.BodyText))
        }

        Write-Host "NOTES OK create=201 update=$($noteUpdate.StatusCode) note_id=$noteId"
    }

    if ($ProbeForeignAccess) {
        if ([string]::IsNullOrWhiteSpace($SecondaryUsername) -or [string]::IsNullOrWhiteSpace($SecondaryPassword)) {
            throw "INPUT FAILED: ProbeForeignAccess icin SecondaryUsername ve SecondaryPassword zorunlu."
        }

        $secondaryHeaders = New-AuthHeaders `
            -Client $client `
            -ResolvedBaseUrl $resolvedBaseUrl `
            -StepPrefix "SECONDARY" `
            -UserName $SecondaryUsername `
            -UserPassword $SecondaryPassword `
            -TimeoutSec $AuthTimeoutSec

        $foreignCreateUrl = "$resolvedBaseUrl/api/dokuman-asistani/notlar/"
        Write-Host "FOREIGN CREATE START timeout=${NotesTimeoutSec}s url=$foreignCreateUrl"
        $foreignCreate = Invoke-ApiRequest `
            -Client $client `
            -StepName "FOREIGN CREATE" `
            -TimeoutSec $NotesTimeoutSec `
            -Method "POST" `
            -Url $foreignCreateUrl `
            -Headers $secondaryHeaders `
            -Body @{
                baslik = "Foreign smoke note"
                metin = "Baska kullaniciya ait not."
            }

        if ($foreignCreate.StatusCode -ne 201) {
            throw (New-StepFailureMessage `
                -Step "FOREIGN CREATE" `
                -TimeoutSec $NotesTimeoutSec `
                -Url $foreignCreateUrl `
                -Reason ("http={0}" -f $foreignCreate.StatusCode) `
                -BodyText (Get-ErrorDetail -Prefix "" -Payload $foreignCreate.Json -BodyText $foreignCreate.BodyText))
        }

        $foreignNoteId = Resolve-DocId -Payload $foreignCreate.Json
        $foreignFetchUrl = "$resolvedBaseUrl/api/dokuman-asistani/notlar/$foreignNoteId/"
        Write-Host "FOREIGN ACCESS START timeout=${NotesTimeoutSec}s url=$foreignFetchUrl"
        $foreignFetch = Invoke-ApiRequest `
            -Client $client `
            -StepName "FOREIGN ACCESS" `
            -TimeoutSec $NotesTimeoutSec `
            -Method "GET" `
            -Url $foreignFetchUrl `
            -Headers $headers

        $foreignErrorCode = Get-JsonStringValue -Payload $foreignFetch.Json -Name "error_code"
        if (($foreignFetch.StatusCode -ne 404) -or ($foreignErrorCode -ne "resource_not_found")) {
            throw (New-StepFailureMessage `
                -Step "FOREIGN ACCESS" `
                -TimeoutSec $NotesTimeoutSec `
                -Url $foreignFetchUrl `
                -Reason ("expected 404/resource_not_found got http={0} error_code={1}" -f $foreignFetch.StatusCode, $foreignErrorCode) `
                -BodyText $foreignFetch.BodyText)
        }

        Write-Host "FOREIGN ACCESS OK status=404 error_code=$foreignErrorCode"
    }

    if ($ProbeThrottle) {
        $throttleUrl = "$resolvedBaseUrl/api/dokuman-asistani/notlar/"
        $throttleHit = $false
        for ($i = 1; $i -le $ThrottleAttempts; $i++) {
            $throttleResponse = Invoke-ApiRequest `
                -Client $client `
                -StepName "THROTTLE" `
                -TimeoutSec $NotesTimeoutSec `
                -Method "POST" `
                -Url $throttleUrl `
                -Headers $headers `
                -Body @{
                    baslik = "Throttle smoke $i"
                    metin = "Throttle smoke note $i"
                }

            if ($throttleResponse.StatusCode -eq 429) {
                $throttleErrorCode = Get-JsonStringValue -Payload $throttleResponse.Json -Name "error_code"
                if ($throttleErrorCode -ne "rate_limited") {
                    throw (New-StepFailureMessage `
                        -Step "THROTTLE" `
                        -TimeoutSec $NotesTimeoutSec `
                        -Url $throttleUrl `
                        -Reason ("429 geldi ama error_code beklenen degil: {0}" -f $throttleErrorCode) `
                        -BodyText $throttleResponse.BodyText)
                }
                $retryAfter = Get-JsonStringValue -Payload $throttleResponse.Json -Name "retry_after"
                Write-Host "THROTTLE OK status=429 error_code=$throttleErrorCode retry_after=$retryAfter attempt=$i"
                $throttleHit = $true
                break
            }
        }

        if ((-not $throttleHit) -and $RequireThrottleHit) {
            throw "THROTTLE FAILED: belirtilen deneme sayisinda 429 gorulmedi. Duz dusuk throttle oranli ortam kullanin."
        }
        elseif (-not $throttleHit) {
            Write-Host "THROTTLE NO_HIT attempts=$ThrottleAttempts note=ortam throttle limiti yuksek olabilir"
        }
    }

    Write-Host "SMOKE OK"
    Write-Host "doc_id=$docId upload_durum=$uploadDurum parca_sayisi=$($parcalar.Count)"
    Write-Host "parca_id=$($seciliParca.id) adres=$(Get-JsonStringValue -Payload $seciliParca -Name 'adres')"
    if ($SkipExplain) {
        Write-Host "anlamadim=skipped"
    }
    else {
        Write-Host "dokumanda_yok=$(Get-JsonStringValue -Payload $anlamadimResponse.Json -Name 'dokumanda_yok') fallback_nedeni=$fallbackNedeni"
        Write-Host "one_liner=$oneLiner"
    }
    if ($ExpectOcrSignal) {
        Write-Host "ocr_signal=true"
    }
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
finally {
    $client.Dispose()
}

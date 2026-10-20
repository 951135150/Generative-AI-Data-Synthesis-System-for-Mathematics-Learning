param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$NarrationFile = 'data/evaluation/demo_narration.json'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$narration = Get-Content -LiteralPath (Join-Path $projectRoot $NarrationFile) -Raw -Encoding UTF8 | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SelectVoice($narration.voice)
    $speaker.Rate = $narration.rate
    $speaker.Volume = 95
    foreach ($scene in $narration.scenes) {
        $destination = Join-Path $OutputDirectory ($scene.id + '.wav')
        $speaker.SetOutputToWaveFile($destination)
        $speaker.Speak($scene.text)
        $speaker.SetOutputToNull()
    }
} finally { $speaker.Dispose() }
Write-Output ('Narration rendered with ' + $narration.voice + ' (' + $narration.language + ').')

# Synthèse SSML Hortense — une seule passe, hors ligne
#
# Remplace la boucle qui produisait 19 WAV séparés. Une seule synthèse = continuité
# d'intonation entre les phrases, donc une voix nettement moins hachée.
#
# Aucun accès réseau. System.Speech est la bibliothèque SAPI locale de Windows.
#
# Usage :
#   .\tools\synthesize_ssml_hortense.ps1 -SsmlPath narration.ssml -OutPath narration.wav
#
# Sortie :
#   - le WAV complet ;
#   - un JSON de marques {scene_01: 1.23, scene_02: 4.56, ...} donnant le moment exact
#     de chaque scène, pour synchroniser les images sans se fier aux durées estimées.

param(
    [Parameter(Mandatory = $true)][string]$SsmlPath,
    [Parameter(Mandatory = $true)][string]$OutPath,
    [string]$MarksPath = ""
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Speech

if (-not (Test-Path $SsmlPath)) { throw "SSML introuvable : $SsmlPath" }
$ssml = Get-Content -Path $SsmlPath -Raw -Encoding UTF8

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer

# Voix imposée : Hortense, fr-FR, hors ligne. Aucune substitution silencieuse.
$voice = $synth.GetInstalledVoices() |
    Where-Object { $_.VoiceInfo.Name -eq "Microsoft Hortense Desktop" } |
    Select-Object -First 1

if (-not $voice) {
    $dispo = ($synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }) -join ", "
    throw "Microsoft Hortense Desktop introuvable. Voix disponibles : $dispo"
}
if ($voice.VoiceInfo.Culture.Name -notlike "fr*") {
    throw "Hortense trouvée mais culture inattendue : $($voice.VoiceInfo.Culture.Name)"
}

$synth.SelectVoice("Microsoft Hortense Desktop")
Write-Host "Voix : $($synth.Voice.Name) [$($synth.Voice.Culture.Name)]"

# Récupération des marques : chaque <mark> déclenche BookmarkReached avec son temps.
$marks = [ordered]@{}
$handler = {
    param($sender, $eventArgs)
    $marks[$eventArgs.BookmarkName] = [math]::Round($eventArgs.AudioPosition.TotalSeconds, 3)
}
Register-ObjectEvent -InputObject $synth -EventName BookmarkReached -Action $handler | Out-Null

$outFull = [System.IO.Path]::GetFullPath($OutPath)
$dir = [System.IO.Path]::GetDirectoryName($outFull)
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

$synth.SetOutputToWaveFile($outFull)
$synth.SpeakSsml($ssml)
$synth.SetOutputToNull()

$duration = $synth.GetType().GetProperty("AudioPosition")  # informatif
$synth.Dispose()

if (-not (Test-Path $outFull)) { throw "Aucun WAV produit : $outFull" }
$size = (Get-Item $outFull).Length
Write-Host "WAV : $outFull ($size octets)"

if ($MarksPath -eq "") {
    $MarksPath = [System.IO.Path]::ChangeExtension($outFull, ".marks.json")
}
$marks | ConvertTo-Json | Set-Content -Path $MarksPath -Encoding UTF8
Write-Host "Marques : $MarksPath"
$marks.GetEnumerator() | ForEach-Object { Write-Host ("  {0} -> {1} s" -f $_.Key, $_.Value) }

$targets = @(
    "https://www.amazon.de/s?k=rtx+5070+ti",
    "https://www.amazon.de/s?k=gl-mt6000",
    "https://www.caseking.de/search?search=rtx+5070+ti",
    "https://www.mediamarkt.de/de/search.html?query=rtx%205070%20ti",
    "https://www.saturn.de/de/search.html?query=rtx%205070%20ti",
    "https://www.notebooksbilliger.de/search?q=rtx+5070+ti",
    "https://www.cyberport.de/search.html?query=rtx+5070+ti",
    "https://www.galaxus.de/de/search?q=rtx%205070%20ti",
    "https://www.proshop.de/?s=rtx%205070%20ti",
    "https://www.computeruniverse.net/de/search?query=rtx%205070%20ti",
    "https://webshop.asus.com/de/"
)

foreach ($target in $targets) {
    Start-Process $target
    Start-Sleep -Milliseconds 200
}

Write-Host "Opened $($targets.Count) Distill target tabs."

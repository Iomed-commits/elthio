# Run the Supplement Label Auditor (Life Extension example).
# Use the same terminal where you set: $env:OPENAI_API_KEY = "sk-..."
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\main.py" "https://www.lifeextension.com/vitamins-supplements/item02040/vitamins-d-and-k-with-sea-iodine" --pretty

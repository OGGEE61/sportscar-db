import os, glob

for file in glob.glob("/Users/gustaw/Documents/Projects/sportscar-db/scrapers/mercedes_*.py"):
    with open(file, 'r') as f:
        content = f.read()
    
    # Very manual replacements for known ones
    if "cl55" in file:
        content = content.replace('title_must_contain = "55",', 'title_must_contain = "cl55",')
    elif "cls55" in file:
        content = content.replace('title_must_contain = "55",', 'title_must_contain = "cls55",')
    elif "e55" in file:
        content = content.replace('title_must_contain = "55",', 'title_must_contain = "e55",')
    elif "g55" in file:
        content = content.replace('title_must_contain = "55",', 'title_must_contain = "g55",')
    elif "s55" in file:
        content = content.replace('title_must_contain = "s55",', 'title_must_contain = "s55",')
    elif "sl55" in file:
        content = content.replace('title_must_contain = "55",', 'title_must_contain = "sl55",')
        
    with open(file, 'w') as f:
        f.write(content)

with open("scrapers/base_scraper.py", "r") as f:
    lines = f.readlines()

for i in range(703, 847):
    if lines[i].strip():
        lines[i] = "    " + lines[i]
    else:
        lines[i] = "    \n"

with open("scrapers/base_scraper.py", "w") as f:
    f.writelines(lines)

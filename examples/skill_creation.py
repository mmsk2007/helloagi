"""Skill Crystallization Demo — Shows how HelloAGI learns from experience.

After completing a complex multi-step task, the agent can save the workflow
as a reusable skill. Future similar requests invoke the skill automatically.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agi_runtime.skills.manager import SkillManager

sm = SkillManager(skills_dir="memory/demo_skills")

# Create a skill from a successful workflow
print("=== Creating a Skill ===\n")

sm.create_skill(
    name="web-scraper",
    description="Build a Python web scraper for any website",
    triggers=["scrape", "scraper", "crawl", "extract data from website"],
    tools=["python_exec", "file_write", "web_fetch"],
    steps=(
        "## Steps\n"
        "1. Use web_fetch to download the target page\n"
        "2. Parse HTML with BeautifulSoup (install if needed)\n"
        "3. Extract data using CSS selectors\n"
        "4. Save results to JSON/CSV file\n"
        "5. Verify output file exists and has content\n"
    ),
)
print("Created skill: web-scraper")

# List skills
print("\n=== Available Skills ===\n")
skills = sm.list_skills()
for s in skills:
    print(f"  {s.name}: {s.description}")
    print(f"    Triggers: {', '.join(s.triggers)}")
    print(f"    Tools: {', '.join(s.tools)}")
    print()

# Find matching skill
print("=== Finding Skills ===\n")
test_queries = [
    "scrape data from a website",
    "build a web crawler",
    "write a Python script",
]

for query in test_queries:
    match = sm.find_matching_skill(query)
    if match:
        print(f"  '{query}' -> matched skill: {match.name}")
    else:
        print(f"  '{query}' -> no match")

# Cleanup
import shutil
if os.path.exists("memory/demo_skills"):
    shutil.rmtree("memory/demo_skills")

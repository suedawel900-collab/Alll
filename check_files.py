import os
import sys

print("=" * 50)
print("FILE CHECK REPORT")
print("=" * 50)

print(f"\nCurrent Directory: {os.getcwd()}")
print(f"Python Version: {sys.version}")

print("\n📁 Files in root directory:")
files = os.listdir('.')
for file in sorted(files):
    size = os.path.getsize(file) if os.path.isfile(file) else 0
    if os.path.isfile(file):
        print(f"  📄 {file} ({size} bytes)")
    else:
        print(f"  📂 {file}/")

# Check for Procfile
print("\n🔍 Checking Procfile:")
if os.path.exists('Procfile'):
    with open('Procfile', 'r') as f:
        content = f.read().strip()
    print(f"  ✅ Found: '{content}'")
else:
    print("  ❌ NOT FOUND!")

# Check for start.py
print("\n🔍 Checking start.py:")
if os.path.exists('start.py'):
    print("  ✅ Found")
else:
    print("  ❌ NOT FOUND!")

# Check for templates
print("\n🔍 Checking templates directory:")
if os.path.exists('templates'):
    if os.path.exists('templates/bingo.html'):
        print("  ✅ templates/bingo.html found")
    else:
        print("  ❌ templates/bingo.html missing")
else:
    print("  ❌ templates directory missing")

print("\n" + "=" * 50)
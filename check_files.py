import os

print("Current directory:", os.getcwd())
print("\nFiles in current directory:")
for file in os.listdir('.'):
    print(f"  - {file}")

print("\nChecking for Procfile:")
if os.path.exists('Procfile'):
    with open('Procfile', 'r') as f:
        content = f.read().strip()
    print(f"  ✓ Procfile found with content: '{content}'")
else:
    print("  ✗ Procfile NOT found!")

print("\nChecking for start.py:")
if os.path.exists('start.py'):
    print("  ✓ start.py found")
else:
    print("  ✗ start.py NOT found!")
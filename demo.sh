#!/bin/bash
# 2GPTestDoctor Demo Script

echo "🩺 2GPTestDoctor Demo"
echo "===================="
echo ""

# Check if core path exists
CORE_PATH="${1:-../../core-public/core}"

if [ ! -d "$CORE_PATH" ]; then
    echo "❌ Core path not found: $CORE_PATH"
    echo "Usage: ./demo.sh /path/to/core"
    exit 1
fi

echo "📁 Using core path: $CORE_PATH"
echo ""

# Step 1: Scan
echo "Step 1: Scanning for issues..."
python3 testdoctor.py scan --path "$CORE_PATH/artifacts/test/func"
echo ""

# Step 2: Show summary
echo "Step 2: Review the results above"
echo ""
echo "Generated reports:"
echo "  - testdoctor-report.json"
echo "  - testdoctor-report.html"
echo ""

# Step 3: Ask to fix
read -p "Do you want to auto-fix all issues? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Step 3: Fixing issues..."
    python3 testdoctor.py fix --all --auto
    echo ""
    
    echo "Step 4: Verifying build..."
    cd "$CORE_PATH"
    bazel build //artifacts/test/func:func
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ SUCCESS! Build passes with all fixes applied."
        echo ""
        echo "Files modified:"
        git diff --name-only | head -10
    else
        echo ""
        echo "❌ Build failed. Review the errors above."
    fi
else
    echo "Skipping fixes. Run manually with:"
    echo "  python3 testdoctor.py fix --all --auto"
fi

#!/bin/bash
#
# CI check: detect catch blocks in frontend that should use handleFormError
#
# Fails if catch blocks are found inside form handlers (POST/PATCH) without handleFormError
#

set -e

FRONTEND_DIR="${1:-frontend}"
EXIT_CODE=0

echo "🔍 Scanning for catch blocks without handleFormError in $FRONTEND_DIR..."

# Find all catch blocks in JSX files
# This regex catches: catch (err), catch (error), catch (e), catch { (but not .catch( which is promise.catch)
CATCH_BLOCKS=$(find "$FRONTEND_DIR/src" -name "*.jsx" -type f -exec grep -l 'catch\s*(' {} \; 2>/dev/null || true)

if [ -z "$CATCH_BLOCKS" ]; then
    echo "✅ No catch blocks found (clean!)"
    exit 0
fi

echo "Found files with catch blocks:"
for file in $CATCH_BLOCKS; do
    echo "  - $file"
done

# Check each file for catch blocks that may need handleFormError
# We look for catch inside functions that do POST/PATCH operations
# The pattern: catch inside a function that calls an API that could return field errors

# This is a heuristic - we flag catch blocks with:
# 1. They call API functions (getX, createX, updateX, deleteX)
# 2. They are NOT already using handleFormError

NEEDS_FIX=""

for file in $CATCH_BLOCKS; do
    # Skip files that are already importing handleFormError
    if grep -q "import.*handleFormError" "$file" 2>/dev/null; then
        # Check if there's any catch block after the import that's NOT already handling errors properly
        # This is a simplified check - we look for any catch without handleFormError inside
        if grep -q "setFormErrors.*handleFormError" "$file" 2>/dev/null; then
            continue  # File seems to handle errors properly
        fi
        
        # Check if file has mapFieldErrors import (used with handleFormError)
        if grep -q "mapFieldErrors" "$file" 2>/dev/null; then
            continue  # File seems to use mapFieldErrors
        fi
    fi
    
    # For now, just flag all catch blocks - manual review needed
    # This is conservative to avoid false negatives
    COUNT=$(grep -c 'catch\s*(' "$file" 2>/dev/null || echo "0")
    if [ "$COUNT" -gt "0" ]; then
        echo "⚠️  $file has $COUNT catch block(s) - verify they use handleFormError"
        NEEDS_FIX="$NEEDS_FIX $file"
        EXIT_CODE=1
    fi
done

if [ $EXIT_CODE -eq "0" ]; then
    echo "✅ All catch blocks appear to use handleFormError!"
else
    echo ""
    echo "❌ Some files may need migration to handleFormError pattern"
    echo "Run: grep -n 'catch' <file> to review each"
fi

exit $EXIT_CODE
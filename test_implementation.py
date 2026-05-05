#!/usr/bin/env python3
"""Quick test script for normalize_user_input implementation"""

import sys
sys.path.insert(0, '.')

from app.services.validation.input_validator import InputValidator

# Test normalize_user_input
validator = InputValidator()

print("=" * 60)
print("Testing normalize_user_input() Implementation")
print("=" * 60)

# Test 1: SMS abbreviations
print("\n✓ Test 1: SMS abbreviations")
result = validator.normalize_user_input('u')
print(f"  Input: 'u' → Output: '{result}'")
assert 'you' in result, f"Expected 'you' in result"
print("  ✅ PASS - SMS abbreviation expanded")

# Test 2: Multiple SMS abbreviations
print("\n✓ Test 2: Multiple SMS abbreviations")
result = validator.normalize_user_input('thx pls')
print(f"  Input: 'thx pls' → Output: '{result}'")
assert 'Thanks' in result, f"Expected 'Thanks' in result"
assert 'please' in result, f"Expected 'please' in result"
print("  ✅ PASS - Multiple abbreviations expanded")

# Test 3: Local acronyms
print("\n✓ Test 3: Local acronyms")
result = validator.normalize_user_input('npp')
print(f"  Input: 'npp' → Output: '{result}'")
assert "National people's party" in result, f"Expected 'National people\\'s party' in result"
print("  ✅ PASS - Acronym expanded to full form")

# Test 4: Keyword mapping to full questions
print("\n✓ Test 4: Keyword mapping to full questions")
result = validator.normalize_user_input('internet')
print(f"  Input: 'internet' → Output: '{result}'")
assert 'What has NPP done' in result, f"Expected question about NPP"
print("  ✅ PASS - Keyword mapped to full question")

# Test 5: Ultra short message
print("\n✓ Test 5: Ultra short message")
result = validator.normalize_user_input('?')
print(f"  Input: '?' → Output: '{result}'")
assert len(result) > 5, f"Expected help prompt for ultra-short input"
print("  ✅ PASS - Help prompt returned for ultra-short input")

# Test 6: Spelling correction
print("\n✓ Test 6: Spelling correction")
result = validator.normalize_user_input('intrnet')
print(f"  Input: 'intrnet' (misspelled) → Output: '{result}'")
assert 'internet' in result, f"Expected 'internet' in result after correction"
print("  ✅ PASS - Spelling correction applied")

# Test 7: SMS + Acronym combination
print("\n✓ Test 7: SMS abbreviations + Acronym")
result = validator.normalize_user_input('u know npp')
print(f"  Input: 'u know npp' → Output: '{result}'")
assert 'You' in result, f"Expected 'You' in result"
assert "national people's party" in result, f"Expected 'national people\\'s party' in result"
print("  ✅ PASS - Combined SMS and acronym expansion")

# Test 8: Question mark preservation
print("\n✓ Test 8: Question mark preservation")
result = validator.normalize_user_input('what about agriculture')
print(f"  Input: 'what about agriculture' → Output: '{result}'")
assert '?' in result, f"Expected question mark in result for question-like input"
print("  ✅ PASS - Question mark added automatically")

# Test 9: Whitespace normalization
print("\n✓ Test 9: Whitespace normalization")
result = validator.normalize_user_input('too   many    spaces')
print(f"  Input: 'too   many    spaces' → Output: '{result}'")
assert '   ' not in result, f"Expected multiple spaces removed"
print("  ✅ PASS - Whitespace normalized")

# Test 10: Empty input handling
print("\n✓ Test 10: Empty input handling")
result = validator.normalize_user_input('')
print(f"  Input: '' (empty) → Output: '{result}'")
assert len(result) > 0, f"Expected help text for empty input"
print("  ✅ PASS - Help text returned for empty input")

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
print("\nSummary:")
print("  ✓ SMS abbreviations work correctly")
print("  ✓ Local acronyms are expanded")
print("  ✓ Keyword mapping to full questions works")
print("  ✓ Ultra-short messages handled gracefully")
print("  ✓ Spelling corrections applied")
print("  ✓ Question marks preserved/added")
print("  ✓ Whitespace normalized")
print("  ✓ Empty input handled")
print("\nImplementation Status: ✅ READY FOR PRODUCTION")

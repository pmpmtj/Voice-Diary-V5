#!/usr/bin/env python3
"""
Script to run all unit tests for the voice_diary.download_audio_files module sequentially.
This script allows for more control over the test execution order than pytest's default.
"""
import os
import sys
import subprocess
from pathlib import Path

def get_test_files():
    """Get all test files from the unit directory."""
    current_dir = Path(__file__).parent
    unit_dir = current_dir / "unit"
    
    # Get all Python files that start with "test_"
    test_files = [f for f in unit_dir.glob("test_*.py")]
    return sorted(test_files)  # Sort to ensure consistent order

def run_tests(test_files):
    """Run each test file sequentially using pytest."""
    success_count = 0
    failure_count = 0
    
    print("\n" + "="*80)
    print(f"Running {len(test_files)} test files sequentially")
    print("="*80 + "\n")
    
    # Process each test file individually
    for i, test_file in enumerate(test_files, 1):
        test_name = test_file.stem
        test_path = str(test_file)
        
        print(f"\n[{i}/{len(test_files)}] Running {test_name}...")
        
        # Run pytest on the specific file
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_path, "-v"],
            capture_output=False
        )
        
        # Check result
        if result.returncode == 0:
            print(f"✅ {test_name} PASSED")
            success_count += 1
        else:
            print(f"❌ {test_name} FAILED")
            failure_count += 1
    
    # Print summary
    print("\n" + "="*80)
    print(f"Test Summary: {success_count} passed, {failure_count} failed")
    print("="*80)
    
    return success_count, failure_count

def run_coverage(test_files):
    """Run coverage on all tests."""
    print("\n" + "="*80)
    print("Running coverage report")
    print("="*80 + "\n")
    
    # Convert all test files to strings
    test_paths = [str(f) for f in test_files]
    
    # Run coverage
    subprocess.run([
        sys.executable, "-m", "pytest", 
        "--cov=voice_diary.download_audio_files",
        "--cov-report=term",
        "--cov-report=html:coverage_html",
        *test_paths
    ])
    
    print("\nHTML coverage report generated in coverage_html directory")

def main():
    """Main entry point."""
    # Ensure pytest is installed
    try:
        import pytest
        try:
            import pytest_cov
        except ImportError:
            print("Warning: pytest-cov not installed. Coverage report will be skipped.")
            print("Install with: pip install pytest-cov")
            has_coverage = False
        else:
            has_coverage = True
    except ImportError:
        print("Error: pytest not installed. Please install with: pip install pytest")
        return 1
    
    # Get test files
    test_files = get_test_files()
    if not test_files:
        print("No test files found in unit directory!")
        return 1
    
    # Run tests
    success_count, failure_count = run_tests(test_files)
    
    # Run coverage if available
    if has_coverage and success_count > 0:
        run_coverage(test_files)
    
    # Return appropriate exit code
    return 0 if failure_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main()) 
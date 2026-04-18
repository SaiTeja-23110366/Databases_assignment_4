"""
run_all_tests.py
Runs all tests and saves complete output to a report file
"""
import subprocess
import sys
import time

def run_test(script_name):
    """Run a test script and return its output"""
    print(f"\n{'='*70}")
    print(f"Running {script_name}...")
    print(f"{'='*70}\n")
    
    try:
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=True,
            text=True,
            timeout=180
        )
        output = result.stdout + result.stderr
        print(output)
        return output
    except subprocess.TimeoutExpired:
        print(f"[!] {script_name} timed out after 180 seconds")
        return f"[!] {script_name} timed out"
    except Exception as e:
        print(f"[!] Error running {script_name}: {str(e)}")
        return f"[!] Error: {str(e)}"

if __name__ == "__main__":
    print("\n" + "="*70)
    print("MESS MANAGEMENT SYSTEM - COMPREHENSIVE TEST REPORT")
    print("="*70)
    print("\nRunning all ACID and concurrency tests...\n")
    
    # Wait for Flask app to be ready
    time.sleep(2)
    
    all_output = []
    
    # Run all tests
    tests = [
        "test_failure_simulation.py",
        "test_concurrent.py",
        "test_stress.py"
    ]
    
    for test in tests:
        output = run_test(test)
        all_output.append(f"\n{'#'*70}\n# {test}\n{'#'*70}\n{output}\n")
        time.sleep(1)
    
    # Save complete output
    with open("test_report_output.txt", "w") as f:
        for item in all_output:
            f.write(item)
    
    print("\n" + "="*70)
    print("All tests completed!")
    print("Output saved to test_report_output.txt")
    print("="*70)

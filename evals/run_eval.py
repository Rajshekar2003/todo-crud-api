import json
import time
import requests

ENDPOINT = "http://localhost:8000/enrich"
CASES_PATH = "evals/cases.json"


def main():
    with open(CASES_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    correct = 0
    failures = []

    for case in cases:
        try:
            response = requests.post(ENDPOINT, json=case["input"], timeout=35)
        except requests.exceptions.RequestException as e:
            failures.append({"id": case["id"], "note": case["note"], "error": str(e)})
            continue

        if response.status_code != 200:
            failures.append({
                "id": case["id"],
                "note": case["note"],
                "error": f"status {response.status_code}: {response.text}",
            })
            continue

        actual_category = response.json().get("category")
        expected_category = case["expected_category"]

        if actual_category == expected_category:
            correct += 1
            print(f"[PASS] case {case['id']} ({case['note']}): got '{actual_category}'")
        else:
            failures.append({
                "id": case["id"],
                "note": case["note"],
                "expected": expected_category,
                "actual": actual_category,
            })
            print(f"[FAIL] case {case['id']} ({case['note']}): expected '{expected_category}', got '{actual_category}'")

        time.sleep(1)  # be gentle on the free-tier rate limit between eval calls

    total = len(cases)
    print(f"\nScore: {correct}/{total}")

    if failures:
        print("\nFailed cases:")
        for f in failures:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
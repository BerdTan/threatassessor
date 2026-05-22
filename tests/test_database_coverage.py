"""
Test database control coverage in generated diagrams.

Checks that recommended controls are properly placed on all database nodes.
"""

import json
from pathlib import Path

def test_safeentry_database_coverage():
    """Test that 00_safeentry databases get appropriate controls."""

    # Load ground truth
    gt_path = Path("report/00_safeentry/ground_truth.json")
    assert gt_path.exists(), f"Ground truth not found: {gt_path}"

    with open(gt_path) as f:
        gt = json.load(f)

    # Load after diagram
    after_path = Path("report/00_safeentry/after.mmd")
    assert after_path.exists(), f"After diagram not found: {after_path}"

    with open(after_path) as f:
        after_content = f.read()

    # Database nodes in architecture
    databases = ["UserDB", "AccessLogDB", "Cache"]

    # Controls that should protect databases
    expected_db_controls = {
        "backup": ["UserDB", "AccessLogDB"],  # Not cache (volatile)
        "dlp": databases,  # All databases
        "encryption at rest": databases,  # All databases (if recommended)
        "logging": databases  # All databases should log access
    }

    # Check control recommendations
    ctrl_names = [c['control'] for c in gt['control_recommendations']]
    print(f"\n=== Controls Recommended ({len(ctrl_names)}) ===")
    for ctrl in ctrl_names:
        print(f"  - {ctrl}")

    # Check which controls were placed
    print(f"\n=== Database Control Coverage ===")
    issues = []

    for db_node in databases:
        print(f"\n{db_node}:")

        # Find all control connections to this database
        connections = [line for line in after_content.split('\n')
                      if db_node in line and 'NEW_' in line and ('-->' in line or '-.->') in line]

        if connections:
            for conn in connections:
                # Extract control name
                if 'NEW_' in conn:
                    ctrl_start = conn.find('NEW_')
                    ctrl_end = conn.find(' ', ctrl_start) if ' ' in conn[ctrl_start:] else conn.find('[', ctrl_start)
                    if ctrl_end == -1:
                        ctrl_end = len(conn)
                    ctrl_node = conn[ctrl_start:ctrl_end].strip()
                    print(f"  ✓ {ctrl_node}")
        else:
            print(f"  ❌ NO CONTROLS")
            issues.append(f"{db_node} has no controls")

    # Check specific controls
    print(f"\n=== Expected Control Placement ===")
    for control, expected_dbs in expected_db_controls.items():
        if control not in ctrl_names:
            print(f"\n{control}: Not recommended (skipped)")
            continue

        print(f"\n{control}:")
        control_upper = control.replace(' ', '').upper()

        for db in expected_dbs:
            # Check if control is connected to this DB
            pattern1 = f"{db}.*NEW_{control_upper}"
            pattern2 = f"NEW_{control_upper}.*{db}"

            if pattern1 in after_content.replace('\n', ' ') or pattern2 in after_content.replace('\n', ' '):
                print(f"  ✓ {db}")
            else:
                print(f"  ❌ {db} - MISSING")
                issues.append(f"{control} not connected to {db}")

    # Summary
    print(f"\n=== Summary ===")
    if issues:
        print(f"❌ {len(issues)} issues found:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print(f"✅ All databases properly protected")
        return True

if __name__ == "__main__":
    success = test_safeentry_database_coverage()
    exit(0 if success else 1)

import os, sys, time, yaml, re
from core.executor import run_goal
from core.reporter import write_report

def subst(text, mapping):
    return re.sub(r"\$\{([^}]+)\}", lambda m: str(mapping.get(m.group(1), m.group(0))), text)

def load_goal(path):
    with open(path, "r", encoding="utf-8") as f:
        y = yaml.safe_load(f)
    name = y.get("name", "Unnamed Goal")
    url = y.get("url")
    steps = y["steps"]
    assertions = y.get("assertions", [])
    vars_map = y.get("vars", {})
    for s in steps:
        s["description"] = subst(s["description"], vars_map)
    assertions = [subst(a, vars_map) for a in assertions]
    return name, url, steps, assertions

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py goals/<file>.yaml [--headed]")
        sys.exit(1)
    goal_file = sys.argv[1]
    headed = "--headed" in sys.argv
    name, url, steps, assertions = load_goal(goal_file)
    start_ts = time.time()
    out_dir, srec, arec = run_goal(name, url, steps, assertions, headless=not headed)
    report_path = write_report(out_dir, name, url or "", start_ts, srec, arec)
    print(f"\n✅ Done. Report: {report_path}\nArtifacts dir: {out_dir}")

if __name__ == "__main__":
    main()

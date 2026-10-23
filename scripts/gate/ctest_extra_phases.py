"""Count the CTest result files `colcon test-result` skips, and print the combined summary.

colcon reads only the Testing/<TAG>/Test.xml named by Testing/TAG (the newest). A package tested in two ctest phases (so101_teleop:
serial, then parallel) has one Test.xml per phase, so the colcon summary lacks the older phases. This adds them, with the same
classification as colcon_cmake.test_result.ctest (failed -> failure, notrun -> skipped, other non-passed -> error).
usage: ctest_extra_phases.py <build-base> <colcon-test-result.log>
Read only. Prints one line per extra Test.xml and a final 'Summary (all ctest phases)' line; exit 0 always (pass/fail is colcon's)."""
import re
import sys
from pathlib import Path
from xml.etree.ElementTree import parse

build, log = Path(sys.argv[1]), Path(sys.argv[2])
base = [0, 0, 0, 0]
for line in log.read_text(errors="replace").splitlines():
    m = re.match(r"Summary: (\d+) tests, (\d+) errors, (\d+) failures, (\d+) skipped", line)
    if m:
        base = [int(x) for x in m.groups()]
extra = [0, 0, 0, 0]
for tag in sorted(build.glob("*/Testing/TAG")):
    latest = tag.read_text().splitlines()[0]
    newest = (tag.parent / latest / "Test.xml").read_bytes() if (tag.parent / latest / "Test.xml").is_file() else None
    for xml in sorted(tag.parent.glob("*/Test.xml")):
        if xml.parent.name == latest or xml.read_bytes() == newest:   # the newest phase, or its preserved copy (result_sets.py preserve)
            continue
        root = parse(str(xml)).getroot()
        counts = [0, 0, 0, 0]
        for test in root.iterfind("Testing/Test"):
            counts[0] += 1
            status = test.attrib.get("Status")
            if status == "failed":
                counts[2] += 1
            elif status == "notrun":
                counts[3] += 1
            elif status != "passed":
                counts[1] += 1
        print(f"{xml}: {counts[0]} tests, {counts[1]} errors, {counts[2]} failures, {counts[3]} skipped (older ctest phase, not read by colcon)")
        extra = [a + b for a, b in zip(extra, counts)]
total = [a + b for a, b in zip(base, extra)]
print(f"Summary (all ctest phases): {total[0]} tests, {total[1]} errors, {total[2]} failures, {total[3]} skipped"
      f" [colcon {base[0]} + older ctest phases {extra[0]}]")

"""Check every frozen inference invocation and compare actual transcript JSON."""

import json
import subprocess
import sys
from pathlib import Path

exe = str(Path(sys.argv[1]).resolve())
subprocess.run([exe, "models", "download"], check=True)
for speaker, name in ((3, "female"), (58, "male")):
    output = Path(f".evidence/frozen-real-{name}.json")
    subprocess.run(
        [exe, "wav", f"fixtures/positive-{speaker}.wav", "--output", str(output)], check=True
    )
    evidence = json.loads(output.read_text("utf-8"))
    text = [event["text"] for event in evidence["events"] if event["type"] == "transcript"]
    assert len(text) == 1 and "打开记事本" in text[0], evidence
    assert evidence["final_state"] == "IDLE", evidence
    assert evidence["hardware_acceptance"] == "NOT_VERIFIED"
print("PASS: frozen real models, default wake, female/male synthetic command and IDLE recovery")

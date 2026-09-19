"""Collection cannot use unmeasured, corrupted or wrongly dimensioned calibration."""

import hashlib
import pytest

from so101_demo.act.calibration import REQUIRED_MEASUREMENTS, require_qualified


def report(tmp_path):
    sample=tmp_path/"measurement.json"; sample.write_text("measured evidence\n")
    values={}
    for key,(unit,size) in REQUIRED_MEASUREMENTS.items():
        value=[1.]*size if size>1 else 1.
        if key=="max_fine_corrections": value=3
        values[key]=dict(value=value,unit=unit,sample_path=str(sample),
                         sample_sha256=hashlib.sha256(sample.read_bytes()).hexdigest())
    return dict(schema_version=1,status="QUALIFIED",source_commit="a"*40,config_sha256="b"*64,
                measurements=values, checks={key:"PASS" for key in
                ("fov","collision","search","synchronization","execution","release","retreat")})


def test_unqualified_and_missing_evidence_cannot_start_collection(tmp_path):
    with pytest.raises(ValueError): require_qualified({"status":"CALIBRATION_REQUIRED","checks":{}})
    measured=report(tmp_path); require_qualified(measured)
    measured["measurements"].pop("stop_latency_s")
    with pytest.raises(ValueError): require_qualified(measured)


@pytest.mark.parametrize("mutation", ("hash","unit","nan","extra","check","bool"))
def test_measurement_corruption_fails_closed(tmp_path,mutation):
    measured=report(tmp_path); item=measured["measurements"]["stop_latency_s"]
    if mutation=="hash": item["sample_sha256"]="c"*64
    if mutation=="unit": item["unit"]="milliseconds"
    if mutation=="nan": item["value"]=float("nan")
    if mutation=="bool": item["value"]=True
    if mutation=="extra": measured["truth"]=True
    if mutation=="check": measured["checks"]["release"]="UNMEASURED"
    with pytest.raises(ValueError): require_qualified(measured)

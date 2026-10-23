"""Single-run CPU-only offline audit. Tool rc reports integrity/publication."""
import sys
sys.dont_write_bytecode = True

import argparse
import json

from ..act.head_run_reader import AuditToolError, RunReader
from ..act.head_run_audit import audit_run
from ..act.head_run_audit_report import publish_report, summary


def main(argv=None):
    parser=argparse.ArgumentParser(description='Basic offline Head Search audit; no qualification decision')
    parser.add_argument('--run-root',required=True)
    parser.add_argument('--execution-receipt',required=True)
    parser.add_argument('--execution-receipt-sha256',required=True)
    parser.add_argument('--output-root',required=True)
    try:
        try:args=parser.parse_args(argv)
        except SystemExit as error:return 0 if error.code==0 else 3
        reader=RunReader(args.run_root,args.execution_receipt,args.execution_receipt_sha256).load()
        result=audit_run(reader)
        publish_report(reader,result,args.output_root)
        code={'PASS':0,'FAIL':1,'INCOMPLETE':2}[result['integrity']['status']]
        print(summary(result)+f" report=COMPLETE tool_rc={code}")
        return code
    except (KeyboardInterrupt,Exception) as error:
        # One bounded diagnostic; never recursively try to publish a success report.
        print(json.dumps(dict(tool_status='AUDIT_NOT_COMPLETED',error=type(error).__name__,
                              detail=str(error)[:512])),file=sys.stderr)
        return 3


if __name__=='__main__':
    raise SystemExit(main())

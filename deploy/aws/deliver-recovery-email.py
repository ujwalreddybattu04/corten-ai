"""Host mail worker. Uses the EC2 role; application containers get no AWS keys."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

def app(*args):
    command=["docker","compose","-f","deploy/aws/compose.yaml","exec","-T","backend","python","-m","src.services.recovery_delivery",*args]
    result=subprocess.run(command,check=True,capture_output=True,text=True,timeout=20)
    return result.stdout

def main():
    os.umask(0o077)
    os.chdir("/opt/corten/current")
    with open("/opt/corten/private/recovery-email.lock","w") as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return
        maintenance = Path("/opt/corten/private/recovery-email-pruned")
        if not maintenance.exists() or time.time() - maintenance.stat().st_mtime > 86400:
            app("prune")
            maintenance.touch(mode=0o600)
        row=json.loads(app("claim"))
        if not row: return
        # Inputs remain JSON data in a protected file, never shell syntax or logs.
        if not re.fullmatch(r"[a-f0-9-]{36}",row["id"]) or not re.fullmatch(r"[a-f0-9]{32}",row["lease"]): raise ValueError("Invalid mail lease")
        with tempfile.TemporaryDirectory(dir="/opt/corten/private",prefix="recovery-email-") as directory:
            request=Path(directory)/"request.json"
            request.write_text(json.dumps(row["message"],ensure_ascii=False),encoding="utf-8")
            try:
                sent=subprocess.run(["aws","sesv2","send-email","--region","ap-southeast-2","--cli-input-json","file://"+str(request)],capture_output=True,text=True,timeout=25)
                if sent.returncode==0:
                    receipt=json.loads(sent.stdout).get("MessageId","")
                    app("finish",row["id"],row["lease"],"sent",receipt)
                    print("Recovery email accepted by provider")
                else:
                    permanent=any(code in sent.stderr for code in ("MessageRejected","AccessDenied","BadRequestException","AccountSuspended","MailFromDomainNotVerified"))
                    app("finish",row["id"],row["lease"],"permanent" if permanent else "retry")
                    print("Recovery email provider rejected delivery" if permanent else "Recovery email scheduled for retry")
            except subprocess.TimeoutExpired:
                app("finish",row["id"],row["lease"],"retry")
                print("Recovery email provider timed out")

if __name__ == "__main__": main()

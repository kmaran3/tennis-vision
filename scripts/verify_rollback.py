"""Verify atomic local rollback, then restore the exact original release."""
from baseline.config import DATA,ARTIFACTS,write_json
from baseline.release import check_release,rollback,activate

def main():
    current=(DATA/"releases/current").resolve();previous=(DATA/"releases/previous").resolve()
    assert current!=previous;check_release(current);check_release(previous)
    try:
        rollback();assert (DATA/"releases/current").resolve()==previous;check_release(previous)
    finally:activate(current)
    assert (DATA/"releases/current").resolve()==current
    write_json(ARTIFACTS/"rollback-verification.json",dict(status="passed",restored=current.name,previous=previous.name))
    print("Rollback and restoration verified")

if __name__=="__main__":main()

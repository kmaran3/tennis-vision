"""Create a clean Docker context that downloads its pinned serving release."""
from pathlib import Path
import shutil
import tempfile
from baseline.config import ROOT,ARTIFACTS,serving_path,reserve,write_json
from baseline.release import check_release

def main():
    reserve(1);release=serving_path().parent.resolve();manifest=check_release(release)
    ARTIFACTS.mkdir(exist_ok=True)
    target=ARTIFACTS/"deploy"
    with tempfile.TemporaryDirectory(dir=ARTIFACTS) as temp:
        stage=Path(temp)/"context";stage.mkdir()
        for name in ("Dockerfile",".dockerignore","pyproject.toml","uv.lock","package.json","package-lock.json"):shutil.copy2(ROOT/name,stage/name)
        (stage/'.railway').mkdir();shutil.copy2(ROOT/'.railway/railway.ts',stage/'.railway/railway.ts')
        shutil.copytree(ROOT/"baseline",stage/"baseline",ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
        shutil.copytree(ROOT/"frontend",stage/"frontend",ignore=shutil.ignore_patterns("node_modules","dist","test-results","playwright-report","e2e"))
        shutil.copytree(ROOT/'deployment',stage/'deployment')
        (stage/'scripts').mkdir();shutil.copy2(ROOT/'scripts/fetch_serving.py',stage/'scripts/fetch_serving.py')
        write_json(stage/".baseline-deploy.json",{"snapshot":manifest["snapshot"],"metric_version":manifest["metric_version"]})
        if target.exists():
            if not (target/".baseline-deploy.json").exists():raise ValueError("Refusing to replace an unrecognized deployment directory")
            shutil.rmtree(target)
        stage.rename(target)
    print("Prepared Docker context:",target)

if __name__=="__main__":main()

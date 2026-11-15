"""Read-only cost/credential checks. Never print or persist authentication tokens."""
import json
import os
from pathlib import Path
import subprocess
import sys
import httpx
from baseline.config import ARTIFACTS,write_json,utcnow


def google():
    report={'checked_at':utcnow(),'billing_verified_disabled':False,'generation_calls_made':0}
    key=os.environ.get('GEMINI_API_KEY')
    if not key:report['status']='key_unavailable';return report
    env={**os.environ,'CLOUDSDK_PYTHON':sys.executable}
    command=subprocess.run(['gcloud','auth','print-access-token','--quiet'],env=env,capture_output=True,text=True,timeout=30)
    if command.returncode:report['status']='cloud_auth_unavailable';return report
    token=command.stdout.strip()
    with httpx.Client(timeout=20,headers={'Authorization':'Bearer '+token}) as client:
        lookup=client.get('https://apikeys.googleapis.com/v2/keys:lookupKey',params={'keyString':key})
        if lookup.is_error:
            report.update(status='key_project_lookup_denied',lookup_http_status=lookup.status_code);return report
        parent=lookup.json().get('parent','')
        project='/'.join(parent.split('/')[:2])
        if not project.startswith('projects/'):report['status']='key_project_unresolved';return report
        quota_project=os.environ.get('BASELINE_GOOGLE_QUOTA_PROJECT',project.split('/')[-1])
        response=client.get('https://cloudbilling.googleapis.com/v1/'+project+'/billingInfo',headers={'x-goog-user-project':quota_project})
        if response.is_error:
            reasons=[d.get('reason') for d in response.json().get('error',{}).get('details',[]) if d.get('reason')]
            report.update(status='billing_access_denied',project=project,billing_http_status=response.status_code,reasons=reasons)
            return report
        billing=response.json()
        report.update(project=project,billing_enabled=billing.get('billingEnabled'),billing_verified_disabled=billing.get('billingEnabled') is False,status='verified_free_project' if billing.get('billingEnabled') is False else 'billing_enabled_or_unknown')
    return report


def railway():
    report={'checked_at':utcnow(),'mutations_made':0}
    path=Path.home()/'.railway/config.json'
    if not path.exists():report['status']='cli_configuration_unavailable';return report
    config=json.loads(path.read_text())
    user=config.get('user',{})
    token=(user.get('accessToken') or user.get('token')) if isinstance(user,dict) else None
    if not token:token=config.get('token') or os.environ.get('RAILWAY_API_TOKEN')
    if not token:report.update(status='cli_token_not_accessible',config_keys=sorted(config));return report
    workspace=os.environ.get('BASELINE_RAILWAY_WORKSPACE_ID')
    if not workspace:report['status']='workspace_selection_required';return report
    query='''query($workspace: String!) { workspace(workspaceId:$workspace) {
      plan customer { currentUsage remainingUsageCreditBalance
        billingPeriod { start end } usageLimit { hardLimit softLimit isOverLimit }
      }
    } }'''
    with httpx.Client(timeout=20) as client:
        response=client.post('https://backboard.railway.com/graphql/v2',headers={'Authorization':'Bearer '+token},json={'query':query,'variables':{'workspace':workspace}})
    if response.is_error:report.update(status='api_access_unavailable',http_status=response.status_code);return report
    result=response.json()
    if result.get('errors'):report.update(status='schema_access_denied',error_codes=[e.get('extensions',{}).get('code') for e in result['errors']]);return report
    account=result['data']['workspace']
    report.update(status='budget_inspected_deployment_deferred',workspace_id=workspace,account=account,
      resource_pricing_source='https://docs.railway.com/pricing',
      deployment_reason='The local process peak is not a container billing forecast. A conservative 0.5 GB RAM budget alone uses the $5 monthly Hobby allowance at $10/GB/month, before existing services, CPU, storage or egress. No zero-additional-charge deployment is established.')
    return report

if __name__=='__main__':
    for name,fn in (('gemini',google),('railway',railway)):
        try:value=fn()
        except Exception as error:value={'status':'inspection_unavailable','error_type':type(error).__name__}
        write_json(ARTIFACTS/(name+'-account-inspection.json'),value)
        print(name,json.dumps(value))

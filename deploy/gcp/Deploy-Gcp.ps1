# Requires reviewed infrastructure and approved billing; default is a read-only check.
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidatePattern('^[a-z][a-z0-9-]{4,28}[a-z0-9]$')][string]$ProjectId,
  [ValidatePattern('^[a-z]+-[a-z]+[0-9]$')][string]$Region = 'asia-southeast1',
  [ValidatePattern('^[a-z0-9][a-z0-9._-]{0,80}$')][string]$ImageTag = 'review',
  [ValidatePattern('^[a-z][a-z0-9-]*$')][string]$Network = 'corten-vpc',
  [ValidatePattern('^[a-z][a-z0-9-]*$')][string]$Subnet = 'corten-run',
  [ValidatePattern('^[a-z][a-z0-9-]*$')][string]$SqlInstance = 'corten-db',
  [string]$GcloudPath = 'gcloud',
  [switch]$Deploy
)
$ErrorActionPreference = 'Stop'
$repositoryPath = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
function Invoke-Cloud([string[]]$Arguments) {
  & $GcloudPath @Arguments
  if ($LASTEXITCODE -ne 0) { throw 'Google Cloud command failed. Deployment stopped before the next step.' }
}
$common = @('--project', $ProjectId, '--quiet')
Invoke-Cloud (@('projects','describe',$ProjectId,'--format=value(projectId)') + $common)
$billingJson = & $GcloudPath billing projects describe $ProjectId --format=json --project=$ProjectId
if ($LASTEXITCODE -ne 0) { throw 'Could not check project billing.' }
$billing = $billingJson | ConvertFrom-Json
if (-not $billing.billingEnabled) { throw 'Enable billing on this project before deployment.' }
Invoke-Cloud (@('artifacts','repositories','describe','corten','--location',$Region,'--format=value(name)') + $common)
Invoke-Cloud (@('sql','instances','describe',$SqlInstance,'--format=value(connectionName)') + $common)
Invoke-Cloud (@('compute','networks','subnets','describe',$Subnet,'--region',$Region,'--format=value(name)') + $common)
$backendIdentity = "corten-api@$ProjectId.iam.gserviceaccount.com"
$frontendIdentity = "corten-web@$ProjectId.iam.gserviceaccount.com"
foreach ($account in @($backendIdentity, $frontendIdentity)) {
  Invoke-Cloud (@('iam','service-accounts','describe',$account,'--format=value(email)') + $common)
}
# Versions are checked without reading their secret payloads.
$requiredSecrets = @{ DATABASE_URL='corten-database-url'; REDIS_URL='corten-redis-url'; JWT_SECRET_KEY='corten-jwt-secret'; GROQ_API_KEY='corten-groq-key'; TAVILY_API_KEY='corten-tavily-key' }
$optionalSecrets = @{ GROQ_FALLBACK_API_KEYS='corten-groq-fallback-keys'; SERPER_API_KEY='corten-serper-key'; NEWSAPI_KEY='corten-newsapi-key'; GUARDIAN_API_KEY='corten-guardian-key'; OPENFDA_API_KEY='corten-openfda-key' }
$bindings = New-Object System.Collections.Generic.List[string]
foreach ($environmentName in @($requiredSecrets.Keys) + @($optionalSecrets.Keys)) {
  $secretName = if ($requiredSecrets.ContainsKey($environmentName)) { $requiredSecrets[$environmentName] } else { $optionalSecrets[$environmentName] }
  $versionJson = & $GcloudPath secrets versions describe latest --secret=$secretName --format=json --project=$ProjectId 2>$null
  if ($LASTEXITCODE -ne 0) {
    if ($requiredSecrets.ContainsKey($environmentName)) { throw "Required secret is missing or inaccessible: $secretName" }
    Write-Host "Optional source secret absent: $secretName"; continue
  }
  $version = $versionJson | ConvertFrom-Json
  if ($version.state -ne 'ENABLED' -or $version.name -notmatch '/versions/([0-9]+)$') { throw "Secret version is not enabled: $secretName" }
  $bindings.Add("${environmentName}=${secretName}:$($Matches[1])")
}
if (-not $Deploy) { Write-Host 'Preflight completed. No deployment or paid resource creation was performed.'; return }
if ($ImageTag -notmatch '^[a-f0-9]{7,40}$') { throw 'Deployment ImageTag must be the reviewed Git commit SHA.' }
$registry = "$Region-docker.pkg.dev/$ProjectId/corten"
$backendImage = "${registry}/backend:$ImageTag"
$frontendImage = "${registry}/frontend:$ImageTag"
$sqlConnection = "${ProjectId}:${Region}:${SqlInstance}"
$secretBindings = $bindings -join ','
Push-Location $repositoryPath
try {
  Invoke-Cloud (@('builds','submit','.','--config','deploy/gcp/cloudbuild.yaml','--substitutions',"_REGION=$Region,_REPOSITORY=corten,_TAG=$ImageTag") + $common)
  # Exactly one job task; schema changes finish before a new app revision is deployed.
  Invoke-Cloud (@('run','jobs','deploy','corten-migrate','--image',$backendImage,'--region',$Region,'--service-account',$backendIdentity,'--set-cloudsql-instances',$sqlConnection,'--network',$Network,'--subnet',$Subnet,'--vpc-egress','private-ranges-only','--set-secrets',$secretBindings,'--env-vars-file','deploy/gcp/backend.env.yaml','--command','python','--args=-m,src.db.migrate','--tasks','1','--parallelism','1','--max-retries','0','--task-timeout','600s','--memory','1Gi','--cpu','1') + $common)
  Invoke-Cloud (@('run','jobs','execute','corten-migrate','--region',$Region,'--wait') + $common)
  Invoke-Cloud (@('run','deploy','corten-ai-api','--image',$backendImage,'--region',$Region,'--service-account',$backendIdentity,'--add-cloudsql-instances',$sqlConnection,'--network',$Network,'--subnet',$Subnet,'--vpc-egress','private-ranges-only','--set-secrets',$secretBindings,'--env-vars-file','deploy/gcp/backend.env.yaml','--no-allow-unauthenticated','--min','1','--max','10','--concurrency','16','--memory','1Gi','--cpu','1','--cpu-boost','--timeout','300s','--startup-probe','httpGet.path=/ready,httpGet.port=8080,initialDelaySeconds=0,timeoutSeconds=5,periodSeconds=10,failureThreshold=24','--liveness-probe','httpGet.path=/health,httpGet.port=8080,periodSeconds=30,timeoutSeconds=5,failureThreshold=3') + $common)
  Invoke-Cloud (@('run','services','add-iam-policy-binding','corten-ai-api','--region',$Region,'--member',"serviceAccount:$frontendIdentity",'--role','roles/run.invoker') + $common)
  $backendUrl = & $GcloudPath run services describe corten-ai-api --region=$Region --project=$ProjectId '--format=value(status.url)'
  if ($LASTEXITCODE -ne 0 -or $backendUrl -notmatch '^https://[a-z0-9.-]+\.run\.app$') { throw 'Could not validate the backend URL.' }
  Invoke-Cloud (@('run','deploy','corten-ai-web','--image',$frontendImage,'--region',$Region,'--service-account',$frontendIdentity,'--set-env-vars',"NODE_ENV=production,BACKEND_URL=$backendUrl,BACKEND_IDENTITY_AUDIENCE=$backendUrl",'--allow-unauthenticated','--min','1','--max','20','--concurrency','40','--memory','1Gi','--cpu','1','--cpu-boost','--timeout','300s','--port','8080','--startup-probe','httpGet.path=/,httpGet.port=8080,timeoutSeconds=5,periodSeconds=10,failureThreshold=24') + $common)
  $frontendUrl = & $GcloudPath run services describe corten-ai-web --region=$Region --project=$ProjectId '--format=value(status.url)'
  if ($LASTEXITCODE -ne 0 -or $frontendUrl -notmatch '^https://[a-z0-9.-]+\.run\.app$') { throw 'Could not validate the frontend URL.' }
  Invoke-Cloud (@('run','services','update','corten-ai-web','--region',$Region,'--update-env-vars',"APP_ORIGIN=$frontendUrl") + $common)
  Write-Host "Frontend deployed: $frontendUrl"
} finally { Pop-Location }

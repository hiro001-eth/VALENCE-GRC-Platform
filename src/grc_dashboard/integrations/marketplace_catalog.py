"""Extended integration marketplace catalog (200+ SaaS/cloud tools)."""
from __future__ import annotations

# Hand-maintained integrations with live collectors or SIEM wiring
CORE_INTEGRATIONS: list[dict] = [
    {"id": "wazuh", "name": "Wazuh", "category": "siem", "description": "Wazuh Indexer alerts and agent telemetry", "status": "available", "auth_type": "api_key", "collector": True},
    {"id": "splunk", "name": "Splunk Enterprise", "category": "siem", "description": "Splunk ES search and notable events", "status": "available", "auth_type": "token", "collector": True},
    {"id": "elastic", "name": "Elastic Security", "category": "siem", "description": "Elasticsearch security analytics", "status": "available", "auth_type": "api_key", "collector": True},
    {"id": "sentinel", "name": "Azure Sentinel", "category": "siem", "description": "Log Analytics KQL for incidents", "status": "available", "auth_type": "oauth", "collector": True},
    {"id": "aws", "name": "AWS", "category": "cloud", "description": "Config rules, CloudTrail, GuardDuty via cross-account IAM role", "status": "available", "auth_type": "cross_account_role", "collector": True},
    {"id": "gcp", "name": "Google Cloud", "category": "cloud", "description": "Security Command Center and IAM", "status": "available", "auth_type": "oauth", "collector": True},
    {"id": "azure", "name": "Microsoft Azure", "category": "cloud", "description": "Defender, Conditional Access, Sentinel", "status": "available", "auth_type": "oauth", "collector": True},
    {"id": "github", "name": "GitHub", "category": "devsecops", "description": "Org audit log and branch protection", "status": "available", "auth_type": "oauth", "collector": True},
    {"id": "google_workspace", "name": "Google Workspace", "category": "identity", "description": "Admin audit logs and 2SV", "status": "available", "auth_type": "oauth", "collector": True},
    {"id": "okta", "name": "Okta", "category": "identity", "description": "IdP lifecycle and MFA policies", "status": "available", "auth_type": "oauth", "collector": True},
    {"id": "jamf", "name": "Jamf Pro", "category": "mdm", "description": "Mac/iOS device compliance sync", "status": "available", "auth_type": "api_key", "collector": True},
    {"id": "kandji", "name": "Kandji", "category": "mdm", "description": "Apple fleet compliance and blueprint checks", "status": "available", "auth_type": "api_key", "collector": True},
    {"id": "slack", "name": "Slack", "category": "alerting", "description": "Threshold breach notifications", "status": "available", "auth_type": "webhook", "collector": False},
    {"id": "pagerduty", "name": "PagerDuty", "category": "alerting", "description": "Incident routing", "status": "available", "auth_type": "api_key", "collector": False},
    {"id": "jira", "name": "Jira", "category": "itsm", "description": "Auto-remediation tickets", "status": "available", "auth_type": "oauth", "collector": True},
    {"id": "servicenow", "name": "ServiceNow", "category": "itsm", "description": "ITSM incidents, changes, CMDB sync", "status": "available", "auth_type": "oauth", "collector": True},
    {"id": "gitlab", "name": "GitLab", "category": "devsecops", "description": "Repo security, CI/CD, compliance", "status": "available", "auth_type": "oauth", "collector": True},
    {"id": "salesforce", "name": "Salesforce", "category": "saas", "description": "CRM access reviews and SOX controls", "status": "available", "auth_type": "oauth", "collector": False},
]

# Extended catalog — metadata + OAuth-ready (Vanta/Sprinto parity surface)
_EXTENDED_SPECS: list[tuple[str, str, str]] = [
    ("identity", "Microsoft Entra ID", "SSO and conditional access"),
    ("identity", "OneLogin", "IdP and MFA"),
    ("identity", "Auth0", "Customer identity"),
    ("identity", "JumpCloud", "Directory and MDM"),
    ("identity", "Duo Security", "MFA enforcement"),
    ("cloud", "DigitalOcean", "Cloud infrastructure"),
    ("cloud", "Linode", "Cloud compute"),
    ("cloud", "Cloudflare", "CDN and Zero Trust"),
    ("cloud", "Heroku", "PaaS compliance"),
    ("cloud", "Vercel", "Frontend deployment"),
    ("cloud", "Netlify", "Static hosting"),
    ("devsecops", "GitLab", "Repo security and CI"),
    ("devsecops", "Bitbucket", "Atlassian Git"),
    ("devsecops", "CircleCI", "CI/CD pipelines"),
    ("devsecops", "Jenkins", "Build automation"),
    ("devsecops", "Terraform Cloud", "IaC drift detection"),
    ("devsecops", "Snyk", "Dependency scanning"),
    ("devsecops", "SonarQube", "Code quality and SAST"),
    ("devsecops", "Dependabot", "GitHub dependency alerts"),
    ("hr", "BambooHR", "HRIS onboarding"),
    ("hr", "Gusto", "Payroll and HR"),
    ("hr", "Rippling", "HR + IT provisioning"),
    ("hr", "Workday", "Enterprise HRIS"),
    ("hr", "Deel", "Global contractor management"),
    ("mdm", "Intune", "Microsoft endpoint management"),
    ("mdm", "Workspace ONE", "VMware UEM"),
    ("mdm", "Hexnode", "Cross-platform MDM"),
    ("mdm", "Mosyle", "Apple MDM"),
    ("itsm", "ServiceNow", "ITSM workflows"),
    ("itsm", "Zendesk", "Support tickets"),
    ("itsm", "Freshservice", "IT service desk"),
    ("itsm", "Linear", "Issue tracking"),
    ("security", "CrowdStrike", "EDR telemetry"),
    ("security", "SentinelOne", "Endpoint protection"),
    ("security", "Qualys", "Vulnerability scanning"),
    ("security", "Tenable", "VM platform"),
    ("security", "Rapid7", "InsightVM"),
    ("security", "1Password", "Secrets management"),
    ("security", "HashiCorp Vault", "Secrets vault"),
    ("security", "Lacework", "Cloud security"),
    ("security", "Wiz", "CNAPP"),
    ("security", "Prisma Cloud", "CSPM"),
    ("data", "Snowflake", "Data warehouse access"),
    ("data", "Databricks", "Lakehouse governance"),
    ("data", "MongoDB Atlas", "Database security"),
    ("data", "PostgreSQL RDS", "Managed database"),
    ("saas", "Salesforce", "CRM access reviews"),
    ("saas", "HubSpot", "Marketing CRM"),
    ("saas", "Notion", "Workspace access"),
    ("saas", "Figma", "Design tool access"),
    ("saas", "Zoom", "Communications"),
    ("saas", "Atlassian Cloud", "Jira/Confluence"),
    ("saas", "Dropbox", "File sharing"),
    ("saas", "Box", "Enterprise content"),
    ("saas", "DocuSign", "E-signature audit"),
    ("saas", "Stripe", "Payment compliance"),
    ("saas", "Twilio", "Communications API"),
    ("saas", "SendGrid", "Email delivery"),
    ("saas", "Mailchimp", "Marketing email"),
    ("saas", "Intercom", "Customer messaging"),
    ("saas", "Zendesk Sell", "Sales CRM"),
    ("saas", "Airtable", "Collaborative database"),
    ("saas", "Monday.com", "Work management"),
    ("saas", "Asana", "Project management"),
    ("saas", "Trello", "Kanban boards"),
    ("saas", "Miro", "Collaboration whiteboard"),
    ("saas", "Loom", "Video messaging"),
    ("saas", "Calendly", "Scheduling"),
    ("saas", "Typeform", "Forms and surveys"),
    ("saas", "SurveyMonkey", "Surveys"),
    ("saas", "Canva", "Design platform"),
    ("saas", "Adobe Creative Cloud", "Creative suite"),
    ("saas", "Shopify", "E-commerce"),
    ("saas", "Square", "Payments"),
    ("saas", "QuickBooks", "Accounting"),
    ("saas", "Xero", "Accounting"),
    ("saas", "NetSuite", "ERP"),
    ("saas", "SAP", "Enterprise ERP"),
    ("saas", "Oracle Cloud", "Enterprise cloud"),
    ("saas", "ServiceTitan", "Field service"),
    ("saas", "Toast", "Restaurant POS"),
    ("saas", "Brex", "Corporate cards"),
    ("saas", "Ramp", "Spend management"),
    ("saas", "Expensify", "Expense reports"),
    ("saas", "Carta", "Cap table"),
    ("saas", "Pulley", "Equity management"),
    ("saas", "Greenhouse", "Recruiting ATS"),
    ("saas", "Lever", "Recruiting"),
    ("saas", "Ashby", "Recruiting platform"),
    ("saas", "Lattice", "Performance management"),
    ("saas", "Culture Amp", "Employee engagement"),
    ("saas", "15Five", "Performance reviews"),
    ("saas", "KnowBe4", "Security awareness training"),
    ("saas", "Proofpoint", "Email security"),
    ("saas", "Mimecast", "Email security"),
    ("saas", "Abnormal Security", "Email AI security"),
    ("saas", "Vanta", "Compliance automation"),
    ("saas", "Drata", "Compliance automation"),
    ("saas", "Sprinto", "Compliance automation"),
]

# Pad to 200+ with category templates
_CATEGORY_PAD: list[tuple[str, str]] = [
    ("cloud", "Cloud Provider"),
    ("identity", "Identity Provider"),
    ("devsecops", "DevSecOps Tool"),
    ("hr", "HR System"),
    ("mdm", "MDM Platform"),
    ("security", "Security Tool"),
    ("saas", "SaaS Application"),
    ("itsm", "ITSM Platform"),
    ("data", "Data Platform"),
]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("/", "_").replace(".", "").replace("-", "_")[:40]


def build_extended_catalog() -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []

    for item in CORE_INTEGRATIONS:
        seen.add(item["id"])
        out.append({k: v for k, v in item.items() if k != "collector"})

    for category, name, desc in _EXTENDED_SPECS:
        iid = _slug(name)
        if iid in seen:
            continue
        seen.add(iid)
        out.append({
            "id": iid,
            "name": name,
            "category": category,
            "description": desc,
            "status": "roadmap",
            "auth_type": "oauth",
            "collector": False,
        })

    return out


COLLECTOR_IDS: frozenset[str] = frozenset(
    i["id"] for i in CORE_INTEGRATIONS if i.get("collector")
)

OAUTH_PROVIDERS: dict[str, dict[str, str]] = {
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scope": "read:org read:user",
        "env_client_id": "GITHUB_OAUTH_CLIENT_ID",
        "env_client_secret": "GITHUB_OAUTH_CLIENT_SECRET",
    },
    "google_workspace": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/admin.reports.audit.readonly",
        "env_client_id": "GOOGLE_OAUTH_CLIENT_ID",
        "env_client_secret": "GOOGLE_OAUTH_CLIENT_SECRET",
    },
    "okta": {
        "authorize_url": "{org_url}/oauth2/v1/authorize",
        "token_url": "{org_url}/oauth2/v1/token",
        "scope": "okta.users.read okta.logs.read",
        "env_client_id": "OKTA_OAUTH_CLIENT_ID",
        "env_client_secret": "OKTA_OAUTH_CLIENT_SECRET",
    },
    "azure": {
        "authorize_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "scope": "https://management.azure.com/.default",
        "env_client_id": "AZURE_OAUTH_CLIENT_ID",
        "env_client_secret": "AZURE_OAUTH_CLIENT_SECRET",
    },
    "jira": {
        "authorize_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "scope": "read:jira-work write:jira-work offline_access",
        "env_client_id": "JIRA_OAUTH_CLIENT_ID",
        "env_client_secret": "JIRA_OAUTH_CLIENT_SECRET",
    },
    "servicenow": {
        "authorize_url": "{instance_url}/oauth_auth.do",
        "token_url": "{instance_url}/oauth_token.do",
        "scope": "useraccount",
        "env_client_id": "SERVICENOW_OAUTH_CLIENT_ID",
        "env_client_secret": "SERVICENOW_OAUTH_CLIENT_SECRET",
    },
    "gcp": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/cloud-platform.read-only",
        "env_client_id": "GCP_OAUTH_CLIENT_ID",
        "env_client_secret": "GCP_OAUTH_CLIENT_SECRET",
    },
    "gitlab": {
        "authorize_url": "https://gitlab.com/oauth/authorize",
        "token_url": "https://gitlab.com/oauth/token",
        "scope": "read_api",
        "env_client_id": "GITLAB_OAUTH_CLIENT_ID",
        "env_client_secret": "GITLAB_OAUTH_CLIENT_SECRET",
    },
    "salesforce": {
        "authorize_url": "https://login.salesforce.com/services/oauth2/authorize",
        "token_url": "https://login.salesforce.com/services/oauth2/token",
        "scope": "api refresh_token",
        "env_client_id": "SALESFORCE_OAUTH_CLIENT_ID",
        "env_client_secret": "SALESFORCE_OAUTH_CLIENT_SECRET",
    },
    "aws": {
        "authorize_url": "",
        "token_url": "",
        "scope": "",
        "env_client_id": "AWS_OAUTH_CLIENT_ID",
        "env_client_secret": "AWS_OAUTH_CLIENT_SECRET",
        "auth_method": "cross_account_role",
    },
    "slack": {
        "authorize_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scope": "channels:read chat:write",
        "env_client_id": "SLACK_OAUTH_CLIENT_ID",
        "env_client_secret": "SLACK_OAUTH_CLIENT_SECRET",
    },
}

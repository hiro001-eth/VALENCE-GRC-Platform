#!/usr/bin/env python3
"""Generate full ISO 27001:2022 Annex A and SOC 2 TSC control YAML."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "frameworks"

ISO_ANNEX_A: list[tuple[str, str, str, list[str]]] = [
    ("A.5.1", "Policies for information security", "Information security policy and topic-specific policies.", ["KPI-PHI-001"]),
    ("A.5.2", "Information security roles and responsibilities", "Define and allocate information security responsibilities.", ["KPI-PHI-001"]),
    ("A.5.3", "Segregation of duties", "Conflicting duties segregated to reduce misuse.", ["KPI-PHI-001"]),
    ("A.5.4", "Management responsibilities", "Management requires personnel to apply security.", ["KPI-PHI-001"]),
    ("A.5.5", "Contact with authorities", "Maintain contacts with relevant authorities.", ["KRI-MTTD-001"]),
    ("A.5.6", "Contact with special interest groups", "Maintain contacts with security forums.", ["KRI-CVE-001"]),
    ("A.5.7", "Threat intelligence", "Receive and analyze threat intelligence.", ["KRI-CVE-001", "KPI-FPR-001"]),
    ("A.5.8", "Information security in project management", "Address security in project management.", ["KRI-CVE-001"]),
    ("A.5.9", "Inventory of information and assets", "Inventory of information and associated assets.", ["KPI-FPR-001"]),
    ("A.5.10", "Acceptable use of information", "Rules for acceptable use identified and documented.", ["KPI-PHI-001"]),
    ("A.5.11", "Return of assets", "Personnel return organizational assets on change/termination.", ["KPI-PHI-001"]),
    ("A.5.12", "Classification of information", "Information classified according to needs.", ["KRI-DLP-001"]),
    ("A.5.13", "Labelling of information", "Appropriate procedures for labelling.", ["KRI-DLP-001"]),
    ("A.5.14", "Information transfer", "Rules and procedures for information transfer.", ["KRI-DLP-001"]),
    ("A.5.15", "Access control", "Rules to control physical and logical access.", ["KPI-PHI-001"]),
    ("A.5.16", "Identity management", "Manage full lifecycle of identities.", ["KPI-PHI-001"]),
    ("A.5.17", "Authentication information", "Manage authentication information securely.", ["KPI-PHI-001"]),
    ("A.5.18", "Access rights", "Provision, review, modify and remove access rights.", ["KPI-PHI-001"]),
    ("A.5.19", "Information security in supplier relationships", "Processes for supplier security.", ["KRI-CVE-001"]),
    ("A.5.20", "Addressing security in supplier agreements", "Establish and agree security requirements.", ["KRI-CVE-001"]),
    ("A.5.21", "Managing ICT supply chain security", "Manage ICT supply chain risks.", ["KRI-CVE-001"]),
    ("A.5.22", "Monitoring and review of supplier services", "Monitor and review supplier services.", ["KPI-FPR-001"]),
    ("A.5.23", "Information security for cloud services", "Acquire, use, manage and exit cloud services securely.", ["KRI-CVE-001"]),
    ("A.5.24", "Information security incident management planning", "Plan and prepare for incident management.", ["KRI-MTTD-001", "KRI-MTTR-001"]),
    ("A.5.25", "Assessment and decision on security events", "Assess and decide on information security events.", ["KRI-MTTD-001"]),
    ("A.5.26", "Response to information security incidents", "Respond to incidents per documented procedures.", ["KRI-MTTR-001"]),
    ("A.5.27", "Learning from information security incidents", "Knowledge from incidents used to strengthen controls.", ["KRI-MTTR-001"]),
    ("A.5.28", "Collection of evidence", "Establish procedures for evidence identification and handling.", ["KPI-FPR-001"]),
    ("A.5.29", "Information security during disruption", "Protect information during disruption.", ["KRI-MTTD-001"]),
    ("A.5.30", "ICT readiness for business continuity", "ICT readiness planned and implemented.", ["KRI-MTTD-001"]),
    ("A.5.31", "Legal and regulatory requirements", "Identify and comply with legal requirements.", ["KPI-PHI-001"]),
    ("A.5.32", "Intellectual property rights", "Implement procedures to protect IP rights.", ["KRI-DLP-001"]),
    ("A.5.33", "Protection of records", "Records protected from loss and unauthorized access.", ["KRI-DLP-001"]),
    ("A.5.34", "Privacy and protection of PII", "Protect PII per applicable legislation.", ["KRI-DLP-001"]),
    ("A.5.35", "Independent review of information security", "Review approach independently at planned intervals.", ["KPI-FPR-001"]),
    ("A.5.36", "Compliance with policies and standards", "Review compliance with security policies.", ["KPI-FPR-001"]),
    ("A.5.37", "Documented operating procedures", "Operating procedures documented and available.", ["KPI-PHI-001"]),
    ("A.6.1", "Screening", "Background verification checks on candidates.", ["KPI-PHI-001"]),
    ("A.6.2", "Terms and conditions of employment", "Employment contracts state security responsibilities.", ["KPI-PHI-001"]),
    ("A.6.3", "Information security awareness and training", "Personnel receive appropriate awareness and training.", ["KPI-PHI-001"]),
    ("A.6.4", "Disciplinary process", "Formal disciplinary process for security violations.", ["KPI-PHI-001"]),
    ("A.6.5", "Responsibilities after termination", "Security responsibilities remain valid after termination.", ["KPI-PHI-001"]),
    ("A.6.6", "Confidentiality or non-disclosure agreements", "NDAs identified and enforced.", ["KRI-DLP-001"]),
    ("A.6.7", "Remote working", "Security measures for remote working.", ["KPI-PHI-001"]),
    ("A.6.8", "Information security event reporting", "Mechanism for reporting security events.", ["KRI-MTTD-001"]),
    ("A.7.1", "Physical security perimeters", "Security perimeters to protect information.", ["KPI-PHI-001"]),
    ("A.7.2", "Physical entry", "Secure areas protected by entry controls.", ["KPI-PHI-001"]),
    ("A.7.3", "Securing offices, rooms and facilities", "Physical security for offices and facilities.", ["KPI-PHI-001"]),
    ("A.7.4", "Physical security monitoring", "Premises continuously monitored.", ["KPI-FPR-001"]),
    ("A.7.5", "Protecting against physical threats", "Protection against natural and environmental threats.", ["KPI-PHI-001"]),
    ("A.7.6", "Working in secure areas", "Procedures for working in secure areas.", ["KPI-PHI-001"]),
    ("A.7.7", "Clear desk and clear screen", "Clear desk and clear screen rules.", ["KRI-DLP-001"]),
    ("A.7.8", "Equipment siting and protection", "Equipment sited and protected.", ["KPI-PHI-001"]),
    ("A.7.9", "Security of assets off-premises", "Off-site assets protected.", ["KPI-PHI-001"]),
    ("A.7.10", "Storage media", "Storage media managed through lifecycle.", ["KRI-DLP-001"]),
    ("A.7.11", "Supporting utilities", "Information processing facilities protected from utility failures.", ["KRI-MTTD-001"]),
    ("A.7.12", "Cabling security", "Cables carrying power or data protected.", ["KPI-PHI-001"]),
    ("A.7.13", "Equipment maintenance", "Equipment maintained correctly.", ["KPI-FPR-001"]),
    ("A.7.14", "Secure disposal or re-use of equipment", "Items securely disposed or sanitized.", ["KRI-DLP-001"]),
    ("A.8.1", "User endpoint devices", "Information on endpoint devices protected.", ["KPI-PHI-001"]),
    ("A.8.2", "Privileged access rights", "Restrict and manage privileged access.", ["KPI-PHI-001"]),
    ("A.8.3", "Information access restriction", "Access to information restricted per policy.", ["KPI-PHI-001"]),
    ("A.8.4", "Access to source code", "Read and write access to source code managed.", ["KRI-CVE-001"]),
    ("A.8.5", "Secure authentication", "Secure authentication technologies and procedures.", ["KPI-PHI-001"]),
    ("A.8.6", "Capacity management", "Use of resources monitored and adjusted.", ["KPI-FPR-001"]),
    ("A.8.7", "Protection against malware", "Protection against malware implemented.", ["KRI-CVE-001"]),
    ("A.8.8", "Management of technical vulnerabilities", "Identify and remediate vulnerabilities.", ["KRI-CVE-001"]),
    ("A.8.9", "Configuration management", "Configurations established and monitored.", ["KRI-CVE-001"]),
    ("A.8.10", "Information deletion", "Information deleted when no longer required.", ["KRI-DLP-001"]),
    ("A.8.11", "Data masking", "Data masked per policy and legislation.", ["KRI-DLP-001"]),
    ("A.8.12", "Data leakage prevention", "DLP measures applied to systems and networks.", ["KRI-DLP-001"]),
    ("A.8.13", "Information backup", "Backup copies maintained and tested.", ["KRI-MTTR-001"]),
    ("A.8.14", "Redundancy of information processing facilities", "Processing facilities implemented with redundancy.", ["KRI-MTTD-001"]),
    ("A.8.15", "Logging", "Logs produced, stored, protected and analyzed.", ["KPI-FPR-001"]),
    ("A.8.16", "Monitoring activities", "Networks and systems monitored for anomalies.", ["KPI-FPR-001", "KRI-MTTD-001"]),
    ("A.8.17", "Clock synchronization", "Clocks synchronized to approved time sources.", ["KPI-FPR-001"]),
    ("A.8.18", "Use of privileged utility programs", "Use of utility programs restricted and controlled.", ["KPI-PHI-001"]),
    ("A.8.19", "Installation of software on operational systems", "Procedures govern software installation.", ["KRI-CVE-001"]),
    ("A.8.20", "Networks security", "Networks and network devices secured and managed.", ["KRI-DLP-001"]),
    ("A.8.21", "Security of network services", "Security mechanisms for network services.", ["KRI-DLP-001"]),
    ("A.8.22", "Segregation of networks", "Groups of services and users segregated on networks.", ["KRI-DLP-001"]),
    ("A.8.23", "Web filtering", "Access to external websites managed.", ["KRI-CVE-001"]),
    ("A.8.24", "Use of cryptography", "Rules for effective use of cryptography.", ["KRI-DLP-001"]),
    ("A.8.25", "Secure development life cycle", "Rules for secure development established.", ["KRI-CVE-001"]),
    ("A.8.26", "Application security requirements", "Security requirements identified and applied.", ["KRI-CVE-001"]),
    ("A.8.27", "Secure system architecture and engineering principles", "Principles established and applied.", ["KRI-CVE-001"]),
    ("A.8.28", "Secure coding", "Secure coding principles applied.", ["KRI-CVE-001"]),
    ("A.8.29", "Security testing in development and acceptance", "Security testing defined and performed.", ["KRI-CVE-001"]),
    ("A.8.30", "Outsourced development", "Direct and monitor outsourced development.", ["KRI-CVE-001"]),
    ("A.8.31", "Separation of development, test and production", "Environments separated and secured.", ["KRI-CVE-001"]),
    ("A.8.32", "Change management", "Changes to information processing facilities controlled.", ["KRI-CVE-001"]),
    ("A.8.33", "Test information", "Test information selected and protected.", ["KRI-DLP-001"]),
    ("A.8.34", "Protection of information systems during audit testing", "Audit tests planned to minimize operational impact.", ["KPI-FPR-001"]),
]

SOC2_EXTRA: list[tuple[str, str, str, list[str]]] = [
    ("SOC2-A1.1", "Capacity Planning", "Maintain capacity to meet availability commitments.", ["KPI-FPR-001"]),
    ("SOC2-A1.2", "Environmental Protections", "Protect against environmental disruptions.", ["KRI-MTTD-001"]),
    ("SOC2-A1.3", "Recovery Testing", "Test recovery procedures for availability.", ["KRI-MTTR-001"]),
    ("SOC2-C1.1", "Confidential Information Identification", "Identify and maintain confidential information.", ["KRI-DLP-001"]),
    ("SOC2-C1.2", "Confidential Information Disposal", "Dispose of confidential information securely.", ["KRI-DLP-001"]),
    ("SOC2-PI1.1", "Processing Integrity — Inputs", "Process inputs completely and accurately.", ["KPI-FPR-001"]),
    ("SOC2-PI1.2", "Processing Integrity — Processing", "Processing achieves intended purpose.", ["KPI-FPR-001"]),
    ("SOC2-PI1.3", "Processing Integrity — Outputs", "Outputs complete, accurate, and timely.", ["KPI-FPR-001"]),
    ("SOC2-PI1.4", "Processing Integrity — Error Handling", "Errors identified and corrected timely.", ["KRI-MTTD-001"]),
    ("SOC2-PI1.5", "Processing Integrity — Storage", "Store inputs and outputs completely and accurately.", ["KRI-DLP-001"]),
]


def main() -> None:
    iso_doc = {
        "framework_name": "ISO27001",
        "full_name": "ISO/IEC 27001:2022 Information Security Management — Annex A",
        "version": "2022",
        "controls": [
            {
                "id": f"ISO-{cid}",
                "title": title,
                "description": desc,
                "metric_ids": metrics,
            }
            for cid, title, desc, metrics in ISO_ANNEX_A
        ],
    }
    (RULES / "iso27001.yaml").write_text(
        yaml.dump(iso_doc, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )

    soc2_path = RULES / "soc2.yaml"
    existing = yaml.safe_load(soc2_path.read_text(encoding="utf-8"))
    existing_ids = {c["id"] for c in existing.get("controls", [])}
    for cid, title, desc, metrics in SOC2_EXTRA:
        if cid not in existing_ids:
            existing["controls"].append({
                "id": cid,
                "title": title,
                "description": desc,
                "metric_ids": metrics,
            })
    existing["full_name"] = "SOC 2 Type II — Full Trust Services Criteria (CC, A, C, PI, P)"
    (soc2_path).write_text(
        yaml.dump(existing, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    print(f"ISO controls: {len(iso_doc['controls'])}")
    print(f"SOC2 controls: {len(existing['controls'])}")


if __name__ == "__main__":
    main()

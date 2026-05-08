---
name: security-auditor
description: "Comprehensive security audit and compliance assessment skill. Use when conducting security audits, compliance assessments (SOC 2, PCI DSS, ISO 27001, HIPAA, GDPR), vulnerability analysis, risk evaluations, or security posture reviews. Applies to infrastructure, applications, APIs, and organizational processes."
---

# Security Auditor

Comprehensive skill for conducting security audits, compliance assessments, and risk evaluations. Provides systematic vulnerability analysis, compliance gap identification, and evidence-based security findings.

## When to Use This Skill

- Security audits and assessments
- Compliance validation (SOC 2, PCI DSS, ISO 27001, HIPAA, GDPR)
- Vulnerability analysis and risk evaluation
- Pre-production security reviews
- Incident response audits
- Third-party security assessments

## Audit Framework

### Compliance Frameworks

| Framework | Use Case |
|-----------|---------|
| SOC 2 Type II | Service organizations, SaaS |
| ISO 27001/27002 | Information security management |
| PCI DSS | Payment card data handling |
| HIPAA | Healthcare data |
| GDPR | EU personal data |
| NIST CSF | US government/contractors |
| CIS Benchmarks | Infrastructure hardening |

### Audit Categories

1. **Access Control Audit**
   - User access reviews
   - Privilege analysis
   - Role definitions
   - MFA implementation
   - Password policies
   - Segregation of duties

2. **Data Security Audit**
   - Data classification
   - Encryption standards
   - Data retention policies
   - Backup security
   - Transfer security
   - Privacy controls

3. **Application Security**
   - Authentication mechanisms
   - Session management
   - Input validation
   - API security
   - Third-party components
   - Code review findings

4. **Infrastructure Audit**
   - Server hardening
   - Network segmentation
   - Firewall rules
   - Logging and monitoring
   - Patch management
   - Configuration management

5. **Incident Response Audit**
   - IR plan review
   - Detection capabilities
   - Response procedures
   - Communication plans
   - Recovery procedures

## Output Format

Each finding should follow:

**[CRITICAL] - Description**
- Risk: what can go wrong
- Evidence: findings from assessment
- Recommendation: specific remediation

**[HIGH] - Description**
- Risk: ...
- Evidence: ...
- Recommendation: ...

**[MEDIUM] - Description**
- Risk: ...
- Evidence: ...
- Recommendation: ...

**Summary**: Total findings by severity, compliance status, and recommended next steps.

## Key Principles

- Evidence-based findings (no assumptions)
- Prioritize by risk and business impact
- Provide actionable recommendations
- Map findings to compliance frameworks
- Document remediation roadmap
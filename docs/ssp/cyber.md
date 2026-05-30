# Singapore Government Cybersecurity Control Catalog

Source: https://info.standards.tech.gov.sg/control-catalog/cybersecurity/

Scraped into `chatbot/data/ssp/cybersecurity_catalog.json` via `scripts/ingest/scrape_ssp_catalog.py`.

## Categories

| Code | Name | URL |
|------|------|-----|
| AC | Access Control | /control-catalog/cybersecurity/ac/ |
| AS | Application Security | /control-catalog/cybersecurity/as/ |
| BR | Backup and Recovery | /control-catalog/cybersecurity/br/ |
| CS | Container Security | /control-catalog/cybersecurity/cs/ |
| CK | Cryptography, Encryption & Key Management | /control-catalog/cybersecurity/ck/ |
| DP | Data Protection | /control-catalog/cybersecurity/dp/ |
| DC | Datacentre | /control-catalog/cybersecurity/dc/ |
| GA | Generative AI | /control-catalog/cybersecurity/ga/ |
| HR | Human Resource | /control-catalog/cybersecurity/hr/ |
| IS | Infrastructure Security | /control-catalog/cybersecurity/is/ |
| LM | Logging and Monitoring | /control-catalog/cybersecurity/lm/ |
| NS | Network Security | /control-catalog/cybersecurity/ns/ |
| PM | Security Programme Management | /control-catalog/cybersecurity/pm/ |
| RS | Resiliency | /control-catalog/cybersecurity/rs/ |
| SC | Software Supply Chain | /control-catalog/cybersecurity/sc/ |
| SD | Secure Development | /control-catalog/cybersecurity/sd/ |
| ST | Security Testing | /control-catalog/cybersecurity/st/ |

## DSS Catalog

Source: https://info.standards.tech.gov.sg/control-catalog/dss/

Scraped into `chatbot/data/ssp/dss_catalog.json`.

| Code | Name |
|------|------|
| BD | Baseline Design Practices |
| PR | Performance and Reliability |
| TX | Transactions and Payments |
| TL | Trust and Legitimacy |
| UU | Understand Users |
| WO | WCAG: Operable |
| WP | WCAG: Perceivable |
| WR | WCAG: Robust |
| WU | WCAG: Understandable |

## SSP Profiles

Source: https://info.standards.tech.gov.sg/ssp/

Scraped into `chatbot/data/ssp/ssp_profiles.json`.

| Profile Key | Description |
|------------|-------------|
| low_risk_cloud | Low-risk cloud systems |
| low_risk_onprem | Low-risk on-premises systems |
| medium_risk_cloud | Medium-risk cloud systems |
| high_risk_cloud_cii | High-risk cloud / CII systems |
| generative_ai | Generative AI systems |
| digital_services_others | Digital services (under 1M visits/year) |
| digital_services_high_impact | Digital services (1M+ visits/year) |
| sandbox | Sandbox / pilot |

## Control Levels

- **L0 — Cardinal**: Foundational governance requirements (mandatory for all)
- **L1 — Basic Hygiene**: Process + technical baseline controls (recommended)
- **L2 — Best Practice**: Enhanced/advanced controls (conditional/optional)

## Regenerating Data

```bash
python scripts/ingest/scrape_ssp_catalog.py
```

Run quarterly or when catalog is updated. Data files are excluded from git.

"""Load packaged bootstrap data, never runtime scraping targets."""

import json
from importlib.resources import files

from job_scrapper.companies.contracts import Company, CompanyTarget


def load_seed() -> tuple[tuple[Company, ...], tuple[CompanyTarget, ...]]:
    raw = json.loads(files('job_scrapper').joinpath('company_seed.json').read_text(encoding='utf-8'))
    if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw['version'] != 1 or set(raw) != {'version', 'companies', 'targets'}:
        raise ValueError('unsupported company seed format')
    if not isinstance(raw['companies'], list) or not isinstance(raw['targets'], list):
        raise ValueError('seed companies and targets must be arrays')
    companies = tuple(Company.model_validate(row) for row in raw['companies'])
    targets = tuple(CompanyTarget.model_validate(row) for row in raw['targets'])
    by_key = {row.company_key: row for row in companies}
    keys = set(by_key)
    if len(keys) != len(companies):
        raise ValueError('duplicate company seed key')
    pairs = {(row.provider, row.account_key) for row in targets}
    if len(pairs) != len(targets):
        raise ValueError('duplicate provider/account seed pair')
    if any(row.company_key not in keys for row in targets):
        raise ValueError('seed target references an unknown company')
    if any(row.company_name != by_key[row.company_key].company_name for row in targets):
        raise ValueError('seed target employer must match its company identity')
    return companies, targets

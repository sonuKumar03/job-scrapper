"""Shared read/export filters; ingestion never uses these predicates."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_

from job_scrapper.storage.postgres.models import JobModel, EXPERIENCE_MIN, EXPERIENCE_MAX, WORK_ARRANGEMENT, EMPLOYMENT_TYPE


class JobFilters(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    q: str = Field(default='', max_length=200)
    source: str = Field(default='', max_length=64)
    company: str = Field(default='', max_length=500)
    work_arrangement: Literal['', 'remote', 'hybrid', 'in-office', 'unknown'] = ''
    employment_type: Literal['', 'full_time', 'part_time', 'contract', 'temporary', 'internship', 'volunteer', 'per_diem', 'other', 'unknown'] = ''
    experience_min: float | None = Field(default=None, ge=0)
    experience_max: float | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def valid_range(self):
        if self.experience_min is not None and self.experience_max is not None and self.experience_min > self.experience_max:
            raise ValueError('Minimum experience cannot exceed maximum experience.')
        return self


def job_predicates(filters: JobFilters, *, exclude: str | None = None) -> list:
    predicates = []
    if filters.q.strip():
        literal = filters.q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        predicates.append(or_(JobModel.title.ilike(f'%{literal}%', escape='\\'),
                              JobModel.company_name.ilike(f'%{literal}%', escape='\\')))
    for field, column in (('source', JobModel.source), ('company', JobModel.company_name),
                          ('work_arrangement', WORK_ARRANGEMENT), ('employment_type', EMPLOYMENT_TYPE)):
        value = getattr(filters, field)
        if value and field != exclude:
            predicates.append(column == value)
    if exclude != 'experience' and (filters.experience_min is not None or filters.experience_max is not None):
        predicates.append(or_(EXPERIENCE_MIN.is_not(None), EXPERIENCE_MAX.is_not(None)))
        if filters.experience_min is not None:
            predicates.append(or_(EXPERIENCE_MAX.is_(None), EXPERIENCE_MAX >= filters.experience_min))
        if filters.experience_max is not None:
            predicates.append(or_(EXPERIENCE_MIN.is_(None), EXPERIENCE_MIN <= filters.experience_max))
    return predicates

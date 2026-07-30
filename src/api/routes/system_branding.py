"""Compatibility stub for a Flirexa commercial component.

The implementation is delivered only with the `white_label` entitlement.
"""

FLIREXA_COMMERCIAL_STUB = True
REQUIRED_FEATURE = "white_label"
_UPGRADE_HINT = (
    "This component requires the white_label commercial entitlement. "
    "See https://flirexa.biz/#pricing for available plans."
)


import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from src.database.connection import get_db
from src.modules.branding import get_all_branding
from src.api.middleware.license_gate import require_license_feature

router = APIRouter()
_gate = Depends(require_license_feature('white_label'))

class BrandingUpdateRequest(BaseModel):
    branding_privacy_url: Optional[str] = Field(None, max_length=500)
    branding_terms_url: Optional[str] = Field(None, max_length=500)
    branding_privacy_text: Optional[str] = Field(None, max_length=50000)
    branding_terms_text: Optional[str] = Field(None, max_length=50000)

    @field_validator('branding_privacy_url', 'branding_terms_url')
    @classmethod
    def validate_legal_url(cls, value):
        if value is None or value == '':
            return value
        if value.startswith('/') and not value.startswith('//') and '\\' not in value:
            return value
        if not re.match(r'^https?://', value, flags=re.IGNORECASE):
            raise ValueError('Legal page URLs must use http(s) or start with /')
        return value

    @field_validator('branding_privacy_text', 'branding_terms_text')
    @classmethod
    def validate_legal_text(cls, value):
        if value is not None and '\x00' in value:
            raise ValueError('Legal text cannot contain NUL characters')
        return value

@router.get('/branding')
async def get_branding_settings(db=Depends(get_db)):
    return get_all_branding(db)

@router.post('/branding', dependencies=[_gate])
async def update_branding_settings():
    raise HTTPException(status_code=403, detail=_UPGRADE_HINT)

@router.post('/branding/logo', dependencies=[_gate])
async def upload_branding_logo():
    raise HTTPException(status_code=403, detail=_UPGRADE_HINT)

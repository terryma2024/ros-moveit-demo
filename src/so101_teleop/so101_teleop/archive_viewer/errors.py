"""Structured refusals shared by archive readers and the HTTP boundary."""
from fastapi import HTTPException


def refuse(code: str, message: str, status: int = 404):
    raise HTTPException(status_code=status, detail=dict(code=code, message=message))


def invalid(document: str, message: str):
    refuse('ARCHIVE_DOCUMENT_INVALID', f'{document}: {message}', 422)

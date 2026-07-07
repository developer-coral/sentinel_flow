from __future__ import annotations

import io
import json
import logging
import os
import re
from enum import Enum
from typing import Any, Literal

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from pypdf import PdfReader

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("sentinel.extractor")

app = FastAPI(title="Sentinel Flow Extractor", version="1.0.0")


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ExtractedDocument(BaseModel):
    document_type: str = Field(description="Contract, invoice, proposal, legal notice, etc.")
    risk_level: RiskLevel
    customer_name: str | None = None
    contact_email: str | None = None
    amount: str | None = None
    due_date: str | None = None
    summary: str
    recommended_route: Literal["crm_update", "legal_review", "finance_review", "general_review"]
    confidence: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)


class AnalysisSummary(BaseModel):
    title: str
    executive_summary: str
    workflow_decision: str
    risk_level: str
    confidence: float


class AnalysisMetrics(BaseModel):
    findings_count: int
    risks_count: int
    placeholders_found: int
    monetary_values_found: int


class AnalyzeResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    
    extracted_text_preview: str
    
    analysis: AnalysisSummary
    
    findings: list[str]
    risks: list[str]
    recommendations: list[str]
    
    metrics: AnalysisMetrics
    
    result: ExtractedDocument


def extract_text_from_bytes(filename: str, content: bytes) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else "txt"
    if suffix == "pdf":
        try:
            reader = PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"PDF extraction failed: {exc}") from exc
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="ignore")


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("Could not parse JSON from response")
        return json.loads(match.group(0))


SYSTEM_PROMPT = """You are Sentinel Flow, an enterprise document triage engine.
Return ONLY valid JSON matching this schema:
{
  "document_type": "string",
  "risk_level": "low|medium|high",
  "customer_name": "string|null",
  "contact_email": "string|null",
  "amount": "string|null",
  "due_date": "string|null",
  "summary": "short business summary",
  "recommended_route": "crm_update|legal_review|finance_review|general_review",
  "confidence": 0.0,
  "flags": ["string"]
}
Classify high risk when the document includes legal exposure, missing required fields, payment default, termination, privacy/security issues, or unusually large financial amounts.
"""


def deterministic_dev_analysis(text: str) -> ExtractedDocument:
    lowered = text.lower()

    findings = []
    flags = []

    document_type = "business_document"

    if "contract" in lowered:
        document_type = "contract"
    elif "agreement" in lowered:
        document_type = "agreement"
    elif "invoice" in lowered:
        document_type = "invoice"
    elif "proposal" in lowered:
        document_type = "proposal"

    email_match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", text)
    amount_match = re.search(r"(?:USD|EUR|GBP|\$|€|£)\s?[\d,]+(?:\.\d{2})?", text)

    amount = amount_match.group(0) if amount_match else None

    risk_score = 0

    if "termination" in lowered:
        findings.append("Termination clause detected")
        risk_score += 2

    if "penalty" in lowered:
        findings.append("Late payment penalties detected")
        risk_score += 2

    if "security" in lowered or "data breach" in lowered:
        findings.append("Data security obligations detected")
        risk_score += 1

    if "payment" in lowered:
        findings.append("Payment obligations detected")

    if amount:
        findings.append(f"Monetary value detected ({amount})")
        risk_score += 1

    placeholders = []

    placeholder_patterns = [
        ("Client Name", r"\[client"),
        ("Start Date", r"\[start date"),
        ("End Date", r"\[end date"),
        ("Amount", r"\[amount"),
        ("Payment Date", r"\[payment date"),
    ]

    for label, pattern in placeholder_patterns:
        if re.search(pattern, lowered):
            placeholders.append(label)
            risk_score += 1

    flags.extend(f"Missing {p}" for p in placeholders)

    if risk_score >= 5:
        risk = RiskLevel.high
    elif risk_score >= 2:
        risk = RiskLevel.medium
    else:
        risk = RiskLevel.low

    if risk == RiskLevel.high:
        route = "legal_review"
    elif amount:
        route = "finance_review"
    elif document_type in ("contract", "agreement"):
        route = "general_review"
    else:
        route = "crm_update"

    summary = (
        f"{document_type.replace('_', ' ').title()} detected. "
        f"{len(findings)} key findings identified. "
        f"{len(placeholders)} required fields are incomplete."
    )

    return ExtractedDocument(
        document_type=document_type,
        risk_level=risk,
        customer_name=None,
        contact_email=email_match.group(0) if email_match else None,
        amount=amount,
        due_date=None,
        summary=summary,
        recommended_route=route,
        confidence=0.90,
        flags=flags,
    )


async def call_openrouter(text: str) -> ExtractedDocument:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not configured")
    model = os.getenv("AI_MODEL", "anthropic/claude-3.5-sonnet")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this document:\n\n{text[:12000]}"},
        ],
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {response.text[:500]}")
    content = response.json()["choices"][0]["message"]["content"]
    return ExtractedDocument.model_validate(parse_json_object(content))


async def call_anthropic(text: str) -> ExtractedDocument:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")
    model = os.getenv("AI_MODEL", "claude-3-5-sonnet-20241022")
    payload = {
        "model": model,
        "max_tokens": 1000,
        "temperature": 0.1,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"Analyze this document:\n\n{text[:12000]}"}],
    }
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Anthropic error: {response.text[:500]}")
    content = "".join(block.get("text", "") for block in response.json().get("content", []))
    return ExtractedDocument.model_validate(parse_json_object(content))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
) -> AnalyzeResponse:

    if file is not None:
        raw = await file.read()
        extracted_text = extract_text_from_bytes(file.filename or "upload.txt", raw)
    elif text:
        extracted_text = text
    else:
        raise HTTPException(status_code=400, detail="Provide either a file or text")

    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="No readable text found")

    provider = os.getenv("AI_PROVIDER", "openrouter").lower()
    model = os.getenv("AI_MODEL", "anthropic/claude-3.5-sonnet")
    require_real_ai = os.getenv("REQUIRE_REAL_AI", "true").lower() == "true"

    if not require_real_ai:
        result = deterministic_dev_analysis(extracted_text)
        provider = "dev_fallback"
        model = "deterministic_dev_analysis"
    else:
        try:
            if provider == "anthropic":
                result = await call_anthropic(extracted_text)
            else:
                result = await call_openrouter(extracted_text)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"AI Provider error: {str(e)}")
            # Fallback to dev mode if AI fails unexpectedly to keep PoC running
            result = deterministic_dev_analysis(extracted_text)
            provider = "fallback_on_error"
            model = "deterministic_dev_analysis"

    findings: list[str] = []

    if result.document_type:
        findings.append(f"Document classified as '{result.document_type.replace('_', ' ').title()}'.")
    if result.amount:
        findings.append(f"Monetary value detected: {result.amount}.")
    if result.contact_email:
        findings.append(f"Email address detected: {result.contact_email}.")
    if result.customer_name:
        findings.append(f"Customer identified: {result.customer_name}.")
    if result.recommended_route:
        findings.append(f"Workflow route: {result.recommended_route.replace('_', ' ').title()}.")

    risks = []
    if result.flags:
        risks.extend(result.flags)
    if result.risk_level.value == "high":
        risks.append("Document contains clauses requiring legal review.")

    recommendations = []
    if result.risk_level.value == "high":
        recommendations.append("Route document to Legal Review.")
    elif result.risk_level.value == "medium":
        recommendations.append("Review document before approval.")
    else:
        recommendations.append("Proceed with standard workflow.")

    if result.amount:
        recommendations.append("Verify payment amounts and payment schedule.")
    if result.flags:
        recommendations.append("Complete all missing placeholders before execution.")
    recommendations.append("Validate extracted information before final processing.")

    return AnalyzeResponse(
        ok=True,
        provider=provider,
        model=model,
        extracted_text_preview=extracted_text[:500],
        analysis=AnalysisSummary(
            title="Document Analysis Report",
            executive_summary=result.summary,
            workflow_decision=result.recommended_route.replace("_", " ").title(),
            risk_level=result.risk_level.value.title(),
            confidence=result.confidence,
        ),
        findings=findings,
        risks=risks,
        recommendations=recommendations,
        metrics=AnalysisMetrics(
            findings_count=len(findings),
            risks_count=len(risks),
            placeholders_found=len(result.flags),
            monetary_values_found=1 if result.amount else 0,
        ),
        result=result,
    )
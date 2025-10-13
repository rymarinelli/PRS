"""ML-backed recommendation service used by Azure RBAC Risk Advisor.

This module exposes a Flask application that scores incoming Azure resource IDs
with a lightweight PyTorch model.  The model was trained offline on synthetic
alert telemetry so that we can run the entire experience locally without
talking to Azure.  Recommendations returned by the ``/recommend`` endpoint are
therefore realistic enough for demos while remaining deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import torch
from flask import Flask, jsonify, request

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Feature engineering utilities
# ---------------------------------------------------------------------------


@dataclass
class ResourceMetadata:
    """Thin container describing a parsed Azure resource ID."""

    resource_id: str
    subscription_id: Optional[str]
    resource_group: Optional[str]
    provider_namespace: Optional[str]
    resource_type: Optional[str]
    name: Optional[str]
    segments: List[str]


def parse_resource_id(resource_id: str) -> ResourceMetadata:
    """Parse the incoming resource ID into its core components.

    The parser is intentionally permissive so that it continues to work with
    partially formed IDs when developing against the simulator.
    """

    normalized = (resource_id or "").strip()
    segments = [segment for segment in normalized.split("/") if segment]

    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None
    provider_namespace: Optional[str] = None
    resource_type: Optional[str] = None
    name: Optional[str] = None

    if len(segments) >= 2 and segments[0].lower() == "subscriptions":
        subscription_id = segments[1]

    if "resourceGroups" in [seg.lower() for seg in segments]:
        try:
            rg_index = [seg.lower() for seg in segments].index("resourcegroups")
            resource_group = segments[rg_index + 1]
        except (ValueError, IndexError):
            resource_group = None

    try:
        provider_index = [seg.lower() for seg in segments].index("providers")
    except ValueError:
        provider_index = -1

    if provider_index > -1:
        try:
            provider_namespace = segments[provider_index + 1]
            type_part = segments[provider_index + 2 : provider_index + 4]
            if type_part:
                resource_type = "/".join(type_part)
            name = segments[-1] if segments[-1] != provider_namespace else None
        except IndexError:
            provider_namespace = provider_namespace or None

    return ResourceMetadata(
        resource_id=normalized,
        subscription_id=subscription_id,
        resource_group=resource_group,
        provider_namespace=provider_namespace,
        resource_type=resource_type,
        name=name,
        segments=segments,
    )


# Risk priors by resource type derived from a synthetic training set.  Values in
# this table mimic the signal we would see from real alert telemetry.
RESOURCE_TYPE_PRIORS: Dict[str, float] = {
    "Microsoft.Storage/storageAccounts": 0.78,
    "Microsoft.KeyVault/vaults": 0.91,
    "Microsoft.Compute/virtualMachines": 0.56,
    "Microsoft.Sql/servers": 0.74,
}


# Demo incident history for a handful of resource IDs.  During scoring this is
# converted into a feature and surfaced back in the summary copy so we can tell
# a cohesive story in demos.
INCIDENT_HISTORY: Dict[str, Dict[str, str]] = {
    "/subscriptions/2b51c4a0-3e70-4d9e-b26d-8f4f1dce0214/resourceGroups/contoso-retail-prod/providers/Microsoft.Storage/storageAccounts/corestoreprod": {
        "principal": "spn-contoso-checkout",
        "role": "Storage Blob Data Owner",
        "incidentCount": "3",
    },
    "/subscriptions/bc5f1075-9489-4c9a-9ffb-1e57d6d98c21/resourceGroups/fabrikam-secops/providers/Microsoft.KeyVault/vaults/fabrikam-kv-prod": {
        "principal": "runbook-automation",
        "role": "Key Vault Administrator",
        "incidentCount": "2",
    },
    "/subscriptions/4458cfd6-2c8b-42e3-a2f4-0f3041a4e768/resourceGroups/northwind-finance/providers/Microsoft.Sql/servers/northwind-ledger-sql": {
        "principal": "ledger-sync-app",
        "role": "SQL DB Contributor",
        "incidentCount": "4",
    },
}


FEATURE_NAMES = [
    "resource_length",
    "hierarchy_depth",
    "resource_sensitivity",
    "incident_history",
    "permissions_focus",
    "environment_risk",
]


def build_feature_vector(metadata: ResourceMetadata, page_hash: str, incident_signal: float) -> torch.Tensor:
    """Turn raw metadata into the numeric features consumed by the model."""

    segments = metadata.segments
    depth = len(segments)
    page_lower = (page_hash or "").lower()

    resource_length = min(len(metadata.resource_id) / 180.0, 1.2)
    hierarchy_depth = min(depth / 12.0, 1.0)
    resource_sensitivity = RESOURCE_TYPE_PRIORS.get(metadata.resource_type or "", 0.35)
    history_signal = min(incident_signal / 4.0, 1.0)
    permissions_focus = 1.0 if any(term in page_lower for term in ["access", "role", "permission"]) else 0.25
    environment_risk = 0.8 if metadata.resource_group and "prod" in metadata.resource_group.lower() else 0.3

    features = torch.tensor(
        [
            resource_length,
            hierarchy_depth,
            resource_sensitivity,
            history_signal,
            permissions_focus,
            environment_risk,
        ],
        dtype=torch.float32,
    )
    return features


# ---------------------------------------------------------------------------
# PyTorch model definition
# ---------------------------------------------------------------------------


class PermissionRiskModel(torch.nn.Module):
    """Logistic regression style scorer implemented with PyTorch tensors."""

    def __init__(self) -> None:
        super().__init__()
        self.register_buffer(
            "weights",
            torch.tensor([1.12, 0.84, 2.1, 1.65, 0.92, 1.35], dtype=torch.float32),
        )
        self.register_buffer("bias", torch.tensor([-1.55], dtype=torch.float32))

    def forward(self, features: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        logits = features @ self.weights + self.bias
        return torch.sigmoid(logits)

    def explain(self, features: torch.Tensor) -> List[Tuple[str, float]]:
        """Return feature contributions so the UI can surface the top factors."""

        contributions = features * self.weights
        factors = list(zip(FEATURE_NAMES, contributions.tolist()))
        factors.sort(key=lambda item: abs(item[1]), reverse=True)
        return factors


MODEL = PermissionRiskModel()


# ---------------------------------------------------------------------------
# Recommendation knowledge base
# ---------------------------------------------------------------------------


Recommendation = Dict[str, str]


KNOWLEDGE_BASE: Dict[str, Recommendation] = {
    "Microsoft.Storage/storageAccounts": {
        "issueId": "storage-access-excess",
        "title": "Scope down Storage account data-plane permissions",
        "summary": (
            "Microsoft Defender for Cloud has raised repeated data-plane alerts tied to service principals holding "
            "Storage Blob Data Owner rights."
        ),
        "panelUrl": "https://app.example.com/panel/storage",
        "azFix": "az role assignment delete --assignee {principal} --role '{role}' --scope {resource_id}",
    },
    "Microsoft.KeyVault/vaults": {
        "issueId": "keyvault-secrets-permission",
        "title": "Rotate and reduce Key Vault administrator scope",
        "summary": (
            "Privileged administrator assignments continue to trigger Defender for Cloud alerts for this Key Vault."
        ),
        "panelUrl": "https://app.example.com/panel/keyvault",
        "azFix": "az role assignment delete --assignee {principal} --role '{role}' --scope {resource_id}",
    },
    "Microsoft.Compute/virtualMachines": {
        "issueId": "vm-privilege-alert",
        "title": "Review VM local admin delegations",
        "summary": "Lateral movement heuristics highlight local admin grants connected to this VM.",
        "panelUrl": "https://app.example.com/panel/vm",
        "azFix": "az vm extension set --name AADSSHLoginForLinux --resource-group {resource_group} --vm-name {name} --enable false",
    },
    "Microsoft.Sql/servers": {
        "issueId": "sql-admin-risk",
        "title": "Audit SQL Server administrator assignments",
        "summary": "Privileged SQL roles look over-scoped when compared to baseline telemetry.",
        "panelUrl": "https://app.example.com/panel/sql",
        "azFix": "az sql server ad-admin delete --resource-group {resource_group} --server {name}",
    },
}


DEFAULT_RECOMMENDATION: Recommendation = {
    "issueId": "generic-permission-alert",
    "title": "Verify role assignments on this resource",
    "summary": "Modelled risk sits above the Microsoft Entra permissions analytics baseline for similar resources.",
    "panelUrl": "https://app.example.com/panel/overview",
    "azFix": "az role assignment list --scope {resource_id}",
}


def enrich_summary(base_summary: str, incident_context: Dict[str, str], risk_score: float) -> str:
    """Add contextual numbers and actors to the base summary copy."""

    incident_count = incident_context.get("incidentCount") or "0"
    principal = incident_context.get("principal") or "an identity"
    risk_percent = int(round(risk_score * 100))

    suffix = (
        f" The model estimates a {risk_percent}% likelihood of mis-scoped permissions "
        f"after {incident_count} recent alert(s) involving principal '{principal}'."
    )
    return f"{base_summary}{suffix}"


def build_issue_payload(
    metadata: ResourceMetadata,
    recommendation: Recommendation,
    risk_score: float,
    top_factors: Iterable[Tuple[str, float]],
    incident_context: Dict[str, str],
) -> dict:
    """Compose the JSON payload consumed by the extension."""

    rendered_summary = enrich_summary(recommendation["summary"], incident_context, risk_score)

    az_fix = recommendation["azFix"].format(
        resource_id=metadata.resource_id,
        resource_group=metadata.resource_group or "<resource-group>",
        name=metadata.name or "<resource-name>",
        principal=incident_context.get("principal", "<principal>"),
        role=incident_context.get("role", "Contributor"),
    )

    payload = {
        "hasIssue": True,
        "issueId": recommendation["issueId"],
        "title": recommendation["title"],
        "summary": rendered_summary,
        "source": "informed by alerts",
        "panelUrl": recommendation["panelUrl"],
        "azFix": az_fix,
        "resourceId": metadata.resource_id,
        "seenAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "modelScore": round(risk_score, 3),
        "topFactors": [
            {"feature": feature, "contribution": round(value, 3)}
            for feature, value in list(top_factors)[:3]
        ],
    }
    return payload


@app.after_request
def add_cors_headers(response):
    response.headers.setdefault("Access-Control-Allow-Origin", "*")
    response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type")
    response.headers.setdefault("Access-Control-Allow-Methods", "POST, OPTIONS")
    return response


@app.route("/recommend", methods=["POST", "OPTIONS"])
def recommend():
    if request.method == "OPTIONS":
        return ("", 204)

    body = request.get_json(silent=True) or {}
    resource_id = body.get("resourceId")
    page_hash = body.get("page", "")

    if not resource_id:
        return jsonify({"error": "resourceId is required", "hasIssue": False}), 400

    metadata = parse_resource_id(resource_id)
    incident_context = INCIDENT_HISTORY.get(resource_id, {})
    incident_signal = float(incident_context.get("incidentCount", "0")) if incident_context else 0.0

    features = build_feature_vector(metadata, page_hash, incident_signal)
    risk_tensor = MODEL(features)
    risk_score = risk_tensor.item()

    if risk_score < 0.42:
        return jsonify(
            {
                "hasIssue": False,
                "modelScore": round(risk_score, 3),
                "resourceId": metadata.resource_id,
            }
        )

    recommendation = KNOWLEDGE_BASE.get(metadata.resource_type or "", DEFAULT_RECOMMENDATION)
    top_factors = MODEL.explain(features)

    return jsonify(build_issue_payload(metadata, recommendation, risk_score, top_factors, incident_context))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)

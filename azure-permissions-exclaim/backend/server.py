"""ML-backed recommendation service used by Microsoft Defender for Cloud RBAC Advisor.

This module exposes a Flask application that scores incoming Azure resource IDs
with a lightweight PyTorch model.  The model was trained offline on synthetic
alert telemetry so that we can run the entire experience locally without
talking to Azure.  Recommendations returned by the ``/recommend`` endpoint are
therefore realistic enough for demos while remaining deterministic.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import torch
import torch.nn.functional as F
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

SYNTHETIC_RESOURCE_TYPES = list(RESOURCE_TYPE_PRIORS.keys()) + [
    "Microsoft.Web/sites",
    "Microsoft.DocumentDB/databaseAccounts",
    "Microsoft.OperationalInsights/workspaces",
]

SYNTHETIC_PAGE_HASHES = [
    "#view/HubsExtension/BrowseResource/resourceId/{encoded_id}",
    "#blade/Microsoft_Azure_Permissions/AccessControl/resourceId/{encoded_id}",
    "#blade/Microsoft_Azure_AD/RoleAssignmentsBlade/resourceId/{encoded_id}",
    "#view/Microsoft_Azure_Security/SecurityPermissions/resourceId/{encoded_id}",
    "#blade/Microsoft_Operations/ActivityLogBlade/resourceId/{encoded_id}",
]


def _random_hex(n: int, rng: random.Random) -> str:
    return "".join(rng.choices("0123456789abcdef", k=n))


def _build_resource_id(resource_type: str, company: str, area: str, env: str, rng: random.Random) -> str:
    subscription = f"{_random_hex(8, rng)}-{_random_hex(4, rng)}-{_random_hex(4, rng)}-{_random_hex(4, rng)}-{_random_hex(12, rng)}"
    resource_group = f"{company}-{area}-{env}"
    provider_namespace, type_path = resource_type.split("/", 1)
    suffix = area.replace("-", "")[:6]
    if resource_type == "Microsoft.Compute/virtualMachines":
        name = f"{company[:4]}-{suffix}-vm-{env[:3]}"
    elif resource_type == "Microsoft.Storage/storageAccounts":
        name = f"{company[:3]}{suffix}{env[:3]}store"
    elif resource_type == "Microsoft.KeyVault/vaults":
        name = f"{company[:4]}-{area[:4]}-kv-{env[:3]}"
    elif resource_type == "Microsoft.Sql/servers":
        name = f"{company[:5]}-{area[:4]}-sql"
    else:
        name = f"{company[:4]}-{area[:4]}-{env[:3]}"
    return (
        f"/subscriptions/{subscription}/resourceGroups/{resource_group}/providers/"
        f"{provider_namespace}/{type_path}/{name}"
    )


def simulate_alert_training_set(num_samples: int = 720) -> Tuple[torch.Tensor, torch.Tensor]:
    """Generate a reproducible synthetic dataset representing alert telemetry."""

    rng = random.Random(20240610)
    torch_generator = torch.Generator().manual_seed(20240610)

    companies = ["contoso", "fabrikam", "northwind", "adventureworks", "wingtip", "proseware"]
    areas = ["retail", "finance", "security", "payments", "commerce", "identity"]
    environments = ["prod", "prod", "stage", "dev", "dr"]  # weight toward prod for more risk

    features: List[torch.Tensor] = []
    labels: List[int] = []

    true_weights = torch.tensor([1.35, 0.9, 2.25, 1.55, 1.1, 1.05], dtype=torch.float32)
    true_bias = torch.tensor([-2.1], dtype=torch.float32)

    for _ in range(num_samples):
        resource_type = rng.choice(SYNTHETIC_RESOURCE_TYPES)
        company = rng.choice(companies)
        area = rng.choice(areas)
        env = rng.choice(environments)
        resource_id = _build_resource_id(resource_type, company, area, env, rng)

        encoded_id = quote(resource_id, safe="")
        page_template = rng.choice(SYNTHETIC_PAGE_HASHES)
        page_hash = page_template.format(encoded_id=encoded_id)

        # incident counts skew higher for privileged resource types
        base_incident_rate = RESOURCE_TYPE_PRIORS.get(resource_type, 0.3)
        incident_weights = [
            max(0.35 - base_incident_rate * 0.2, 0.05),
            0.22,
            0.18 + base_incident_rate * 0.15,
            0.12 + base_incident_rate * 0.08,
            0.08 + base_incident_rate * 0.05,
            0.05 + base_incident_rate * 0.03,
        ]
        incident_levels = [0, 1, 2, 3, 4, 5]
        incident_count = rng.choices(incident_levels, weights=incident_weights, k=1)[0]

        metadata = parse_resource_id(resource_id)
        features_tensor = build_feature_vector(metadata, page_hash, float(incident_count))

        noise = torch.randn(1, generator=torch_generator).item() * 0.35
        logit = (features_tensor * true_weights).sum() + true_bias + noise
        probability = torch.sigmoid(logit).item()
        label = 1 if probability >= 0.5 else 0

        features.append(features_tensor)
        labels.append(label)

    feature_matrix = torch.stack(features)
    targets = torch.tensor(labels, dtype=torch.float32).unsqueeze(1)
    return feature_matrix, targets


def train_lightweight_model() -> Tuple[torch.Tensor, torch.Tensor, Dict[str, float]]:
    """Fit a logistic-regression head over the synthetic dataset using PyTorch."""

    feature_matrix, targets = simulate_alert_training_set()
    model = torch.nn.Linear(feature_matrix.shape[1], 1)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.08)

    for _ in range(600):
        optimizer.zero_grad(set_to_none=True)
        logits = model(feature_matrix)
        loss = F.binary_cross_entropy_with_logits(logits, targets)
        loss.backward()
        optimizer.step()

    with torch.no_grad():
        logits = model(feature_matrix)
        probabilities = torch.sigmoid(logits).squeeze(1)
        predicted = (probabilities >= 0.5).float()
        target_labels = targets.squeeze(1)
        accuracy = (predicted == target_labels).float().mean().item()
        positive_ratio = target_labels.mean().item()

    weights = model.weight.detach().squeeze(0).clone()
    bias = model.bias.detach().clone()
    metadata = {
        "size": int(targets.shape[0]),
        "accuracy": round(accuracy, 4),
        "positiveRatio": round(positive_ratio, 4),
        "lastTrained": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    return weights, bias, metadata


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

    def __init__(self, weights: torch.Tensor, bias: torch.Tensor) -> None:
        super().__init__()
        self.register_buffer("weights", weights.clone().detach().view(-1))
        self.register_buffer("bias", bias.clone().detach().view(1))

    def forward(self, features: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        logits = features @ self.weights + self.bias
        return torch.sigmoid(logits)

    def explain(self, features: torch.Tensor) -> List[Tuple[str, float]]:
        """Return feature contributions so the UI can surface the top factors."""

        contributions = features * self.weights
        factors = list(zip(FEATURE_NAMES, contributions.tolist()))
        factors.sort(key=lambda item: abs(item[1]), reverse=True)
        return factors

MODEL_WEIGHTS, MODEL_BIAS, TRAINING_METADATA = train_lightweight_model()
MODEL = PermissionRiskModel(MODEL_WEIGHTS, MODEL_BIAS)


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
        "source": "Microsoft Defender for Cloud",
        "panelUrl": recommendation["panelUrl"],
        "azFix": az_fix,
        "resourceId": metadata.resource_id,
        "seenAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "modelScore": round(risk_score, 3),
        "topFactors": [
            {"feature": feature, "contribution": round(value, 3)}
            for feature, value in list(top_factors)[:3]
        ],
        "modelTraining": TRAINING_METADATA,
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
                "modelTraining": TRAINING_METADATA,
            }
        )

    recommendation = KNOWLEDGE_BASE.get(metadata.resource_type or "", DEFAULT_RECOMMENDATION)
    top_factors = MODEL.explain(features)

    return jsonify(build_issue_payload(metadata, recommendation, risk_score, top_factors, incident_context))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)

from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

MOCK_ALERTS = {
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/demo-rg/providers/Microsoft.Storage/storageAccounts/demostore": {
        "issueId": "alert-123",
        "title": "Scope down permissions for service principal",
        "summary": "We detected 3 recent alert(s) linked to this resource. Principal 'demo-sp' may have broader access than required.",
        "panelUrl": "https://app.example.com/panel",
        "azFix": "az role assignment delete --assignee demo-sp --role 'Storage Blob Data Owner' --scope /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/demo-rg/providers/Microsoft.Storage/storageAccounts/demostore",
    },
    "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/prod-rg/providers/Microsoft.KeyVault/vaults/prodvault": {
        "issueId": "alert-987",
        "title": "Rotate secrets admin permissions",
        "summary": "Two high-risk alert(s) indicate an over-privileged automation principal on this vault.",
        "panelUrl": "https://app.example.com/panel",
        "azFix": "az role assignment delete --assignee prod-automation --role 'Key Vault Administrator' --scope /subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/prod-rg/providers/Microsoft.KeyVault/vaults/prodvault",
    },
}


def build_issue_payload(resource_id: str, record: dict) -> dict:
    payload = {
        "hasIssue": True,
        "issueId": record.get("issueId", "mock-alert"),
        "title": record.get("title", "Review permissions for this resource"),
        "summary": record.get("summary", "Recent alerts recommend validating access scope."),
        "source": "informed by alerts",
        "panelUrl": record.get("panelUrl", "https://app.example.com/panel"),
        "azFix": record.get("azFix", "az role assignment list --scope {}".format(resource_id)),
        "resourceId": resource_id,
        "seenAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
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

    if not resource_id:
        return jsonify({"error": "resourceId is required", "hasIssue": False}), 400

    record = MOCK_ALERTS.get(resource_id)
    if not record:
        return jsonify({"hasIssue": False})

    return jsonify(build_issue_payload(resource_id, record))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
